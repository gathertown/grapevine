"""Base class for source-specific citation resolvers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from connectors.base.document_source import DocumentWithSourceAndMetadata
from src.utils.logging import get_logger

if TYPE_CHECKING:
    from src.mcp.api.citation_resolver import CitationResolver

logger = get_logger(__name__)


class BaseCitationResolver[MetadataT](ABC):
    """Abstract base class for source-specific citation resolvers."""

    @abstractmethod
    async def resolve_citation(
        self,
        document: DocumentWithSourceAndMetadata[MetadataT],
        excerpt: str,
        resolver: CitationResolver,
    ) -> str:
        """Resolve a citation to a deeplink URL.

        Args:
            document: Document with source and metadata
            excerpt: Text excerpt from the citation
            resolver: Main citation resolver for accessing shared functionality

        Returns:
            URL string for the citation, or empty string if no URL can be generated
        """
        pass
