"""Cron job for periodic Salesforce object synchronization."""

from __future__ import annotations

from connectors.salesforce import SALESFORCE_OBJECT_TYPES
from connectors.salesforce.salesforce_models import SalesforceObjectSyncConfig
from src.clients.sqs import SQSClient
from src.clients.tenant_db import tenant_db_manager
from src.cron import cron
from src.ingest.services.salesforce import salesforce_installation_service
from src.utils.logging import get_logger

logger = get_logger(__name__)


# Run every 30 minutes for incremental sync
@cron(id="salesforce_object_sync", crontab="*/30 * * * *", tags=["salesforce"])
async def salesforce_object_sync() -> None:
    """Sync Salesforce objects across all eligible tenants.

    This periodic job performs incremental syncs of Salesforce objects to supplement
    the real-time CDC (Change Data Capture) stream. This helps ensure:
    - Any missed CDC events are caught
    - Objects created before CDC connection are synced
    - Data consistency is maintained
    """
    logger.info("Starting Salesforce object sync cron job")
    control_pool = await tenant_db_manager.get_control_db()
    async with control_pool.acquire() as conn:
        all_installations = await salesforce_installation_service.get_all_installations(conn)

    if not all_installations:
        logger.info("No Salesforce installations found")
        return

    sqs_client = SQSClient()
    logger.info(f"Sending Salesforce object sync for {len(all_installations)} tenants")

    for installation in all_installations:
        try:
            # Send sync job for each object type
            for object_type in SALESFORCE_OBJECT_TYPES:
                await sqs_client.send_backfill_ingest_message(
                    backfill_config=SalesforceObjectSyncConfig(
                        tenant_id=installation.tenant_id,
                        object_type=object_type,
                        suppress_notification=True,  # Don't notify Slack for periodic syncs
                    ),
                )
            logger.info(f"Sent Salesforce object sync for tenant {installation.tenant_id}")
        except Exception as e:
            logger.error(f"Failed to send Salesforce sync for tenant {installation.tenant_id}: {e}")
            # Continue with other tenants even if one fails
            continue

    logger.info(f"Successfully queued Salesforce object sync for {len(all_installations)} tenants")
