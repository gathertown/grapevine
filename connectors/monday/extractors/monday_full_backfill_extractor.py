"""Root extractor that orchestrates all Monday.com backfill jobs with batch splitting."""

import secrets
from datetime import UTC, datetime, timedelta

import asyncpg

from connectors.base import BaseExtractor, TriggerIndexingCallback
from connectors.monday.client import get_monday_client_for_tenant
from connectors.monday.monday_job_models import (
    MondayBackfillRootConfig,
    MondayItemBackfillConfig,
)
from connectors.monday.monday_sync_service import MondaySyncService
from src.clients.sqs import SQSClient
from src.clients.ssm import SSMClient
from src.utils.logging import get_logger
from src.utils.tenant_config import increment_backfill_total_ingest_jobs

logger = get_logger(__name__)

# Batch size (items) per child job
BATCH_SIZE = 50

# Monday.com API complexity limits: 5M points/minute for apps
# Conservative estimate: ~200 points per item fetch (with column values + updates)
# Burst capacity for initial fast processing
BURST_ITEM_COUNT = 1000
BURST_BATCH_COUNT = BURST_ITEM_COUNT // BATCH_SIZE

# After burst, process at a conservative rate
ITEMS_PER_HOUR_AFTER_BURST = 5000
BATCH_DELAY_SECONDS = BATCH_SIZE * 3600 // ITEMS_PER_HOUR_AFTER_BURST


class MondayFullBackfillExtractor(BaseExtractor[MondayBackfillRootConfig]):
    """Root extractor that collects all item IDs and splits into batch jobs.

    This extractor:
    1. Collects all board IDs from Monday.com
    2. For each board, collects all item IDs
    3. Splits items into batches of BATCH_SIZE
    4. Sends child jobs with burst + rate-limited scheduling

    All child jobs share the same backfill_id for unified tracking and notification.
    """

    source_name = "monday_backfill_root"

    def __init__(self, ssm_client: SSMClient, sqs_client: SQSClient):
        super().__init__()
        self.ssm_client = ssm_client
        self.sqs_client = sqs_client

    async def process_job(
        self,
        job_id: str,
        config: MondayBackfillRootConfig,
        db_pool: asyncpg.Pool,
        trigger_indexing: TriggerIndexingCallback,
    ) -> None:
        backfill_id = config.backfill_id or secrets.token_hex(8)
        tenant_id = config.tenant_id

        logger.info(
            "Starting Monday.com backfill root job",
            backfill_id=backfill_id,
            tenant_id=tenant_id,
        )

        try:
            monday_client = await get_monday_client_for_tenant(tenant_id, self.ssm_client)
        except Exception as e:
            logger.error(f"Failed to get Monday.com client: {e}")
            raise

        # Set sync cursor to now so incremental backfill picks up from this point
        # This ensures any changes during full backfill are captured by incremental
        sync_service = MondaySyncService(db_pool)
        backfill_start_time = datetime.now(UTC)
        await sync_service.set_incr_items_synced_until(backfill_start_time)
        logger.info(
            "Set incremental sync cursor to full backfill start time",
            sync_cursor=backfill_start_time.isoformat(),
            backfill_id=backfill_id,
        )

        # Collect all board IDs, filtering to only indexable boards (public and shareable)
        # Unknown/missing board_kind is treated as private and excluded
        all_boards = monday_client.get_boards()
        boards = [b for b in all_boards if b.is_indexable()]
        excluded_count = len(all_boards) - len(boards)
        logger.info(
            f"Found {len(all_boards)} boards ({excluded_count} excluded as private/unknown)",
            backfill_id=backfill_id,
        )

        # Collect item IDs grouped by board
        board_items: dict[int, list[int]] = {}
        total_items = 0

        for board in boards:
            try:
                item_ids = monday_client.get_board_item_ids(board.id)
                if item_ids:
                    board_items[board.id] = item_ids
                    total_items += len(item_ids)
                    logger.debug(
                        f"Board {board.name} ({board.id}): {len(item_ids)} items",
                        backfill_id=backfill_id,
                    )
            except Exception as e:
                logger.warning(
                    f"Failed to get items for board {board.id}: {e}",
                    backfill_id=backfill_id,
                )
                continue

        logger.info(
            f"Collected {total_items} items across {len(board_items)} boards",
            backfill_id=backfill_id,
        )

        if total_items == 0:
            logger.warning("No Monday.com items found to backfill", tenant_id=tenant_id)
            return

        # Create batches for each board
        all_batches: list[tuple[int, list[int]]] = []  # (board_id, item_ids)

        for board_id, item_ids in board_items.items():
            for i in range(0, len(item_ids), BATCH_SIZE):
                batch_ids = item_ids[i : i + BATCH_SIZE]
                all_batches.append((board_id, batch_ids))

        total_batches = len(all_batches)

        logger.info(
            f"Splitting {total_items} items into {total_batches} batches",
            backfill_id=backfill_id,
        )

        # Track total number of child ingest jobs for this backfill
        await increment_backfill_total_ingest_jobs(backfill_id, tenant_id, total_batches)

        # Calculate burst and rate-limiting strategy
        burst_batch_count = min(total_batches, BURST_BATCH_COUNT)
        base_start_time = datetime.now(UTC)

        # Log the schedule
        rate_limited_batches = max(0, total_batches - burst_batch_count)
        if rate_limited_batches > 0:
            total_delay_minutes = rate_limited_batches * BATCH_DELAY_SECONDS / 60
            logger.info(
                f"Burst processing {burst_batch_count} batches, "
                f"then rate-limiting {rate_limited_batches} batches with {BATCH_DELAY_SECONDS}s delays "
                f"(rate-limited duration: {total_delay_minutes:.1f} minutes)",
                backfill_id=backfill_id,
            )
        else:
            logger.info(
                f"Burst processing all {burst_batch_count} batches",
                backfill_id=backfill_id,
            )

        # Send all batch jobs
        for batch_index, (board_id, item_ids) in enumerate(all_batches):
            await self._send_item_batch(
                tenant_id=tenant_id,
                board_id=board_id,
                item_ids=item_ids,
                batch_index=batch_index,
                base_start_time=base_start_time,
                burst_batch_count=burst_batch_count,
                backfill_id=backfill_id,
                suppress_notification=config.suppress_notification,
            )

        logger.info(
            "Monday.com backfill root job completed - all child jobs sent",
            backfill_id=backfill_id,
            total_batches=total_batches,
        )

    def _calculate_start_timestamp(
        self,
        batch_index: int,
        base_start_time: datetime,
        burst_batch_count: int,
    ) -> datetime | None:
        """Calculate start timestamp for a batch based on burst/rate-limit strategy."""
        if batch_index < burst_batch_count:
            # Burst processing - no delay
            return None
        else:
            # Rate-limited processing - calculate delay
            rate_limited_index = batch_index - burst_batch_count
            delay_seconds = rate_limited_index * BATCH_DELAY_SECONDS
            return base_start_time + timedelta(seconds=delay_seconds)

    async def _send_item_batch(
        self,
        tenant_id: str,
        board_id: int,
        item_ids: list[int],
        batch_index: int,
        base_start_time: datetime,
        burst_batch_count: int,
        backfill_id: str,
        suppress_notification: bool,
    ) -> None:
        """Send an item batch job."""
        start_timestamp = self._calculate_start_timestamp(
            batch_index, base_start_time, burst_batch_count
        )

        config = MondayItemBackfillConfig(
            tenant_id=tenant_id,
            board_id=board_id,
            item_ids=item_ids,
            start_timestamp=start_timestamp,
            backfill_id=backfill_id,
            suppress_notification=suppress_notification,
        )

        await self.sqs_client.send_backfill_ingest_message(config)
        logger.debug(
            f"Sent item batch {batch_index}",
            items=len(item_ids),
            board_id=board_id,
            delayed=start_timestamp is not None,
        )


# Backwards compatible alias
MondayBackfillRootExtractor = MondayFullBackfillExtractor
