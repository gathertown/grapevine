import logging
import math
from datetime import UTC, datetime

import asyncpg

from connectors.base import TriggerIndexingCallback
from connectors.base.document_source import DocumentSource
from connectors.notion.notion_base import NotionExtractor
from connectors.notion.notion_models import NotionApiBackfillConfig
from src.clients.sqs import cap_sqs_visibility_timeout
from src.ingest.utils import DEFAULT_INDEX_BATCH_SIZE
from src.jobs.exceptions import ExtendVisibilityException
from src.utils.tenant_config import (
    increment_backfill_attempted_ingest_jobs,
    increment_backfill_done_ingest_jobs,
    increment_backfill_total_index_jobs,
)

logger = logging.getLogger(__name__)


class NotionApiBackfillExtractor(NotionExtractor[NotionApiBackfillConfig]):
    source_name = "notion_api_backfill"

    async def process_job(
        self,
        job_id: str,
        config: NotionApiBackfillConfig,
        db_pool: asyncpg.Pool,
        trigger_indexing: TriggerIndexingCallback,
    ) -> None:
        # Check if we should start processing yet (for rate limiting)
        if config.start_timestamp:
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

            logger.info(
                f"Starting batch processing at {current_time.isoformat()} "
                f"(scheduled for {config.start_timestamp.isoformat()})"
            )
        notion_client = await self.get_notion_client(config.tenant_id)
        processed_page_ids: list[str] = []
        failed_page_ids: list[str] = []
        index_batch_size = DEFAULT_INDEX_BATCH_SIZE

        # Calculate total number of index batches upfront and track them
        total_index_batches = math.ceil(len(config.page_ids) / index_batch_size)
        if config.backfill_id and total_index_batches > 0:
            await increment_backfill_total_index_jobs(
                config.backfill_id, config.tenant_id, total_index_batches
            )

        # Process page_ids serially to avoid too spiky of load on the Notion API
        logger.info(
            f"Processing {len(config.page_ids)} pages serially for tenant {config.tenant_id}"
        )
        for i, page_id in enumerate(config.page_ids):
            try:
                # Get fresh page data from API
                page_data = notion_client.get_page(page_id)
                if not page_data:
                    logger.warning(f"Could not fetch page data for page {page_id}")
                    failed_page_ids.append(page_id)
                    continue

                logger.info(
                    f"Processing notion_page {page_id} ({i + 1}/{len(config.page_ids)} in batch)"
                )

                # Process the page into an artifact
                try:
                    artifact = await self.process_page(job_id, page_data, config.tenant_id)
                except Exception as e:
                    logger.warning(f"Failed to create artifact for page {page_id}: {e}")
                    failed_page_ids.append(page_id)
                    continue

                # Store the page immediately
                await self.store_artifact(db_pool, artifact)

                # Collect page IDs for batch indexing
                processed_page_ids.append(page_id)

                # Trigger indexing every index_batch_size pages
                if len(processed_page_ids) >= index_batch_size:
                    await trigger_indexing(
                        processed_page_ids,
                        DocumentSource.NOTION,
                        config.tenant_id,
                        config.backfill_id,
                        config.suppress_notification,
                    )
                    processed_page_ids = []  # Reset for next batch

            except Exception as e:
                logger.error(
                    f"Error processing page {page_id} ({i + 1}/{len(config.page_ids)} in batch): {e}"
                )
                failed_page_ids.append(page_id)
                # Continue processing other pages even if one fails

        # Trigger indexing for any remaining pages
        if processed_page_ids:
            await trigger_indexing(
                processed_page_ids,
                DocumentSource.NOTION,
                config.tenant_id,
                config.backfill_id,
                config.suppress_notification,
            )

        # Report results and fail if there were errors
        successful_count = len(processed_page_ids)
        failed_count = len(failed_page_ids)
        total_count = len(config.page_ids)

        logger.info(
            f"Batch processing complete for tenant {config.tenant_id}: "
            f"{successful_count}/{total_count} pages successful, {failed_count} failed"
        )

        # Track completion if backfill_id exists
        try:
            if config.backfill_id:
                await increment_backfill_done_ingest_jobs(config.backfill_id, config.tenant_id, 1)

            if failed_count > 0:
                error_msg = (
                    f"Failed to process {failed_count}/{total_count} pages for tenant {config.tenant_id}. "
                    f"Failed page IDs: {failed_page_ids[:10]}{'...' if len(failed_page_ids) > 10 else ''}"
                )
                logger.error(error_msg)
                raise Exception(error_msg)
        finally:
            # Always track that we attempted this job, regardless of success/failure
            if config.backfill_id:
                await increment_backfill_attempted_ingest_jobs(
                    config.backfill_id, config.tenant_id, 1
                )
