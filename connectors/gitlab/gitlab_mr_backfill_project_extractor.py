"""GitLab MR backfill project extractor.

This extractor enumerates all MRs in a project and sends batch jobs
to process them.
"""

import asyncio
import logging
from datetime import UTC, datetime

import asyncpg

from connectors.base import BaseExtractor, TriggerIndexingCallback
from connectors.gitlab.gitlab_client_factory import get_gitlab_client_for_tenant
from connectors.gitlab.gitlab_models import (
    GitLabMRBackfillConfig,
    GitLabMRBackfillProjectConfig,
    GitLabMRBatch,
)
from connectors.gitlab.gitlab_sync_service import GitLabSyncService
from src.clients.sqs import SQSClient
from src.clients.ssm import SSMClient

logger = logging.getLogger(__name__)

# Number of MRs per child job
CHILD_JOB_BATCH_SIZE = 50

# Maximum concurrent SQS operations
MAX_CONCURRENT_SQS_OPERATIONS = 100


class GitLabMRBackfillProjectExtractor(BaseExtractor[GitLabMRBackfillProjectConfig]):
    """
    Extracts GitLab MRs from a single project and sends child jobs to process them.
    This is an intermediate job between root and leaf jobs.
    """

    source_name = "gitlab_mr_backfill_project"

    def __init__(self, ssm_client: SSMClient, sqs_client: SQSClient) -> None:
        super().__init__()
        self.ssm_client = ssm_client
        self.sqs_client = sqs_client
        # Semaphore to limit concurrent SQS operations
        self._sqs_semaphore = asyncio.Semaphore(MAX_CONCURRENT_SQS_OPERATIONS)

    async def process_job(
        self,
        job_id: str,
        config: GitLabMRBackfillProjectConfig,
        db_pool: asyncpg.Pool,
        trigger_indexing: TriggerIndexingCallback,
    ) -> None:
        logger.info(
            f"Processing GitLab MR project backfill job for tenant {config.tenant_id}, "
            f"project: {config.project_path}"
        )

        # Get GitLab client for this tenant
        gitlab_client = await get_gitlab_client_for_tenant(
            config.tenant_id, self.ssm_client, per_page=100
        )

        sync_service = GitLabSyncService(db_pool)

        try:
            # Record the start time for setting the sync cursor
            # Any MRs updated after this will be picked up by incremental sync
            sync_cursor_time = datetime.now(UTC)

            # Enumerate all MRs for this project
            mr_batches = await self._enumerate_mrs_for_project(
                gitlab_client, config.project_id, config.project_path
            )

            logger.info(
                f"Project job {job_id} found {len(mr_batches)} MR batches for {config.project_path}"
            )

            # Send child jobs for MR processing
            if mr_batches:
                await self._send_child_jobs(config, mr_batches)
                logger.info(f"Sent child jobs for {len(mr_batches)} MR batches")

            # Set the MR sync cursor so incremental sync knows where to start
            # This enables hourly incremental syncs to work after full backfill
            await sync_service.set_mr_synced_until(config.project_id, sync_cursor_time)
            logger.info(f"Set MR sync cursor for project {config.project_id} to {sync_cursor_time}")

            logger.info(f"Successfully completed project job {job_id} for {config.project_path}")

        finally:
            await gitlab_client.aclose()

    async def _enumerate_mrs_for_project(
        self,
        gitlab_client,
        project_id: int,
        project_path: str,
    ) -> list[GitLabMRBatch]:
        """Enumerate all MRs for a single project and create batches."""
        mr_batches = []

        logger.info(f"Enumerating MRs for project: {project_path}")

        # Get all MRs (all states: opened, closed, merged)
        all_mrs = await gitlab_client.get_project_merge_requests(
            project_id,
            state="all",
            scope="all",
            order_by="updated_at",
            sort="desc",
        )

        # Extract just the IIDs
        all_mr_iids = [mr["iid"] for mr in all_mrs if mr.get("iid")]

        logger.info(f"Found {len(all_mr_iids)} MRs in {project_path}")

        # Split MRs into batches
        for i in range(0, len(all_mr_iids), CHILD_JOB_BATCH_SIZE):
            batch_mr_iids = all_mr_iids[i : i + CHILD_JOB_BATCH_SIZE]

            mr_batch = GitLabMRBatch(
                project_id=project_id,
                project_path=project_path,
                mr_iids=batch_mr_iids,
            )

            mr_batches.append(mr_batch)

        return mr_batches

    async def _send_child_jobs(
        self, config: GitLabMRBackfillProjectConfig, mr_batches: list[GitLabMRBatch]
    ) -> None:
        """Send child jobs to process MR batches."""
        total_batches = len(mr_batches)
        logger.info(f"Preparing to send child jobs for {total_batches} MR batches")

        # Create all child job tasks
        tasks = []
        for i, mr_batch in enumerate(mr_batches):
            child_config = GitLabMRBackfillConfig(
                tenant_id=config.tenant_id,
                mr_batches=[mr_batch],
                backfill_id=config.backfill_id,
                suppress_notification=config.suppress_notification,
            )

            # Create task to send this batch
            task = self._send_single_child_job(child_config, i)
            tasks.append(task)

        # Send all child jobs in parallel
        logger.info(f"Sending {len(tasks)} child jobs to process {total_batches} MR batches...")
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Check for failures
        jobs_sent = 0
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"Failed to send child job batch {i}: {result}")
                raise result
            jobs_sent += 1

        logger.info(f"Sent {jobs_sent} child jobs to process {total_batches} MR batches!")

    async def _send_single_child_job(
        self,
        child_config: GitLabMRBackfillConfig,
        batch_index: int,
    ) -> None:
        """Send a single child job message to SQS."""
        # Use semaphore to limit concurrent SQS operations
        async with self._sqs_semaphore:
            success = await self.sqs_client.send_backfill_ingest_message(
                backfill_config=child_config,
            )

            if not success:
                raise RuntimeError(f"Failed to send child job batch {batch_index} to SQS")

            log = logger.info if batch_index % 100 == 0 else logger.debug
            log(
                f"Sent child job batch {batch_index} with {len(child_config.mr_batches)} MR batches"
            )
