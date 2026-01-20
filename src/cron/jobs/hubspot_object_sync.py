from __future__ import annotations

from connectors.hubspot.hubspot_models import HubSpotObjectSyncConfig
from src.clients.sqs import SQSClient
from src.clients.tenant_db import tenant_db_manager
from src.cron import cron
from src.ingest.services.hubspot import hubspot_installation_service
from src.utils.logging import get_logger

logger = get_logger(__name__)


# every 20 minutes, xx:01, xx:21, xx:41
# https://crontab.guru/#1/20_*_*_*_*
@cron(id="hubspot_object_sync", crontab="1/20 * * * *", tags=["hubspot"])
async def hubspot_object_sync() -> None:
    """Sync HubSpot objects across all eligible tenants."""
    logger.info("Starting HubSpot object sync cron job")
    control_pool = await tenant_db_manager.get_control_db()
    async with control_pool.acquire() as conn:
        all_installations = await hubspot_installation_service.get_all_installations(conn)
    if not all_installations:
        logger.info("No HubSpot installations found")
        return
    sqs_client = SQSClient()
    logger.info(f"Sending HubSpot object sync for {len(all_installations)} tenants")
    for installation in all_installations:
        for object_type in ["company", "deal", "ticket", "contact"]:
            await sqs_client.send_backfill_ingest_message(
                backfill_config=HubSpotObjectSyncConfig(
                    tenant_id=installation.tenant_id,
                    object_type=object_type,
                    suppress_notification=True,
                ),
            )
        logger.info(f"Sent HubSpot object sync for tenant {installation.tenant_id}")
