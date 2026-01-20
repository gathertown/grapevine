"""Gong citation resolver."""

from __future__ import annotations

from typing import TYPE_CHECKING

from connectors.base import BaseCitationResolver
from connectors.base.document_source import DocumentWithSourceAndMetadata
from connectors.gong.gong_call_document import GongCallDocumentMetadata
from src.utils.logging import get_logger

if TYPE_CHECKING:
    from src.mcp.api.citation_resolver import CitationResolver

logger = get_logger(__name__)


class GongCitationResolver(BaseCitationResolver[GongCallDocumentMetadata]):
    """Resolver for Gong call citations."""

    async def resolve_citation(
        self,
        document: DocumentWithSourceAndMetadata[GongCallDocumentMetadata],
        excerpt: str,
        resolver: CitationResolver,
    ) -> str:
        # Generate Gong call URL from metadata
        url = document.metadata.get("url")
        if url:
            return url

        return ""
