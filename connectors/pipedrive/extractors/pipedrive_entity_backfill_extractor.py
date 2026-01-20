"""Entity-specific backfill extractor for Pipedrive.

Handles backfilling individual entity types (deals, persons, organizations)
by processing batches of record IDs passed from the root extractor.
"""

import math
from uuid import UUID

import asyncpg

from connectors.base import BaseExtractor, TriggerIndexingCallback
from connectors.base.document_source import DocumentSource
from connectors.pipedrive.pipedrive_artifacts import (
    PipedriveDealArtifact,
    PipedriveEntityType,
    PipedriveOrganizationArtifact,
    PipedrivePersonArtifact,
    PipedriveProductArtifact,
)
from connectors.pipedrive.pipedrive_client import (
    PipedriveClient,
    get_pipedrive_client_for_tenant,
)
from connectors.pipedrive.pipedrive_models import PipedriveBackfillEntityConfig
from src.clients.sqs import SQSClient
from src.clients.ssm import SSMClient
from src.ingest.utils import DEFAULT_INDEX_BATCH_SIZE
from src.utils.logging import get_logger
from src.utils.tenant_config import (
    increment_backfill_attempted_ingest_jobs,
    increment_backfill_done_ingest_jobs,
    increment_backfill_total_index_jobs,
)

logger = get_logger(__name__)


class PipedriveEntityBackfillExtractor(BaseExtractor[PipedriveBackfillEntityConfig]):
    """Extracts and stores Pipedrive entities during full backfill.

    Each job processes a batch of record IDs for a specific entity type.
    """

    source_name = "pipedrive_entity_backfill"

    def __init__(self, ssm_client: SSMClient, sqs_client: SQSClient):
        super().__init__()
        self.ssm_client = ssm_client
        self.sqs_client = sqs_client

    async def process_job(
        self,
        job_id: str,
        config: PipedriveBackfillEntityConfig,
        db_pool: asyncpg.Pool,
        trigger_indexing: TriggerIndexingCallback,
    ) -> None:
        """Execute the entity backfill job.

        Args:
            job_id: Unique job identifier
            config: Entity backfill configuration including entity_type and record_ids
            db_pool: Database connection pool
            trigger_indexing: Callback to trigger indexing
        """
        tenant_id = config.tenant_id
        entity_type = config.entity_type
        record_ids = list(config.record_ids)
        backfill_id = config.backfill_id

        logger.info(
            f"Starting Pipedrive {entity_type} backfill",
            tenant_id=tenant_id,
            record_count=len(record_ids),
            backfill_id=backfill_id,
        )

        try:
            await self._process_batch(
                job_id=job_id,
                db_pool=db_pool,
                trigger_indexing=trigger_indexing,
                config=config,
            )
        except Exception as e:
            logger.error(f"Failed to process Pipedrive {entity_type} batch: {e}", exc_info=True)
            raise
        finally:
            # Always track that we attempted this job, regardless of success/failure
            if backfill_id:
                await increment_backfill_attempted_ingest_jobs(backfill_id, tenant_id, 1)

    async def _process_batch(
        self,
        job_id: str,
        db_pool: asyncpg.Pool,
        trigger_indexing: TriggerIndexingCallback,
        config: PipedriveBackfillEntityConfig,
    ) -> None:
        """Process a batch of Pipedrive entities."""
        tenant_id = config.tenant_id
        entity_type = config.entity_type
        record_ids = list(config.record_ids)
        backfill_id = config.backfill_id

        # Initialize client
        client = await get_pipedrive_client_for_tenant(tenant_id, self.ssm_client)

        # Route to appropriate entity handler
        entity_ids: list[str] = []
        artifacts_count = 0

        if entity_type == PipedriveEntityType.DEAL.value:
            deal_artifacts, entity_ids = await self._process_deals(client, record_ids, UUID(job_id))
            document_source = DocumentSource.PIPEDRIVE_DEAL
            if deal_artifacts:
                artifacts_count = len(deal_artifacts)
                await self.store_artifacts_batch(db_pool, deal_artifacts)
        elif entity_type == PipedriveEntityType.PERSON.value:
            person_artifacts, entity_ids = await self._process_persons(
                client, record_ids, UUID(job_id)
            )
            document_source = DocumentSource.PIPEDRIVE_PERSON
            if person_artifacts:
                artifacts_count = len(person_artifacts)
                await self.store_artifacts_batch(db_pool, person_artifacts)
        elif entity_type == PipedriveEntityType.ORGANIZATION.value:
            org_artifacts, entity_ids = await self._process_organizations(
                client, record_ids, UUID(job_id)
            )
            document_source = DocumentSource.PIPEDRIVE_ORGANIZATION
            if org_artifacts:
                artifacts_count = len(org_artifacts)
                await self.store_artifacts_batch(db_pool, org_artifacts)
        elif entity_type == PipedriveEntityType.PRODUCT.value:
            product_artifacts, entity_ids = await self._process_products(
                client, record_ids, UUID(job_id)
            )
            document_source = DocumentSource.PIPEDRIVE_PRODUCT
            if product_artifacts:
                artifacts_count = len(product_artifacts)
                await self.store_artifacts_batch(db_pool, product_artifacts)
        else:
            logger.error(f"Unknown Pipedrive entity type: {entity_type}")
            return

        if artifacts_count == 0:
            logger.warning(
                f"No Pipedrive {entity_type} artifacts created",
                backfill_id=backfill_id,
            )
            # Still need to track progress even for empty batches
            if backfill_id:
                await increment_backfill_done_ingest_jobs(backfill_id, tenant_id, 1)
            return

        logger.info(f"Stored {artifacts_count} Pipedrive {entity_type} artifacts")

        # Trigger indexing
        if entity_ids:
            logger.info(f"Triggering indexing for {len(entity_ids)} Pipedrive {entity_type}s")

            # Calculate total number of index batches and track them upfront
            total_index_batches = math.ceil(len(entity_ids) / DEFAULT_INDEX_BATCH_SIZE)
            if backfill_id and total_index_batches > 0:
                await increment_backfill_total_index_jobs(
                    backfill_id, tenant_id, total_index_batches
                )

            for i in range(0, len(entity_ids), DEFAULT_INDEX_BATCH_SIZE):
                batch = entity_ids[i : i + DEFAULT_INDEX_BATCH_SIZE]
                await trigger_indexing(
                    batch,
                    document_source,
                    tenant_id,
                    backfill_id,
                    config.suppress_notification,
                )

        logger.info(
            f"Completed Pipedrive {entity_type} batch: {artifacts_count} processed",
            tenant_id=tenant_id,
            backfill_id=backfill_id,
            records_processed=artifacts_count,
            records_failed=len(record_ids) - artifacts_count,
        )

        if backfill_id:
            await increment_backfill_done_ingest_jobs(backfill_id, tenant_id, 1)

    async def _process_deals(
        self,
        client: PipedriveClient,
        record_ids: list[int],
        job_id: UUID,
    ) -> tuple[list[PipedriveDealArtifact], list[str]]:
        """Process deal records."""
        artifacts: list[PipedriveDealArtifact] = []
        entity_ids: list[str] = []

        for deal_id in record_ids:
            try:
                deal_data = client.get_deal(deal_id)
                if not deal_data:
                    continue

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
                logger.warning(f"Failed to process deal {deal_id}: {e}")
                continue

        return artifacts, entity_ids

    async def _process_persons(
        self,
        client: PipedriveClient,
        record_ids: list[int],
        job_id: UUID,
    ) -> tuple[list[PipedrivePersonArtifact], list[str]]:
        """Process person records."""
        artifacts: list[PipedrivePersonArtifact] = []
        entity_ids: list[str] = []

        for person_id in record_ids:
            try:
                person_data = client.get_person(person_id)
                if not person_data:
                    continue

                artifact = PipedrivePersonArtifact.from_api_response(
                    person_data=person_data,
                    ingest_job_id=job_id,
                )
                artifacts.append(artifact)
                entity_ids.append(artifact.entity_id)

            except Exception as e:
                logger.warning(f"Failed to process person {person_id}: {e}")
                continue

        return artifacts, entity_ids

    async def _process_organizations(
        self,
        client: PipedriveClient,
        record_ids: list[int],
        job_id: UUID,
    ) -> tuple[list[PipedriveOrganizationArtifact], list[str]]:
        """Process organization records."""
        artifacts: list[PipedriveOrganizationArtifact] = []
        entity_ids: list[str] = []

        for org_id in record_ids:
            try:
                org_data = client.get_organization(org_id)
                if not org_data:
                    continue

                artifact = PipedriveOrganizationArtifact.from_api_response(
                    org_data=org_data,
                    ingest_job_id=job_id,
                )
                artifacts.append(artifact)
                entity_ids.append(artifact.entity_id)

            except Exception as e:
                logger.warning(f"Failed to process organization {org_id}: {e}")
                continue

        return artifacts, entity_ids

    async def _process_products(
        self,
        client: PipedriveClient,
        record_ids: list[int],
        job_id: UUID,
    ) -> tuple[list[PipedriveProductArtifact], list[str]]:
        """Process product records."""
        artifacts: list[PipedriveProductArtifact] = []
        entity_ids: list[str] = []

        for product_id in record_ids:
            try:
                product_data = client.get_product(product_id)
                if not product_data:
                    continue

                artifact = PipedriveProductArtifact.from_api_response(
                    product_data=product_data,
                    ingest_job_id=job_id,
                )
                artifacts.append(artifact)
                entity_ids.append(artifact.entity_id)

            except Exception as e:
                logger.warning(f"Failed to process product {product_id}: {e}")
                continue

        return artifacts, entity_ids
