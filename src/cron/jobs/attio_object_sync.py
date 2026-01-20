"""Attio full sync cron job.

Runs every 4 hours but only triggers a full backfill if one is due (every 4 weeks).
Reuses the existing backfill infrastructure with notifications suppressed.
"""

from __future__ import annotations

from connectors.attio.attio_artifacts import AttioObjectType
from connectors.attio.attio_models import AttioBackfillRootConfig
from src.clients.sqs import SQSClient
from src.clients.tenant_db import tenant_db_manager
from src.cron import cron
from src.database.connector_installations import ConnectorInstallationsRepository
from src.ingest.services.attio import attio_object_sync_service
from src.utils.logging import get_logger

logger = get_logger(__name__)


# Run every 4 hours
# https://crontab.guru/#0_*/4_*_*_*
@cron(id="attio_full_sync", crontab="0 */4 * * *", tags=["attio"])
async def attio_full_sync() -> None:
    """Trigger full Attio backfill for tenants where a sync is due.

    This cron runs every 4 hours and checks each tenant to see if a full sync
    is needed (never synced or last sync >= 4 weeks ago). When due, it triggers
    the full backfill process with notifications suppressed.
    """
    connector_repo = ConnectorInstallationsRepository()
    tenant_ids = await connector_repo.get_active_tenant_ids_by_type("attio")

    if not tenant_ids:
        logger.info("No tenants with Attio integration found")
        return

    logger.info(f"Checking Attio sync status for {len(tenant_ids)} tenants")

    sqs_client = SQSClient()
    tenants_queued = 0

    for tenant_id in tenant_ids:
        try:
            async with tenant_db_manager.acquire_pool(tenant_id) as db_pool:
                # Check if any object type needs a sync - if so, run full backfill
                # We check all types because the backfill processes all of them together
                needs_sync = False
                for object_type in AttioObjectType:
                    if await attio_object_sync_service.is_full_sync_due(object_type, db_pool):
                        needs_sync = True
                        break

                if needs_sync:
                    # Trigger full backfill with notifications suppressed
                    await sqs_client.send_backfill_ingest_message(
                        backfill_config=AttioBackfillRootConfig(
                            tenant_id=tenant_id,
                            suppress_notification=True,
                        ),
                    )
                    tenants_queued += 1
                    logger.info(
                        f"Queued Attio full backfill for tenant {tenant_id}",
                        tenant_id=tenant_id,
                    )
        except Exception as e:
            logger.error(
                f"Failed to check/queue Attio sync for tenant {tenant_id}: {e}",
                tenant_id=tenant_id,
                exc_info=True,
            )
            continue

    if tenants_queued > 0:
        logger.info(f"Queued Attio full backfill for {tenants_queued} tenants")
    else:
        logger.info("No Attio sync due at this time")
