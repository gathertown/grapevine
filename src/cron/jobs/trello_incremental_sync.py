"""Cron job for Trello incremental sync.

This job periodically syncs Trello data by fetching board actions since
the last sync and re-indexing modified cards. It provides an alternative
to webhooks for keeping data up-to-date through periodic polling.

The job runs every 2 hours for all tenants with active Trello installations.
"""

from __future__ import annotations

from connectors.trello.trello_models import TrelloIncrementalSyncConfig
from src.clients.sqs import SQSClient
from src.clients.tenant_db import tenant_db_manager
from src.cron import cron
from src.ingest.services.trello import trello_installation_service
from src.utils.logging import get_logger

logger = get_logger(__name__)


# Run every 30 minutes
# https://crontab.guru/#*/30_*_*_*_*
@cron(id="trello_incremental_sync", crontab="*/30 * * * *", tags=["trello"])
async def trello_incremental_sync() -> None:
    """Trigger Trello incremental sync for all tenants with active installations."""
    logger.info("[trello] Starting incremental sync cron job")

    control_pool = await tenant_db_manager.get_control_db()
    async with control_pool.acquire() as conn:
        installations = await trello_installation_service.get_all_installations(conn)

    if not installations:
        logger.info("[trello] No tenants with Trello installation found")
        return

    # Get unique tenant IDs (a tenant should only have one installation, but just in case)
    tenant_ids = list({installation.tenant_id for installation in installations})

    logger.info(f"[trello] Triggering incremental sync for {len(tenant_ids)} tenants")

    sqs_client = SQSClient()
    for tenant_id in tenant_ids:
        await sqs_client.send_backfill_ingest_message(
            backfill_config=TrelloIncrementalSyncConfig(
                tenant_id=tenant_id,
                suppress_notification=True,
            ),
        )
        logger.debug(f"[trello] Sent incremental sync job for tenant {tenant_id}")

    logger.info(f"[trello] Incremental sync cron job complete: queued {len(tenant_ids)} jobs")
