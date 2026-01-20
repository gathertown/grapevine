"""Cron job for Pipedrive incremental sync.

This job periodically syncs Pipedrive data by fetching records updated since
the last sync. It provides real-time data synchronization through periodic polling.

The job runs every 5 minutes for all tenants with active Pipedrive installations.
"""

from __future__ import annotations

import time

from connectors.pipedrive.pipedrive_models import PipedriveIncrementalBackfillConfig
from src.clients.sqs import SQSClient
from src.cron import cron
from src.database.connector_installations import ConnectorInstallationsRepository
from src.utils.logging import get_logger

logger = get_logger(__name__)

# Deduplication window in seconds (5 minutes = 300 seconds)
# This should match the cron interval to ensure each scheduled run gets a unique dedup ID
DEDUP_WINDOW_SECONDS = 300


def _get_dedup_id(tenant_id: str, source: str) -> str:
    """Generate a deterministic deduplication ID for incremental sync jobs.

    Uses a time bucket based on DEDUP_WINDOW_SECONDS to ensure:
    - Multiple triggers within the same window get deduplicated by SQS
    - The next scheduled run gets a different dedup ID

    Args:
        tenant_id: The tenant ID
        source: The source type (e.g., "pipedrive_incremental_backfill")

    Returns:
        A deterministic deduplication ID
    """
    time_bucket = int(time.time() // DEDUP_WINDOW_SECONDS)
    return f"{tenant_id}_{source}_{time_bucket}"


# Run every 5 minutes (for testing)
# https://crontab.guru/#*/5_*_*_*_*
@cron(id="pipedrive_incremental_sync", crontab="*/5 * * * *", tags=["pipedrive"])
async def pipedrive_incremental_sync() -> None:
    """Trigger Pipedrive incremental sync for all tenants with active installations."""
    logger.info("[pipedrive] Starting incremental sync cron job")

    connector_repo = ConnectorInstallationsRepository()
    tenant_ids = await connector_repo.get_active_tenant_ids_by_type("pipedrive")

    if not tenant_ids:
        logger.info("[pipedrive] No tenants with Pipedrive installation found")
        return

    logger.info(f"[pipedrive] Triggering incremental sync for {len(tenant_ids)} tenants")

    sqs_client = SQSClient()
    for tenant_id in tenant_ids:
        config = PipedriveIncrementalBackfillConfig(
            tenant_id=tenant_id,
            suppress_notification=True,
        )
        dedup_id = _get_dedup_id(tenant_id, config.source)

        await sqs_client.send_backfill_ingest_message(
            backfill_config=config,
            message_deduplication_id=dedup_id,
        )
        logger.debug(f"[pipedrive] Sent incremental sync job for tenant {tenant_id}")

    logger.info(f"[pipedrive] Incremental sync cron job complete: queued {len(tenant_ids)} jobs")
