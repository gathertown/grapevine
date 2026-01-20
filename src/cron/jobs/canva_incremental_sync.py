"""Cron job for Canva incremental sync.

This job periodically syncs Canva designs by fetching designs updated since
the last sync. Since Canva doesn't support webhooks, this polling approach
ensures data stays up-to-date.

The job runs every 30 minutes for all tenants with active Canva installations.
"""

from __future__ import annotations

import time

from connectors.canva.canva_models import CanvaIncrementalBackfillConfig
from src.clients.sqs import SQSClient
from src.cron import cron
from src.database.connector_installations import ConnectorInstallationsRepository
from src.utils.logging import get_logger

logger = get_logger(__name__)

# Deduplication window in seconds (30 minutes = 1800 seconds)
# This should match the cron interval to ensure each scheduled run gets a unique dedup ID
DEDUP_WINDOW_SECONDS = 1800

# Number of recent designs to check for updates
CHECK_COUNT = 100


def _get_dedup_id(tenant_id: str, source: str) -> str:
    """Generate a deterministic deduplication ID for incremental sync jobs.

    Uses a time bucket based on DEDUP_WINDOW_SECONDS to ensure:
    - Multiple triggers within the same window get deduplicated by SQS
    - The next scheduled run gets a different dedup ID

    Args:
        tenant_id: The tenant ID
        source: The source type (e.g., "canva_incremental_backfill")

    Returns:
        A deterministic deduplication ID
    """
    time_bucket = int(time.time() // DEDUP_WINDOW_SECONDS)
    return f"{tenant_id}_{source}_{time_bucket}"


# Run every 30 minutes
# https://crontab.guru/#*/30_*_*_*_*
@cron(id="canva_incremental_sync", crontab="*/30 * * * *", tags=["canva"])
async def canva_incremental_sync() -> None:
    """Trigger Canva incremental sync for all tenants with active installations."""
    logger.info("[canva] Starting incremental sync cron job")

    connector_repo = ConnectorInstallationsRepository()
    tenant_ids = await connector_repo.get_active_tenant_ids_by_type("canva")

    if not tenant_ids:
        logger.info("[canva] No tenants with Canva installation found")
        return

    logger.info(f"[canva] Triggering incremental sync for {len(tenant_ids)} tenants")

    sqs_client = SQSClient()
    for tenant_id in tenant_ids:
        config = CanvaIncrementalBackfillConfig(
            tenant_id=tenant_id,
            check_count=CHECK_COUNT,
        )
        dedup_id = _get_dedup_id(tenant_id, config.source)

        await sqs_client.send_backfill_ingest_message(
            backfill_config=config,
            message_deduplication_id=dedup_id,
        )
        logger.debug(f"[canva] Sent incremental sync job for tenant {tenant_id}")

    logger.info(f"[canva] Incremental sync cron job complete: queued {len(tenant_ids)} jobs")
