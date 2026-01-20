from __future__ import annotations

from connectors.gitlab.gitlab_models import GitLabIncrBackfillConfig
from src.clients.sqs import SQSClient
from src.cron import cron
from src.database.connector_installations import ConnectorInstallationsRepository
from src.utils.logging import get_logger

logger = get_logger(__name__)


# Run once an hour at xx:33
# https://crontab.guru/#33_*_*_*_*
@cron(id="gitlab_hourly_sync", crontab="33 * * * *", tags=["gitlab"])
async def gitlab_hourly_sync() -> None:
    """Trigger an hourly incremental sync for all tenants with active GitLab connections."""
    connector_repo = ConnectorInstallationsRepository()
    tenant_ids = await connector_repo.get_active_tenant_ids_by_type("gitlab")

    if not tenant_ids:
        logger.info("No tenants with GitLab integration found")
        return

    logger.info(f"Triggering GitLab hourly incremental sync for {len(tenant_ids)} tenants")

    sqs_client = SQSClient()
    failed_tenants: list[str] = []
    for tenant_id in tenant_ids:
        success = await sqs_client.send_backfill_ingest_message(
            backfill_config=GitLabIncrBackfillConfig(
                tenant_id=tenant_id,
                suppress_notification=True,
            ),
        )
        if not success:
            logger.error(f"Failed to send GitLab incremental sync job for tenant {tenant_id}")
            failed_tenants.append(tenant_id)

    if failed_tenants:
        raise RuntimeError(
            f"Failed to send GitLab incremental sync jobs for {len(failed_tenants)} tenants: "
            f"{failed_tenants}"
        )
