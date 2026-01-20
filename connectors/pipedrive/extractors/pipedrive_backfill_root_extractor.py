"""Root extractor for Pipedrive full backfill.

Orchestrates the full backfill by:
1. Setting incremental sync cursors to "now"
2. Syncing reference data (users, person labels)
3. Collecting all record IDs for each entity type
4. Enqueuing entity-specific backfill jobs for batch processing

Following the batch multi-job pattern from Attio connector.
"""

import json
import secrets
from datetime import UTC, datetime
from uuid import UUID

import asyncpg

from connectors.base import BaseExtractor, TriggerIndexingCallback
from connectors.pipedrive.pipedrive_artifacts import (
    PipedriveEntityType,
    PipedriveUserArtifact,
)
from connectors.pipedrive.pipedrive_client import (
    PipedriveClient,
    get_pipedrive_client_for_tenant,
)
from connectors.pipedrive.pipedrive_models import (
    PIPEDRIVE_PERSON_LABELS_KEY,
    PipedriveBackfillEntityConfig,
    PipedriveBackfillRootConfig,
)
from connectors.pipedrive.pipedrive_sync_service import PipedriveSyncService
from src.clients.sqs import SQSClient
from src.clients.ssm import SSMClient
from src.ingest.repositories.artifact_repository import ArtifactRepository
from src.utils.logging import get_logger
from src.utils.tenant_config import increment_backfill_total_ingest_jobs, set_config_value_with_pool

logger = get_logger(__name__)

# Batch size (records) per child job
BATCH_SIZE = 100


class PipedriveBackfillRootExtractor(BaseExtractor[PipedriveBackfillRootConfig]):
    """Root extractor that collects all record IDs and splits into batch jobs.

    This extractor:
    1. Sets incremental sync cursors to "now" (so incremental picks up changes during backfill)
    2. Syncs reference data (users) for name hydration
    3. Collects all record IDs for deals, persons, organizations
    4. Splits them into batches and enqueues child jobs
    """

    source_name = "pipedrive_backfill_root"

    def __init__(self, ssm_client: SSMClient, sqs_client: SQSClient):
        super().__init__()
        self.ssm_client = ssm_client
        self.sqs_client = sqs_client

    async def process_job(
        self,
        job_id: str,
        config: PipedriveBackfillRootConfig,
        db_pool: asyncpg.Pool,
        trigger_indexing: TriggerIndexingCallback,
    ) -> None:
        backfill_id = config.backfill_id or secrets.token_hex(8)
        tenant_id = config.tenant_id

        logger.info(
            "Starting Pipedrive backfill root job",
            backfill_id=backfill_id,
            tenant_id=tenant_id,
        )

        try:
            client = await get_pipedrive_client_for_tenant(tenant_id, self.ssm_client)
        except Exception as e:
            logger.error(f"Failed to get Pipedrive client: {e}")
            raise

        # Initialize services
        sync_service = PipedriveSyncService(db_pool, tenant_id)
        artifact_repo = ArtifactRepository(db_pool)

        # Step 1: Set incremental sync cursors to "now"
        # This ensures incremental backfill picks up any changes that occur
        # during the (potentially long-running) full backfill
        sync_start_time = datetime.now(UTC)
        await sync_service.set_deals_synced_until(sync_start_time)
        await sync_service.set_persons_synced_until(sync_start_time)
        await sync_service.set_orgs_synced_until(sync_start_time)
        await sync_service.set_products_synced_until(sync_start_time)

        logger.info(
            "Set incremental sync cursors",
            tenant_id=tenant_id,
            sync_start_time=sync_start_time.isoformat(),
        )

        # Step 2: Sync reference data (users, labels) for name hydration
        await _sync_users(client, artifact_repo, UUID(job_id), tenant_id)
        await _sync_person_labels(client, db_pool, tenant_id)

        # Step 3: Collect all record IDs for each entity type
        deal_ids = self._collect_record_ids(client, PipedriveEntityType.DEAL)
        person_ids = self._collect_record_ids(client, PipedriveEntityType.PERSON)
        org_ids = self._collect_record_ids(client, PipedriveEntityType.ORGANIZATION)
        product_ids = self._collect_record_ids(client, PipedriveEntityType.PRODUCT)

        logger.info(
            "Collected all Pipedrive record IDs",
            backfill_id=backfill_id,
            deals=len(deal_ids),
            persons=len(person_ids),
            organizations=len(org_ids),
            products=len(product_ids),
        )

        # Step 4: Create batches for each entity type
        deal_batches = self._create_batches(deal_ids)
        person_batches = self._create_batches(person_ids)
        org_batches = self._create_batches(org_ids)
        product_batches = self._create_batches(product_ids)

        # Step 5: Schedule all batch jobs with burst + rate-limited scheduling
        all_batches: list[tuple[PipedriveEntityType, list[int]]] = []
        for batch in deal_batches:
            all_batches.append((PipedriveEntityType.DEAL, batch))
        for batch in person_batches:
            all_batches.append((PipedriveEntityType.PERSON, batch))
        for batch in org_batches:
            all_batches.append((PipedriveEntityType.ORGANIZATION, batch))
        for batch in product_batches:
            all_batches.append((PipedriveEntityType.PRODUCT, batch))

        # Track total jobs for backfill progress tracking
        total_jobs = len(all_batches)
        await increment_backfill_total_ingest_jobs(backfill_id, tenant_id, total_jobs)

        # Schedule all batch jobs
        for entity_type, record_ids in all_batches:
            entity_config = PipedriveBackfillEntityConfig(
                tenant_id=tenant_id,
                entity_type=entity_type.value,
                record_ids=tuple(record_ids),
                backfill_id=backfill_id,
            )

            await self.sqs_client.send_backfill_ingest_message(entity_config)

        logger.info(
            "Pipedrive root backfill complete - batch jobs enqueued",
            tenant_id=tenant_id,
            backfill_id=backfill_id,
            total_batches=total_jobs,
            deal_batches=len(deal_batches),
            person_batches=len(person_batches),
            org_batches=len(org_batches),
            product_batches=len(product_batches),
        )

    def _collect_record_ids(
        self, client: PipedriveClient, entity_type: PipedriveEntityType
    ) -> list[int]:
        """Collect all record IDs for an entity type."""
        record_ids: list[int] = []

        if entity_type == PipedriveEntityType.DEAL:
            for page in client.iterate_deals():
                for deal in page:
                    if deal.get("id"):
                        record_ids.append(deal["id"])
        elif entity_type == PipedriveEntityType.PERSON:
            for page in client.iterate_persons():
                for person in page:
                    if person.get("id"):
                        record_ids.append(person["id"])
        elif entity_type == PipedriveEntityType.ORGANIZATION:
            for page in client.iterate_organizations():
                for org in page:
                    if org.get("id"):
                        record_ids.append(org["id"])
        elif entity_type == PipedriveEntityType.PRODUCT:
            for page in client.iterate_products():
                for product in page:
                    if product.get("id"):
                        record_ids.append(product["id"])

        return record_ids

    def _create_batches(self, record_ids: list[int]) -> list[list[int]]:
        """Split record IDs into batches."""
        batches = []
        for i in range(0, len(record_ids), BATCH_SIZE):
            batches.append(record_ids[i : i + BATCH_SIZE])
        return batches


async def _sync_users(
    client: PipedriveClient,
    artifact_repo: ArtifactRepository,
    job_id: UUID,
    tenant_id: str,
) -> None:
    """Sync all Pipedrive users as reference data.

    Users are stored as artifacts for hydrating documents with names.
    """
    logger.info("Syncing Pipedrive users", tenant_id=tenant_id)

    users = client.get_users()
    user_count = 0

    for user_data in users:
        artifact = PipedriveUserArtifact.from_api_response(
            user_data=user_data,
            ingest_job_id=job_id,
        )
        await artifact_repo.upsert_artifact(artifact)
        user_count += 1

    logger.info(
        "Synced Pipedrive users",
        tenant_id=tenant_id,
        user_count=user_count,
    )


async def _sync_person_labels(
    client: PipedriveClient,
    db_pool: asyncpg.Pool,
    tenant_id: str,
) -> None:
    """Sync person label definitions and store in tenant config.

    Labels are stored as JSON mapping of ID to name for use during transformation.
    """
    logger.info("Syncing Pipedrive person labels", tenant_id=tenant_id)

    label_map = client.get_person_label_map()

    if label_map:
        # Store as JSON string in tenant config
        await set_config_value_with_pool(
            PIPEDRIVE_PERSON_LABELS_KEY,
            json.dumps(label_map),
            db_pool,
        )
        logger.info(
            "Synced Pipedrive person labels",
            tenant_id=tenant_id,
            label_count=len(label_map),
        )
    else:
        logger.info("No Pipedrive person labels found", tenant_id=tenant_id)
