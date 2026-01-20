from __future__ import annotations

from connectors.google_drive.google_drive_models import GoogleDriveWebhookRefreshConfig
from connectors.google_drive.google_drive_webhook_handler import webhook_manager
from src.clients.sqs import SQSClient
from src.cron import cron
from src.utils.logging import get_logger

logger = get_logger(__name__)


# once a day at 5am UTC
@cron(id="google_drive_webhook_refresh", crontab="0 5 * * *", tags=["google_drive"])
async def google_drive_webhook_refresh() -> None:
    """Refresh Google Drive webhook subscriptions across all eligible tenants.

    Returns:
        None. Publishes SQS messages as a side effect.

    Side Effects:
        - Logs when no tenants are found with Google Drive integration.
        - Publishes one SQS message per tenant to trigger refresh processing.
    """
    tenant_ids = await webhook_manager.get_all_tenants_with_google_drive_webhook_config()

    if not tenant_ids:
        logger.info("No tenants with Google Drive integration found")
        return

    logger.info(f"Refreshing Google Drive webhook subscriptions for {len(tenant_ids)} tenants")

    sqs_client = SQSClient()
    for tenant_id in tenant_ids:
        await sqs_client.send_backfill_ingest_message(
            backfill_config=GoogleDriveWebhookRefreshConfig(
                tenant_id=tenant_id,
                suppress_notification=True,
            ),
        )
