"""
Canva transformers for converting Canva artifacts to documents.
"""

import logging

import asyncpg

from connectors.base import BaseTransformer
from connectors.base.document_source import DocumentSource
from connectors.canva.canva_documents import CanvaDesignDocument
from connectors.canva.canva_models import CanvaDesignArtifact
from src.ingest.repositories.artifact_repository import ArtifactRepository
from src.utils.error_handling import ErrorCounter, record_exception_and_ignore

logger = logging.getLogger(__name__)


class CanvaDesignTransformer(BaseTransformer[CanvaDesignDocument]):
    """Transformer for Canva design artifacts."""

    def __init__(self):
        super().__init__(DocumentSource.CANVA_DESIGN)

    async def transform_artifacts(
        self, entity_ids: list[str], readonly_db_pool: asyncpg.Pool
    ) -> list[CanvaDesignDocument]:
        """Transform Canva design artifacts into documents.

        Args:
            entity_ids: List of design entity IDs to transform
            readonly_db_pool: Database connection pool

        Returns:
            List of CanvaDesignDocument instances
        """
        repo = ArtifactRepository(readonly_db_pool)

        # Get Canva design artifacts for the given entity IDs
        artifacts = await repo.get_artifacts_by_entity_ids(CanvaDesignArtifact, entity_ids)

        logger.info(
            f"Loaded {len(artifacts)} Canva design artifacts for {len(entity_ids)} entity IDs"
        )

        documents = []
        counter: ErrorCounter = {}

        for artifact in artifacts:
            with record_exception_and_ignore(
                logger, f"Failed to transform Canva design artifact {artifact.id}", counter
            ):
                document = CanvaDesignDocument.from_artifact(artifact)
                documents.append(document)

                if len(documents) % 100 == 0:
                    logger.info(f"Processed {len(documents)}/{len(artifacts)} designs")

        successful = counter.get("successful", 0)
        failed = counter.get("failed", 0)

        logger.info(
            f"Canva design transformation complete: {successful} successful, {failed} failed. "
            f"Created {len(documents)} documents from {len(artifacts)} artifacts"
        )

        return documents
