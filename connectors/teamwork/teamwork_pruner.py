"""Teamwork pruner for cleaning up deleted and private tasks.

This pruner handles:
1. Deleted tasks - tasks that no longer exist in Teamwork
2. Private tasks - tasks that have become private (isPrivate=True)
3. Missing visibility - tasks where isPrivate field is missing (fail-closed)
"""

import asyncpg

from connectors.base import BasePruner
from connectors.base.base_ingest_artifact import get_teamwork_task_entity_id
from connectors.base.document_source import DocumentSource
from connectors.teamwork.teamwork_client import get_teamwork_client_for_tenant
from src.clients.ssm import SSMClient
from src.utils.logging import get_logger

logger = get_logger(__name__)

# Batch size for checking tasks
PRUNE_BATCH_SIZE = 50

# Document ID prefix for Teamwork tasks
TEAMWORK_TASK_DOC_ID_PREFIX = "teamwork_task_"


def get_teamwork_task_doc_id(task_id: int | str) -> str:
    """Get document ID for a Teamwork task."""
    return f"{TEAMWORK_TASK_DOC_ID_PREFIX}{task_id}"


class TeamworkPruner(BasePruner):
    """Prunes Teamwork tasks that have been deleted or made private.

    This pruner:
    1. Gets all indexed Teamwork task IDs from the database
    2. Checks each task's current state in Teamwork
    3. Marks deleted/private tasks for removal from the index

    SECURITY: Uses fail-closed approach - if isPrivate field is missing,
    the task is treated as private and marked for deletion.
    """

    async def delete_task(self, task_id: int, tenant_id: str, db_pool: asyncpg.Pool) -> bool:
        """Delete a Teamwork task from all data stores.

        Args:
            task_id: The Teamwork task ID
            tenant_id: The tenant ID
            db_pool: Database connection pool

        Returns:
            True if deletion was successful, False otherwise
        """
        if not task_id:
            logger.warning("No task_id provided for Teamwork task deletion")
            return False

        logger.info(f"Deleting Teamwork task: {task_id}")

        # Use the same entity_id format used when storing artifacts
        entity_id = get_teamwork_task_entity_id(task_id=task_id)

        return await self.delete_entity(
            entity_id=entity_id,
            tenant_id=tenant_id,
            db_pool=db_pool,
            document_id_resolver=lambda eid: get_teamwork_task_doc_id(
                eid.replace("teamwork_task_", "")
            ),
            entity_type="teamwork_task",
        )

    async def find_stale_documents(
        self,
        tenant_id: str,
        db_pool: asyncpg.Pool,
        ssm_client: SSMClient | None = None,
    ) -> list[str]:
        """Find Teamwork documents that should be removed.

        A task is considered stale if:
        - It no longer exists in Teamwork (deleted)
        - It has become private (isPrivate=True or null)
        - Its visibility is unknown (isPrivate field missing - fail-closed)

        Note: ssm_client is passed as a parameter rather than stored in __init__
        because BasePruner uses a singleton pattern. Callers MUST provide ssm_client
        for this method to work; without it, the method returns an empty list.

        Args:
            tenant_id: Tenant identifier
            db_pool: Database connection pool
            ssm_client: SSM client for retrieving Teamwork credentials (REQUIRED)

        Returns:
            List of document IDs to delete
        """
        if ssm_client is None:
            logger.error("SSM client required for find_stale_documents")
            return []

        try:
            client = await get_teamwork_client_for_tenant(tenant_id, ssm_client)
        except Exception as e:
            logger.error(f"Failed to get Teamwork client for pruning: {e}")
            return []

        # Get all indexed Teamwork task IDs
        async with db_pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id FROM documents
                WHERE source = $1
                """,
                DocumentSource.TEAMWORK_TASK.value,
            )

        indexed_doc_ids = [row["id"] for row in rows]
        if not indexed_doc_ids:
            logger.info("No Teamwork documents to prune")
            return []

        # Extract task IDs from document IDs
        # Document IDs are in format: teamwork_task_{task_id}
        indexed_task_ids: dict[int, str] = {}
        for doc_id in indexed_doc_ids:
            try:
                task_id_str = doc_id.replace(TEAMWORK_TASK_DOC_ID_PREFIX, "")
                task_id = int(task_id_str)
                indexed_task_ids[task_id] = doc_id
            except (ValueError, TypeError):
                continue

        if not indexed_task_ids:
            return []

        logger.info(f"Checking {len(indexed_task_ids)} indexed Teamwork tasks for staleness")

        # Check tasks in batches using the batch API
        stale_doc_ids: list[str] = []
        deleted_count = 0
        private_count = 0
        missing_visibility_count = 0

        task_ids_list = list(indexed_task_ids.keys())

        for i in range(0, len(task_ids_list), PRUNE_BATCH_SIZE):
            batch_ids = task_ids_list[i : i + PRUNE_BATCH_SIZE]

            try:
                # Use batch API to fetch tasks with minimal includes for performance
                # We only need the isPrivate field for staleness checking
                response = client.get_tasks_by_ids(batch_ids, includes=[])
                tasks = response.get("tasks", [])

                # Build lookup of fetched tasks
                fetched_tasks: dict[int, dict] = {}
                for task in tasks:
                    task_id = task.get("id")
                    if task_id is not None:
                        fetched_tasks[int(task_id)] = task

                # Check each task in batch
                for task_id in batch_ids:
                    doc_id = indexed_task_ids[task_id]

                    if task_id not in fetched_tasks:
                        # Task not found - deleted
                        stale_doc_ids.append(doc_id)
                        deleted_count += 1
                    else:
                        task = fetched_tasks[task_id]

                        # SECURITY: Fail-closed - only keep tasks with isPrivate explicitly False
                        # This handles: missing field, null value, or True value
                        if task.get("isPrivate") is not False:
                            stale_doc_ids.append(doc_id)
                            if "isPrivate" not in task:
                                missing_visibility_count += 1
                            else:
                                private_count += 1

            except Exception as e:
                logger.warning(f"Failed to check task batch for staleness: {e}")
                continue

        logger.info(
            f"Found {len(stale_doc_ids)} stale Teamwork documents",
            deleted_count=deleted_count,
            private_count=private_count,
            missing_visibility_count=missing_visibility_count,
        )
        return stale_doc_ids
