import asyncpg

from connectors.base import BaseTransformer
from connectors.base.document_source import DocumentSource
from connectors.fireflies.extractors.artifacts.fireflies_transcript_artifact import (
    FirefliesTranscriptArtifact,
)
from connectors.fireflies.transformers.fireflies_transcript_document import (
    FirefliesTranscriptDocument,
)
from src.ingest.repositories.artifact_repository import ArtifactRepository
from src.utils.logging import get_logger

logger = get_logger(__name__)


class FirefliesTranscriptTransformer(BaseTransformer[FirefliesTranscriptDocument]):
    def __init__(self):
        super().__init__(DocumentSource.FIREFLIES_TRANSCRIPT)

    async def transform_artifacts(
        self, entity_ids: list[str], readonly_db_pool: asyncpg.Pool
    ) -> list[FirefliesTranscriptDocument]:
        db = ArtifactRepository(readonly_db_pool)

        transcript_artifacts = await db.get_artifacts_by_entity_ids(
            FirefliesTranscriptArtifact, entity_ids
        )

        documents = [
            FirefliesTranscriptDocument.from_artifacts(transcript=artifact)
            for artifact in transcript_artifacts
        ]

        logger.info(
            f"Fireflies Transcript transformation complete: Created {len(documents)} documents from {len(entity_ids)} entity_ids and {len(transcript_artifacts)} transcript artifacts."
        )

        return documents
