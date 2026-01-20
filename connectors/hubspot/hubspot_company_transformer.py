"""
HubSpot transformer for converting HubSpot company artifacts to documents.
"""

import logging

import asyncpg

from connectors.base import BaseTransformer
from connectors.base.doc_ids import get_hubspot_doc_id
from connectors.base.document_source import DocumentSource
from connectors.hubspot.hubspot_artifacts import HubspotCompanyArtifact
from connectors.hubspot.hubspot_company_document import HubspotCompanyDocument
from src.clients.hubspot.hubspot_client import HubSpotProperty
from src.ingest.repositories.artifact_repository import ArtifactRepository
from src.ingest.services.hubspot_custom_properties import hubspot_custom_properties
from src.utils.error_handling import ErrorCounter, record_exception_and_ignore

logger = logging.getLogger(__name__)


class HubSpotCompanyTransformer(BaseTransformer[HubspotCompanyDocument]):
    """Transformer for HubSpot company artifacts."""

    def __init__(self):
        super().__init__(DocumentSource.HUBSPOT_COMPANY)

    async def transform_artifacts(
        self, entity_ids: list[str], readonly_db_pool: asyncpg.Pool
    ) -> list[HubspotCompanyDocument]:
        """Transform HubSpot company artifacts into documents.

        Args:
            entity_ids: List of company IDs to transform
            readonly_db_pool: Database connection pool

        Returns:
            List of HubspotCompanyDocument instances
        """
        repo = ArtifactRepository(readonly_db_pool)

        # Get HubSpot company artifacts for the given entity IDs
        artifacts = await repo.get_artifacts_by_entity_ids(HubspotCompanyArtifact, entity_ids)

        logger.info(
            f"Loaded {len(artifacts)} HubSpot company artifacts for {len(entity_ids)} entity IDs"
        )

        company_custom_properties = await self._get_company_custom_properties(readonly_db_pool)
        logger.info(
            f"Loaded {len(company_custom_properties)} company custom properties for {len(entity_ids)} entity IDs"
        )

        documents = []
        counter: ErrorCounter = {}

        for artifact in artifacts:
            with record_exception_and_ignore(
                logger, f"Failed to transform HubSpot company artifact {artifact.id}", counter
            ):
                document = self._create_document(artifact, company_custom_properties)
                documents.append(document)

                if len(documents) % 100 == 0:
                    logger.info(f"Processed {len(documents)}/{len(artifacts)} companies")

        successful = counter.get("successful", 0)
        failed = counter.get("failed", 0)

        logger.info(
            f"HubSpot company transformation complete: {successful} successful, {failed} failed. "
            f"Created {len(documents)} documents from {len(artifacts)} artifacts"
        )

        return documents

    async def _get_company_custom_properties(
        self, readonly_db_pool: asyncpg.Pool
    ) -> list[HubSpotProperty]:
        async with readonly_db_pool.acquire() as conn:
            return await hubspot_custom_properties.get_by_object_type(
                object_type="company", conn=conn
            )

    def _create_document(
        self, artifact: HubspotCompanyArtifact, company_custom_properties: list[HubSpotProperty]
    ) -> HubspotCompanyDocument:
        """Create a HubspotCompanyDocument from an artifact.

        Args:
            artifact: The HubspotCompanyArtifact to transform

        Returns:
            HubspotCompanyDocument
        """
        # Generate document ID using the company ID (entity_id)
        document_id = get_hubspot_doc_id("company", artifact.entity_id)

        # The artifact content has the raw API response
        content = artifact.content

        # Extract properties if they exist in nested structure
        if "properties" in content:
            # API response has nested structure
            properties = content.get("properties", {})
            raw_data = dict(properties)

            # Add top-level fields
            raw_data["created_at"] = content.get("created_at")
            raw_data["updated_at"] = content.get("updated_at")
            raw_data["archived"] = content.get("archived", False)
        else:
            # Content is already flat (shouldn't happen based on backfill, but be defensive)
            raw_data = content

        # Add company custom property data
        raw_data["custom_properties"] = {
            property.name: property.label for property in company_custom_properties
        }

        # Merge metadata fields into raw_data
        if artifact.metadata:
            raw_data["company_id"] = artifact.metadata.get("company_id")
            raw_data["source_created_at"] = artifact.metadata.get("source_created_at")
            raw_data["source_updated_at"] = artifact.metadata.get("source_updated_at")

        document = HubspotCompanyDocument(
            id=document_id,
            raw_data=raw_data,
            source_updated_at=artifact.source_updated_at,
            permission_policy="tenant",
            permission_allowed_tokens=None,
        )

        return document
