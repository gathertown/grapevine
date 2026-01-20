from __future__ import annotations

from typing import TYPE_CHECKING

from connectors.base import BaseCitationResolver
from connectors.base.document_source import DocumentWithSourceAndMetadata
from connectors.confluence.confluence_page_document import ConfluencePageDocumentMetadata
from src.utils.logging import get_logger

if TYPE_CHECKING:
    from src.mcp.api.citation_resolver import CitationResolver

logger = get_logger(__name__)


class ConfluenceCitationResolver(BaseCitationResolver[ConfluencePageDocumentMetadata]):
    async def resolve_citation(
        self,
        document: DocumentWithSourceAndMetadata[ConfluencePageDocumentMetadata],
        excerpt: str,
        resolver: CitationResolver,
    ) -> str:
        page_url = document.metadata.get("page_url", "")

        if not page_url:
            logger.warning(f"No URL found in metadata for Confluence document {document.id}")
            return ""

        return page_url
