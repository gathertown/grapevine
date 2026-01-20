import logging

import asyncpg

from connectors.base import BaseExtractor, TriggerIndexingCallback
from connectors.base.document_source import DocumentSource
from connectors.salesforce.salesforce_artifacts import SalesforceObjectArtifactType
from connectors.salesforce.salesforce_models import SalesforceBackfillConfig, SalesforceObjectBatch
from connectors.salesforce.salesforce_utils import create_salesforce_artifact
from src.clients.salesforce import SalesforceClient
from src.clients.salesforce_factory import get_salesforce_client_for_tenant
from src.clients.ssm import SSMClient
from src.utils.tenant_config import (
    increment_backfill_attempted_ingest_jobs,
    increment_backfill_done_ingest_jobs,
    increment_backfill_total_index_jobs,
)

logger = logging.getLogger(__name__)

# Batch this many entities at a time for indexing
INDEX_BATCH_SIZE = 100


class SalesforceBackfillExtractor(BaseExtractor[SalesforceBackfillConfig]):
    """
    Extracts Salesforce objects from specific batches of record IDs.
    This is a child job of SalesforceBackfillRootExtractor.
    """

    source_name = "salesforce_backfill"

    def __init__(self, ssm_client: SSMClient):
        super().__init__()
        self.ssm_client = ssm_client

    async def process_job(
        self,
        job_id: str,
        config: SalesforceBackfillConfig,
        db_pool: asyncpg.Pool,
        trigger_indexing: TriggerIndexingCallback,
    ) -> None:
        logger.info(f"Processing {len(config.object_batches)} object batches for job {job_id}")

        # Get Salesforce client for this tenant
        salesforce_client = await get_salesforce_client_for_tenant(
            config.tenant_id, self.ssm_client, db_pool
        )

        # Process all object batches
        all_artifacts = []

        for batch_idx, object_batch in enumerate(config.object_batches):
            logger.info(
                f"Processing batch {batch_idx + 1}/{len(config.object_batches)}: "
                f"{len(object_batch.record_ids)} {object_batch.object_type} records"
            )

            try:
                batch_artifacts = await self._process_object_batch(
                    job_id, salesforce_client, object_batch, db_pool
                )
                all_artifacts.extend(batch_artifacts)

            except Exception as e:
                logger.error(f"Failed to process {object_batch.object_type} batch: {e}")
                raise

        # Clean up client resources
        await salesforce_client.close()

        logger.info(
            f"Successfully processed {len(all_artifacts)} object artifacts for job {job_id}"
        )

        # Trigger indexing for all created artifacts in batches
        if all_artifacts:
            entity_ids = [artifact.entity_id for artifact in all_artifacts]
            total_batches = (len(entity_ids) + INDEX_BATCH_SIZE - 1) // INDEX_BATCH_SIZE
            logger.info(
                f"Triggering indexing for {len(entity_ids)} Salesforce entities in batches of {INDEX_BATCH_SIZE}"
            )

            # Track total index jobs upfront if backfill_id exists
            if config.backfill_id and total_batches > 0:
                await increment_backfill_total_index_jobs(
                    config.backfill_id, config.tenant_id, total_batches
                )

            for i in range(0, len(entity_ids), INDEX_BATCH_SIZE):
                batch = entity_ids[i : i + INDEX_BATCH_SIZE]
                batch_num = (i // INDEX_BATCH_SIZE) + 1

                logger.info(
                    f"Triggering indexing batch {batch_num}/{total_batches} with {len(batch)} entities"
                )
                await trigger_indexing(
                    batch,
                    DocumentSource.SALESFORCE,
                    config.tenant_id,
                    config.backfill_id,
                    config.suppress_notification,
                )

            logger.info(
                f"Successfully triggered indexing for all {len(entity_ids)} entities across {total_batches} batches"
            )

        # Track completion if backfill_id exists
        try:
            if config.backfill_id:
                await increment_backfill_done_ingest_jobs(config.backfill_id, config.tenant_id, 1)
        finally:
            # Always track that we attempted this job, regardless of success/failure
            if config.backfill_id:
                await increment_backfill_attempted_ingest_jobs(
                    config.backfill_id, config.tenant_id, 1
                )

    async def _process_object_batch(
        self,
        job_id: str,
        salesforce_client: SalesforceClient,
        object_batch: SalesforceObjectBatch,
        db_pool: asyncpg.Pool,
    ) -> list[SalesforceObjectArtifactType]:
        """Process a specific batch of records from a single object type."""
        try:
            # Fetch all record data in a single batch API call
            records_data = await salesforce_client.get_records_by_ids(
                object_batch.object_type, object_batch.record_ids
            )
        except Exception as e:
            logger.error(f"Error fetching batch of {object_batch.object_type} records: {e}")
            raise

        # Create a mapping of ID -> record_data for easy lookup
        records_by_id = {record.get("Id"): record for record in records_data if record.get("Id")}

        # Process each requested record ID
        artifacts: list[SalesforceObjectArtifactType] = []
        for record_id in object_batch.record_ids:
            try:
                record_data = records_by_id.get(record_id)
                if not record_data:
                    logger.warning(f"Could not fetch {object_batch.object_type} record {record_id}")
                    continue

                # Create artifact
                artifact = create_salesforce_artifact(job_id, object_batch.object_type, record_data)

                if artifact:
                    artifacts.append(artifact)

            except Exception as e:
                logger.error(f"Error processing {object_batch.object_type} record {record_id}: {e}")
                continue

        # Store all  artifacts in a single batch
        await self.store_artifacts_batch(db_pool, artifacts)

        logger.info(
            f"Completed processing {object_batch.object_type} batch with {len(object_batch.record_ids)} records (stored {len(artifacts)} artifacts)"
        )
        return artifacts
