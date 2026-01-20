"""
Salesforce object sync extractor.

Fetches objects that have been updated since the last sync timestamp.
"""

import logging
from datetime import UTC, datetime, timedelta

import asyncpg

from connectors.base import BaseExtractor, TriggerIndexingCallback
from connectors.base.document_source import DocumentSource
from connectors.salesforce.salesforce_artifacts import (
    SUPPORTED_SALESFORCE_OBJECTS,
    SalesforceObjectArtifactType,
)
from connectors.salesforce.salesforce_models import SalesforceObjectSyncConfig
from connectors.salesforce.salesforce_utils import create_salesforce_artifact
from src.clients.salesforce import SalesforceClient
from src.clients.salesforce_factory import get_salesforce_client_for_tenant
from src.clients.ssm import SSMClient
from src.ingest.services.salesforce import salesforce_object_sync_service

logger = logging.getLogger(__name__)

# Batch this many entities at a time for indexing
INDEX_BATCH_SIZE = 100


class SalesforceObjectSyncExtractor(BaseExtractor[SalesforceObjectSyncConfig]):
    """Extract and process updated Salesforce objects since last sync."""

    source_name = "salesforce_object_sync"

    def __init__(self, ssm_client: SSMClient):
        super().__init__()
        self.ssm_client = ssm_client

    async def process_job(
        self,
        job_id: str,
        config: SalesforceObjectSyncConfig,
        db_pool: asyncpg.Pool,
        trigger_indexing: TriggerIndexingCallback,
    ) -> None:
        logger.info(
            f"[tenant={config.tenant_id}] Processing Salesforce object sync "
            f"for object type {config.object_type}"
        )

        # Get last synced timestamp
        last_synced_at = await salesforce_object_sync_service.get_object_last_synced_at(
            config.object_type, db_pool
        )

        if last_synced_at:
            logger.info(f"[tenant={config.tenant_id}] Last synced at: {last_synced_at.isoformat()}")
        else:
            # If no last synced at, set to 30 minutes ago to catch recent changes
            last_synced_at = datetime.now(UTC) - timedelta(minutes=30)
            logger.info(
                f"[tenant={config.tenant_id}] No previous sync found, syncing from {last_synced_at.isoformat()}"
            )

        # Record the sync timestamp before we start (to avoid missing updates during processing)
        synced_till = datetime.now(UTC)

        # Get Salesforce client
        salesforce_client = await get_salesforce_client_for_tenant(
            config.tenant_id, self.ssm_client, db_pool
        )

        try:
            # Fetch updated objects
            artifacts = await self._fetch_updated_objects(
                salesforce_client, config.object_type, last_synced_at, job_id
            )

            if not artifacts:
                logger.info(
                    f"[tenant={config.tenant_id}] No updated {config.object_type} objects found"
                )
                # Still update the timestamp even if no objects were updated
                await salesforce_object_sync_service.set_object_last_synced_at(
                    config.object_type, synced_till, db_pool
                )
                return

            logger.info(f"[tenant={config.tenant_id}] Found {len(artifacts)} updated objects")

            # Store artifacts
            await self.store_artifacts_batch(db_pool, artifacts)

            # Trigger indexing for all created artifacts in batches
            entity_ids = [artifact.entity_id for artifact in artifacts]
            for i in range(0, len(entity_ids), INDEX_BATCH_SIZE):
                batch = entity_ids[i : i + INDEX_BATCH_SIZE]
                await trigger_indexing(
                    batch,
                    DocumentSource.SALESFORCE,
                    config.tenant_id,
                    config.backfill_id,
                )

            # Update last synced timestamp
            await salesforce_object_sync_service.set_object_last_synced_at(
                config.object_type, synced_till, db_pool
            )

            logger.info(
                f"[tenant={config.tenant_id}] Successfully processed {len(artifacts)} "
                f"{config.object_type} objects, updated sync timestamp to {synced_till.isoformat()}"
            )

        finally:
            # Always close the client
            await salesforce_client.close()

    async def _fetch_updated_objects(
        self,
        salesforce_client: SalesforceClient,
        object_type: SUPPORTED_SALESFORCE_OBJECTS,
        last_synced_at: datetime,
        job_id: str,
    ) -> list[SalesforceObjectArtifactType]:
        """Fetch and process objects updated since the last sync."""
        # Format timestamp for Salesforce SOQL query (ISO 8601 format)
        # Example: 2024-10-30T14:30:00Z
        last_modified_date = last_synced_at.strftime("%Y-%m-%dT%H:%M:%SZ")

        logger.info(f"Fetching {object_type} objects updated since {last_modified_date}")

        # Get IDs of updated objects
        try:
            updated_ids = await salesforce_client.get_updated_object_ids(
                object_type,
                last_modified_date,
            )
        except Exception as e:
            logger.error(f"Error fetching updated {object_type} IDs: {e}")
            raise

        if not updated_ids:
            return []

        logger.info(f"Found {len(updated_ids)} updated {object_type} records")

        # Fetch full record data for updated objects
        try:
            records_data = await salesforce_client.get_records_by_ids(
                object_type,
                updated_ids,
            )
        except Exception as e:
            logger.error(f"Error fetching {object_type} records data: {e}")
            raise

        # Create artifacts from records
        artifacts: list[SalesforceObjectArtifactType] = []
        for record_data in records_data:
            try:
                artifact = create_salesforce_artifact(job_id, object_type, record_data)
                if artifact:
                    artifacts.append(artifact)
            except Exception as e:
                record_id = record_data.get("Id", "unknown")
                logger.error(f"Error creating artifact for {object_type} record {record_id}: {e}")
                continue

        return artifacts
