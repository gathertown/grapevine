"""Linear citation resolver."""

from __future__ import annotations

from typing import TYPE_CHECKING

from connectors.base import BaseCitationResolver
from connectors.base.document_source import DocumentWithSourceAndMetadata
from connectors.linear.linear_issue_document import LinearIssueDocumentMetadata
from src.utils.logging import get_logger

if TYPE_CHECKING:
    from src.mcp.api.citation_resolver import CitationResolver

logger = get_logger(__name__)


class LinearCitationResolver(BaseCitationResolver[LinearIssueDocumentMetadata]):
    """Resolver for Linear issue citations."""

    async def resolve_citation(
        self,
        document: DocumentWithSourceAndMetadata[LinearIssueDocumentMetadata],
        excerpt: str,
        resolver: CitationResolver,
    ) -> str:
        logger.info(f"Linear resolver: doc_id={document.id}")

        # Use existing issue_url from metadata
        issue_url = document.metadata.get("issue_url")
        if not issue_url:
            raise ValueError(f"No issue URL found for Linear document {document.id}")
        return issue_url
