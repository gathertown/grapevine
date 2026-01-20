"""Task backfill extractor for processing batches of Teamwork tasks.

Uses the Teamwork v3 API batch fetching to minimize API calls:
- Single request to fetch all tasks with `ids` parameter
- Comments, attachments, tags, users, etc. included via `include` parameter
- Reduces API calls from ~2N to 1 for N tasks
"""

from uuid import UUID

import asyncpg

from connectors.base import BaseExtractor, TriggerIndexingCallback
from connectors.base.document_source import DocumentSource
from connectors.teamwork.teamwork_artifacts import TeamworkTaskArtifact
from connectors.teamwork.teamwork_backfill_config import TeamworkTaskBackfillConfig
from connectors.teamwork.teamwork_client import get_teamwork_client_for_tenant
from src.clients.ssm import SSMClient
from src.ingest.repositories.artifact_repository import ArtifactRepository
from src.jobs.exceptions import ExtendVisibilityException
from src.utils.logging import get_logger
from src.utils.rate_limiter import RateLimitedError
from src.utils.tenant_config import increment_backfill_done_ingest_jobs

logger = get_logger(__name__)


class TeamworkTaskBackfillExtractor(BaseExtractor[TeamworkTaskBackfillConfig]):
    """Extractor for processing batches of Teamwork task IDs.

    Uses batch fetching via v3 API to fetch all tasks and related data in a single request.
    This significantly reduces API calls and rate limit issues.
    """

    source_name = "teamwork_task_backfill"

    def __init__(self, ssm_client: SSMClient):
        super().__init__()
        self.ssm_client = ssm_client

    async def process_job(
        self,
        job_id: str,
        config: TeamworkTaskBackfillConfig,
        db_pool: asyncpg.Pool,
        trigger_indexing: TriggerIndexingCallback,
    ) -> None:
        tenant_id = config.tenant_id
        task_ids = list(config.task_ids)  # Convert tuple to list for API
        backfill_id = config.backfill_id

        logger.info(
            "Starting Teamwork task batch backfill (v3 batch API)",
            tenant_id=tenant_id,
            task_count=len(task_ids),
            backfill_id=backfill_id,
        )

        job_uuid = UUID(job_id)
        repo = ArtifactRepository(db_pool)

        try:
            client = await get_teamwork_client_for_tenant(tenant_id, self.ssm_client)
        except Exception as e:
            logger.error(f"Failed to get Teamwork client: {e}", tenant_id=tenant_id)
            raise

        try:
            # Batch fetch all tasks with related data in a single API call
            # This fetches: tasks + projects + tasklists + tags + comments +
            #               attachments + users + parentTasks
            response = client.get_tasks_by_ids(task_ids)
            tasks = response["tasks"]
            included = response["included"]

            # Enrich tasks with their related data
            all_enriched_tasks = client.enrich_tasks_with_included(tasks, included)

            # Calculate fetched IDs BEFORE filtering (for accurate missing task detection)
            fetched_ids = {
                int(task_id) for t in all_enriched_tasks if (task_id := t.get("id")) is not None
            }

            # SECURITY: Fail-closed - filter out tasks where isPrivate is missing or True
            # This ensures we don't accidentally index private content if API changes
            enriched_tasks = []
            private_count = 0
            missing_visibility_count = 0

            for t in all_enriched_tasks:
                # SECURITY: Fail-closed - only index tasks with isPrivate explicitly False
                # This handles: missing field, null value, or True value
                if t.get("isPrivate") is not False:
                    if "isPrivate" not in t:
                        missing_visibility_count += 1
                    else:
                        private_count += 1
                    continue
                enriched_tasks.append(t)

            if private_count > 0 or missing_visibility_count > 0:
                logger.info(
                    "Filtered out non-public tasks",
                    tenant_id=tenant_id,
                    private_count=private_count,
                    missing_visibility_count=missing_visibility_count,
                    public_count=len(enriched_tasks),
                )

            logger.info(
                "Batch fetched tasks from Teamwork API",
                tenant_id=tenant_id,
                requested_count=len(task_ids),
                fetched_count=len(all_enriched_tasks),
                public_count=len(enriched_tasks),
                private_skipped=private_count,
                missing_visibility_skipped=missing_visibility_count,
                included_types=list(included.keys()),
            )

        except (RateLimitedError, ExtendVisibilityException):
            logger.warning(
                "Rate limited during batch fetch, will retry job",
                tenant_id=tenant_id,
                task_count=len(task_ids),
            )
            raise
        except Exception as e:
            logger.error(
                f"Failed to batch fetch tasks: {e}",
                tenant_id=tenant_id,
                task_count=len(task_ids),
            )
            raise

        # Create artifacts from enriched tasks
        artifacts: list[TeamworkTaskArtifact] = []
        entity_ids: list[str] = []

        for task in enriched_tasks:
            try:
                # Extract comments from enriched data (already fetched via include)
                comments = task.get("_comments", [])

                # Create artifact from enriched API response
                artifact = TeamworkTaskArtifact.from_api_response(
                    task_data=task,
                    ingest_job_id=job_uuid,
                    comments=comments,
                )
                artifacts.append(artifact)
                entity_ids.append(artifact.entity_id)

            except Exception as e:
                task_id = task.get("id", "unknown")
                logger.warning(
                    f"Failed to create artifact for task {task_id}: {e}",
                    tenant_id=tenant_id,
                    task_id=task_id,
                )
                continue

        # Log any tasks that weren't found (using fetched_ids calculated before filtering)
        missing_ids = set(task_ids) - fetched_ids
        if missing_ids:
            logger.warning(
                "Some tasks were not found in batch fetch",
                tenant_id=tenant_id,
                missing_count=len(missing_ids),
                missing_ids=list(missing_ids)[:10],  # Log first 10
            )

        # Save artifacts to database
        if artifacts:
            await repo.upsert_artifacts_batch(artifacts)
            logger.info(
                f"Saved {len(artifacts)} Teamwork task artifacts",
                tenant_id=tenant_id,
            )

            # Trigger indexing for the task documents
            await trigger_indexing(
                entity_ids,
                DocumentSource.TEAMWORK_TASK,
                tenant_id,
                backfill_id,
                config.suppress_notification,
            )

        # Track backfill progress (even if no artifacts, to mark job as done)
        if backfill_id:
            await increment_backfill_done_ingest_jobs(backfill_id, tenant_id)

        logger.info(
            "Teamwork task batch backfill complete",
            tenant_id=tenant_id,
            tasks_processed=len(artifacts),
            tasks_requested=len(task_ids),
            backfill_id=backfill_id,
        )
