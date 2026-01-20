"""
Attio transformer for converting Attio company artifacts to documents.
"""

import logging

import asyncpg

from connectors.attio.attio_artifacts import AttioCompanyArtifact
from connectors.attio.attio_company_document import AttioCompanyDocument
from connectors.base import BaseTransformer
from connectors.base.document_source import DocumentSource
from src.ingest.repositories.artifact_repository import ArtifactRepository
from src.utils.error_handling import ErrorCounter, record_exception_and_ignore

logger = logging.getLogger(__name__)


class AttioCompanyTransformer(BaseTransformer[AttioCompanyDocument]):
    """Transformer for Attio company artifacts."""

    def __init__(self):
        super().__init__(DocumentSource.ATTIO_COMPANY)

    async def transform_artifacts(
        self, entity_ids: list[str], readonly_db_pool: asyncpg.Pool
    ) -> list[AttioCompanyDocument]:
        """Transform Attio company artifacts into documents.

        Args:
            entity_ids: List of company entity IDs to transform
            readonly_db_pool: Database connection pool

        Returns:
            List of AttioCompanyDocument instances
        """
        repo = ArtifactRepository(readonly_db_pool)

        # Get Attio company artifacts for the given entity IDs
        artifacts = await repo.get_artifacts_by_entity_ids(AttioCompanyArtifact, entity_ids)

        logger.info(
            f"Loaded {len(artifacts)} Attio company artifacts for {len(entity_ids)} entity IDs"
        )

        documents = []
        counter: ErrorCounter = {}

        for artifact in artifacts:
            with record_exception_and_ignore(
                logger, f"Failed to transform Attio company artifact {artifact.id}", counter
            ):
                document = AttioCompanyDocument.from_artifact(artifact)
                documents.append(document)

                if len(documents) % 100 == 0:
                    logger.info(f"Processed {len(documents)}/{len(artifacts)} companies")

        successful = counter.get("successful", 0)
        failed = counter.get("failed", 0)

        logger.info(
            f"Attio company transformation complete: {successful} successful, {failed} failed. "
            f"Created {len(documents)} documents from {len(artifacts)} artifacts"
        )

        return documents
