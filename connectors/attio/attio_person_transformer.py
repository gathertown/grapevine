"""
Attio transformer for converting Attio person artifacts to documents.
"""

import logging

import asyncpg

from connectors.attio.attio_artifacts import AttioPersonArtifact
from connectors.attio.attio_person_document import AttioPersonDocument
from connectors.base import BaseTransformer
from connectors.base.document_source import DocumentSource
from src.ingest.repositories.artifact_repository import ArtifactRepository
from src.utils.error_handling import ErrorCounter, record_exception_and_ignore

logger = logging.getLogger(__name__)


class AttioPersonTransformer(BaseTransformer[AttioPersonDocument]):
    """Transformer for Attio person artifacts."""

    def __init__(self):
        super().__init__(DocumentSource.ATTIO_PERSON)

    async def transform_artifacts(
        self, entity_ids: list[str], readonly_db_pool: asyncpg.Pool
    ) -> list[AttioPersonDocument]:
        """Transform Attio person artifacts into documents.

        Args:
            entity_ids: List of person entity IDs to transform
            readonly_db_pool: Database connection pool

        Returns:
            List of AttioPersonDocument instances
        """
        repo = ArtifactRepository(readonly_db_pool)

        # Get Attio person artifacts for the given entity IDs
        artifacts = await repo.get_artifacts_by_entity_ids(AttioPersonArtifact, entity_ids)

        logger.info(
            f"Loaded {len(artifacts)} Attio person artifacts for {len(entity_ids)} entity IDs"
        )

        documents = []
        counter: ErrorCounter = {}

        for artifact in artifacts:
            with record_exception_and_ignore(
                logger, f"Failed to transform Attio person artifact {artifact.id}", counter
            ):
                document = AttioPersonDocument.from_artifact(artifact)
                documents.append(document)

                if len(documents) % 100 == 0:
                    logger.info(f"Processed {len(documents)}/{len(artifacts)} people")

        successful = counter.get("successful", 0)
        failed = counter.get("failed", 0)

        logger.info(
            f"Attio person transformation complete: {successful} successful, {failed} failed. "
            f"Created {len(documents)} documents from {len(artifacts)} artifacts"
        )

        return documents
