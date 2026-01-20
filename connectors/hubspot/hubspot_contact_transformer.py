"""
HubSpot transformer for converting HubSpot contact artifacts to documents.
"""

import logging

import asyncpg

from connectors.base import BaseTransformer
from connectors.base.doc_ids import get_hubspot_doc_id
from connectors.base.document_source import DocumentSource
from connectors.hubspot.hubspot_artifacts import HubspotContactArtifact
from connectors.hubspot.hubspot_contact_document import HubspotContactDocument
from src.clients.hubspot.hubspot_client import HubSpotProperty
from src.ingest.repositories.artifact_repository import ArtifactRepository
from src.ingest.services.hubspot_custom_properties import hubspot_custom_properties
from src.utils.error_handling import ErrorCounter, record_exception_and_ignore

logger = logging.getLogger(__name__)


class HubSpotContactTransformer(BaseTransformer[HubspotContactDocument]):
    """Transformer for HubSpot contact artifacts."""

    def __init__(self):
        super().__init__(DocumentSource.HUBSPOT_CONTACT)

    async def transform_artifacts(
        self, entity_ids: list[str], readonly_db_pool: asyncpg.Pool
    ) -> list[HubspotContactDocument]:
        """Transform HubSpot contact artifacts into documents.

        Args:
            entity_ids: List of contact IDs to transform
            readonly_db_pool: Database connection pool

        Returns:
            List of HubspotContactDocument instances
        """
        repo = ArtifactRepository(readonly_db_pool)

        # Get HubSpot contact artifacts for the given entity IDs
        artifacts = await repo.get_artifacts_by_entity_ids(HubspotContactArtifact, entity_ids)

        logger.info(
            f"Loaded {len(artifacts)} HubSpot contact artifacts for {len(entity_ids)} entity IDs"
        )

        contact_custom_properties = await self._get_contact_custom_properties(readonly_db_pool)

        logger.info(
            f"Loaded {len(contact_custom_properties)} contact custom properties for {len(entity_ids)} entity IDs"
        )

        documents = []
        counter: ErrorCounter = {}

        for artifact in artifacts:
            with record_exception_and_ignore(
                logger, f"Failed to transform HubSpot contact artifact {artifact.id}", counter
            ):
                document = self._create_document(artifact, contact_custom_properties)
                documents.append(document)

                if len(documents) % 100 == 0:
                    logger.info(f"Processed {len(documents)}/{len(artifacts)} hubspot contacts")

        successful = counter.get("successful", 0)
        failed = counter.get("failed", 0)

        logger.info(
            f"HubSpot transformation complete: {successful} successful, {failed} failed. "
            f"Created {len(documents)} documents from {len(artifacts)} artifacts"
        )

        return documents

    async def _get_contact_custom_properties(
        self, readonly_db_pool: asyncpg.Pool
    ) -> list[HubSpotProperty]:
        async with readonly_db_pool.acquire() as conn:
            return await hubspot_custom_properties.get_by_object_type(
                object_type="contact", conn=conn
            )

    def _create_document(
        self, artifact: HubspotContactArtifact, contact_custom_properties: list[HubSpotProperty]
    ) -> HubspotContactDocument:
        """Create a HubspotContactDocument from an artifact.

        Args:
            artifact: The HubspotContactArtifact to transform

        Returns:
            HubspotContactDocument
        """
        # The artifact content already has all the fields we need
        # Just pass them directly to the document

        # Generate document ID using the contact ID (entity_id)
        document_id = get_hubspot_doc_id("contact", artifact.entity_id)

        # Extract properties from the new nested structure
        # artifact.content now has: {id, properties, createdAt, updatedAt, archived, ...}
        content = artifact.content
        properties = content.get("properties", {})

        # Build raw_data with properties plus our additions
        raw_data = dict(properties)  # Start with HubSpot properties

        # Add contact custom property data
        raw_data["custom_properties"] = {
            property.name: property.label for property in contact_custom_properties
        }

        # Add top-level fields
        raw_data["created_at"] = content.get("createdAt")
        raw_data["updated_at"] = content.get("updatedAt")
        raw_data["archived"] = content.get("archived", False)

        # Add our resolved names (stored at top level in content)
        raw_data["company_names"] = content.get("company_names")

        # Add IDs from metadata (always present in artifact)
        raw_data["company_ids"] = artifact.metadata["company_ids"]  # Always a list
        raw_data["source_created_at"] = artifact.metadata.get("source_created_at")
        raw_data["source_updated_at"] = artifact.metadata.get("source_updated_at")

        document = HubspotContactDocument(
            id=document_id,
            raw_data=raw_data,
            source_updated_at=artifact.source_updated_at,
            permission_policy="tenant",
            permission_allowed_tokens=None,
        )

        return document
