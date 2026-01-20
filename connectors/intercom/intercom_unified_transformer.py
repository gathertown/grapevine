"""
Unified transformer that converts Intercom artifacts (conversations and help center articles) into documents.
"""

import logging
from typing import Any

import asyncpg
import markdownify

from connectors.base import BaseTransformer
from connectors.base.document_source import DocumentSource
from connectors.intercom.intercom_api_types import (
    IntercomArticleData,
    IntercomCompanyData,
    IntercomContactData,
    IntercomConversationData,
)
from connectors.intercom.intercom_artifacts import (
    IntercomCompanyArtifact,
    IntercomContactArtifact,
    IntercomConversationArtifact,
    IntercomHelpCenterArticleArtifact,
)
from connectors.intercom.intercom_company_document import IntercomCompanyDocument
from connectors.intercom.intercom_contact_document import IntercomContactDocument
from connectors.intercom.intercom_conversation_document import (
    IntercomConversationDocument,
)
from connectors.intercom.intercom_conversation_markdown import (
    IntercomMarkdownSection,
    build_conversation_markdown,
)
from connectors.intercom.intercom_help_center_document import (
    IntercomHelpCenterArticleDocument,
)
from connectors.intercom.intercom_utils import convert_timestamp_to_iso
from src.ingest.repositories.artifact_repository import ArtifactRepository
from src.utils.error_handling import ErrorCounter, record_exception_and_ignore

logger = logging.getLogger(__name__)

# Type union for all Intercom document types
type IntercomDocumentType = (
    IntercomConversationDocument
    | IntercomHelpCenterArticleDocument
    | IntercomContactDocument
    | IntercomCompanyDocument
)


class IntercomUnifiedTransformer(BaseTransformer[IntercomDocumentType]):
    """Unified transformer for Intercom artifacts (conversations and help center articles)."""

    def __init__(self) -> None:
        super().__init__(DocumentSource.INTERCOM)

    async def transform_artifacts(
        self,
        entity_ids: list[str],
        readonly_db_pool: asyncpg.Pool,
    ) -> list[IntercomDocumentType]:
        repo = ArtifactRepository(readonly_db_pool)

        # Load conversation, help center, contact, and company artifacts
        conversation_artifacts = await repo.get_artifacts_by_entity_ids(
            IntercomConversationArtifact, entity_ids
        )
        help_center_artifacts = await repo.get_artifacts_by_entity_ids(
            IntercomHelpCenterArticleArtifact, entity_ids
        )
        contact_artifacts = await repo.get_artifacts_by_entity_ids(
            IntercomContactArtifact, entity_ids
        )
        company_artifacts = await repo.get_artifacts_by_entity_ids(
            IntercomCompanyArtifact, entity_ids
        )

        all_artifacts = (
            list(conversation_artifacts)
            + list(help_center_artifacts)
            + list(contact_artifacts)
            + list(company_artifacts)
        )

        logger.info(
            "Loaded %s Intercom artifacts (%s conversations, %s help center articles, %s contacts, %s companies) for %s entity IDs",
            len(all_artifacts),
            len(conversation_artifacts),
            len(help_center_artifacts),
            len(contact_artifacts),
            len(company_artifacts),
            len(entity_ids),
        )

        documents: list[IntercomDocumentType] = []
        counter: ErrorCounter = {}

        for artifact in all_artifacts:
            with record_exception_and_ignore(
                logger, f"Failed to transform Intercom artifact {artifact.id}", counter
            ):
                document: IntercomDocumentType | None = None
                if isinstance(artifact, IntercomConversationArtifact):
                    document = self._create_conversation_document(artifact)
                elif isinstance(artifact, IntercomHelpCenterArticleArtifact):
                    document = self._create_help_center_document(artifact)
                elif isinstance(artifact, IntercomContactArtifact):
                    document = self._create_contact_document(artifact)
                elif isinstance(artifact, IntercomCompanyArtifact):
                    document = self._create_company_document(artifact)

                if document:
                    documents.append(document)

        logger.info(
            "Intercom transformation complete: %s successful, %s failed; produced %s documents",
            counter.get("successful", 0),
            counter.get("failed", 0),
            len(documents),
        )
        return documents

    def _create_conversation_document(
        self, artifact: IntercomConversationArtifact
    ) -> IntercomConversationDocument | None:
        """Create a conversation document from a conversation artifact."""
        conversation_data: IntercomConversationData = artifact.content.conversation_data

        # Convert typed model to dict for markdown builder
        conversation_dict = conversation_data.model_dump(exclude_none=True)

        result = build_conversation_markdown(conversation_dict)
        sections_payload = [_section_to_raw(section) for section in result.sections]

        # Add workspace_id to metadata for citation URL construction
        # Try artifact metadata first, fall back to content (for older artifacts)
        metadata = result.metadata
        metadata["workspace_id"] = artifact.metadata.workspace_id or conversation_data.workspace_id

        document = IntercomConversationDocument(
            id=artifact.entity_id,
            raw_data={
                "conversation_id": artifact.metadata.conversation_id,
                "markdown": result.markdown,
                "title": result.metadata.get("title"),
                "sections": sections_payload,
            },
            metadata=metadata,
            source_updated_at=artifact.source_updated_at,
            permission_policy="tenant",
            permission_allowed_tokens=None,
        )
        return document

    def _create_help_center_document(
        self, artifact: IntercomHelpCenterArticleArtifact
    ) -> IntercomHelpCenterArticleDocument | None:
        """Create a help center document from a help center artifact."""
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
                "workspace_id": artifact.metadata.workspace_id or article_data.workspace_id,
            },
            source_updated_at=artifact.source_updated_at,
            permission_policy="tenant",
            permission_allowed_tokens=None,
        )
        return document

    def _create_contact_document(
        self, artifact: IntercomContactArtifact
    ) -> IntercomContactDocument | None:
        """Create a contact document from an artifact."""
        contact_data: IntercomContactData = artifact.content.contact_data

        # Use shared timestamp utility
        created_at_iso = convert_timestamp_to_iso(artifact.metadata.created_at)
        updated_at_iso = convert_timestamp_to_iso(artifact.metadata.updated_at)

        # Ensure we have valid ISO timestamps - use source_updated_at as fallback
        if not created_at_iso:
            created_at_iso = artifact.source_updated_at.isoformat()
        if not updated_at_iso:
            updated_at_iso = artifact.source_updated_at.isoformat()

        # Extract companies from typed model
        companies: list[str] = []
        if contact_data.companies and contact_data.companies.data:
            companies = [c.id for c in contact_data.companies.data if c.id]

        # Extract tags from typed model
        tags: list[str] = []
        if contact_data.tags and contact_data.tags.data:
            tags = [t.name for t in contact_data.tags.data if t.name]

        # Extract location as dict for metadata
        location_dict: dict[str, Any] | None = None
        if contact_data.location:
            location_dict = contact_data.location.model_dump(exclude_none=True)

        document = IntercomContactDocument(
            id=artifact.entity_id,
            raw_data={
                "contact_data": contact_data.model_dump(exclude_none=True),
            },
            metadata={
                "contact_id": artifact.metadata.contact_id,
                "email": artifact.metadata.email,
                "name": artifact.metadata.name,
                "role": artifact.metadata.role,
                "phone": contact_data.phone,
                "location": location_dict,
                "custom_attributes": dict(contact_data.custom_attributes),
                "companies": companies,
                "tags": tags,
                "source_created_at": created_at_iso,
                "source_updated_at": updated_at_iso,
                "source": DocumentSource.INTERCOM.value,
                "type": "contact",
                "workspace_id": artifact.metadata.workspace_id or contact_data.workspace_id,
            },
            source_updated_at=artifact.source_updated_at,
            permission_policy="tenant",
            permission_allowed_tokens=None,
        )
        return document

    def _create_company_document(
        self, artifact: IntercomCompanyArtifact
    ) -> IntercomCompanyDocument | None:
        """Create a company document from an artifact."""
        company_data: IntercomCompanyData = artifact.content.company_data

        # Use shared timestamp utility
        created_at_iso = convert_timestamp_to_iso(artifact.metadata.created_at)
        updated_at_iso = convert_timestamp_to_iso(artifact.metadata.updated_at)

        # Ensure we have valid ISO timestamps - use source_updated_at as fallback
        if not created_at_iso:
            created_at_iso = artifact.source_updated_at.isoformat()
        if not updated_at_iso:
            updated_at_iso = artifact.source_updated_at.isoformat()

        # Extract tags from typed model
        tags: list[str] = []
        if company_data.tags and company_data.tags.data:
            tags = [t.name for t in company_data.tags.data if t.name]

        # Extract plan name from typed model
        plan_name = company_data.plan.name if company_data.plan else None

        document = IntercomCompanyDocument(
            id=artifact.entity_id,
            raw_data={
                "company_data": company_data.model_dump(exclude_none=True),
            },
            metadata={
                "company_id": artifact.metadata.company_id,
                "name": artifact.metadata.name,
                "website": company_data.website,
                "industry": company_data.industry,
                "plan": plan_name,
                "size": company_data.size,
                "custom_attributes": dict(company_data.custom_attributes),
                "tags": tags,
                "source_created_at": created_at_iso,
                "source_updated_at": updated_at_iso,
                "source": DocumentSource.INTERCOM.value,
                "type": "company",
                "workspace_id": artifact.metadata.workspace_id or company_data.workspace_id,
            },
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
