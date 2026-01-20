import logging
import secrets
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import asyncpg

from connectors.base import TriggerIndexingCallback, get_jira_project_entity_id
from connectors.jira.jira_artifacts import JiraProjectArtifact, JiraProjectArtifactContent
from connectors.jira.jira_base import JiraExtractor
from connectors.jira.jira_models import (
    JiraApiBackfillConfig,
    JiraApiBackfillRootConfig,
    JiraProjectBatch,
)
from src.utils.tenant_config import increment_backfill_total_ingest_jobs

logger = logging.getLogger(__name__)

# Batch size (issues) per child job
BATCH_SIZE = 25

# Jira API rate limits are typically more restrictive than Linear
# Be conservative with initial burst and then rate limit
BURST_ISSUE_COUNT = 100
BURST_BATCH_COUNT = BURST_ISSUE_COUNT // BATCH_SIZE

# Conservative rate limiting: 200 issues per hour after burst
ISSUES_PER_HOUR_AFTER_BURST = 200

# Delay between rate-limited batches (after burst)
BATCH_DELAY_SECONDS = BATCH_SIZE * 3600 // ISSUES_PER_HOUR_AFTER_BURST


class JiraApiBackfillRootExtractor(JiraExtractor[JiraApiBackfillRootConfig]):
    source_name = "jira_api_backfill_root"

    async def process_job(
        self,
        job_id: str,
        config: JiraApiBackfillRootConfig,
        db_pool: asyncpg.Pool,
        trigger_indexing: TriggerIndexingCallback,
    ) -> None:
        try:
            backfill_id = secrets.token_hex(8)
            logger.info(f"Processing Jira backfill_id {backfill_id} for tenant {config.tenant_id}")

            all_projects = await self.collect_all_projects(config.tenant_id, config.project_keys)

            if not all_projects:
                logger.warning(f"No Jira projects found for tenant {config.tenant_id}")
                return

            await self.store_project_artifacts(db_pool, all_projects)

            batches = [
                all_projects[i : i + BATCH_SIZE] for i in range(0, len(all_projects), BATCH_SIZE)
            ]

            logger.info(
                f"Splitting {len(all_projects)} Jira projects into {len(batches)} batches for tenant {config.tenant_id} with backfill_id {backfill_id}"
            )

            # Send child jobs with burst and rate limiting strategy
            burst_batch_count = min(len(batches), BURST_BATCH_COUNT)

            # Calculate base start time (now) for rate-limited batches
            base_start_time = datetime.now(UTC)

            # Log the delay schedule
            rate_limited_batches = max(0, len(batches) - burst_batch_count)

            if rate_limited_batches > 0:
                total_delay_minutes = rate_limited_batches * BATCH_DELAY_SECONDS / 60
                logger.info(
                    f"Burst processing {burst_batch_count} batches, "
                    f"then rate-limiting {rate_limited_batches} batches with {BATCH_DELAY_SECONDS}s delays "
                    f"(rate-limited duration: {total_delay_minutes:.1f} minutes)"
                )
            else:
                logger.info(
                    f"Burst processing all {burst_batch_count} batches ({len(all_projects)} projects)"
                )

            # Track total number of ingest jobs (child batches) for this backfill
            if batches:
                await increment_backfill_total_ingest_jobs(
                    backfill_id, config.tenant_id, len(batches)
                )

            # Send all jobs sequentially to guarantee increasing start_timestamp order
            for batch_index, batch in enumerate(batches):
                if batch:
                    await self.send_child_job(
                        config.tenant_id,
                        batch,
                        batch_index,
                        base_start_time,
                        burst_batch_count,
                        backfill_id,
                        config.suppress_notification,
                    )

        except Exception as e:
            logger.error(f"Job {job_id} failed: {e}")
            raise

    async def store_project_artifacts(
        self, db_pool: asyncpg.Pool, project_batches: list[JiraProjectBatch]
    ) -> None:
        """
        Store project artifacts for all collected projects.

        Args:
            db_pool: Database connection pool
            project_batches: List of project batches containing project metadata
        """
        if not project_batches:
            return

        artifacts = []
        for project_batch in project_batches:
            project_data = {
                "id": project_batch.project_id,
                "key": project_batch.project_key,
                "name": project_batch.project_name,
            }

            project_content = JiraProjectArtifactContent(project_data=project_data)
            project_entity_id = get_jira_project_entity_id(project_id=project_batch.project_id)

            project_artifact = JiraProjectArtifact(
                entity_id=project_entity_id,
                ingest_job_id=uuid4(),
                content=project_content,
                metadata={},
                source_updated_at=datetime.now(UTC),
            )
            artifacts.append(project_artifact)

        await self.store_artifacts_batch(db_pool, artifacts)
        logger.info(f"Stored {len(artifacts)} Jira project artifacts")

    async def collect_all_projects(
        self, tenant_id: str, project_keys: list[str]
    ) -> list[JiraProjectBatch]:
        """
        Collect all Jira projects and return them as project batches.
        No accessibility filtering - gets everything the API returns.
        """
        try:
            jira_client = await self.get_jira_client(tenant_id)

            if not project_keys:
                # Get all projects
                all_projects = jira_client.get_projects()
            else:
                # Filter to only the specified project keys
                all_projects_map = {p.key: p for p in jira_client.get_projects()}
                all_projects = []

                for project_key in project_keys:
                    if project_key in all_projects_map:
                        all_projects.append(all_projects_map[project_key])
                    else:
                        logger.warning(f"Project {project_key} not found, skipping")

            if not all_projects:
                logger.warning("No projects found. No issues will be indexed.")
                return []

            # Convert to project batches
            project_batches = []
            for project in all_projects:
                project_batch = JiraProjectBatch(
                    project_key=project.key,
                    project_id=project.id,
                    project_name=project.name,
                )
                project_batches.append(project_batch)

            logger.info(
                f"Collected {len(project_batches)} Jira projects for tenant {tenant_id}: "
                f"{[p.project_key for p in project_batches]}"
            )
            return project_batches

        except Exception as e:
            logger.error(f"Failed to collect Jira projects: {e}")
            raise

    async def send_child_job(
        self,
        tenant_id: str,
        project_batches: list[JiraProjectBatch],
        batch_index: int,
        base_start_time: datetime,
        burst_batch_count: int,
        backfill_id: str,
        suppress_notification: bool,
    ) -> None:
        """
        Send a child job to process a batch of projects with rate limiting.

        Args:
            tenant_id: The tenant ID
            project_batches: List of project batches to process
            batch_index: Index of this batch (for logging and delay calculation)
            base_start_time: Base time for calculating delays for rate-limited batches
            burst_batch_count: Number of batches to process in burst mode
            backfill_id: Unique ID for tracking this backfill
        """
        # Determine if this batch should be burst processed or rate-limited
        if batch_index < burst_batch_count:
            # Burst processing - no delay
            start_timestamp = None
            description = f"burst child job batch {batch_index}"
        else:
            # Rate-limited processing - calculate delay
            rate_limited_index = batch_index - burst_batch_count
            delay_seconds = rate_limited_index * BATCH_DELAY_SECONDS

            start_timestamp = base_start_time + timedelta(seconds=delay_seconds)
            description = f"rate-limited child job batch {batch_index}"

        # Create the child job config with backfill_id
        child_config = JiraApiBackfillConfig(
            tenant_id=tenant_id,
            project_batches=project_batches,
            start_timestamp=start_timestamp,
            backfill_id=backfill_id,
            suppress_notification=suppress_notification,
        )

        # Use the shared base method to send the message
        await self.send_backfill_child_job_message(
            config=child_config,
            _description=description,
        )
