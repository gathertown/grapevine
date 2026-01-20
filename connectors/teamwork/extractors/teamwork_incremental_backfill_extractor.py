"""Incremental backfill extractor for Teamwork.

Uses the updatedAfter filter to fetch only tasks that have changed since the last sync.
"""

from datetime import UTC, datetime, timedelta
from uuid import UUID

import asyncpg

from connectors.base import BaseExtractor, TriggerIndexingCallback
from connectors.base.document_source import DocumentSource
from connectors.teamwork.teamwork_artifacts import TeamworkTaskArtifact
from connectors.teamwork.teamwork_backfill_config import TeamworkIncrementalBackfillConfig
from connectors.teamwork.teamwork_client import get_teamwork_client_for_tenant
from connectors.teamwork.teamwork_pruner import TeamworkPruner
from connectors.teamwork.teamwork_sync_service import TeamworkSyncService
from src.clients.ssm import SSMClient
from src.ingest.repositories.artifact_repository import ArtifactRepository
from src.utils.logging import get_logger

logger = get_logger(__name__)

# Default lookback window for first-time incremental sync
DEFAULT_LOOKBACK_HOURS = 24


class TeamworkIncrementalBackfillExtractor(BaseExtractor[TeamworkIncrementalBackfillConfig]):
    """Extractor for incremental Teamwork sync.

    Fetches tasks that have been updated since the last sync time.
    Uses the Teamwork updatedAfter filter for efficient incremental sync.
    """

    source_name = "teamwork_incremental"

    def __init__(self, ssm_client: SSMClient):
        super().__init__()
        self.ssm_client = ssm_client

    async def process_job(
        self,
        job_id: str,
        config: TeamworkIncrementalBackfillConfig,
        db_pool: asyncpg.Pool,
        trigger_indexing: TriggerIndexingCallback,
    ) -> None:
        tenant_id = config.tenant_id
        lookback_hours = config.lookback_hours or DEFAULT_LOOKBACK_HOURS

        logger.info(
            "Starting Teamwork incremental backfill",
            tenant_id=tenant_id,
            lookback_hours=lookback_hours,
        )

        job_uuid = UUID(job_id)
        repo = ArtifactRepository(db_pool)
        sync_service = TeamworkSyncService(db_pool, tenant_id)

        # Get the last sync time
        last_sync = await sync_service.get_tasks_synced_until()

        # If no previous sync, use default lookback
        if not last_sync:
            last_sync = datetime.now(UTC) - timedelta(hours=lookback_hours)
            logger.info(
                "No previous sync found, using default lookback",
                tenant_id=tenant_id,
                lookback_hours=lookback_hours,
                since=last_sync.isoformat(),
            )
        else:
            # Subtract a small buffer to handle edge cases
            last_sync = last_sync - timedelta(seconds=1)
            logger.info(
                "Using last sync time with buffer",
                tenant_id=tenant_id,
                since=last_sync.isoformat(),
            )

        # Track sync start time for cursor update
        sync_start_time = datetime.now(UTC)

        artifacts: list[TeamworkTaskArtifact] = []
        entity_ids: list[str] = []
        private_skipped = 0
        missing_visibility_skipped = 0
        # Track task IDs that need to be de-indexed (privacy flips)
        tasks_to_deindex: list[int] = []

        try:
            client = await get_teamwork_client_for_tenant(tenant_id, self.ssm_client)

            # Fetch tasks updated since last sync
            for tasks_page in client.iterate_tasks(
                updated_after=last_sync,
                include_completed=True,
                include_deleted=False,
            ):
                for task in tasks_page:
                    task_id = task.get("id")
                    if not task_id:
                        continue

                    # SECURITY: Fail-closed - only index tasks with isPrivate explicitly False
                    # This handles: missing field, null value, or True value
                    if task.get("isPrivate") is not False:
                        if "isPrivate" not in task:
                            missing_visibility_skipped += 1
                        else:
                            private_skipped += 1
                        # Mark for de-indexing in case it was previously indexed as public
                        tasks_to_deindex.append(int(task_id))
                        continue

                    # Fetch comments for the task
                    comments = []
                    try:
                        comments = client.get_all_task_comments(int(task_id))
                    except Exception as e:
                        logger.warning(
                            f"Failed to fetch comments for task {task_id}: {e}",
                            tenant_id=tenant_id,
                        )

                    # Create artifact
                    artifact = TeamworkTaskArtifact.from_api_response(
                        task_data=task,
                        ingest_job_id=job_uuid,
                        comments=comments,
                    )
                    artifacts.append(artifact)
                    entity_ids.append(artifact.entity_id)

                # Log progress periodically
                if len(artifacts) % 100 == 0 and len(artifacts) > 0:
                    logger.info(
                        f"Processed {len(artifacts)} updated tasks so far",
                        tenant_id=tenant_id,
                        private_skipped=private_skipped,
                        missing_visibility_skipped=missing_visibility_skipped,
                    )

        except Exception as e:
            logger.error(f"Failed during incremental sync: {e}", tenant_id=tenant_id)
            raise

        # Save artifacts to database
        if artifacts:
            await repo.upsert_artifacts_batch(artifacts)
            logger.info(
                f"Saved {len(artifacts)} updated Teamwork task artifacts",
                tenant_id=tenant_id,
            )

            # Trigger indexing for the task documents
            await trigger_indexing(
                entity_ids,
                DocumentSource.TEAMWORK_TASK,
                tenant_id,
                None,  # No backfill_id for incremental sync
                True,  # Suppress notifications for incremental
            )

        # De-index tasks that have become private or have missing visibility
        # IMPORTANT: Do this BEFORE updating the cursor so that if de-indexing fails,
        # these tasks will be re-fetched and re-evaluated in the next incremental sync
        tasks_deindexed = 0
        deindex_failed = 0
        deindex_skipped = False

        if tasks_to_deindex:
            # GUARDRAIL: Abort de-indexing if missing-visibility rate is too high
            # This protects against mass de-indexing if the API is returning bad data
            total_tasks_processed = len(artifacts) + private_skipped + missing_visibility_skipped
            if total_tasks_processed > 0:
                missing_rate = missing_visibility_skipped / total_tasks_processed
                if missing_rate > 0.2:  # More than 20% missing visibility
                    logger.error(
                        "Aborting de-indexing: missing visibility rate too high, possible API issue",
                        tenant_id=tenant_id,
                        missing_visibility_skipped=missing_visibility_skipped,
                        total_tasks=total_tasks_processed,
                        missing_rate=f"{missing_rate:.1%}",
                    )
                    deindex_skipped = True

            if not deindex_skipped:
                logger.info(
                    "De-indexing tasks that became private or have missing visibility",
                    tenant_id=tenant_id,
                    count=len(tasks_to_deindex),
                )
                pruner = TeamworkPruner()
                for task_id in tasks_to_deindex:
                    try:
                        success = await pruner.delete_task(task_id, tenant_id, db_pool)
                        if success:
                            tasks_deindexed += 1
                        else:
                            deindex_failed += 1
                    except Exception as e:
                        deindex_failed += 1
                        logger.warning(
                            f"Failed to de-index task {task_id}: {e}",
                            tenant_id=tenant_id,
                        )

        # Only advance cursor if de-indexing succeeded or was skipped due to guardrail
        # If de-indexing failed, don't advance so tasks are re-fetched next sync
        if deindex_failed == 0:
            await sync_service.set_tasks_synced_until(sync_start_time)
        else:
            logger.warning(
                "Not advancing sync cursor due to de-indexing failures",
                tenant_id=tenant_id,
                deindex_failed=deindex_failed,
                tasks_deindexed=tasks_deindexed,
            )

        # Log private task count if any were skipped
        if private_skipped > 0 or missing_visibility_skipped > 0:
            logger.info(
                "Skipped non-public tasks during incremental sync",
                tenant_id=tenant_id,
                private_skipped=private_skipped,
                missing_visibility_skipped=missing_visibility_skipped,
                tasks_deindexed=tasks_deindexed,
            )

        logger.info(
            "Teamwork incremental backfill complete",
            tenant_id=tenant_id,
            tasks_updated=len(artifacts),
            private_skipped=private_skipped,
            missing_visibility_skipped=missing_visibility_skipped,
            tasks_deindexed=tasks_deindexed,
            deindex_failed=deindex_failed,
            cursor_advanced=deindex_failed == 0,
            sync_cursor=sync_start_time.isoformat() if deindex_failed == 0 else "not advanced",
        )
