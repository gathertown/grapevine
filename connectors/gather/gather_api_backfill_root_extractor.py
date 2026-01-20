"""
Root extractor for Gather meetings API backfill.
Fetches all meetings from a space and creates child jobs for processing.
"""

import logging
import uuid

import asyncpg

from connectors.base import TriggerIndexingCallback
from connectors.gather.gather_base import GatherExtractor
from connectors.gather.gather_models import GatherApiBackfillConfig, GatherApiBackfillRootConfig
from src.utils.tenant_config import (
    increment_backfill_attempted_ingest_jobs,
    increment_backfill_total_ingest_jobs,
)

logger = logging.getLogger(__name__)

# Batch size for processing meetings
MEETINGS_PER_BATCH = 50


class GatherApiBackfillRootExtractor(GatherExtractor[GatherApiBackfillRootConfig]):
    """Root extractor that fetches all meetings and creates child processing jobs."""

    source_name = "gather_api_backfill_root"

    async def process_job(
        self,
        job_id: str,
        config: GatherApiBackfillRootConfig,
        db_pool: asyncpg.Pool,
        trigger_indexing: TriggerIndexingCallback,
    ) -> None:
        """
        Fetch all meetings from the space and create child jobs for processing.

        Args:
            job_id: The ingest job ID
            config: Root backfill configuration
            db_pool: Database connection pool
            trigger_indexing: Callback to trigger indexing
        """
        tenant_id = config.tenant_id
        space_id = config.space_id

        try:
            # Generate a backfill ID for tracking
            backfill_id = config.backfill_id or str(uuid.uuid4())

            logger.info(
                f"Starting Gather meetings backfill for tenant {tenant_id}, space {space_id}, backfill_id: {backfill_id}"
            )

            # Get Gather client
            gather_client = await self.get_gather_client(tenant_id)

            # Fetch all meetings from the space
            logger.info(f"Fetching all meetings from space {space_id}")

            # TODO - Optimize space by running generator in downstream for loop
            all_meetings = list(gather_client.get_all_meetings(space_id=space_id))

            logger.info(f"Found {len(all_meetings)} total meetings in space {space_id}")

            if not all_meetings:
                logger.info("No meetings found, backfill complete")
                return

            # Batch the meetings
            meeting_batches = []

            for i in range(0, len(all_meetings), MEETINGS_PER_BATCH):
                batch = all_meetings[i : i + MEETINGS_PER_BATCH]
                meeting_batches.append(batch)

            logger.info(
                f"Created {len(meeting_batches)} batches of up to {MEETINGS_PER_BATCH} meetings each"
            )

            # Track total ingest jobs
            await increment_backfill_total_ingest_jobs(backfill_id, tenant_id, len(meeting_batches))
            await increment_backfill_attempted_ingest_jobs(backfill_id, tenant_id, 1)

            # Create child jobs for each batch
            for batch_idx, meeting_batch in enumerate(meeting_batches):
                child_config = GatherApiBackfillConfig(
                    tenant_id=tenant_id,
                    space_id=space_id,
                    meetings_data=meeting_batch,
                    backfill_id=backfill_id,
                    start_timestamp=None,  # Process immediately
                    suppress_notification=config.suppress_notification,
                )

                await self.send_backfill_child_job_message(
                    config=child_config,
                    description=f"child job batch {batch_idx}",
                )

            logger.info(
                f"Successfully created {len(meeting_batches)} child jobs for backfill {backfill_id}"
            )

        except Exception as e:
            logger.error(f"Failed to process Gather meetings backfill root job: {e}")
            raise
