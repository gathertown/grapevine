import logging

import asyncpg
from pydantic import BaseModel

from connectors.base import BaseExtractor, TriggerIndexingCallback
from connectors.base.document_source import DocumentSource
from connectors.salesforce.salesforce_artifacts import (
    SUPPORTED_SALESFORCE_OBJECTS,
    SalesforceObjectArtifactType,
)
from connectors.salesforce.salesforce_models import SalesforceCDCEvent
from connectors.salesforce.salesforce_pruner import salesforce_pruner
from connectors.salesforce.salesforce_utils import create_salesforce_artifact
from src.clients.salesforce import SalesforceClient
from src.clients.salesforce_factory import get_salesforce_client_for_tenant
from src.clients.ssm import SSMClient

logger = logging.getLogger(__name__)


class SalesforceCDCWebhookBody(BaseModel):
    """Strictly typed body for Salesforce CDC webhook."""

    events: list[SalesforceCDCEvent]


class SalesforceCDCWebhookConfig(BaseModel):
    """Config for Salesforce CDC webhook processing."""

    body: SalesforceCDCWebhookBody
    tenant_id: str


class SalesforceCDCExtractor(BaseExtractor[SalesforceCDCWebhookConfig]):
    """
    Extracts and processes Salesforce Change Data Capture events.
    Handles real-time changes to Salesforce objects from CDC streams.
    """

    source_name = "salesforce_cdc"

    def __init__(self, ssm_client: SSMClient):
        super().__init__()
        self.ssm_client = ssm_client

    async def process_job(
        self,
        job_id: str,
        config: SalesforceCDCWebhookConfig,
        db_pool: asyncpg.Pool,
        trigger_indexing: TriggerIndexingCallback,
    ) -> None:
        logger.info(f"Processing {len(config.body.events)} CDC events for job {job_id}")

        # Get Salesforce client for this tenant
        salesforce_client = await get_salesforce_client_for_tenant(
            config.tenant_id, self.ssm_client, db_pool
        )

        try:
            # Process all CDC events
            all_artifacts = []
            entity_ids_to_index = []

            for event in config.body.events:
                try:
                    artifacts = await self._process_cdc_event(
                        job_id, salesforce_client, event, db_pool, config.tenant_id
                    )
                    all_artifacts.extend(artifacts)

                    # Collect entity IDs for indexing
                    for artifact in artifacts:
                        entity_ids_to_index.append(artifact.entity_id)

                except Exception as e:
                    logger.error(f"Failed to process CDC event for {event.record_id}: {e}")
                    # Continue processing other events
                    continue

            # Store all artifacts in batch
            if all_artifacts:
                await self.store_artifacts_batch(db_pool, all_artifacts)

            # Trigger indexing for all processed entities
            if entity_ids_to_index:
                await trigger_indexing(
                    entity_ids_to_index, DocumentSource.SALESFORCE, config.tenant_id
                )

            logger.info(
                f"Successfully processed {len(config.body.events)} CDC events, "
                f"created {len(all_artifacts)} artifacts for job {job_id}"
            )

        finally:
            # Clean up client resources
            await salesforce_client.close()

    async def _process_cdc_event(
        self,
        job_id: str,
        salesforce_client: SalesforceClient,
        event: SalesforceCDCEvent,
        db_pool: asyncpg.Pool,
        tenant_id: str,
    ) -> list[SalesforceObjectArtifactType]:
        """Process a single CDC event."""

        # For DELETE operations, we need to remove everything associated with this record
        if event.operation_type == "DELETE":
            await salesforce_pruner.delete_record(
                record_id=event.record_id,
                object_type=event.object_type,
                tenant_id=tenant_id,
                db_pool=db_pool,
            )
            return []

        # For INSERT, UPDATE, UNDELETE operations, we need the full record
        record_data = await self._fetch_complete_record(
            salesforce_client, event.object_type, event.record_id
        )

        if not record_data:
            logger.warning(
                f"Could not fetch complete record for {event.object_type} {event.record_id}"
            )
            return []

        # Create artifact from the complete record
        artifact = create_salesforce_artifact(job_id, event.object_type, record_data)

        return [artifact] if artifact else []

    async def _fetch_complete_record(
        self,
        salesforce_client: SalesforceClient,
        object_type: SUPPORTED_SALESFORCE_OBJECTS,
        record_id: str,
    ) -> dict | None:
        """Fetch complete record data from Salesforce API."""
        # Fetch single record by ID
        records = await salesforce_client.get_records_by_ids(object_type, [record_id])

        if records:
            return records[0]
        return None
