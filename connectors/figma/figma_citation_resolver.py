"""Figma citation resolvers."""

from __future__ import annotations

from typing import TYPE_CHECKING

from connectors.base import BaseCitationResolver
from connectors.base.document_source import DocumentWithSourceAndMetadata
from connectors.figma.figma_documents import (
    FigmaCommentDocumentMetadata,
    FigmaFileDocumentMetadata,
)
from src.utils.logging import get_logger

if TYPE_CHECKING:
    from src.mcp.api.citation_resolver import CitationResolver

logger = get_logger(__name__)

# Figma URLs follow this pattern:
# Files: https://www.figma.com/file/{file_key}
# Files (design): https://www.figma.com/design/{file_key}
# FigJam: https://www.figma.com/board/{file_key}
# Comments: https://www.figma.com/file/{file_key}?comment={comment_id}
FIGMA_APP_BASE_URL = "https://www.figma.com"


class FigmaFileCitationResolver(BaseCitationResolver[FigmaFileDocumentMetadata]):
    """Resolver for Figma file citations."""

    async def resolve_citation(
        self,
        document: DocumentWithSourceAndMetadata[FigmaFileDocumentMetadata],
        _excerpt: str,
        _resolver: CitationResolver,
    ) -> str:
        """Generate Figma file URL.

        Figma file URLs follow the format:
        - Design files: https://www.figma.com/design/{file_key}
        - FigJam boards: https://www.figma.com/board/{file_key}
        """
        file_key = document.metadata.get("file_key")
        if not file_key:
            return ""

        editor_type = document.metadata.get("editor_type", "figma")

        # Use different URL paths based on editor type
        if editor_type == "figjam":
            return f"{FIGMA_APP_BASE_URL}/board/{file_key}"
        else:
            return f"{FIGMA_APP_BASE_URL}/design/{file_key}"


class FigmaCommentCitationResolver(BaseCitationResolver[FigmaCommentDocumentMetadata]):
    """Resolver for Figma comment citations."""

    async def resolve_citation(
        self,
        document: DocumentWithSourceAndMetadata[FigmaCommentDocumentMetadata],
        _excerpt: str,
        _resolver: CitationResolver,
    ) -> str:
        """Generate Figma comment URL.

        Figma comment URLs follow the format:
        - Design files: https://www.figma.com/design/{file_key}?comment-id={comment_id}
        - FigJam boards: https://www.figma.com/board/{file_key}?comment-id={comment_id}

        Note: For replies, we link to the parent comment thread.
        """
        file_key = document.metadata.get("file_key")
        comment_id = document.metadata.get("comment_id")
        editor_type = document.metadata.get("editor_type", "figma")

        if not file_key:
            return ""

        # Use different URL paths based on editor type
        url_path = "board" if editor_type == "figjam" else "design"

        # For replies, use the parent_id to link to the thread
        parent_id = document.metadata.get("parent_id")
        target_comment = parent_id if parent_id else comment_id

        if not target_comment:
            # If we don't have a comment ID, just link to the file
            return f"{FIGMA_APP_BASE_URL}/{url_path}/{file_key}"

        return f"{FIGMA_APP_BASE_URL}/{url_path}/{file_key}?comment-id={target_comment}"
