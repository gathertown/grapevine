"""
Base extractor class for HubSpot-based extractors.

Provides common functionality for all HubSpot extractors including:
- Custom properties retrieval
- Object processing helpers
- Client initialization
"""

from abc import ABC
from collections.abc import Sequence
from typing import TypeVar

import asyncpg
from pydantic import BaseModel

from connectors.base import BaseExtractor, BaseIngestArtifact, TriggerIndexingCallback
from connectors.base.document_source import DocumentSource
from src.clients.hubspot.hubspot_client import HubSpotClient, HubSpotProperty
from src.clients.hubspot.hubspot_factory import get_hubspot_client_for_tenant
from src.clients.ssm import SSMClient
from src.utils.logging import get_logger

logger = get_logger(__name__)

HubSpotConfigType = TypeVar("HubSpotConfigType", bound=BaseModel)


class HubSpotExtractor(BaseExtractor[HubSpotConfigType], ABC):
    """Abstract base class for HubSpot-based extractors."""

    def __init__(self, ssm_client: SSMClient):
        """Initialize the HubSpot extractor.

        Args:
            ssm_client: SSM client for retrieving secrets and configuration
        """
        super().__init__()
        self.ssm_client = ssm_client

    async def get_hubspot_client(self, tenant_id: str, db_pool: asyncpg.Pool) -> HubSpotClient:
        """Get HubSpot client for the specified tenant.

        Args:
            tenant_id: The tenant ID
            db_pool: Database connection pool

        Returns:
            Initialized HubSpot client for the tenant
        """
        return await get_hubspot_client_for_tenant(tenant_id, self.ssm_client, db_pool)

    async def get_object_custom_properties(
        self, object_type: str, db_pool: asyncpg.Pool
    ) -> list[HubSpotProperty]:
        """Get custom properties for a specific HubSpot object type.

        Args:
            object_type: The HubSpot object type (company, deal, contact, ticket)
            db_pool: Database connection pool

        Returns:
            List of custom properties for the object type
        """
        from src.ingest.services.hubspot_custom_properties import hubspot_custom_properties

        async with db_pool.acquire() as conn:
            return await hubspot_custom_properties.get_by_object_type(
                object_type=object_type, conn=conn
            )

    async def process_and_store_artifacts(
        self,
        artifacts: Sequence[BaseIngestArtifact],
        source: DocumentSource,
        tenant_id: str,
        db_pool: asyncpg.Pool,
        trigger_indexing: TriggerIndexingCallback,
        backfill_id: str | None = None,
    ) -> None:
        """Store artifacts and trigger indexing.

        Helper method to reduce boilerplate in processing methods.

        Args:
            artifacts: Sequence of artifacts to store
            source: Document source type
            tenant_id: Tenant ID
            db_pool: Database connection pool
            trigger_indexing: Callback to trigger indexing
            backfill_id: Optional backfill job ID
        """
        if not artifacts:
            logger.info("No artifacts to process")
            return

        await self.store_artifacts_batch(db_pool, artifacts)

        entity_ids = [artifact.entity_id for artifact in artifacts]
        if backfill_id:
            await trigger_indexing(entity_ids, source, tenant_id, backfill_id)
        else:
            await trigger_indexing(entity_ids, source, tenant_id)

        logger.info(f"Processed and stored {len(artifacts)} {source.value} artifacts")
