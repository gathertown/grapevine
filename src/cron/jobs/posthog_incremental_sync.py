"""Cron job for PostHog periodic sync.

This job periodically triggers a full backfill of PostHog data to keep
dashboards, insights, feature flags, experiments, and surveys up to date.

PostHog's API does not support timestamp-based filtering or webhooks for
config changes, so we do a full sync every hour. This is efficient since
PostHog config data is typically small (hundreds of items, not millions).

The job runs every hour for all tenants with active PostHog installations.
"""

from __future__ import annotations

import time

from connectors.posthog.posthog_models import PostHogBackfillRootConfig
from src.clients.sqs import SQSClient
from src.cron import cron
from src.database.connector_installations import ConnectorInstallationsRepository
from src.utils.logging import get_logger

logger = get_logger(__name__)

# Deduplication window in seconds (1 hour = 3600 seconds)
# This should match the cron interval to ensure each scheduled run gets a unique dedup ID
DEDUP_WINDOW_SECONDS = 3600


def _get_dedup_id(tenant_id: str, source: str) -> str:
    """Generate a deterministic deduplication ID for sync jobs.

    Uses a time bucket based on DEDUP_WINDOW_SECONDS to ensure:
    - Multiple triggers within the same window get deduplicated by SQS
    - The next scheduled run gets a different dedup ID

    Args:
        tenant_id: The tenant ID
        source: The source type (e.g., "posthog_backfill_root")

    Returns:
        A deterministic deduplication ID
    """
    time_bucket = int(time.time() // DEDUP_WINDOW_SECONDS)
    return f"{tenant_id}_{source}_{time_bucket}"


# Run every hour
# https://crontab.guru/#0_*_*_*_*
@cron(id="posthog_periodic_sync", crontab="0 * * * *", tags=["posthog"])
async def posthog_periodic_sync() -> None:
    """Trigger PostHog full backfill for all tenants with active installations."""
    logger.info("[posthog] Starting periodic sync cron job")

    connector_repo = ConnectorInstallationsRepository()
    tenant_ids = await connector_repo.get_active_tenant_ids_by_type("posthog")

    if not tenant_ids:
        logger.info("[posthog] No tenants with PostHog installation found")
        return

    logger.info(f"[posthog] Triggering periodic sync for {len(tenant_ids)} tenants")

    sqs_client = SQSClient()
    for tenant_id in tenant_ids:
        config = PostHogBackfillRootConfig(
            tenant_id=tenant_id,
            suppress_notification=True,
        )
        dedup_id = _get_dedup_id(tenant_id, config.source)

        await sqs_client.send_backfill_ingest_message(
            backfill_config=config,
            message_deduplication_id=dedup_id,
        )
        logger.debug(f"[posthog] Sent periodic sync job for tenant {tenant_id}")

    logger.info(f"[posthog] Periodic sync cron job complete: queued {len(tenant_ids)} jobs")
