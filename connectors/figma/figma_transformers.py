"""
Figma transformers for converting Figma artifacts to documents.
"""

import logging

import asyncpg

from connectors.base import BaseTransformer
from connectors.base.document_source import DocumentSource
from connectors.figma.figma_documents import FigmaCommentDocument, FigmaFileDocument
from connectors.figma.figma_models import FigmaCommentArtifact, FigmaFileArtifact
from src.ingest.repositories.artifact_repository import ArtifactRepository
from src.utils.error_handling import ErrorCounter, record_exception_and_ignore

logger = logging.getLogger(__name__)


class FigmaFileTransformer(BaseTransformer[FigmaFileDocument]):
    """Transformer for Figma file artifacts."""

    def __init__(self):
        super().__init__(DocumentSource.FIGMA_FILE)

    async def transform_artifacts(
        self, entity_ids: list[str], readonly_db_pool: asyncpg.Pool
    ) -> list[FigmaFileDocument]:
        """Transform Figma file artifacts into documents.

        Args:
            entity_ids: List of file entity IDs to transform
            readonly_db_pool: Database connection pool

        Returns:
            List of FigmaFileDocument instances
        """
        repo = ArtifactRepository(readonly_db_pool)

        # Get Figma file artifacts for the given entity IDs
        artifacts = await repo.get_artifacts_by_entity_ids(FigmaFileArtifact, entity_ids)

        logger.info(
            f"Loaded {len(artifacts)} Figma file artifacts for {len(entity_ids)} entity IDs"
        )

        documents = []
        counter: ErrorCounter = {}

        for artifact in artifacts:
            with record_exception_and_ignore(
                logger, f"Failed to transform Figma file artifact {artifact.id}", counter
            ):
                document = FigmaFileDocument.from_artifact(artifact)
                documents.append(document)

                if len(documents) % 100 == 0:
                    logger.info(f"Processed {len(documents)}/{len(artifacts)} files")

        successful = counter.get("successful", 0)
        failed = counter.get("failed", 0)

        logger.info(
            f"Figma file transformation complete: {successful} successful, {failed} failed. "
            f"Created {len(documents)} documents from {len(artifacts)} artifacts"
        )

        return documents


class FigmaCommentTransformer(BaseTransformer[FigmaCommentDocument]):
    """Transformer for Figma comment artifacts."""

    def __init__(self):
        super().__init__(DocumentSource.FIGMA_COMMENT)

    async def transform_artifacts(
        self, entity_ids: list[str], readonly_db_pool: asyncpg.Pool
    ) -> list[FigmaCommentDocument]:
        """Transform Figma comment artifacts into documents.

        Args:
            entity_ids: List of comment entity IDs to transform
            readonly_db_pool: Database connection pool

        Returns:
            List of FigmaCommentDocument instances
        """
        repo = ArtifactRepository(readonly_db_pool)

        # Get Figma comment artifacts for the given entity IDs
        artifacts = await repo.get_artifacts_by_entity_ids(FigmaCommentArtifact, entity_ids)

        logger.info(
            f"Loaded {len(artifacts)} Figma comment artifacts for {len(entity_ids)} entity IDs"
        )

        documents = []
        counter: ErrorCounter = {}

        for artifact in artifacts:
            with record_exception_and_ignore(
                logger, f"Failed to transform Figma comment artifact {artifact.id}", counter
            ):
                document = FigmaCommentDocument.from_artifact(artifact)
                documents.append(document)

                if len(documents) % 100 == 0:
                    logger.info(f"Processed {len(documents)}/{len(artifacts)} comments")

        successful = counter.get("successful", 0)
        failed = counter.get("failed", 0)

        logger.info(
            f"Figma comment transformation complete: {successful} successful, {failed} failed. "
            f"Created {len(documents)} documents from {len(artifacts)} artifacts"
        )

        return documents
