from __future__ import annotations

from typing import TYPE_CHECKING

from connectors.base import BaseCitationResolver
from connectors.base.document_source import DocumentWithSourceAndMetadata
from connectors.fireflies.transformers.fireflies_transcript_document import (
    FirefliesTranscriptDocumentMetadata,
)
from src.utils.logging import get_logger

if TYPE_CHECKING:
    from src.mcp.api.citation_resolver import CitationResolver

logger = get_logger(__name__)


class FirefliesTranscriptCitationResolver(
    BaseCitationResolver[FirefliesTranscriptDocumentMetadata]
):
    async def resolve_citation(
        self,
        document: DocumentWithSourceAndMetadata[FirefliesTranscriptDocumentMetadata],
        excerpt: str,
        resolver: CitationResolver,
    ) -> str:
        return document.metadata["transcript_url"]
