from __future__ import annotations

from connectors.asana import AsanaIncrBackfillConfig
from connectors.asana.extractors.asana_permissions_backfill_extractor import (
    AsanaPermissionsBackfillConfig,
)
from src.clients.sqs import SQSClient
from src.cron import cron
from src.database.connector_installations import ConnectorInstallationsRepository
from src.utils.logging import get_logger

logger = get_logger(__name__)


# Run once an hour at xx:07
# https://crontab.guru/#7_*_*_*_*
@cron(id="asana_incremental_backfill", crontab="7 * * * *", tags=["asana"])
async def asana_incremental_backfill() -> None:
    connector_repo = ConnectorInstallationsRepository()
    tenant_ids = await connector_repo.get_active_tenant_ids_by_type("asana")

    if not tenant_ids:
        logger.info("No tenants with Asana integration found")
        return

    logger.info(f"Triggering Asana incremental backfill for {len(tenant_ids)} tenants")

    sqs_client = SQSClient()
    for tenant_id in tenant_ids:
        await sqs_client.send_backfill_ingest_message(
            backfill_config=AsanaIncrBackfillConfig(
                tenant_id=tenant_id,
                suppress_notification=True,
            ),
        )


# Run every week at 6:05 AM on Saturday
# https://crontab.guru/#5_6_*_*_sat
@cron(id="asana_permissions_backfill", crontab="5 6 * * sat", tags=["asana"])
async def asana_permissions_backfill() -> None:
    connector_repo = ConnectorInstallationsRepository()
    tenant_ids = await connector_repo.get_active_tenant_ids_by_type("asana")

    if not tenant_ids:
        logger.info("No tenants with Asana integration found")
        return

    logger.info(f"Triggering Asana permissions backfill for {len(tenant_ids)} tenants")

    sqs_client = SQSClient()
    for tenant_id in tenant_ids:
        await sqs_client.send_backfill_ingest_message(
            backfill_config=AsanaPermissionsBackfillConfig(
                tenant_id=tenant_id,
                suppress_notification=True,
            ),
        )
