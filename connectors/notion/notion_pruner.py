"""Notion page pruner for handling complete deletion flow."""

import logging

import asyncpg

from connectors.base import BasePruner
from connectors.base.doc_ids import get_notion_doc_id

logger = logging.getLogger(__name__)


class NotionPruner(BasePruner):
    """Singleton class for handling Notion page deletions across all data stores."""

    async def delete_page(
        self,
        page_id: str,
        tenant_id: str,
        db_pool: asyncpg.Pool,
    ) -> bool:
        """
        Delete a Notion page from all data stores using the standardized template method.

        Args:
            page_id: The Notion page ID to delete
            tenant_id: The tenant ID
            db_pool: Database connection pool

        Returns:
            True if deletion was successful, False otherwise
        """
        if not page_id:
            logger.warning("No page_id provided for deletion")
            return False

        logger.info(f"Deleting Notion page: {page_id}")

        # Use the template method from BasePruner
        # Pass the notion document ID resolver directly
        return await self.delete_entity(
            entity_id=page_id,
            tenant_id=tenant_id,
            db_pool=db_pool,
            document_id_resolver=get_notion_doc_id,
            entity_type="notion_page",
        )


# Singleton instance
notion_pruner = NotionPruner()
