"""Incremental backfill extractor for Pipedrive.

Uses timestamp-based filtering (updated_after) to sync only recently
modified records. This is the preferred sync strategy as it's more
efficient than webhooks for most use cases.

Scheduled via cron every 30 minutes.
"""

from datetime import UTC, datetime, timedelta
from uuid import UUID

import asyncpg

from connectors.base import BaseExtractor, TriggerIndexingCallback
from connectors.base.document_source import DocumentSource
from connectors.pipedrive.pipedrive_artifacts import (
    PipedriveDealArtifact,
    PipedriveOrganizationArtifact,
    PipedrivePersonArtifact,
    PipedriveProductArtifact,
)
from connectors.pipedrive.pipedrive_client import (
    PipedriveClient,
    get_pipedrive_client_for_tenant,
)
from connectors.pipedrive.pipedrive_models import PipedriveIncrementalBackfillConfig
from connectors.pipedrive.pipedrive_sync_service import PipedriveSyncService
from src.clients.ssm import SSMClient
from src.ingest.utils import DEFAULT_INDEX_BATCH_SIZE
from src.utils.logging import get_logger

logger = get_logger(__name__)

# Default lookback window (2 hours)
DEFAULT_LOOKBACK_HOURS = 2


class PipedriveIncrementalBackfillExtractor(BaseExtractor[PipedriveIncrementalBackfillConfig]):
    """Extracts recently modified Pipedrive entities.

    Uses the updated_after filter supported by Pipedrive v2 API
    to efficiently sync only changed records.
    """

    source_name = "pipedrive_incremental_backfill"

    def __init__(self, ssm_client: SSMClient):
        super().__init__()
        self.ssm_client = ssm_client

    async def process_job(
        self,
        job_id: str,
        config: PipedriveIncrementalBackfillConfig,
        db_pool: asyncpg.Pool,
        trigger_indexing: TriggerIndexingCallback,
    ) -> None:
        """Execute the incremental backfill job.

        Args:
            job_id: Unique job identifier
            config: Incremental backfill configuration
            db_pool: Database connection pool
            trigger_indexing: Callback to trigger indexing
        """
        tenant_id = config.tenant_id
        lookback_hours = config.lookback_hours or DEFAULT_LOOKBACK_HOURS

        logger.info(
            "Starting Pipedrive incremental backfill",
            tenant_id=tenant_id,
            lookback_hours=lookback_hours,
        )

        # Initialize services
        client = await get_pipedrive_client_for_tenant(tenant_id, self.ssm_client)
        sync_service = PipedriveSyncService(db_pool, tenant_id)

        # Calculate the lookback timestamp for first run
        default_lookback = datetime.now(UTC) - timedelta(hours=lookback_hours)

        # Get sync cursors - use stored cursor if available, otherwise use default
        deals_since = await sync_service.get_deals_synced_until() or default_lookback
        persons_since = await sync_service.get_persons_synced_until() or default_lookback
        orgs_since = await sync_service.get_orgs_synced_until() or default_lookback
        products_since = await sync_service.get_products_synced_until() or default_lookback

        # Track sync time BEFORE fetching (to handle changes during sync)
        sync_time = datetime.now(UTC)

        # Sync deals
        deals_count, deal_entity_ids = await self._sync_deals(
            client, db_pool, UUID(job_id), tenant_id, deals_since
        )

        # Sync persons
        persons_count, person_entity_ids = await self._sync_persons(
            client, db_pool, UUID(job_id), tenant_id, persons_since
        )

        # Sync organizations
        orgs_count, org_entity_ids = await self._sync_organizations(
            client, db_pool, UUID(job_id), tenant_id, orgs_since
        )

        # Sync products
        products_count, product_entity_ids = await self._sync_products(
            client, db_pool, UUID(job_id), tenant_id, products_since
        )

        # Trigger indexing for all synced entities
        await self._trigger_indexing_for_entities(
            trigger_indexing,
            tenant_id,
            config,
            deal_entity_ids,
            person_entity_ids,
            org_entity_ids,
            product_entity_ids,
        )

        # Update sync cursors with overlap (subtract 1 second to handle boundary)
        cursor_time = sync_time - timedelta(seconds=1)
        await sync_service.set_deals_synced_until(cursor_time)
        await sync_service.set_persons_synced_until(cursor_time)
        await sync_service.set_orgs_synced_until(cursor_time)
        await sync_service.set_products_synced_until(cursor_time)

        logger.info(
            "Completed Pipedrive incremental backfill",
            tenant_id=tenant_id,
            deals_synced=deals_count,
            persons_synced=persons_count,
            orgs_synced=orgs_count,
            products_synced=products_count,
            next_sync_cursor=cursor_time.isoformat(),
        )

    async def _sync_deals(
        self,
        client: PipedriveClient,
        db_pool: asyncpg.Pool,
        job_id: UUID,
        tenant_id: str,
        since: datetime,
    ) -> tuple[int, list[str]]:
        """Sync deals updated since the given timestamp."""
        artifacts: list[PipedriveDealArtifact] = []
        entity_ids: list[str] = []

        for page in client.iterate_deals(updated_after=since):
            for deal_data in page:
                try:
                    deal_id = deal_data.get("id", 0)

                    # Fetch notes for enrichment
                    notes: list[dict] = []
                    try:
                        notes = client.get_notes_for_deal(deal_id)
                    except Exception as e:
                        logger.warning(f"Failed to fetch notes for deal {deal_id}: {e}")

                    # Fetch activities for enrichment
                    activities: list[dict] = []
                    try:
                        activities = client.get_activities_for_deal(deal_id)
                    except Exception as e:
                        logger.warning(f"Failed to fetch activities for deal {deal_id}: {e}")

                    artifact = PipedriveDealArtifact.from_api_response(
                        deal_data=deal_data,
                        ingest_job_id=job_id,
                        notes=notes,
                        activities=activities,
                    )
                    artifacts.append(artifact)
                    entity_ids.append(artifact.entity_id)
                except Exception as e:
                    deal_id = deal_data.get("id", "unknown")
                    logger.warning(f"Failed to create artifact for deal {deal_id}: {e}")
                    continue

        if artifacts:
            await self.store_artifacts_batch(db_pool, artifacts)
            logger.debug(
                "Synced Pipedrive deals",
                tenant_id=tenant_id,
                count=len(artifacts),
                since=since.isoformat(),
            )

        return len(artifacts), entity_ids

    async def _sync_persons(
        self,
        client: PipedriveClient,
        db_pool: asyncpg.Pool,
        job_id: UUID,
        tenant_id: str,
        since: datetime,
    ) -> tuple[int, list[str]]:
        """Sync persons updated since the given timestamp."""
        artifacts: list[PipedrivePersonArtifact] = []
        entity_ids: list[str] = []

        for page in client.iterate_persons(updated_after=since):
            for person_data in page:
                try:
                    artifact = PipedrivePersonArtifact.from_api_response(
                        person_data=person_data,
                        ingest_job_id=job_id,
                    )
                    artifacts.append(artifact)
                    entity_ids.append(artifact.entity_id)
                except Exception as e:
                    person_id = person_data.get("id", "unknown")
                    logger.warning(f"Failed to create artifact for person {person_id}: {e}")
                    continue

        if artifacts:
            await self.store_artifacts_batch(db_pool, artifacts)
            logger.debug(
                "Synced Pipedrive persons",
                tenant_id=tenant_id,
                count=len(artifacts),
                since=since.isoformat(),
            )

        return len(artifacts), entity_ids

    async def _sync_organizations(
        self,
        client: PipedriveClient,
        db_pool: asyncpg.Pool,
        job_id: UUID,
        tenant_id: str,
        since: datetime,
    ) -> tuple[int, list[str]]:
        """Sync organizations updated since the given timestamp."""
        artifacts: list[PipedriveOrganizationArtifact] = []
        entity_ids: list[str] = []

        for page in client.iterate_organizations(updated_after=since):
            for org_data in page:
                try:
                    artifact = PipedriveOrganizationArtifact.from_api_response(
                        org_data=org_data,
                        ingest_job_id=job_id,
                    )
                    artifacts.append(artifact)
                    entity_ids.append(artifact.entity_id)
                except Exception as e:
                    org_id = org_data.get("id", "unknown")
                    logger.warning(f"Failed to create artifact for organization {org_id}: {e}")
                    continue

        if artifacts:
            await self.store_artifacts_batch(db_pool, artifacts)
            logger.debug(
                "Synced Pipedrive organizations",
                tenant_id=tenant_id,
                count=len(artifacts),
                since=since.isoformat(),
            )

        return len(artifacts), entity_ids

    async def _sync_products(
        self,
        client: PipedriveClient,
        db_pool: asyncpg.Pool,
        job_id: UUID,
        tenant_id: str,
        since: datetime,
    ) -> tuple[int, list[str]]:
        """Sync products updated since the given timestamp."""
        artifacts: list[PipedriveProductArtifact] = []
        entity_ids: list[str] = []

        for page in client.iterate_products(updated_after=since):
            for product_data in page:
                try:
                    artifact = PipedriveProductArtifact.from_api_response(
                        product_data=product_data,
                        ingest_job_id=job_id,
                    )
                    artifacts.append(artifact)
                    entity_ids.append(artifact.entity_id)
                except Exception as e:
                    product_id = product_data.get("id", "unknown")
                    logger.warning(f"Failed to create artifact for product {product_id}: {e}")
                    continue

        if artifacts:
            await self.store_artifacts_batch(db_pool, artifacts)
            logger.debug(
                "Synced Pipedrive products",
                tenant_id=tenant_id,
                count=len(artifacts),
                since=since.isoformat(),
            )

        return len(artifacts), entity_ids

    async def _trigger_indexing_for_entities(
        self,
        trigger_indexing: TriggerIndexingCallback,
        tenant_id: str,
        config: PipedriveIncrementalBackfillConfig,
        deal_entity_ids: list[str],
        person_entity_ids: list[str],
        org_entity_ids: list[str],
        product_entity_ids: list[str],
    ) -> None:
        """Trigger indexing for all synced entities."""
        # Trigger indexing for deals
        if deal_entity_ids:
            for i in range(0, len(deal_entity_ids), DEFAULT_INDEX_BATCH_SIZE):
                batch = deal_entity_ids[i : i + DEFAULT_INDEX_BATCH_SIZE]
                await trigger_indexing(
                    batch,
                    DocumentSource.PIPEDRIVE_DEAL,
                    tenant_id,
                    config.backfill_id,
                    config.suppress_notification,
                )

        # Trigger indexing for persons
        if person_entity_ids:
            for i in range(0, len(person_entity_ids), DEFAULT_INDEX_BATCH_SIZE):
                batch = person_entity_ids[i : i + DEFAULT_INDEX_BATCH_SIZE]
                await trigger_indexing(
                    batch,
                    DocumentSource.PIPEDRIVE_PERSON,
                    tenant_id,
                    config.backfill_id,
                    config.suppress_notification,
                )

        # Trigger indexing for organizations
        if org_entity_ids:
            for i in range(0, len(org_entity_ids), DEFAULT_INDEX_BATCH_SIZE):
                batch = org_entity_ids[i : i + DEFAULT_INDEX_BATCH_SIZE]
                await trigger_indexing(
                    batch,
                    DocumentSource.PIPEDRIVE_ORGANIZATION,
                    tenant_id,
                    config.backfill_id,
                    config.suppress_notification,
                )

        # Trigger indexing for products
        if product_entity_ids:
            for i in range(0, len(product_entity_ids), DEFAULT_INDEX_BATCH_SIZE):
                batch = product_entity_ids[i : i + DEFAULT_INDEX_BATCH_SIZE]
                await trigger_indexing(
                    batch,
                    DocumentSource.PIPEDRIVE_PRODUCT,
                    tenant_id,
                    config.backfill_id,
                    config.suppress_notification,
                )
