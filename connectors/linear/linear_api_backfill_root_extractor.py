import logging
import secrets
from datetime import UTC, datetime, timedelta

import asyncpg

from connectors.base import TriggerIndexingCallback
from connectors.linear.linear_base import LinearExtractor
from connectors.linear.linear_models import LinearApiBackfillConfig, LinearApiBackfillRootConfig
from src.utils.tenant_config import increment_backfill_total_ingest_jobs

logger = logging.getLogger(__name__)

# Batch size (issues) per child job
BATCH_SIZE = 50

# After fetching all issues, burst process (0 delay) up to this many issues immediately
# In our testing, processing 1 issue costs ~0.07% of our Linear API quota, so we max out at ~1400/hour.
# We burst 50% of that quota upfront and leave headroom for webhooks etc.
BURST_ISSUE_COUNT = 700
BURST_BATCH_COUNT = BURST_ISSUE_COUNT // BATCH_SIZE

# Linear API rate limits by 2 mechanisms:
#   - 1500 requests per hour
#   - 250k query complexity points per hour
# This means it's nontrivial to track exactly where we are relative to our quota.
# We also want to be conservative + leave headroom for Linear webhook processing, so
# we set a conservative ingest rate of 500 issues/hour after the initial burst.
# See context above for quota usage per issue.
ISSUES_PER_HOUR_AFTER_BURST = 500

# Delay between rate-limited batches (after burst)
# For 50-issue batches: 50 * 3600 / 500 = 360 seconds between batches
BATCH_DELAY_SECONDS = BATCH_SIZE * 3600 // ISSUES_PER_HOUR_AFTER_BURST


class LinearApiBackfillRootExtractor(LinearExtractor[LinearApiBackfillRootConfig]):
    source_name = "linear_api_backfill_root"

    async def process_job(
        self,
        job_id: str,
        config: LinearApiBackfillRootConfig,
        db_pool: asyncpg.Pool,
        trigger_indexing: TriggerIndexingCallback,
    ) -> None:
        try:
            # Generate a unique backfill ID for this root job
            backfill_id = secrets.token_hex(8)
            logger.info(
                f"Processing Linear backfill_id {backfill_id} for tenant {config.tenant_id}"
            )

            # Get all issue IDs without processing them
            issue_ids = await self.collect_linear_issue_ids(config.tenant_id, db_pool)

            # Batch the issue IDs and send child jobs
            batches = [issue_ids[i : i + BATCH_SIZE] for i in range(0, len(issue_ids), BATCH_SIZE)]

            if not batches:
                logger.warning(f"No Linear issue IDs found for tenant {config.tenant_id}")
                return

            logger.info(
                f"Splitting {len(issue_ids)} issues into {len(batches)} batches for tenant {config.tenant_id} with backfill_id {backfill_id}"
            )

            # Send child jobs with burst and rate limiting strategy
            # Calculate dynamic burst count based on total issues
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
                    f"Burst processing all {burst_batch_count} batches ({len(issue_ids)} issues)"
                )

            # Track total number of ingest jobs (child batches) for this backfill
            if batches:
                await increment_backfill_total_ingest_jobs(
                    backfill_id, config.tenant_id, len(batches)
                )

            # Send all jobs sequentially to guarantee increasing start_timestamp order
            # This is important given we use FIFO queues
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

    async def collect_linear_issue_ids(self, tenant_id: str, db_pool: asyncpg.Pool) -> list[str]:
        """
        Collect all Linear issue IDs from the tenant's public teams without processing them.
        """
        try:
            # Get Linear client
            linear_client = await self.get_linear_client(tenant_id, db_pool)

            # Get only public teams
            public_teams = linear_client.get_public_teams()

            if not public_teams:
                logger.warning("No public teams found. No issues will be indexed.")
                return []

            logger.info(f"Collecting issue IDs from {len(public_teams)} public teams")

            issue_ids: list[str] = []

            # Fetch issue IDs from each public team
            for team in public_teams:
                team_name = team.name
                logger.info(f"Collecting issue IDs from public team: {team_name}")

                issue_ids_iter = linear_client.get_all_issue_ids(
                    team_id=team.id,  # Fetch from specific public team
                    include_archived=False,  # Don't include archived issues
                )

                team_issue_count = 0
                for issue_id in issue_ids_iter:
                    issue_ids.append(issue_id)
                    team_issue_count += 1

                logger.info(f"Collected {team_issue_count} issue IDs from team: {team_name}")

            logger.info(
                f"Collected {len(issue_ids)} total issue IDs from {len(public_teams)} public teams for tenant {tenant_id}"
            )
            return issue_ids

        except Exception as e:
            logger.error(f"Failed to collect linear_issue_ids: {e}")
            raise

    async def send_child_job(
        self,
        tenant_id: str,
        issue_ids: list[str],
        batch_index: int,
        base_start_time: datetime,
        burst_batch_count: int,
        backfill_id: str,
        suppress_notification: bool,
    ) -> None:
        """
        Send a child job to process a batch of issues with rate limiting.

        Args:
            tenant_id: The tenant ID
            issue_ids: List of issue IDs to process
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
            # Do not cap the delay to SQS max visibility timeout - if it's past the max, we'll just
            # cycle it multiple times. `linear_api_backfill` handles applying the max on each receive.
            rate_limited_index = batch_index - burst_batch_count
            delay_seconds = rate_limited_index * BATCH_DELAY_SECONDS

            start_timestamp = base_start_time + timedelta(seconds=delay_seconds)
            description = f"rate-limited child job batch {batch_index}"

        # Create the child job config with backfill_id
        child_config = LinearApiBackfillConfig(
            tenant_id=tenant_id,
            issue_ids=issue_ids,
            start_timestamp=start_timestamp,
            backfill_id=backfill_id,
            suppress_notification=suppress_notification,
        )

        # Use the shared base method to send the message
        await self.send_backfill_child_job_message(
            config=child_config,
            description=description,
        )
