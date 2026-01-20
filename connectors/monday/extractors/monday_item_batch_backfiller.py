"""Monday.com item batch backfill extractor.

Follows the standard extractor pattern:
1. Fetch data from Monday.com API
2. Create artifacts and store them in ingest_artifact table
3. Trigger indexing for the artifacts
"""

import math
from datetime import UTC, datetime
from uuid import UUID

import asyncpg

from connectors.base import BaseExtractor, TriggerIndexingCallback
from connectors.base.document_source import DocumentSource
from connectors.monday.client import get_monday_client_for_tenant
from connectors.monday.extractors.artifacts import MondayItemArtifact
from connectors.monday.monday_job_models import MondayItemBackfillConfig
from src.clients.sqs import SQSClient, cap_sqs_visibility_timeout
from src.clients.ssm import SSMClient
from src.ingest.utils import DEFAULT_INDEX_BATCH_SIZE
from src.jobs.exceptions import ExtendVisibilityException
from src.utils.logging import get_logger
from src.utils.tenant_config import (
    increment_backfill_attempted_ingest_jobs,
    increment_backfill_done_ingest_jobs,
    increment_backfill_total_index_jobs,
)

logger = get_logger(__name__)


class MondayItemBatchBackfiller(BaseExtractor[MondayItemBackfillConfig]):
    """Extractor that processes a batch of Monday.com items.

    Each job contains a list of item IDs from a single board.
    Items are fetched in batch, converted to artifacts, stored,
    and then indexing is triggered.
    """

    source_name = "monday_item_backfill"

    def __init__(self, ssm_client: SSMClient, sqs_client: SQSClient):
        super().__init__()
        self.ssm_client = ssm_client
        self.sqs_client = sqs_client

    async def process_job(
        self,
        job_id: str,
        config: MondayItemBackfillConfig,
        db_pool: asyncpg.Pool,
        trigger_indexing: TriggerIndexingCallback,
    ) -> None:
        tenant_id = config.tenant_id
        backfill_id = config.backfill_id

        # Check if we should start processing yet (for rate limiting)
        if config.start_timestamp:
            current_time = datetime.now(UTC)
            if current_time < config.start_timestamp:
                # Not time to start yet - extend visibility timeout until start_timestamp
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
            await self._process_batch(
                job_id=job_id,
                db_pool=db_pool,
                trigger_indexing=trigger_indexing,
                config=config,
            )
        except ExtendVisibilityException:
            raise
        except Exception as e:
            logger.error(f"Failed to process Monday.com items batch: {e}", exc_info=True)
            raise
        finally:
            # Always track that we attempted this job, regardless of success/failure
            if backfill_id:
                await increment_backfill_attempted_ingest_jobs(backfill_id, tenant_id, 1)

    async def _process_batch(
        self,
        job_id: str,
        db_pool: asyncpg.Pool,
        trigger_indexing: TriggerIndexingCallback,
        config: MondayItemBackfillConfig,
    ) -> None:
        """Process a batch of Monday.com items."""
        tenant_id = config.tenant_id
        backfill_id = config.backfill_id
        board_id = config.board_id
        item_ids = config.item_ids

        logger.info(
            f"Processing Monday.com item batch: {len(item_ids)} items from board {board_id}",
            backfill_id=backfill_id,
            tenant_id=tenant_id,
        )

        try:
            monday_client = await get_monday_client_for_tenant(tenant_id, self.ssm_client)
        except Exception as e:
            logger.error(f"Failed to get Monday.com client: {e}")
            raise

        # Fetch items in batch
        try:
            items_data = monday_client.get_items_batch(item_ids)
        except Exception as e:
            logger.error(
                f"Failed to fetch items batch: {e}",
                backfill_id=backfill_id,
                board_id=board_id,
            )
            raise

        logger.info(
            f"Fetched {len(items_data)} items from Monday.com",
            backfill_id=backfill_id,
        )

        # Create artifacts from API responses
        artifacts: list[MondayItemArtifact] = []
        entity_ids: list[str] = []

        for item_data in items_data:
            try:
                # Create artifact from API response
                artifact = MondayItemArtifact.from_api_response(
                    item_data=item_data,
                    ingest_job_id=UUID(job_id),
                )
                artifacts.append(artifact)
                entity_ids.append(artifact.entity_id)

            except Exception as e:
                item_id = item_data.get("id", "unknown")
                logger.warning(
                    f"Failed to create artifact for item {item_id}: {e}",
                    backfill_id=backfill_id,
                )
                continue

        if not artifacts:
            logger.warning(
                "No artifacts created from item batch",
                backfill_id=backfill_id,
                board_id=board_id,
            )
            return

        # Store artifacts in batch using the standard method
        logger.info(f"Storing {len(artifacts)} Monday.com item artifacts")
        await self.store_artifacts_batch(db_pool, artifacts)

        # Trigger indexing for all processed records
        if entity_ids:
            logger.info(f"Triggering indexing for {len(entity_ids)} Monday.com items")

            # Calculate total number of index batches and track them upfront
            total_index_batches = math.ceil(len(entity_ids) / DEFAULT_INDEX_BATCH_SIZE)
            if backfill_id and total_index_batches > 0:
                await increment_backfill_total_index_jobs(
                    backfill_id, tenant_id, total_index_batches
                )

            for i in range(0, len(entity_ids), DEFAULT_INDEX_BATCH_SIZE):
                batch = entity_ids[i : i + DEFAULT_INDEX_BATCH_SIZE]
                await trigger_indexing(
                    batch,
                    DocumentSource.MONDAY_ITEM,
                    tenant_id,
                    backfill_id,
                    config.suppress_notification,
                )

        logger.info(
            f"Completed Monday.com items batch: {len(artifacts)} processed",
            tenant_id=tenant_id,
            backfill_id=backfill_id,
            board_id=board_id,
            records_processed=len(artifacts),
            records_failed=len(item_ids) - len(artifacts),
        )

        if backfill_id:
            await increment_backfill_done_ingest_jobs(backfill_id, tenant_id, 1)


# Backwards compatible alias
MondayItemBackfillExtractor = MondayItemBatchBackfiller
