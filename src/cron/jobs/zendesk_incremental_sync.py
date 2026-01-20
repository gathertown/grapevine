from __future__ import annotations

from connectors.zendesk import ZendeskIncrementalBackfillConfig
from src.clients.sqs import SQSClient
from src.cron import cron
from src.database.connector_installations import ConnectorInstallationsRepository
from src.utils.logging import get_logger

logger = get_logger(__name__)


# Run every 30 mins at xx:12 and xx:42
# https://crontab.guru/#12-59/30_*_*_*_*
@cron(id="zendesk_incremental_backfill", crontab="12-59/30 * * * *", tags=["zendesk"])
async def zendesk_incremental_backfill() -> None:
    connector_repo = ConnectorInstallationsRepository()
    tenant_ids = await connector_repo.get_active_tenant_ids_by_type("zendesk")

    if not tenant_ids:
        logger.info("No tenants with Zendesk integration found")
        return

    logger.info(f"Triggering Zendesk incremental backfill for {len(tenant_ids)} tenants")

    sqs_client = SQSClient()
    for tenant_id in tenant_ids:
        await sqs_client.send_backfill_ingest_message(
            backfill_config=ZendeskIncrementalBackfillConfig(
                tenant_id=tenant_id,
                suppress_notification=True,
            ),
        )
