"""
Transformer that converts Intercom conversation artifacts into markdown documents.
"""

import logging
from typing import Any

import asyncpg

from connectors.base import BaseTransformer
from connectors.base.document_source import DocumentSource
from connectors.intercom.intercom_api_types import IntercomConversationData
from connectors.intercom.intercom_artifacts import IntercomConversationArtifact
from connectors.intercom.intercom_conversation_document import (
    IntercomConversationDocument,
)
from connectors.intercom.intercom_conversation_markdown import (
    IntercomMarkdownSection,
    build_conversation_markdown,
)
from src.ingest.repositories import ArtifactRepository
from src.utils.error_handling import ErrorCounter, record_exception_and_ignore

logger = logging.getLogger(__name__)


class IntercomConversationTransformer(BaseTransformer[IntercomConversationDocument]):
    """Transform Intercom conversation artifacts into markdown documents."""

    def __init__(self) -> None:
        super().__init__(DocumentSource.INTERCOM)

    async def transform_artifacts(
        self,
        entity_ids: list[str],
        readonly_db_pool: asyncpg.Pool,
    ) -> list[IntercomConversationDocument]:
        repo = ArtifactRepository(readonly_db_pool)
        artifacts = await repo.get_artifacts_by_entity_ids(IntercomConversationArtifact, entity_ids)

        logger.info(
            "Loaded %s Intercom artifacts for %s entity IDs",
            len(artifacts),
            len(entity_ids),
        )

        documents: list[IntercomConversationDocument] = []
        counter: ErrorCounter = {}

        for artifact in artifacts:
            with record_exception_and_ignore(
                logger, f"Failed to transform Intercom artifact {artifact.id}", counter
            ):
                document = self._create_document(artifact)
                if document:
                    documents.append(document)

        logger.info(
            "Intercom transformation complete: %s successful, %s failed; produced %s documents",
            counter.get("successful", 0),
            counter.get("failed", 0),
            len(documents),
        )
        return documents

    def _create_document(
        self, artifact: IntercomConversationArtifact
    ) -> IntercomConversationDocument | None:
        conversation_data: IntercomConversationData = artifact.content.conversation_data

        # Convert typed model to dict for markdown builder
        conversation_dict = conversation_data.model_dump(exclude_none=True)

        result = build_conversation_markdown(conversation_dict)
        sections_payload = [_section_to_raw(section) for section in result.sections]

        document = IntercomConversationDocument(
            id=artifact.entity_id,
            raw_data={
                "conversation_id": artifact.metadata.conversation_id,
                "markdown": result.markdown,
                "title": result.metadata.get("title"),
                "sections": sections_payload,
            },
            metadata=result.metadata,
            source_updated_at=artifact.source_updated_at,
            permission_policy="tenant",
            permission_allowed_tokens=None,
        )
        return document


def _section_to_raw(section: IntercomMarkdownSection) -> dict[str, Any]:
    return {
        "section_type": section.section_type,
        "markdown": section.markdown,
        "part_index": section.part_index,
        "author_name": section.author_name,
        "author_email": section.author_email,
        "created_at": section.created_at,
        "ai_flags": section.ai_flags,
    }
