"""Notion citation resolver."""

from __future__ import annotations

from difflib import SequenceMatcher
from typing import TYPE_CHECKING

from connectors.base import BaseCitationResolver
from connectors.base.document_source import DocumentWithSourceAndMetadata
from connectors.notion.notion_page_document import NotionPageDocumentMetadata
from src.clients.turbopuffer import MAX_TOP_K, get_turbopuffer_client
from src.utils.logging import get_logger

if TYPE_CHECKING:
    from src.mcp.api.citation_resolver import CitationResolver

logger = get_logger(__name__)


class NotionCitationResolver(BaseCitationResolver[NotionPageDocumentMetadata]):
    """Resolver for Notion page citations."""

    async def resolve_citation(
        self,
        document: DocumentWithSourceAndMetadata[NotionPageDocumentMetadata],
        excerpt: str,
        resolver: CitationResolver,
    ) -> str:
        logger.info(f"Notion resolver: doc_id={document.id}")

        page_id = document.metadata.get("page_id")
        if not page_id:
            logger.warning(f"No page_id found in document metadata: {document.metadata}")
            return ""

        # Fallback to page-level URL
        page_url = document.metadata.get("page_url")
        if not page_url:
            logger.warning(f"Constructing page URL from page_id: {page_id}")
            page_url = f"https://notion.so/{page_id.replace('-', '')}"

        # Try to find specific block that contains the excerpt
        block_id = await self._find_block_id_for_excerpt(document.id, excerpt, resolver)

        if block_id:
            # Create Notion block URL: remove dashes from block ID for the anchor
            block_anchor = block_id.replace("-", "")
            block_url = f"{page_url}#{block_anchor}"
            logger.info(f"Found block-level citation: {block_url}")
            return block_url

        logger.warning(f"Didn't find a block-level citation, using page-level citation: {page_url}")
        return page_url

    async def _find_block_id_for_excerpt(
        self, document_id: str, excerpt: str, resolver: CitationResolver
    ) -> str | None:
        """Find the first block ID from the chunk that contains the excerpt."""
        try:
            # Query Turbopuffer for all chunks for this document to get block IDs
            turbopuffer_client = get_turbopuffer_client()
            chunks = await turbopuffer_client.query_chunks(
                tenant_id=resolver.tenant_id,
                query_vector=None,  # Use metadata-based ranking, not vector similarity
                filters=("document_id", "Eq", document_id),
                include_attributes=["content", "notion_block_ids"],
                top_k=MAX_TOP_K,  # Get all chunks for this document
            )

            if not chunks:
                logger.warning(f"No chunks found for document {document_id}")
                return None

            # Use fuzzy matching to find the best matching chunk
            best_match_chunk = None
            best_ratio = 0.0

            logger.info(f"Searching {len(chunks)} chunks for excerpt")

            for chunk in chunks:
                chunk_content = chunk.get("content") or ""
                notion_block_ids = chunk.get("notion_block_ids")

                if not notion_block_ids or not isinstance(notion_block_ids, list):
                    # This isn't unexpected, e.g. header chunks won't have block IDs
                    logger.info(f"No notion_block_ids found in chunk: {chunk.get('id')} ")
                    continue

                # Calculate similarity ratio between excerpt and chunk content
                ratio = SequenceMatcher(None, excerpt.strip(), chunk_content.strip()).ratio()
                logger.debug(
                    f"Chunk similarity: {ratio:.3f} for notion_block_ids: {notion_block_ids[:2]}..."
                )

                if ratio > best_ratio:
                    best_ratio = ratio
                    best_match_chunk = chunk

            if best_match_chunk:
                notion_block_ids = best_match_chunk["notion_block_ids"]
                if not notion_block_ids:
                    logger.warning("Empty notion_block_ids in best match chunk")
                    return None
                first_block_id = notion_block_ids[0]
                logger.info(
                    f"Found best matching chunk (ratio: {best_ratio:.3f}) with block ID: {first_block_id}"
                )

                # If the best block ID is the same as the document ID, link to the whole page instead
                if first_block_id == document_id:
                    logger.debug(
                        f"Block ID {first_block_id} matches document ID, will link to whole page"
                    )
                    return None  # This will cause fallback to page-level URL

                return first_block_id

            logger.warning(f"No chunks with notion_block_ids found for document {document_id}")
            return None

        except Exception as e:
            logger.error(f"Error finding block ID for excerpt in document {document_id}: {e}")
            return None
