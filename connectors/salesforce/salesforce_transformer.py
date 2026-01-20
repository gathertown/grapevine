import logging

import asyncpg

from connectors.base import BaseTransformer
from connectors.base.doc_ids import get_salesforce_doc_id
from connectors.base.document_source import DocumentSource
from connectors.salesforce.salesforce_account_document import SalesforceAccountDocument
from connectors.salesforce.salesforce_artifacts import (
    SALESFORCE_ARTIFACT_MAPPING,
    SUPPORTED_SALESFORCE_OBJECTS,
    SalesforceObjectArtifactType,
)
from connectors.salesforce.salesforce_case_document import SalesforceCaseDocument
from connectors.salesforce.salesforce_contact_document import SalesforceContactDocument
from connectors.salesforce.salesforce_lead_document import SalesforceLeadDocument
from connectors.salesforce.salesforce_opportunity_document import SalesforceOpportunityDocument
from src.ingest.repositories.artifact_repository import ArtifactRepository
from src.utils.error_handling import ErrorCounter, record_exception_and_ignore

# Type union for all Salesforce document types
type SalesforceDocumentType = (
    SalesforceAccountDocument
    | SalesforceContactDocument
    | SalesforceOpportunityDocument
    | SalesforceLeadDocument
    | SalesforceCaseDocument
)

logger = logging.getLogger(__name__)

DOCUMENT_MAPPING: dict[SUPPORTED_SALESFORCE_OBJECTS, type[SalesforceDocumentType]] = {
    "Account": SalesforceAccountDocument,
    "Contact": SalesforceContactDocument,
    "Opportunity": SalesforceOpportunityDocument,
    "Lead": SalesforceLeadDocument,
    "Case": SalesforceCaseDocument,
}


class SalesforceTransformer(BaseTransformer[SalesforceDocumentType]):
    def __init__(self):
        super().__init__(DocumentSource.SALESFORCE)

    async def transform_artifacts(
        self, entity_ids: list[str], readonly_db_pool: asyncpg.Pool
    ) -> list[SalesforceDocumentType]:
        repo = ArtifactRepository(readonly_db_pool)

        # Get all Salesforce artifacts for the given entity IDs
        all_artifacts = []
        for artifact_class in SALESFORCE_ARTIFACT_MAPPING.values():
            artifacts = await repo.get_artifacts_by_entity_ids(artifact_class, entity_ids)
            all_artifacts.extend(artifacts)

        logger.info(
            f"Loaded {len(all_artifacts)} Salesforce artifacts for {len(entity_ids)} entity IDs"
        )

        documents = []
        counter: ErrorCounter = {}
        skipped_count = 0

        for artifact in all_artifacts:
            with record_exception_and_ignore(
                logger, f"Failed to transform Salesforce artifact {artifact.id}", counter
            ):
                document = self._create_document(artifact)

                if document:
                    documents.append(document)

                    if len(documents) % 100 == 0:
                        logger.info(f"Processed {len(documents)}/{len(all_artifacts)} records")
                else:
                    skipped_count += 1
                    logger.warning(f"Skipped artifact {artifact.entity_id} - no document created")

        successful = counter.get("successful", 0)
        failed = counter.get("failed", 0)

        logger.info(
            f"Salesforce transformation complete: {successful} successful, {failed} failed, {skipped_count} skipped. "
            f"Created {len(documents)} documents from {len(all_artifacts)} artifacts"
        )
        return documents

    def _create_document(self, artifact: SalesforceObjectArtifactType) -> SalesforceDocumentType:
        # Extract data from artifact
        record_data = artifact.content.record_data
        object_type = artifact.metadata.object_type
        record_id = artifact.metadata.record_id
        record_name = artifact.metadata.record_name

        # Prepare document raw_data
        document_raw_data = {
            "object_type": object_type,
            "record_id": record_id,
            "record_name": record_name,
            "record_data": record_data,
            "source_created_at": record_data.get("CreatedDate"),
        }

        # Create the appropriate document class based on object type
        document_class = DOCUMENT_MAPPING.get(object_type)
        if not document_class:
            raise ValueError(f"No document class found for {object_type}")

        # Generate document ID
        document_id = get_salesforce_doc_id(object_type, record_id)

        # Create document
        document = document_class(
            id=document_id,
            raw_data=document_raw_data,
            source_updated_at=artifact.source_updated_at,
            permission_policy="tenant",
            permission_allowed_tokens=None,
        )

        return document
