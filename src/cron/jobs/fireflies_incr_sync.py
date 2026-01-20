from __future__ import annotations

from connectors.fireflies import (
    FirefliesIncrBackfillConfig,
)
from src.clients.sqs import SQSClient
from src.cron import cron
from src.database.connector_installations import ConnectorInstallationsRepository
from src.utils.logging import get_logger

logger = get_logger(__name__)


# Run once an hour at xx:24
# https://crontab.guru/#24_*_*_*_*
@cron(id="fireflies_incremental_backfill", crontab="24 * * * *", tags=["fireflies"])
async def fireflies_incremental_backfill() -> None:
    connector_repo = ConnectorInstallationsRepository()
    tenant_ids = await connector_repo.get_active_tenant_ids_by_type("fireflies")

    if not tenant_ids:
        logger.info("No tenants with Fireflies integration found")
        return

    logger.info(f"Triggering Fireflies incremental backfill for {len(tenant_ids)} tenants")

    sqs_client = SQSClient()
    for tenant_id in tenant_ids:
        await sqs_client.send_backfill_ingest_message(
            backfill_config=FirefliesIncrBackfillConfig(
                tenant_id=tenant_id,
                suppress_notification=True,
            ),
        )
