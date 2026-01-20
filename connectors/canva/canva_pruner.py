"""Canva pruner for cleaning up deleted designs.

This pruner handles designs that have been deleted from Canva.

IMPORTANT: Tenant Isolation
- The db_pool parameter MUST be a tenant-scoped database pool
- OpenSearch operations use tenant_opensearch_manager which handles tenant isolation
- Callers are responsible for ensuring the db_pool matches the tenant_id
"""

import asyncpg

from connectors.base import BasePruner
from connectors.base.base_ingest_artifact import get_canva_design_entity_id
from connectors.base.document_source import DocumentSource
from connectors.canva.client import CanvaClient, get_canva_client_for_tenant
from src.utils.logging import get_logger

logger = get_logger(__name__)

# Document ID prefix
CANVA_DESIGN_DOC_ID_PREFIX = "canva_design_"

# Safety threshold: abort if more than this percentage would be deleted
# Protects against API returning empty/partial results due to errors
MAX_DELETION_RATIO = 0.7  # 70%


def get_canva_design_doc_id(design_id: str) -> str:
    """Get document ID for a Canva design."""
    return f"{CANVA_DESIGN_DOC_ID_PREFIX}{design_id}"


class CanvaPruner(BasePruner):
    """Prunes Canva designs that have been deleted.

    This pruner:
    1. Gets all indexed Canva design IDs from the database
    2. Checks each design's current state in Canva
    3. Marks deleted designs for removal from the index
    """

    async def delete_design(self, design_id: str, tenant_id: str, db_pool: asyncpg.Pool) -> bool:
        """Delete a Canva design from all data stores.

        Args:
            design_id: The Canva design ID
            tenant_id: The tenant ID
            db_pool: Database connection pool

        Returns:
            True if deletion was successful, False otherwise
        """
        if not design_id:
            logger.warning("No design_id provided for Canva design deletion")
            return False

        logger.info(f"Deleting Canva design: {design_id}")
        entity_id = get_canva_design_entity_id(design_id=design_id)

        return await self.delete_entity(
            entity_id=entity_id,
            tenant_id=tenant_id,
            db_pool=db_pool,
            document_id_resolver=lambda eid: eid,  # entity_id == doc_id
            entity_type="canva_design",
        )

    async def find_stale_documents(
        self,
        tenant_id: str,
        db_pool: asyncpg.Pool,
    ) -> list[str]:
        """Find Canva documents that should be removed.

        A design is considered stale if it no longer exists in Canva.

        Args:
            tenant_id: Tenant identifier
            db_pool: Database connection pool

        Returns:
            List of document IDs to delete
        """
        try:
            client = await get_canva_client_for_tenant(tenant_id)
        except Exception as e:
            logger.error(f"Failed to get Canva client for pruning: {e}")
            return []

        try:
            stale_doc_ids = await self._find_stale_designs(client, db_pool)
            logger.info(f"Found {len(stale_doc_ids)} stale Canva documents")
            return stale_doc_ids
        finally:
            await client.close()

    async def _find_stale_designs(
        self,
        client: CanvaClient,
        db_pool: asyncpg.Pool,
    ) -> list[str]:
        """Find stale design documents."""
        async with db_pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT id FROM documents WHERE source = $1",
                DocumentSource.CANVA_DESIGN.value,
            )

        if not rows:
            return []

        # Get all current designs from Canva
        active_ids: set[str] = set()
        try:
            async for design in client.iter_all_designs(ownership="any"):
                if design.id:
                    active_ids.add(design.id)
        except Exception as e:
            logger.warning(f"Failed to get designs for staleness check: {e}")
            return []

        # Safety guard: if API returns empty but we have indexed docs, abort
        # This protects against API errors/scope loss causing mass deletions
        if not active_ids and rows:
            logger.warning(
                "Canva API returned no designs but we have indexed documents. "
                "Aborting staleness check to prevent mass deletion. "
                f"Indexed documents: {len(rows)}"
            )
            return []

        # Find stale documents
        stale_doc_ids: list[str] = []
        for row in rows:
            doc_id = row["id"]
            design_id = doc_id.replace(CANVA_DESIGN_DOC_ID_PREFIX, "")
            if design_id not in active_ids:
                stale_doc_ids.append(doc_id)

        # Safety guard: abort if deletion ratio is too high (likely API issue)
        if rows and len(stale_doc_ids) / len(rows) >= MAX_DELETION_RATIO:
            logger.warning(
                f"Canva staleness check would delete {len(stale_doc_ids)}/{len(rows)} "
                f"documents ({len(stale_doc_ids) / len(rows):.1%}). "
                "Aborting to prevent mass deletion due to potential API issue."
            )
            return []

        logger.info(f"Found {len(stale_doc_ids)} stale Canva designs")
        return stale_doc_ids


# Singleton instance
canva_pruner = CanvaPruner()
