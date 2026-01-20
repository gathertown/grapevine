from __future__ import annotations

from connectors.monday.extractors.monday_incremental_backfill_extractor import (
    MondayIncrementalBackfillConfig,
)
from src.clients.sqs import SQSClient
from src.cron import cron
from src.database.connector_installations import ConnectorInstallationsRepository
from src.utils.logging import get_logger

logger = get_logger(__name__)


# Run every 30 minutes
# https://crontab.guru/#*/30_*_*_*_*
@cron(id="monday_incremental_backfill", crontab="*/30 * * * *", tags=["monday"])
async def monday_incremental_backfill() -> None:
    """Trigger incremental backfill for all tenants with Monday.com integration.

    This runs every 30 minutes to sync recently updated items from Monday.com.
    Uses the Activity Logs API to efficiently find items that have changed
    since the last sync, then fetches and indexes only those items.

    The 2-hour default lookback window ensures no updates are missed between runs.
    """
    connector_repo = ConnectorInstallationsRepository()
    tenant_ids = await connector_repo.get_active_tenant_ids_by_type("monday")

    if not tenant_ids:
        logger.info("No tenants with Monday.com integration found")
        return

    logger.info(f"Triggering Monday.com incremental backfill for {len(tenant_ids)} tenants")

    sqs_client = SQSClient()
    for tenant_id in tenant_ids:
        await sqs_client.send_backfill_ingest_message(
            backfill_config=MondayIncrementalBackfillConfig(
                tenant_id=tenant_id,
                suppress_notification=True,
            ),
        )
