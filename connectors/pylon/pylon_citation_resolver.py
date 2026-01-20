"""Citation resolver for Pylon documents."""

from __future__ import annotations

from typing import TYPE_CHECKING

from connectors.base import BaseCitationResolver
from connectors.base.document_source import DocumentWithSourceAndMetadata
from connectors.pylon.transformers.pylon_issue_document import PylonIssueDocumentMetadata
from src.utils.logging import get_logger

if TYPE_CHECKING:
    from src.mcp.api.citation_resolver import CitationResolver

logger = get_logger(__name__)

# Pylon app URL base
PYLON_APP_BASE_URL = "https://app.usepylon.com"


class PylonIssueCitationResolver(BaseCitationResolver[PylonIssueDocumentMetadata]):
    """Resolve citations for Pylon issue documents."""

    async def resolve_citation(
        self,
        document: DocumentWithSourceAndMetadata[PylonIssueDocumentMetadata],
        excerpt: str,
        resolver: CitationResolver,
    ) -> str:
        """
        Generate a deep link URL to the Pylon issue.

        Pylon issues are accessible at:
        https://app.usepylon.com/issues/views/all-issues?conversationID={issue_id}&view=fs

        The conversationID parameter is the issue UUID, and view=fs opens it in full screen.
        """
        issue_id = document.metadata.get("issue_id")

        if issue_id:
            return f"{PYLON_APP_BASE_URL}/issues/views/all-issues?conversationID={issue_id}&view=fs"

        # Fallback: try to extract issue_id from document.id (format: pylon_issue_{issue_id})
        if document.id.startswith("pylon_issue_"):
            extracted_id = document.id[len("pylon_issue_") :]
            return f"{PYLON_APP_BASE_URL}/issues/views/all-issues?conversationID={extracted_id}&view=fs"

        # Last resort: log warning and return base issues URL
        logger.warning(
            "Could not extract issue_id for citation",
            document_id=document.id,
        )
        return f"{PYLON_APP_BASE_URL}/issues"
