"""Monday.com incremental backfill extractor using Activity Logs API.

Syncs items that have been modified since the last successful sync.
Uses the Activity Logs API which supports native date filtering,
making it more efficient than polling all items.
"""

import secrets
import time
from datetime import UTC, datetime, timedelta
from typing import Literal
from uuid import UUID

import asyncpg

from connectors.base import BaseExtractor, TriggerIndexingCallback
from connectors.base.document_source import DocumentSource
from connectors.base.models import BackfillIngestConfig
from connectors.monday.client.monday_client_factory import get_monday_client_for_tenant
from connectors.monday.extractors.artifacts.monday_item_artifact import MondayItemArtifact
from connectors.monday.monday_sync_service import MondaySyncService
from src.clients.ssm import SSMClient
from src.ingest.repositories.artifact_repository import ArtifactRepository
from src.utils.logging import LogContext, get_logger

logger = get_logger(__name__)

# Default lookback window for first run or if no previous sync
DEFAULT_LOOKBACK_HOURS = 2

# Batch size for processing items
ITEM_BATCH_SIZE = 50


class MondayIncrementalBackfillConfig(BackfillIngestConfig, frozen=True):
    """Configuration for Monday.com incremental backfill."""

    source: Literal["monday_incremental_backfill"] = "monday_incremental_backfill"


class MondayIncrementalBackfillExtractor(BaseExtractor[MondayIncrementalBackfillConfig]):
    """Extractor for incremental backfill of Monday.com items using Activity Logs.

    Uses the Activity Logs API to efficiently find items that have changed
    since the last sync. This is more efficient than polling all items
    because the API supports native date filtering.

    Flow:
    1. Get last sync time from database (or use lookback window)
    2. For each board, query activity logs since last sync
    3. Extract unique item IDs from activity logs
    4. Fetch those items and update artifacts
    5. Update sync cursor
    """

    source_name = "monday_incremental_backfill"

    def __init__(self, ssm_client: SSMClient) -> None:
        super().__init__()
        self.ssm_client = ssm_client

    async def process_job(
        self,
        job_id: str,
        config: MondayIncrementalBackfillConfig,
        db_pool: asyncpg.Pool,
        trigger_indexing: TriggerIndexingCallback,
    ) -> None:
        start_time = time.perf_counter()
        backfill_id = config.backfill_id or secrets.token_hex(8)

        logger.info("Started Monday.com incremental backfill job", backfill_id=backfill_id)

        monday_client = await get_monday_client_for_tenant(config.tenant_id, self.ssm_client)
        sync_service = MondaySyncService(db_pool)
        artifact_repo = ArtifactRepository(db_pool)

        with LogContext(backfill_id=backfill_id):
            await self._run_incremental_backfill(
                monday_client=monday_client,
                sync_service=sync_service,
                artifact_repo=artifact_repo,
                config=config,
                job_id=UUID(job_id),
                trigger_indexing=trigger_indexing,
            )

            duration = time.perf_counter() - start_time
            logger.info("Monday.com incremental backfill complete", duration=duration)

    async def _run_incremental_backfill(
        self,
        monday_client,
        sync_service: MondaySyncService,
        artifact_repo: ArtifactRepository,
        config: MondayIncrementalBackfillConfig,
        job_id: UUID,
        trigger_indexing: TriggerIndexingCallback,
    ) -> None:
        """Run the incremental backfill process using activity logs."""
        # Get the last sync time, or default to lookback window for first run
        synced_until = await sync_service.get_incr_items_synced_until()

        # Always use synced_until if available to avoid missing data after downtime.
        # Only use lookback window for first run (when no sync cursor exists).
        from_time = synced_until or datetime.now(UTC) - timedelta(hours=DEFAULT_LOOKBACK_HOURS)

        from_time_str = from_time.isoformat()
        to_time = datetime.now(UTC)
        to_time_str = to_time.isoformat()

        logger.info(
            f"Fetching Monday.com activity logs from {from_time_str} to {to_time_str}",
            synced_until=synced_until.isoformat() if synced_until else None,
            lookback_hours=DEFAULT_LOOKBACK_HOURS,
        )

        # Get all boards, filtering to only indexable boards (public and shareable)
        # Unknown/missing board_kind is treated as private and excluded
        all_boards = monday_client.get_boards()
        boards = [b for b in all_boards if b.is_indexable()]
        excluded_count = len(all_boards) - len(boards)
        logger.info(
            f"Checking activity logs for {len(boards)} boards ({excluded_count} excluded as private/unknown)"
        )

        # Collect all changed item IDs across all boards
        all_changed_item_ids: set[int] = set()

        for board in boards:
            try:
                activity_logs = monday_client.get_all_activity_logs_since(
                    board_id=board.id,
                    from_time=from_time_str,
                    to_time=to_time_str,
                )

                if activity_logs:
                    item_ids = monday_client.extract_item_ids_from_activity_logs(activity_logs)
                    all_changed_item_ids.update(item_ids)
                    logger.debug(
                        f"Board {board.name}: {len(activity_logs)} logs, {len(item_ids)} items"
                    )

            except Exception as e:
                logger.warning(f"Failed to get activity logs for board {board.id}: {e}")
                continue

        if not all_changed_item_ids:
            logger.info("No changed items found in activity logs")
            await sync_service.set_incr_items_synced_until(to_time)
            return

        logger.info(f"Found {len(all_changed_item_ids)} changed items across all boards")

        # Process items in batches
        item_ids_list = list(all_changed_item_ids)
        items_processed = 0

        for i in range(0, len(item_ids_list), ITEM_BATCH_SIZE):
            batch_ids = item_ids_list[i : i + ITEM_BATCH_SIZE]

            try:
                items_data = monday_client.get_items_batch(batch_ids)

                if not items_data:
                    continue

                # Create artifacts for fetched items
                artifacts: list[MondayItemArtifact] = []
                for item_data in items_data:
                    try:
                        artifact = MondayItemArtifact.from_api_response(
                            item_data=item_data,
                            ingest_job_id=job_id,
                        )
                        artifacts.append(artifact)
                    except Exception as e:
                        item_id = item_data.get("id", "unknown")
                        logger.warning(f"Failed to create artifact for item {item_id}: {e}")
                        continue

                if artifacts:
                    await self._persist_batch(artifacts, artifact_repo, config, trigger_indexing)
                    items_processed += len(artifacts)

            except Exception as e:
                logger.warning(f"Failed to process item batch: {e}")
                continue

        # Update sync cursor to the end of our query window
        await sync_service.set_incr_items_synced_until(to_time)
        logger.info(
            f"Updated Monday.com sync cursor to {to_time_str}",
            items_processed=items_processed,
        )

    async def _persist_batch(
        self,
        artifacts: list[MondayItemArtifact],
        artifact_repo: ArtifactRepository,
        config: MondayIncrementalBackfillConfig,
        trigger_indexing: TriggerIndexingCallback,
    ) -> None:
        """Persist a batch of artifacts and trigger indexing."""
        await artifact_repo.upsert_artifacts_batch(artifacts)

        entity_ids = [a.entity_id for a in artifacts]
        await trigger_indexing(
            entity_ids,
            source=DocumentSource.MONDAY_ITEM,
            tenant_id=config.tenant_id,
            backfill_id=config.backfill_id,
            suppress_notification=config.suppress_notification,
        )

        logger.info(
            "Incremental backfilled Monday.com items batch",
            count=len(artifacts),
        )
