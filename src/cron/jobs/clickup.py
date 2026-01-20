from __future__ import annotations

from connectors.clickup import ClickupIncrBackfillConfig, ClickupPermissionsBackfillConfig
from src.clients.sqs import SQSClient
from src.cron import cron
from src.database.connector_installations import ConnectorInstallationsRepository
from src.utils.logging import get_logger

logger = get_logger(__name__)


# Run once an hour at xx:51
# https://crontab.guru/#51_*_*_*_*
@cron(id="clickup_incremental_backfill", crontab="51 * * * *", tags=["clickup"])
async def clickup_incremental_backfill() -> None:
    connector_repo = ConnectorInstallationsRepository()
    tenant_ids = await connector_repo.get_active_tenant_ids_by_type("clickup")

    if not tenant_ids:
        logger.info("No tenants with ClickUp integration found")
        return

    logger.info(f"Triggering ClickUp incremental backfill for {len(tenant_ids)} tenants")

    sqs_client = SQSClient()
    for tenant_id in tenant_ids:
        await sqs_client.send_backfill_ingest_message(
            backfill_config=ClickupIncrBackfillConfig(
                tenant_id=tenant_id,
                suppress_notification=True,
            ),
        )


# Run every week at 7:05 AM on Saturday (UTC)
# https://crontab.guru/#5_7_*_*_sat
@cron(id="clickup_permissions_backfill", crontab="5 7 * * sat", tags=["clickup"])
async def clickup_permissions_backfill() -> None:
    connector_repo = ConnectorInstallationsRepository()
    tenant_ids = await connector_repo.get_active_tenant_ids_by_type("clickup")
    if not tenant_ids:
        logger.info("No tenants with ClickUp integration found")
        return

    logger.info(f"Triggering ClickUp permissions backfill for {len(tenant_ids)} tenants")

    sqs_client = SQSClient()
    for tenant_id in tenant_ids:
        await sqs_client.send_backfill_ingest_message(
            backfill_config=ClickupPermissionsBackfillConfig(
                tenant_id=tenant_id,
                suppress_notification=True,
            ),
        )
