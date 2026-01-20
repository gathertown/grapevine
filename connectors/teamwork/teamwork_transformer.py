"""
Teamwork transformer for converting Teamwork task artifacts to documents.
"""

import logging

import asyncpg

from connectors.base import BaseTransformer
from connectors.base.document_source import DocumentSource
from connectors.teamwork.teamwork_artifacts import TeamworkTaskArtifact
from connectors.teamwork.teamwork_task_document import TeamworkTaskDocument
from src.ingest.repositories.artifact_repository import ArtifactRepository
from src.utils.error_handling import ErrorCounter, record_exception_and_ignore

logger = logging.getLogger(__name__)


class TeamworkTaskTransformer(BaseTransformer[TeamworkTaskDocument]):
    """Transformer for Teamwork task artifacts."""

    def __init__(self):
        super().__init__(DocumentSource.TEAMWORK_TASK)

    async def transform_artifacts(
        self, entity_ids: list[str], readonly_db_pool: asyncpg.Pool
    ) -> list[TeamworkTaskDocument]:
        """Transform Teamwork task artifacts into documents.

        Args:
            entity_ids: List of task entity IDs to transform
            readonly_db_pool: Database connection pool

        Returns:
            List of TeamworkTaskDocument instances
        """
        repo = ArtifactRepository(readonly_db_pool)

        # Get Teamwork task artifacts for the given entity IDs
        artifacts = await repo.get_artifacts_by_entity_ids(TeamworkTaskArtifact, entity_ids)

        logger.info(
            f"Loaded {len(artifacts)} Teamwork task artifacts for {len(entity_ids)} entity IDs"
        )

        documents = []
        counter: ErrorCounter = {}

        for artifact in artifacts:
            with record_exception_and_ignore(
                logger, f"Failed to transform Teamwork task artifact {artifact.id}", counter
            ):
                document = TeamworkTaskDocument.from_artifact(artifact)
                documents.append(document)

                if len(documents) % 100 == 0:
                    logger.info(f"Processed {len(documents)}/{len(artifacts)} tasks")

        successful = counter.get("successful", 0)
        failed = counter.get("failed", 0)

        logger.info(
            f"Teamwork task transformation complete: {successful} successful, {failed} failed. "
            f"Created {len(documents)} documents from {len(artifacts)} artifacts"
        )

        return documents
