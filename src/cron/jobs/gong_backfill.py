from __future__ import annotations

from connectors.gong.gong_models import GongCallBackfillRootConfig
from src.clients.sqs import SQSClient
from src.cron import cron
from src.database.connector_installations import ConnectorInstallationsRepository
from src.utils.logging import get_logger

logger = get_logger(__name__)


# run hourly
@cron(id="gong_backfill", crontab="0 * * * *", tags=["gong"])
async def gong_backfill() -> None:
    """Trigger Gong call discovery and backfill for all tenants with Gong integration.

    This job triggers the root extractor to discover all calls (full sync)
    and enqueue child jobs to process them.

    How Pruning Works:
        1. Each backfill run generates a unique backfill_id
        2. All artifacts and documents seen during the backfill are marked with this backfill_id
        3. After the backfill completes, the pruner deletes entities NOT marked with the current backfill_id
        4. This ensures stale/deleted entities are removed while preserving active ones

    Critical Implementation Details:
        - ALL documents must have their last_seen_backfill_id updated during indexing, even if
          they don't need re-indexing (content unchanged). This is handled in gen_and_store_embeddings()
          via update_all_document_backfill_ids().
        - Artifacts get their last_seen_backfill_id updated via force_upsert_artifacts_batch().
        - Without updating last_seen_backfill_id for unchanged documents, they would be incorrectly
          pruned as stale on the next backfill run.

    Returns:
        None. Publishes SQS messages as a side effect.

    Side Effects:
        - Logs when no tenants are found with Gong integration.
        - Publishes one SQS message per tenant to trigger call discovery and backfill processing.
    """
    # Get all tenant IDs with active Gong connectors from the control DB
    connector_repo = ConnectorInstallationsRepository()
    tenant_ids = await connector_repo.get_active_tenant_ids_by_type("gong")

    if not tenant_ids:
        logger.info("No tenants with Gong integration found")
        return

    logger.info(f"Triggering Gong call discovery for {len(tenant_ids)} tenants")

    sqs_client = SQSClient()
    for tenant_id in tenant_ids:
        await sqs_client.send_backfill_ingest_message(
            backfill_config=GongCallBackfillRootConfig(
                tenant_id=tenant_id,
                suppress_notification=True,
            ),
        )
