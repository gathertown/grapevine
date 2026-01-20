"""
HubSpot transformer for converting HubSpot ticket artifacts to documents.
"""

import logging

import asyncpg

from connectors.base import BaseTransformer
from connectors.base.doc_ids import get_hubspot_doc_id
from connectors.base.document_source import DocumentSource
from connectors.hubspot.hubspot_artifacts import HubspotTicketArtifact
from connectors.hubspot.hubspot_ticket_document import HubspotTicketDocument
from src.clients.hubspot.hubspot_client import HubSpotProperty
from src.ingest.repositories.artifact_repository import ArtifactRepository
from src.ingest.services.hubspot_custom_properties import hubspot_custom_properties
from src.utils.error_handling import ErrorCounter, record_exception_and_ignore

logger = logging.getLogger(__name__)


class HubSpotTicketTransformer(BaseTransformer[HubspotTicketDocument]):
    """Transformer for HubSpot ticket artifacts."""

    def __init__(self):
        super().__init__(DocumentSource.HUBSPOT_TICKET)

    async def transform_artifacts(
        self, entity_ids: list[str], readonly_db_pool: asyncpg.Pool
    ) -> list[HubspotTicketDocument]:
        """Transform HubSpot ticket artifacts into documents.

        Args:
            entity_ids: List of ticket IDs to transform
            readonly_db_pool: Database connection pool

        Returns:
            List of HubspotTicketDocument instances
        """
        repo = ArtifactRepository(readonly_db_pool)

        # Get HubSpot ticket artifacts for the given entity IDs
        artifacts = await repo.get_artifacts_by_entity_ids(HubspotTicketArtifact, entity_ids)

        logger.info(
            f"Loaded {len(artifacts)} HubSpot ticket artifacts for {len(entity_ids)} entity IDs"
        )

        ticket_custom_properties = await self._get_ticket_custom_properties(readonly_db_pool)

        logger.info(
            f"Loaded {len(ticket_custom_properties)} ticket custom properties for {len(entity_ids)} entity IDs"
        )

        documents = []
        counter: ErrorCounter = {}

        for artifact in artifacts:
            with record_exception_and_ignore(
                logger, f"Failed to transform HubSpot ticket artifact {artifact.id}", counter
            ):
                document = self._create_document(artifact, ticket_custom_properties)
                documents.append(document)

                if len(documents) % 100 == 0:
                    logger.info(f"Processed {len(documents)}/{len(artifacts)} hubspot tickets")

        successful = counter.get("successful", 0)
        failed = counter.get("failed", 0)

        logger.info(
            f"HubSpot transformation complete: {successful} successful, {failed} failed. "
            f"Created {len(documents)} documents from {len(artifacts)} artifacts"
        )

        return documents

    async def _get_ticket_custom_properties(
        self, readonly_db_pool: asyncpg.Pool
    ) -> list[HubSpotProperty]:
        async with readonly_db_pool.acquire() as conn:
            return await hubspot_custom_properties.get_by_object_type(
                object_type="ticket", conn=conn
            )

    def _create_document(
        self, artifact: HubspotTicketArtifact, ticket_custom_properties: list[HubSpotProperty]
    ) -> HubspotTicketDocument:
        """Create a HubspotTicketDocument from an artifact.

        Args:
            artifact: The HubspotTicketArtifact to transform

        Returns:
            HubspotTicketDocument
        """
        # The artifact content already has all the fields we need
        # Just pass them directly to the document

        # Generate document ID using the ticket ID (entity_id)
        document_id = get_hubspot_doc_id("ticket", artifact.entity_id)

        # Extract properties from the new nested structure
        # artifact.content now has: {id, properties, createdAt, updatedAt, archived, ...}
        content = artifact.content
        properties = content.get("properties", {})

        # Build raw_data with properties plus our additions
        raw_data = dict(properties)  # Start with HubSpot properties

        # Add ticket custom property data
        raw_data["custom_properties"] = {
            property.name: property.label for property in ticket_custom_properties
        }

        # Add top-level fields
        raw_data["created_at"] = content.get("createdAt")
        raw_data["updated_at"] = content.get("updatedAt")
        raw_data["archived"] = content.get("archived", False)

        # Add our resolved names (stored at top level in content)
        raw_data["pipeline_name"] = content.get("pipeline_name")
        raw_data["stage_name"] = content.get("stage_name")
        raw_data["company_names"] = content.get("company_names")

        # Add IDs from metadata (always present in artifact)
        raw_data["pipeline_id"] = artifact.metadata["pipeline_id"]  # Might be None
        raw_data["stage_id"] = artifact.metadata["stage_id"]  # Might be None
        raw_data["company_ids"] = artifact.metadata["company_ids"]  # Always a list
        raw_data["source_created_at"] = artifact.metadata.get("source_created_at")
        raw_data["source_updated_at"] = artifact.metadata.get("source_updated_at")

        document = HubspotTicketDocument(
            id=document_id,
            raw_data=raw_data,
            source_updated_at=artifact.source_updated_at,
            permission_policy="tenant",
            permission_allowed_tokens=None,
        )

        return document
