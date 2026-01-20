"""Google Drive citation resolver."""

from __future__ import annotations

from typing import TYPE_CHECKING

from connectors.base import BaseCitationResolver
from connectors.base.document_source import DocumentWithSourceAndMetadata
from connectors.google_drive.google_drive_file_document import GoogleDriveDocumentMetadata
from src.utils.logging import get_logger

if TYPE_CHECKING:
    from src.mcp.api.citation_resolver import CitationResolver

logger = get_logger(__name__)


class GoogleDriveCitationResolver(BaseCitationResolver[GoogleDriveDocumentMetadata]):
    """Resolver for Google Drive document citations."""

    async def resolve_citation(
        self,
        document: DocumentWithSourceAndMetadata[GoogleDriveDocumentMetadata],
        excerpt: str,
        resolver: CitationResolver,
    ) -> str:
        logger.info(
            f"Google Drive resolver: doc_id={document.id}, has_metadata={bool(document.metadata)}"
        )
        link = document.metadata.get("web_view_link")
        if not link:
            logger.warning(
                f"Document {document.id} has no web view link, unable to resolve citation"
            )
            return ""

        return link
