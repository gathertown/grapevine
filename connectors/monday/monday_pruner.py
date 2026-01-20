"""Monday.com pruner for cleaning up deleted/archived items."""

import asyncpg

from connectors.base import BasePruner, get_monday_item_entity_id
from connectors.base.document_source import DocumentSource
from connectors.monday.client import MONDAY_ITEM_DOC_ID_PREFIX, get_monday_client_for_tenant
from src.clients.ssm import SSMClient
from src.utils.logging import get_logger

logger = get_logger(__name__)

# Batch size for checking items
PRUNE_BATCH_SIZE = 100


def get_monday_item_doc_id(item_id: int | str) -> str:
    """Get document ID for a Monday.com item."""
    return f"{MONDAY_ITEM_DOC_ID_PREFIX}{item_id}"


class MondayPruner(BasePruner):
    """Prunes Monday.com items that have been deleted or archived.

    This pruner:
    1. Gets all indexed Monday.com item IDs from the database
    2. Checks each item's current state in Monday.com
    3. Marks deleted/archived items for removal from the index
    """

    def __init__(self, ssm_client: SSMClient | None = None):
        self.ssm_client = ssm_client

    async def delete_item(self, item_id: int, tenant_id: str, db_pool: asyncpg.Pool) -> bool:
        """Delete a Monday.com item from all data stores.

        Args:
            item_id: The Monday.com item ID
            tenant_id: The tenant ID
            db_pool: Database connection pool

        Returns:
            True if deletion was successful, False otherwise
        """
        if not item_id:
            logger.warning("No item_id provided for Monday.com item deletion")
            return False

        logger.info(f"Deleting Monday.com item: {item_id}")

        # Use the same entity_id format used when storing artifacts
        entity_id = get_monday_item_entity_id(item_id=item_id)

        return await self.delete_entity(
            entity_id=entity_id,
            tenant_id=tenant_id,
            db_pool=db_pool,
            document_id_resolver=get_monday_item_doc_id,
            entity_type="monday_item",
        )

    async def find_stale_documents(
        self,
        tenant_id: str,
        db_pool: asyncpg.Pool,
    ) -> list[str]:
        """Find Monday.com documents that should be removed.

        Args:
            tenant_id: Tenant identifier
            db_pool: Database connection pool

        Returns:
            List of document IDs to delete
        """
        if self.ssm_client is None:
            logger.error("SSM client required for find_stale_documents")
            return []

        try:
            monday_client = await get_monday_client_for_tenant(tenant_id, self.ssm_client)
        except Exception as e:
            logger.error(f"Failed to get Monday.com client for pruning: {e}")
            return []

        # Get all indexed Monday.com item IDs
        async with db_pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id FROM documents
                WHERE source = $1
                """,
                DocumentSource.MONDAY_ITEM.value,
            )

        indexed_doc_ids = [row["id"] for row in rows]
        if not indexed_doc_ids:
            logger.info("No Monday.com documents to prune")
            return []

        # Extract item IDs from document IDs
        # Document IDs are in format: monday_item_{item_id}
        indexed_item_ids: dict[int, str] = {}
        for doc_id in indexed_doc_ids:
            try:
                item_id_str = doc_id.replace(MONDAY_ITEM_DOC_ID_PREFIX, "")
                item_id = int(item_id_str)
                indexed_item_ids[item_id] = doc_id
            except (ValueError, TypeError):
                continue

        if not indexed_item_ids:
            return []

        logger.info(f"Checking {len(indexed_item_ids)} indexed Monday.com items for staleness")

        # Check items in batches
        stale_doc_ids: list[str] = []
        item_ids_list = list(indexed_item_ids.keys())

        for i in range(0, len(item_ids_list), PRUNE_BATCH_SIZE):
            batch_ids = item_ids_list[i : i + PRUNE_BATCH_SIZE]

            try:
                items = monday_client.get_items_batch(batch_ids)
                active_item_ids = {int(item["id"]) for item in items}

                # Items not returned or in deleted/archived state are stale
                for item_id in batch_ids:
                    if item_id not in active_item_ids:
                        doc_id = indexed_item_ids[item_id]
                        stale_doc_ids.append(doc_id)
                    else:
                        # Check state
                        for item in items:
                            if int(item["id"]) == item_id:
                                state = item.get("state", "active")
                                if state in ("deleted", "archived"):
                                    doc_id = indexed_item_ids[item_id]
                                    stale_doc_ids.append(doc_id)
                                break

            except Exception as e:
                logger.warning(f"Failed to check item batch for staleness: {e}")
                continue

        logger.info(f"Found {len(stale_doc_ids)} stale Monday.com documents")
        return stale_doc_ids
