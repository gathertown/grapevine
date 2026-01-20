"""Canva citation resolvers."""

from __future__ import annotations

from typing import TYPE_CHECKING

from connectors.base import BaseCitationResolver
from connectors.base.document_source import DocumentWithSourceAndMetadata
from connectors.canva.canva_documents import CanvaDesignDocumentMetadata
from src.utils.logging import get_logger

if TYPE_CHECKING:
    from src.mcp.api.citation_resolver import CitationResolver

logger = get_logger(__name__)

# Canva URLs follow this pattern:
# Edit URL: https://www.canva.com/design/{design_id}/edit
# View URL: https://www.canva.com/design/{design_id}/view
CANVA_APP_BASE_URL = "https://www.canva.com"


class CanvaDesignCitationResolver(BaseCitationResolver[CanvaDesignDocumentMetadata]):
    """Resolver for Canva design citations."""

    async def resolve_citation(
        self,
        document: DocumentWithSourceAndMetadata[CanvaDesignDocumentMetadata],
        _excerpt: str,
        _resolver: CitationResolver,
    ) -> str:
        """Generate Canva design URL.

        Uses the edit_url from metadata if available, otherwise constructs
        a URL using the design_id.
        """
        # Prefer the stored edit_url from the API response
        edit_url = document.metadata.get("edit_url")
        if edit_url:
            return edit_url

        # Fallback: try view_url
        view_url = document.metadata.get("view_url")
        if view_url:
            return view_url

        # Last resort: construct URL from design_id
        design_id = document.metadata.get("design_id")
        if not design_id:
            return ""

        return f"{CANVA_APP_BASE_URL}/design/{design_id}/edit"
