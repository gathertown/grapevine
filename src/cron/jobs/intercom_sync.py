from __future__ import annotations

from connectors.intercom import IntercomApiBackfillRootConfig
from src.clients.sqs import SQSClient
from src.cron import cron
from src.database.connector_installations import ConnectorInstallationsRepository
from src.utils.logging import get_logger

logger = get_logger(__name__)


# Run once an hour at xx:37
# https://crontab.guru/#37_*_*_*_*
@cron(id="intercom_hourly_sync", crontab="37 * * * *", tags=["intercom"])
async def intercom_hourly_sync() -> None:
    """Trigger an hourly sync for all tenants with active Intercom connections."""
    connector_repo = ConnectorInstallationsRepository()
    tenant_ids = await connector_repo.get_active_tenant_ids_by_type("intercom")

    if not tenant_ids:
        logger.info("No tenants with Intercom integration found")
        return

    logger.info(f"Triggering Intercom hourly sync for {len(tenant_ids)} tenants")

    sqs_client = SQSClient()
    for tenant_id in tenant_ids:
        await sqs_client.send_backfill_ingest_message(
            backfill_config=IntercomApiBackfillRootConfig(
                tenant_id=tenant_id,
                suppress_notification=True,
            ),
        )
