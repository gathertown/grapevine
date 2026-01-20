"""Monday.com transformer for converting artifacts to documents.

Follows the standard transformer pattern:
1. Fetch artifacts from ingest_artifact table by entity_ids
2. Transform artifacts to documents
3. Return documents for embedding and indexing
"""

import logging

import asyncpg

from connectors.base import BaseTransformer
from connectors.base.document_source import DocumentSource
from connectors.monday.extractors.artifacts import MondayItemArtifact
from connectors.monday.transformers.monday_item_document import MondayItemDocument
from src.ingest.repositories.artifact_repository import ArtifactRepository
from src.utils.error_handling import ErrorCounter, record_exception_and_ignore

logger = logging.getLogger(__name__)


class MondayItemTransformer(BaseTransformer[MondayItemDocument]):
    """Transformer for Monday.com item artifacts.

    Fetches MondayItemArtifact entries from the ingest_artifact table
    and transforms them into MondayItemDocument instances for indexing.
    """

    def __init__(self):
        super().__init__(DocumentSource.MONDAY_ITEM)

    async def transform_artifacts(
        self, entity_ids: list[str], readonly_db_pool: asyncpg.Pool
    ) -> list[MondayItemDocument]:
        """Transform Monday.com item artifacts into documents.

        Args:
            entity_ids: List of item entity IDs to transform
            readonly_db_pool: Database connection pool

        Returns:
            List of MondayItemDocument instances
        """
        repo = ArtifactRepository(readonly_db_pool)

        # Get Monday.com item artifacts for the given entity IDs
        artifacts = await repo.get_artifacts_by_entity_ids(MondayItemArtifact, entity_ids)

        logger.info(
            f"Loaded {len(artifacts)} Monday.com item artifacts for {len(entity_ids)} entity IDs"
        )

        documents = []
        counter: ErrorCounter = {}

        for artifact in artifacts:
            with record_exception_and_ignore(
                logger, f"Failed to transform Monday.com item artifact {artifact.id}", counter
            ):
                document = MondayItemDocument.from_artifact(artifact)
                documents.append(document)

                if len(documents) % 100 == 0:
                    logger.info(f"Processed {len(documents)}/{len(artifacts)} Monday.com items")

        successful = counter.get("successful", 0)
        failed = counter.get("failed", 0)

        logger.info(
            f"Monday.com item transformation complete: {successful} successful, {failed} failed. "
            f"Created {len(documents)} documents from {len(artifacts)} artifacts"
        )

        return documents
