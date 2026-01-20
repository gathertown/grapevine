"""Root extractor for Canva full backfill.

Orchestrates the full backfill by:
1. Setting incremental sync cursors to "now"
2. Collecting all design IDs
3. Enqueuing design-specific backfill jobs for batch processing
"""

import secrets
from datetime import UTC, datetime

import asyncpg

from connectors.base import BaseExtractor, TriggerIndexingCallback
from connectors.canva.canva_models import CanvaBackfillRootConfig, CanvaDesignBackfillConfig
from connectors.canva.canva_sync_service import CanvaSyncService
from connectors.canva.client import get_canva_client_for_tenant
from src.clients.sqs import SQSClient
from src.utils.logging import get_logger
from src.utils.tenant_config import increment_backfill_total_ingest_jobs

logger = get_logger(__name__)

# Batch size for design processing jobs
BATCH_SIZE = 20  # Canva has 100 req/min rate limit, so moderate batch size


class CanvaBackfillRootExtractor(BaseExtractor[CanvaBackfillRootConfig]):
    """Root extractor that discovers all designs and splits into batch jobs.

    This extractor:
    1. Sets incremental sync cursors to "now" (so incremental picks up changes during backfill)
    2. Discovers all designs from the user's account
    3. Splits them into batches and enqueues child jobs for processing
    """

    source_name = "canva_backfill_root"

    def __init__(self, sqs_client: SQSClient):
        super().__init__()
        self.sqs_client = sqs_client

    async def process_job(
        self,
        job_id: str,
        config: CanvaBackfillRootConfig,
        db_pool: asyncpg.Pool,
        trigger_indexing: TriggerIndexingCallback,
    ) -> None:
        backfill_id = config.backfill_id or secrets.token_hex(8)
        tenant_id = config.tenant_id

        logger.info(
            "Starting Canva backfill root job",
            backfill_id=backfill_id,
            tenant_id=tenant_id,
        )

        # Initialize services
        sync_service = CanvaSyncService(db_pool, tenant_id)

        # Step 1: Set incremental sync cursors to "now"
        sync_start_time = datetime.now(UTC)
        await sync_service.set_designs_synced_until(sync_start_time)

        logger.info(
            "Set incremental sync cursors",
            tenant_id=tenant_id,
            sync_start_time=sync_start_time.isoformat(),
        )

        # Step 2: Collect all design IDs
        all_design_ids: list[str] = []

        try:
            async with await get_canva_client_for_tenant(tenant_id) as client:
                async for design in client.iter_all_designs(
                    ownership="any",
                    sort_by="modified_descending",
                ):
                    all_design_ids.append(design.id)

                    if len(all_design_ids) % 100 == 0:
                        logger.info(
                            f"Collected {len(all_design_ids)} design IDs so far",
                            tenant_id=tenant_id,
                        )

        except Exception as e:
            logger.error(f"Failed to get Canva client: {e}")
            raise

        logger.info(
            "Collected all Canva design IDs",
            backfill_id=backfill_id,
            total_designs=len(all_design_ids),
        )

        if not all_design_ids:
            logger.warning(
                "No designs found for Canva backfill",
                tenant_id=tenant_id,
            )
            # Mark backfill as complete even if empty
            await sync_service.set_full_backfill_complete(True)
            return

        # Step 3: Create batches of designs
        batches = [
            all_design_ids[i : i + BATCH_SIZE] for i in range(0, len(all_design_ids), BATCH_SIZE)
        ]

        # Track total jobs for backfill progress tracking
        total_jobs = len(batches)
        await increment_backfill_total_ingest_jobs(backfill_id, tenant_id, total_jobs)

        # Step 4: Schedule batch jobs
        for batch in batches:
            design_config = CanvaDesignBackfillConfig(
                tenant_id=tenant_id,
                design_ids=batch,
                backfill_id=backfill_id,
            )

            await self.sqs_client.send_backfill_ingest_message(design_config)

        logger.info(
            "Canva root backfill complete - batch jobs enqueued",
            tenant_id=tenant_id,
            backfill_id=backfill_id,
            total_batches=total_jobs,
            total_designs=len(all_design_ids),
        )
