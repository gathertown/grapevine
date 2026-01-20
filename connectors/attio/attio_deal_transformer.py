"""
Attio transformer for converting Attio deal artifacts to documents.
"""

import logging

import asyncpg

from connectors.attio.attio_artifacts import AttioDealArtifact
from connectors.attio.attio_deal_document import AttioDealDocument
from connectors.base import BaseTransformer
from connectors.base.document_source import DocumentSource
from src.ingest.repositories.artifact_repository import ArtifactRepository
from src.utils.error_handling import ErrorCounter, record_exception_and_ignore

logger = logging.getLogger(__name__)


class AttioDealTransformer(BaseTransformer[AttioDealDocument]):
    """Transformer for Attio deal artifacts."""

    def __init__(self):
        super().__init__(DocumentSource.ATTIO_DEAL)

    async def transform_artifacts(
        self, entity_ids: list[str], readonly_db_pool: asyncpg.Pool
    ) -> list[AttioDealDocument]:
        """Transform Attio deal artifacts into documents.

        Args:
            entity_ids: List of deal entity IDs to transform
            readonly_db_pool: Database connection pool

        Returns:
            List of AttioDealDocument instances
        """
        repo = ArtifactRepository(readonly_db_pool)

        # Get Attio deal artifacts for the given entity IDs
        artifacts = await repo.get_artifacts_by_entity_ids(AttioDealArtifact, entity_ids)

        logger.info(
            f"Loaded {len(artifacts)} Attio deal artifacts for {len(entity_ids)} entity IDs"
        )

        documents = []
        counter: ErrorCounter = {}

        for artifact in artifacts:
            with record_exception_and_ignore(
                logger, f"Failed to transform Attio deal artifact {artifact.id}", counter
            ):
                document = AttioDealDocument.from_artifact(artifact)
                documents.append(document)

                if len(documents) % 100 == 0:
                    logger.info(f"Processed {len(documents)}/{len(artifacts)} deals")

        successful = counter.get("successful", 0)
        failed = counter.get("failed", 0)

        logger.info(
            f"Attio deal transformation complete: {successful} successful, {failed} failed. "
            f"Created {len(documents)} documents from {len(artifacts)} artifacts"
        )

        return documents
