"""Cron job for Teamwork incremental sync.

This job periodically syncs Teamwork tasks by fetching tasks updated since
the last sync. Since Teamwork doesn't support webhooks for all events, this
polling approach ensures data stays up-to-date.

The job runs every 30 minutes for all tenants with active Teamwork installations.
"""

from __future__ import annotations

import time

from connectors.teamwork.teamwork_backfill_config import TeamworkIncrementalBackfillConfig
from src.clients.sqs import SQSClient
from src.cron import cron
from src.database.connector_installations import ConnectorInstallationsRepository
from src.utils.logging import get_logger

logger = get_logger(__name__)

# Deduplication window in seconds (30 minutes = 1800 seconds)
# This should match the cron interval to ensure each scheduled run gets a unique dedup ID
DEDUP_WINDOW_SECONDS = 1800


def _get_dedup_id(tenant_id: str, source: str) -> str:
    """Generate a deterministic deduplication ID for incremental sync jobs.

    Uses a time bucket based on DEDUP_WINDOW_SECONDS to ensure:
    - Multiple triggers within the same window get deduplicated by SQS
    - The next scheduled run gets a different dedup ID

    Args:
        tenant_id: The tenant ID
        source: The source type (e.g., "teamwork_incremental")

    Returns:
        A deterministic deduplication ID
    """
    time_bucket = int(time.time() // DEDUP_WINDOW_SECONDS)
    return f"{tenant_id}_{source}_{time_bucket}"


# Run every 30 minutes
# https://crontab.guru/#*/30_*_*_*_*
@cron(id="teamwork_incremental_sync", crontab="*/30 * * * *", tags=["teamwork"])
async def teamwork_incremental_sync() -> None:
    """Trigger Teamwork incremental sync for all tenants with active installations."""
    logger.info("[teamwork] Starting incremental sync cron job")

    connector_repo = ConnectorInstallationsRepository()
    tenant_ids = await connector_repo.get_active_tenant_ids_by_type("teamwork")

    if not tenant_ids:
        logger.info("[teamwork] No tenants with Teamwork installation found")
        return

    logger.info(f"[teamwork] Triggering incremental sync for {len(tenant_ids)} tenants")

    sqs_client = SQSClient()
    for tenant_id in tenant_ids:
        config = TeamworkIncrementalBackfillConfig(
            tenant_id=tenant_id,
        )
        dedup_id = _get_dedup_id(tenant_id, config.source)

        await sqs_client.send_backfill_ingest_message(
            backfill_config=config,
            message_deduplication_id=dedup_id,
        )
        logger.debug(f"[teamwork] Sent incremental sync job for tenant {tenant_id}")

    logger.info(f"[teamwork] Incremental sync cron job complete: queued {len(tenant_ids)} jobs")
