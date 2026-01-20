from __future__ import annotations

from connectors.google_drive.google_drive_models import GoogleDriveDiscoveryConfig
from src.clients.sqs import SQSClient
from src.cron import cron
from src.database.connector_installations import ConnectorInstallationsRepository
from src.utils.logging import get_logger

logger = get_logger(__name__)


# Run every week at 3:00 AM on Sunday
# https://crontab.guru/#0_3_*_*_sun
@cron(id="google_drive_backfill", crontab="0 3 * * sun", tags=["google_drive"])
async def google_drive_backfill() -> None:
    """Trigger Google Drive discovery and backfill for all tenants with Google Drive integration."""
    connector_repo = ConnectorInstallationsRepository()
    tenant_ids = await connector_repo.get_active_tenant_ids_by_type("google_drive")

    if not tenant_ids:
        logger.info("No tenants with Google Drive integration found")
        return

    logger.info(f"Triggering Google Drive backfill for {len(tenant_ids)} tenants")

    sqs_client = SQSClient()
    for tenant_id in tenant_ids:
        await sqs_client.send_backfill_ingest_message(
            backfill_config=GoogleDriveDiscoveryConfig(
                tenant_id=tenant_id,
                suppress_notification=True,
            ),
        )
