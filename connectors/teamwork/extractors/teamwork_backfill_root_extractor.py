"""Root extractor for Teamwork full backfill.

Orchestrates the full backfill by:
1. Setting incremental sync cursors to "now"
2. Collecting all task IDs
3. Enqueuing task-specific backfill jobs for batch processing
"""

import secrets
from datetime import UTC, datetime

import asyncpg

from connectors.base import BaseExtractor, TriggerIndexingCallback
from connectors.teamwork.teamwork_backfill_config import (
    TeamworkBackfillRootConfig,
    TeamworkTaskBackfillConfig,
)
from connectors.teamwork.teamwork_client import get_teamwork_client_for_tenant
from connectors.teamwork.teamwork_sync_service import TeamworkSyncService
from src.clients.sqs import SQSClient
from src.clients.ssm import SSMClient
from src.utils.logging import get_logger
from src.utils.tenant_config import increment_backfill_total_ingest_jobs

logger = get_logger(__name__)

# Batch size for task processing jobs
BATCH_SIZE = 50  # Moderate batch size for rate limit protection


class TeamworkBackfillRootExtractor(BaseExtractor[TeamworkBackfillRootConfig]):
    """Root extractor that discovers all tasks and splits into batch jobs.

    This extractor:
    1. Sets incremental sync cursors to "now" (so incremental picks up changes during backfill)
    2. Discovers all tasks from the workspace
    3. Splits them into batches and enqueues child jobs for processing
    """

    source_name = "teamwork_backfill_root"

    def __init__(self, sqs_client: SQSClient, ssm_client: SSMClient):
        super().__init__()
        self.sqs_client = sqs_client
        self.ssm_client = ssm_client

    async def process_job(
        self,
        job_id: str,
        config: TeamworkBackfillRootConfig,
        db_pool: asyncpg.Pool,
        trigger_indexing: TriggerIndexingCallback,
    ) -> None:
        backfill_id = config.backfill_id or secrets.token_hex(8)
        tenant_id = config.tenant_id

        logger.info(
            "Starting Teamwork backfill root job",
            backfill_id=backfill_id,
            tenant_id=tenant_id,
        )

        # Initialize services
        sync_service = TeamworkSyncService(db_pool, tenant_id)

        # Step 1: Set incremental sync cursors to "now"
        sync_start_time = datetime.now(UTC)
        await sync_service.set_tasks_synced_until(sync_start_time)

        logger.info(
            "Set incremental sync cursors",
            tenant_id=tenant_id,
            sync_start_time=sync_start_time.isoformat(),
        )

        # Step 2: Collect all task IDs (excluding private tasks)
        all_task_ids: list[int] = []
        private_skipped = 0
        missing_visibility_skipped = 0

        try:
            client = await get_teamwork_client_for_tenant(tenant_id, self.ssm_client)

            for tasks_page in client.iterate_tasks(
                page_size=100,
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
                        continue

                    all_task_ids.append(int(task_id))

                if len(all_task_ids) % 500 == 0:
                    logger.info(
                        f"Collected {len(all_task_ids)} task IDs so far",
                        tenant_id=tenant_id,
                        private_skipped=private_skipped,
                        missing_visibility_skipped=missing_visibility_skipped,
                    )

        except Exception as e:
            logger.error(f"Failed to get Teamwork client or tasks: {e}")
            raise

        # Log private task filtering summary
        if private_skipped > 0 or missing_visibility_skipped > 0:
            logger.info(
                "Skipped non-public tasks during discovery",
                tenant_id=tenant_id,
                private_skipped=private_skipped,
                missing_visibility_skipped=missing_visibility_skipped,
            )

        logger.info(
            "Collected all Teamwork task IDs",
            backfill_id=backfill_id,
            total_tasks=len(all_task_ids),
            private_skipped=private_skipped,
            missing_visibility_skipped=missing_visibility_skipped,
        )

        if not all_task_ids:
            logger.warning(
                "No tasks found for Teamwork backfill",
                tenant_id=tenant_id,
            )
            # Mark backfill as complete even if empty
            await sync_service.set_full_backfill_complete(True)
            return

        # Step 3: Create batches of tasks
        batches = [
            all_task_ids[i : i + BATCH_SIZE] for i in range(0, len(all_task_ids), BATCH_SIZE)
        ]

        # Track total jobs for backfill progress tracking
        total_jobs = len(batches)
        await increment_backfill_total_ingest_jobs(backfill_id, tenant_id, total_jobs)

        # Step 4: Schedule batch jobs
        for batch in batches:
            task_config = TeamworkTaskBackfillConfig(
                tenant_id=tenant_id,
                task_ids=tuple(batch),
                backfill_id=backfill_id,
            )

            await self.sqs_client.send_backfill_ingest_message(task_config)

        logger.info(
            "Teamwork root backfill complete - batch jobs enqueued",
            tenant_id=tenant_id,
            backfill_id=backfill_id,
            total_batches=total_jobs,
            total_tasks=len(all_task_ids),
        )
