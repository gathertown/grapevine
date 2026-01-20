import logging
import secrets
from datetime import UTC, datetime, timedelta

import asyncpg

from connectors.base import TriggerIndexingCallback
from connectors.notion.notion_base import NotionExtractor
from connectors.notion.notion_models import NotionApiBackfillConfig, NotionApiBackfillRootConfig
from src.clients.notion import NotionPageSummary
from src.utils.tenant_config import increment_backfill_total_ingest_jobs

logger = logging.getLogger(__name__)

# https://developers.notion.com/reference/request-limits
NOTION_API_RATE_LIMIT_PER_SECOND = 3

# Batch size (pages) for splitting all Notion pages into child jobs
BATCH_SIZE = 10

# Delay between batches to respect Notion's rate limits
# Conservatively estimate each page as making 6 API calls (1 for page data, 1 per 100 blocks),
# then add a 50% buffer. Remember, Notion's API rate limit is *global*, so we're competing
# against e.g. Notion webhook ingest too
BATCH_DELAY_SECONDS = 1.5 * BATCH_SIZE * 6 / NOTION_API_RATE_LIMIT_PER_SECOND


class NotionApiBackfillRootExtractor(NotionExtractor[NotionApiBackfillRootConfig]):
    source_name = "notion_api_backfill_root"

    async def process_job(
        self,
        job_id: str,
        config: NotionApiBackfillRootConfig,
        db_pool: asyncpg.Pool,
        trigger_indexing: TriggerIndexingCallback,
    ) -> None:
        try:
            # Generate a unique backfill ID for this root job
            backfill_id = secrets.token_hex(8)
            logger.info(
                f"Processing Notion backfill_id {backfill_id} for tenant {config.tenant_id}"
            )

            # First collect notion users
            await self.collect_notion_users(db_pool, job_id, config.tenant_id)

            # Get all page IDs, ordered by last edit time
            page_ids = await self.collect_notion_page_ids(config.tenant_id, config.page_limit)

            # Batch the page IDs and send child jobs
            batches = [page_ids[i : i + BATCH_SIZE] for i in range(0, len(page_ids), BATCH_SIZE)]

            logger.info(
                f"Splitting {len(page_ids)} pages into {len(batches)} batches for tenant {config.tenant_id} with backfill_id {backfill_id}"
            )

            # Send child jobs with calculated start timestamps for rate limiting
            if batches:
                # Track total number of ingest jobs (child batches) for this backfill
                await increment_backfill_total_ingest_jobs(
                    backfill_id, config.tenant_id, len(batches)
                )

                # Calculate base start time (now) for first batch
                base_start_time = datetime.now(UTC)

                # Log the delay schedule
                total_delay_minutes = len(batches) * BATCH_DELAY_SECONDS / 60
                logger.info(
                    f"Scheduling {len(batches)} batches with {BATCH_DELAY_SECONDS}s delays "
                    f"(total duration: {total_delay_minutes:.1f} minutes)"
                )

                # Send all jobs sequentially to guarantee increasing start_timestamp order
                # This is important given we use FIFO queues
                for batch_index, batch in enumerate(batches):
                    if batch:
                        await self.send_child_job(
                            config.tenant_id,
                            batch,
                            batch_index,
                            base_start_time + timedelta(seconds=batch_index * BATCH_DELAY_SECONDS),
                            backfill_id,
                            config.suppress_notification,
                        )
            else:
                logger.warning(f"No Notion page IDs found for tenant {config.tenant_id}")

        except Exception as e:
            logger.error(f"Job {job_id} failed: {e}")
            raise

    async def collect_notion_page_ids(self, tenant_id: str, page_limit: int | None) -> list[str]:
        """
        Collect all Notion page IDs ordered by last edit time (most recent first).

        Args:
            tenant_id: The tenant ID
            page_limit: Optional limit on number of pages to collect

        Returns:
            List of page IDs ordered by last_edited_time (descending)
        """
        try:
            notion_client = await self.get_notion_client(tenant_id)
            pages_iter = notion_client.get_all_pages()
            pages: list[NotionPageSummary] = []

            for page_summary in pages_iter:
                if page_limit and len(pages) >= page_limit:
                    logger.info(f"Reached page limit of {page_limit} for workspace")
                    break
                pages.append(page_summary)

            # Sort by last_edited_time in descending order (most recent first)
            # Lexicographical sort should be accurate here
            pages.sort(key=lambda p: p["last_edited_time"], reverse=True)

            page_ids = [page["id"] for page in pages]

            logger.info(f"Collected {len(page_ids)} page IDs for tenant {tenant_id}")
            return page_ids

        except Exception as e:
            logger.error(f"Failed to collect notion_page_ids: {e}")
            raise

    async def send_child_job(
        self,
        tenant_id: str,
        page_ids: list[str],
        batch_index: int,
        start_timestamp: datetime,
        backfill_id: str,
        suppress_notification: bool,
    ) -> None:
        """
        Send a child job to process a batch of pages with rate limiting.

        Args:
            tenant_id: The tenant ID
            page_ids: List of page IDs to process
            batch_index: Index of this batch (for logging)
            start_timestamp: When this batch should actually start processing
            backfill_id: Unique ID for tracking this backfill
        """
        # Create the child job config with start timestamp and backfill_id
        child_config = NotionApiBackfillConfig(
            tenant_id=tenant_id,
            page_ids=page_ids,
            start_timestamp=start_timestamp,
            backfill_id=backfill_id,
            suppress_notification=suppress_notification,
        )

        # Use the shared base method to send the message
        await self.send_backfill_child_job_message(
            config=child_config,
            delay_timestamp=start_timestamp,
            description=f"child job batch {batch_index}",
        )
