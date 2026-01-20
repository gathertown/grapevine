from __future__ import annotations

from typing import TYPE_CHECKING

from connectors.base import BaseCitationResolver
from connectors.base.document_source import DocumentWithSourceAndMetadata
from connectors.jira.jira_issue_document import JiraIssueDocumentMetadata
from src.utils.logging import get_logger

if TYPE_CHECKING:
    from src.mcp.api.citation_resolver import CitationResolver

logger = get_logger(__name__)


class JiraCitationResolver(BaseCitationResolver[JiraIssueDocumentMetadata]):
    async def resolve_citation(
        self,
        document: DocumentWithSourceAndMetadata[JiraIssueDocumentMetadata],
        excerpt: str,
        resolver: CitationResolver,
    ) -> str:
        issue_url = document.metadata.get("url", "")

        if not issue_url:
            logger.warning(f"No URL found in metadata for Jira document {document.id}")
            return ""

        return issue_url
