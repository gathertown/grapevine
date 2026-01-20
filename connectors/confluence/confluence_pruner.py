"""Confluence pruner for handling complete deletion flow."""

import logging

import asyncpg

from connectors.base import BasePruner
from connectors.base.doc_ids import get_confluence_page_doc_id, get_confluence_space_doc_id

logger = logging.getLogger(__name__)


class ConfluencePruner(BasePruner):
    """Singleton class for handling Confluence page and space deletions across all data stores."""

    async def delete_page(self, page_id: str, tenant_id: str, db_pool: asyncpg.Pool) -> bool:
        """
        Delete a Confluence page from all data stores using the standardized template method.

        Args:
            page_id: The Confluence internal page ID (numeric string format, e.g., "123456789")
            tenant_id: The tenant ID
            db_pool: Database connection pool (required)

        Returns:
            True if deletion was successful, False otherwise
        """
        if not page_id:
            logger.warning("No page_id provided for Confluence page deletion")
            return False

        logger.info(f"Deleting Confluence page: {page_id}")

        # Use the template method from BasePruner
        # Pass the confluence page document ID resolver directly
        return await self.delete_entity(
            entity_id=page_id,
            tenant_id=tenant_id,
            db_pool=db_pool,
            document_id_resolver=get_confluence_page_doc_id,
            entity_type="confluence_page",
        )

    async def delete_space(self, space_id: str, tenant_id: str, db_pool: asyncpg.Pool) -> bool:
        """
        Delete a Confluence space and all its pages from all data stores.

        This implements cascading deletion:
        1. Find all pages in the space
        2. Delete each page individually
        3. Delete the space artifact itself

        Args:
            space_id: The Confluence internal space ID (numeric string format, e.g., "987654321")
            tenant_id: The tenant ID
            db_pool: Database connection pool (required)

        Returns:
            True if deletion was successful, False otherwise
        """
        if not space_id:
            logger.warning("No space_id provided for Confluence space deletion")
            return False

        logger.info(f"Deleting Confluence space: {space_id}")

        try:
            async with db_pool.acquire() as conn:
                page_rows = await conn.fetch(
                    "SELECT entity_id FROM ingest_artifact WHERE entity = $1 AND metadata->>'space_id' = $2",
                    "confluence_page",
                    space_id,
                )
                page_ids = [row["entity_id"] for row in page_rows]

                logger.info(f"Found {len(page_ids)} pages to delete in space {space_id}")

                failed_pages = []
                for page_id in page_ids:
                    try:
                        success = await self.delete_page(page_id, tenant_id, db_pool)
                        if not success:
                            failed_pages.append(page_id)
                            logger.error(f"Failed to delete page {page_id} in space {space_id}")
                    except Exception as e:
                        failed_pages.append(page_id)
                        logger.error(f"Exception deleting page {page_id} in space {space_id}: {e}")

                space_artifacts_deleted = await self.delete_artifacts(
                    conn, "confluence_space", space_id
                )

                space_document_id = get_confluence_space_doc_id(space_id)
                space_doc_success = await self.delete_document(
                    space_document_id, tenant_id, db_pool
                )

                if failed_pages:
                    logger.error(
                        f"❌ Space deletion partially failed: {len(failed_pages)} pages failed to delete "
                        f"in space {space_id}: {failed_pages}"
                    )
                    return False
                else:
                    logger.info(
                        f"✅ Successfully deleted space {space_id} "
                        f"(pages: {len(page_ids)}, space artifacts: {space_artifacts_deleted}, "
                        f"space document: {'success' if space_doc_success else 'not found'})"
                    )
                    return True

        except Exception as e:
            logger.error(f"❌ Error deleting Confluence space {space_id}: {e}")
            return False


confluence_pruner = ConfluencePruner()
