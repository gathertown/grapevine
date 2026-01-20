"""
Transformer that converts Intercom Help Center article artifacts into markdown documents.
"""

import logging

import asyncpg
import markdownify

from connectors.base import BaseTransformer
from connectors.base.document_source import DocumentSource
from connectors.intercom.intercom_api_types import IntercomArticleData
from connectors.intercom.intercom_artifacts import IntercomHelpCenterArticleArtifact
from connectors.intercom.intercom_help_center_document import (
    IntercomHelpCenterArticleDocument,
)
from connectors.intercom.intercom_utils import convert_timestamp_to_iso
from src.ingest.repositories import ArtifactRepository
from src.utils.error_handling import ErrorCounter, record_exception_and_ignore

logger = logging.getLogger(__name__)


class IntercomHelpCenterTransformer(BaseTransformer[IntercomHelpCenterArticleDocument]):
    """Transform Intercom Help Center article artifacts into markdown documents."""

    def __init__(self) -> None:
        super().__init__(DocumentSource.INTERCOM)

    async def transform_artifacts(
        self,
        entity_ids: list[str],
        readonly_db_pool: asyncpg.Pool,
    ) -> list[IntercomHelpCenterArticleDocument]:
        repo = ArtifactRepository(readonly_db_pool)
        artifacts = await repo.get_artifacts_by_entity_ids(
            IntercomHelpCenterArticleArtifact, entity_ids
        )

        logger.info(
            "Loaded %s Intercom Help Center artifacts for %s entity IDs",
            len(artifacts),
            len(entity_ids),
        )

        documents: list[IntercomHelpCenterArticleDocument] = []
        counter: ErrorCounter = {}

        for artifact in artifacts:
            with record_exception_and_ignore(
                logger,
                f"Failed to transform Intercom Help Center artifact {artifact.id}",
                counter,
            ):
                document = self._create_document(artifact)
                if document:
                    documents.append(document)

        logger.info(
            "Intercom Help Center transformation complete: %s successful, %s failed; produced %s documents",
            counter.get("successful", 0),
            counter.get("failed", 0),
            len(documents),
        )
        return documents

    def _create_document(
        self, artifact: IntercomHelpCenterArticleArtifact
    ) -> IntercomHelpCenterArticleDocument | None:
        article_data: IntercomArticleData = artifact.content.article_data

        # Extract article body - Intercom articles typically have body in HTML format
        body = article_data.body or ""

        # Convert HTML to markdown
        if body and isinstance(body, str):
            markdown_body = markdownify.markdownify(body, heading_style="ATX")
        else:
            markdown_body = str(body) if body else ""

        # Extract author information from typed model
        author = article_data.author
        author_id = author.id if author else article_data.author_id
        author_name = author.name if author else None
        author_email = author.email if author else None

        # Extract collection and section information from parent_type field
        collection_id = None
        section_id = None
        if article_data.parent_type == "collection":
            collection_id = article_data.parent_id
        elif article_data.parent_type == "section":
            section_id = article_data.parent_id

        # Extract URL from typed model
        url = article_data.url

        # Use shared timestamp utility
        created_at_iso = convert_timestamp_to_iso(artifact.metadata.created_at)
        updated_at_iso = convert_timestamp_to_iso(artifact.metadata.updated_at)

        # Ensure we have valid ISO timestamps - use source_updated_at as fallback
        if not created_at_iso:
            created_at_iso = artifact.source_updated_at.isoformat()
        if not updated_at_iso:
            updated_at_iso = artifact.source_updated_at.isoformat()

        document = IntercomHelpCenterArticleDocument(
            id=artifact.entity_id,
            raw_data={
                "article_id": artifact.metadata.article_id,
                "title": artifact.metadata.title,
                "body": markdown_body,
                "state": artifact.metadata.state,
                "url": url,
                "collection_id": collection_id,
                "section_id": section_id,
                "author_id": author_id,
                "author_name": author_name,
                "author_email": author_email,
                "created_at": created_at_iso,
                "updated_at": updated_at_iso,
            },
            metadata={
                "article_id": artifact.metadata.article_id,
                "title": artifact.metadata.title,
                "state": artifact.metadata.state,
                "url": url,
                "collection_id": collection_id,
                "section_id": section_id,
                "author_id": author_id,
                "author_name": author_name,
                "author_email": author_email,
                "source_created_at": created_at_iso,
                "source_updated_at": updated_at_iso,
                "source": DocumentSource.INTERCOM.value,
                "type": "help_center_article",
            },
            source_updated_at=artifact.source_updated_at,
            permission_policy="tenant",
            permission_allowed_tokens=None,
        )
        return document
