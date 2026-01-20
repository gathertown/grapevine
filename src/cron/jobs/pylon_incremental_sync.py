from __future__ import annotations

from connectors.pylon.extractors.pylon_incremental_backfill_extractor import (
    PylonIncrementalBackfillConfig,
)
from src.clients.sqs import SQSClient
from src.cron import cron
from src.database.connector_installations import ConnectorInstallationsRepository
from src.utils.logging import get_logger

logger = get_logger(__name__)


# Run every 30 mins at xx:17 and xx:47
# https://crontab.guru/#17-59/30_*_*_*_*
@cron(id="pylon_incremental_backfill", crontab="17-59/30 * * * *", tags=["pylon"])
async def pylon_incremental_backfill() -> None:
    """Trigger incremental backfill for all tenants with Pylon integration.

    This runs every 30 minutes to sync recently updated issues from Pylon.
    The incremental backfill uses a 2-hour lookback window by default to ensure
    no updates are missed between runs.
    """
    connector_repo = ConnectorInstallationsRepository()
    tenant_ids = await connector_repo.get_active_tenant_ids_by_type("pylon")

    if not tenant_ids:
        logger.info("No tenants with Pylon integration found")
        return

    logger.info(f"Triggering Pylon incremental backfill for {len(tenant_ids)} tenants")

    sqs_client = SQSClient()
    for tenant_id in tenant_ids:
        await sqs_client.send_backfill_ingest_message(
            backfill_config=PylonIncrementalBackfillConfig(
                tenant_id=tenant_id,
                suppress_notification=True,
            ),
        )
