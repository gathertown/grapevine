"""Intercom citation resolver."""

from __future__ import annotations

from typing import TYPE_CHECKING, TypedDict

from connectors.base import BaseCitationResolver
from connectors.base.document_source import DocumentWithSourceAndMetadata
from src.utils.logging import get_logger

if TYPE_CHECKING:
    from src.mcp.api.citation_resolver import CitationResolver

logger = get_logger(__name__)


class IntercomDocumentMetadata(TypedDict, total=False):
    """Combined metadata type for all Intercom document types."""

    # Common fields
    type: str  # "conversation", "help_center_article", "contact", "company"
    source: str
    workspace_id: str | None

    # Conversation fields
    conversation_id: str

    # Help Center Article fields
    article_id: str | int
    url: str | None

    # Contact fields
    contact_id: str

    # Company fields
    company_id: str


def get_intercom_conversation_url(workspace_id: str, conversation_id: str) -> str:
    """Construct Intercom conversation URL."""
    return f"https://app.intercom.com/a/inbox/{workspace_id}/inbox/conversation/{conversation_id}"


def get_intercom_contact_url(workspace_id: str, contact_id: str) -> str:
    """Construct Intercom contact URL."""
    return f"https://app.intercom.com/a/apps/{workspace_id}/users/{contact_id}/all-conversations"


def get_intercom_company_url(workspace_id: str, company_id: str) -> str:
    """Construct Intercom company URL."""
    return f"https://app.intercom.com/a/apps/{workspace_id}/companies/{company_id}"


class IntercomCitationResolver(BaseCitationResolver[IntercomDocumentMetadata]):
    """Resolver for Intercom citations."""

    async def resolve_citation(
        self,
        document: DocumentWithSourceAndMetadata[IntercomDocumentMetadata],
        excerpt: str,
        resolver: CitationResolver,
    ) -> str:
        doc_type = document.metadata.get("type", "")
        workspace_id = document.metadata.get("workspace_id")

        if doc_type == "help_center_article":
            # Help center articles have a direct URL
            url = document.metadata.get("url")
            if url:
                return url
            logger.warning(f"Help center article {document.id} has no URL in metadata")
            return ""

        elif doc_type == "conversation":
            conversation_id = document.metadata.get("conversation_id")
            if workspace_id and conversation_id:
                return get_intercom_conversation_url(workspace_id, conversation_id)
            logger.warning(
                f"Conversation {conversation_id} citation requested, "
                f"but missing workspace_id ({workspace_id}) for URL construction"
            )
            return ""

        elif doc_type == "contact":
            contact_id = document.metadata.get("contact_id")
            if workspace_id and contact_id:
                return get_intercom_contact_url(workspace_id, contact_id)
            logger.warning(
                f"Contact {contact_id} citation requested, "
                f"but missing workspace_id ({workspace_id}) for URL construction"
            )
            return ""

        elif doc_type == "company":
            company_id = document.metadata.get("company_id")
            if workspace_id and company_id:
                return get_intercom_company_url(workspace_id, company_id)
            logger.warning(
                f"Company {company_id} citation requested, "
                f"but missing workspace_id ({workspace_id}) for URL construction"
            )
            return ""

        else:
            logger.warning(f"Unknown Intercom document type: {doc_type}")
            return ""
