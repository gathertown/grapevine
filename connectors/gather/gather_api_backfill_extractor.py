"""
Child extractor for Gather meetings API backfill.
Processes batches of meeting data and stores artifacts.
"""

import logging
import math

import asyncpg

from connectors.base import TriggerIndexingCallback
from connectors.base.document_source import DocumentSource
from connectors.gather.gather_base import GatherExtractor
from connectors.gather.gather_models import GatherApiBackfillConfig
from src.clients.sqs import cap_sqs_visibility_timeout
from src.ingest.utils import DEFAULT_INDEX_BATCH_SIZE
from src.jobs.exceptions import ExtendVisibilityException
from src.utils.tenant_config import (
    increment_backfill_attempted_ingest_jobs,
    increment_backfill_done_ingest_jobs,
    increment_backfill_total_index_jobs,
)

logger = logging.getLogger(__name__)


class GatherApiBackfillExtractor(GatherExtractor[GatherApiBackfillConfig]):
    """Child extractor that processes batches of meeting data."""

    source_name = "gather_api_backfill"

    async def process_job(
        self,
        job_id: str,
        config: GatherApiBackfillConfig,
        db_pool: asyncpg.Pool,
        trigger_indexing: TriggerIndexingCallback,
    ) -> None:
        """
        Process a batch of meeting data.

        Args:
            job_id: The ingest job ID
            config: Backfill configuration with meeting data
            db_pool: Database connection pool
            trigger_indexing: Callback to trigger indexing
        """
        # Check if we should start processing yet (for rate limiting)
        if config.start_timestamp:
            from datetime import UTC, datetime

            current_time = datetime.now(UTC)
            if current_time < config.start_timestamp:
                # Not time to start yet - extend visibility timeout until start_timestamp
                # Add a 3s buffer to ensure we don't process too early
                delay_seconds = cap_sqs_visibility_timeout(
                    3 + int((config.start_timestamp - current_time).total_seconds())
                )

                logger.info(
                    f"Delaying batch processing until {config.start_timestamp.isoformat()} "
                    f"(current time: {current_time.isoformat()}, delay: {delay_seconds}s)"
                )

                raise ExtendVisibilityException(
                    visibility_timeout_seconds=delay_seconds,
                    message=f"Delaying processing until {config.start_timestamp.isoformat()}",
                )

        try:
            # Process the batch of meetings
            await self.process_meetings_batch(
                db_pool,
                job_id,
                trigger_indexing,
                config.tenant_id,
                config.space_id,
                config.meetings_data,
                config.backfill_id,
                config.suppress_notification,
            )
        except Exception as e:
            logger.error(f"Job {job_id} failed: {e}")
            raise

    async def process_meetings_batch(
        self,
        db_pool: asyncpg.Pool,
        job_id: str,
        trigger_indexing: TriggerIndexingCallback,
        tenant_id: str,
        space_id: str,
        meetings_data: list[dict],
        backfill_id: str | None = None,
        suppress_notification: bool = False,
    ) -> None:
        """Process a batch of meetings."""
        try:
            artifacts_to_store = []
            meeting_ids_for_indexing: list[str] = []

            logger.info(f"Processing batch of {len(meetings_data)} Gather meetings")

            # Process each meeting
            for meeting_data in meetings_data:
                meeting_id = meeting_data.get("id")
                if not meeting_id:
                    logger.warning(
                        f"Meeting missing ID, skipping: {meeting_data.get('type', 'unknown')}"
                    )
                    continue

                logger.debug(f"Processing meeting: {meeting_id}")

                try:
                    # Process the meeting using the base class method
                    # Returns a list of artifacts: meeting, transcripts, and chat messages
                    meeting_artifacts = await self._process_meeting(
                        job_id, meeting_data, space_id, tenant_id
                    )
                    # Collect artifacts for batch storage and meeting IDs for indexing at the end
                    artifacts_to_store.extend(meeting_artifacts)
                    meeting_ids_for_indexing.append(meeting_id)

                    # Log progress
                    if len(meeting_ids_for_indexing) % 10 == 0:
                        logger.info(
                            f"Processed {len(meeting_ids_for_indexing)} of {len(meetings_data)} meetings"
                        )

                except Exception as e:
                    logger.error(f"Error processing meeting {meeting_id}: {e}")
                    raise

            # Store all artifacts in batch first
            if artifacts_to_store:
                logger.info(f"Storing {len(artifacts_to_store)} artifacts in batch")
                await self.store_artifacts_batch(db_pool, artifacts_to_store)

            # Only trigger indexing after all artifacts are stored, since indexing needs to read the artifacts
            if meeting_ids_for_indexing:
                logger.info(f"Triggering indexing for {len(meeting_ids_for_indexing)} meetings")
                # Calculate total number of index batches and track them upfront
                total_index_batches = math.ceil(
                    len(meeting_ids_for_indexing) / DEFAULT_INDEX_BATCH_SIZE
                )
                if backfill_id and total_index_batches > 0:
                    await increment_backfill_total_index_jobs(
                        backfill_id, tenant_id, total_index_batches
                    )

                for i in range(0, len(meeting_ids_for_indexing), DEFAULT_INDEX_BATCH_SIZE):
                    batch = meeting_ids_for_indexing[i : i + DEFAULT_INDEX_BATCH_SIZE]
                    await trigger_indexing(
                        batch, DocumentSource.GATHER, tenant_id, backfill_id, suppress_notification
                    )

            logger.info(
                f"Completed processing batch: {len(artifacts_to_store)} meetings processed successfully"
            )

            # Track completion and send notification if backfill is done
            if backfill_id:
                await increment_backfill_done_ingest_jobs(backfill_id, tenant_id, 1)

        except Exception as e:
            logger.error(f"Failed to process Gather meetings batch: {e}")
            raise
        finally:
            # Always track that we attempted this job, regardless of success/failure
            if backfill_id:
                await increment_backfill_attempted_ingest_jobs(backfill_id, tenant_id, 1)
