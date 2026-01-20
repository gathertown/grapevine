from __future__ import annotations

from connectors.gmail.gmail_models import GoogleEmailWebhookRefreshConfig
from connectors.gmail.google_email_webhook_handler import webhook_manager
from src.clients.sqs import SQSClient
from src.cron import cron
from src.utils.logging import get_logger

logger = get_logger(__name__)


# once a day at 5am UTC
@cron(id="google_email_webhook_refresh", crontab="0 5 * * *", tags=["google_email"])
async def google_email_webhook_refresh() -> None:
    """Refresh Google Email webhook subscriptions across all eligible tenants.

    Returns:
        None. Publishes SQS messages as a side effect.

    Side Effects:
        - Logs when no tenants are found with Google Email integration.
        - Publishes one SQS message per tenant to trigger refresh processing.
    """
    tenant_ids = await webhook_manager.get_all_tenant_with_google_email_integration()

    if not tenant_ids:
        logger.info("No tenants with Google Email integration found")
        return

    logger.info(f"Refreshing Google Email webhook subscriptions for {len(tenant_ids)} tenants")

    sqs_client = SQSClient()
    for tenant_id in tenant_ids:
        await sqs_client.send_backfill_ingest_message(
            backfill_config=GoogleEmailWebhookRefreshConfig(
                tenant_id=tenant_id,
                suppress_notification=True,
            ),
        )
