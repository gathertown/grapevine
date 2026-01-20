"""Citation resolver for Monday.com documents."""

from __future__ import annotations

from typing import TYPE_CHECKING

from connectors.base import BaseCitationResolver
from connectors.base.document_source import DocumentWithSourceAndMetadata
from connectors.monday.client import MONDAY_ITEM_DOC_ID_PREFIX
from connectors.monday.transformers.monday_item_document import MondayItemDocumentMetadata
from src.utils.logging import get_logger

if TYPE_CHECKING:
    from src.mcp.api.citation_resolver import CitationResolver

logger = get_logger(__name__)

# Monday.com base URL for deep links
MONDAY_BASE_URL = "https://monday.com"


class MondayCitationResolver(BaseCitationResolver[MondayItemDocumentMetadata]):
    """Resolve citations for Monday.com item documents."""

    async def resolve_citation(
        self,
        document: DocumentWithSourceAndMetadata[MondayItemDocumentMetadata],
        _excerpt: str,
        _resolver: CitationResolver,
    ) -> str:
        """
        Generate a deep link URL to the Monday.com item.

        Monday.com item URLs follow the pattern:
        https://monday.com/boards/{board_id}/pulses/{item_id}
        """
        item_id = document.metadata.get("item_id")
        board_id = document.metadata.get("board_id")

        if item_id and board_id:
            return f"{MONDAY_BASE_URL}/boards/{board_id}/pulses/{item_id}"

        # Fallback: try to extract item_id from document.id (format: monday_item_{item_id})
        if document.id.startswith(MONDAY_ITEM_DOC_ID_PREFIX):
            extracted_id = document.id[len(MONDAY_ITEM_DOC_ID_PREFIX) :]
            # Without board_id, we can't generate a complete URL
            if board_id:
                return f"{MONDAY_BASE_URL}/boards/{board_id}/pulses/{extracted_id}"

        # Last resort: log warning and return base Monday URL
        logger.warning(
            "Could not extract item_id or board_id for citation",
            document_id=document.id,
        )
        return MONDAY_BASE_URL


# Singleton instance for use in citation resolver registry
monday_citation_resolver = MondayCitationResolver()
