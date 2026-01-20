"""Pipedrive pruner for cleaning up deleted entities.

This pruner handles deleted:
- Deals
- Persons
- Organizations
- Products

IMPORTANT: Tenant Isolation
- The db_pool parameter MUST be a tenant-scoped database pool
- OpenSearch operations use tenant_opensearch_manager which handles tenant isolation
- Callers are responsible for ensuring the db_pool matches the tenant_id

TODO: Performance Improvement
Consider migrating to database-driven staleness detection using last_seen_backfill_id
(see migrations/tenant/20251116210022_add_last_seen_backfill_id_to_track_stale_entities.sql
and connectors/gong/gong_pruner.py for the pattern). The current implementation enumerates
all entities via the API which is slower and rate-limited for large datasets.
"""

import asyncio

import asyncpg

from connectors.base import BasePruner
from connectors.base.base_ingest_artifact import (
    get_pipedrive_deal_entity_id,
    get_pipedrive_organization_entity_id,
    get_pipedrive_person_entity_id,
    get_pipedrive_product_entity_id,
)
from connectors.base.document_source import DocumentSource
from connectors.pipedrive.pipedrive_client import (
    PipedriveClient,
    get_pipedrive_client_for_tenant,
)
from src.clients.ssm import SSMClient
from src.utils.logging import get_logger

logger = get_logger(__name__)

# Batch size for checking entities
PRUNE_BATCH_SIZE = 100

# Safety threshold: abort if more than this percentage would be deleted
# Protects against API returning empty/partial results due to errors
MAX_DELETION_RATIO = 0.7  # 70%

# Document ID prefixes
PIPEDRIVE_DEAL_DOC_ID_PREFIX = "pipedrive_deal_"
PIPEDRIVE_PERSON_DOC_ID_PREFIX = "pipedrive_person_"
PIPEDRIVE_ORGANIZATION_DOC_ID_PREFIX = "pipedrive_organization_"
PIPEDRIVE_PRODUCT_DOC_ID_PREFIX = "pipedrive_product_"


def get_pipedrive_deal_doc_id(deal_id: int) -> str:
    """Get document ID for a Pipedrive deal."""
    return f"{PIPEDRIVE_DEAL_DOC_ID_PREFIX}{deal_id}"


def get_pipedrive_person_doc_id(person_id: int) -> str:
    """Get document ID for a Pipedrive person."""
    return f"{PIPEDRIVE_PERSON_DOC_ID_PREFIX}{person_id}"


def get_pipedrive_organization_doc_id(org_id: int) -> str:
    """Get document ID for a Pipedrive organization."""
    return f"{PIPEDRIVE_ORGANIZATION_DOC_ID_PREFIX}{org_id}"


def get_pipedrive_product_doc_id(product_id: int) -> str:
    """Get document ID for a Pipedrive product."""
    return f"{PIPEDRIVE_PRODUCT_DOC_ID_PREFIX}{product_id}"


def _collect_all_deal_ids(client: PipedriveClient, limit: int) -> set[int]:
    """Collect all deal IDs from Pipedrive (sync, runs in thread)."""
    active_ids: set[int] = set()
    for page in client.iterate_deals(limit=limit):
        for deal in page:
            deal_id = deal.get("id")
            if deal_id:
                active_ids.add(int(deal_id))
    return active_ids


def _collect_all_person_ids(client: PipedriveClient, limit: int) -> set[int]:
    """Collect all person IDs from Pipedrive (sync, runs in thread)."""
    active_ids: set[int] = set()
    for page in client.iterate_persons(limit=limit):
        for person in page:
            person_id = person.get("id")
            if person_id:
                active_ids.add(int(person_id))
    return active_ids


def _collect_all_organization_ids(client: PipedriveClient, limit: int) -> set[int]:
    """Collect all organization IDs from Pipedrive (sync, runs in thread)."""
    active_ids: set[int] = set()
    for page in client.iterate_organizations(limit=limit):
        for org in page:
            org_id = org.get("id")
            if org_id:
                active_ids.add(int(org_id))
    return active_ids


def _collect_all_product_ids(client: PipedriveClient, limit: int) -> set[int]:
    """Collect all product IDs from Pipedrive (sync, runs in thread)."""
    active_ids: set[int] = set()
    for page in client.iterate_products(limit=limit):
        for product in page:
            product_id = product.get("id")
            if product_id:
                active_ids.add(int(product_id))
    return active_ids


class PipedrivePruner(BasePruner):
    """Prunes Pipedrive entities that have been deleted.

    This pruner:
    1. Gets all indexed Pipedrive entity IDs from the database
    2. Checks each entity's current state in Pipedrive
    3. Marks deleted entities for removal from the index
    """

    async def delete_deal(self, deal_id: int, tenant_id: str, db_pool: asyncpg.Pool) -> bool:
        """Delete a Pipedrive deal from all data stores."""
        if not deal_id:
            logger.warning("No deal_id provided for Pipedrive deal deletion")
            return False

        logger.info(f"Deleting Pipedrive deal: {deal_id}")
        entity_id = get_pipedrive_deal_entity_id(deal_id=deal_id)

        return await self.delete_entity(
            entity_id=entity_id,
            tenant_id=tenant_id,
            db_pool=db_pool,
            document_id_resolver=lambda eid: eid,  # entity_id == doc_id
            entity_type="pipedrive_deal",
        )

    async def delete_person(self, person_id: int, tenant_id: str, db_pool: asyncpg.Pool) -> bool:
        """Delete a Pipedrive person from all data stores."""
        if not person_id:
            logger.warning("No person_id provided for Pipedrive person deletion")
            return False

        logger.info(f"Deleting Pipedrive person: {person_id}")
        entity_id = get_pipedrive_person_entity_id(person_id=person_id)

        return await self.delete_entity(
            entity_id=entity_id,
            tenant_id=tenant_id,
            db_pool=db_pool,
            document_id_resolver=lambda eid: eid,
            entity_type="pipedrive_person",
        )

    async def delete_organization(self, org_id: int, tenant_id: str, db_pool: asyncpg.Pool) -> bool:
        """Delete a Pipedrive organization from all data stores."""
        if not org_id:
            logger.warning("No org_id provided for Pipedrive organization deletion")
            return False

        logger.info(f"Deleting Pipedrive organization: {org_id}")
        entity_id = get_pipedrive_organization_entity_id(org_id=org_id)

        return await self.delete_entity(
            entity_id=entity_id,
            tenant_id=tenant_id,
            db_pool=db_pool,
            document_id_resolver=lambda eid: eid,
            entity_type="pipedrive_organization",
        )

    async def delete_product(self, product_id: int, tenant_id: str, db_pool: asyncpg.Pool) -> bool:
        """Delete a Pipedrive product from all data stores."""
        if not product_id:
            logger.warning("No product_id provided for Pipedrive product deletion")
            return False

        logger.info(f"Deleting Pipedrive product: {product_id}")
        entity_id = get_pipedrive_product_entity_id(product_id=product_id)

        return await self.delete_entity(
            entity_id=entity_id,
            tenant_id=tenant_id,
            db_pool=db_pool,
            document_id_resolver=lambda eid: eid,
            entity_type="pipedrive_product",
        )

    async def find_stale_documents(
        self,
        tenant_id: str,
        db_pool: asyncpg.Pool,
        ssm_client: SSMClient | None = None,
    ) -> list[str]:
        """Find Pipedrive documents that should be removed.

        A document is considered stale if it no longer exists in Pipedrive.

        Args:
            tenant_id: Tenant identifier
            db_pool: Database connection pool
            ssm_client: SSM client for retrieving Pipedrive credentials (REQUIRED)

        Returns:
            List of document IDs to delete
        """
        if ssm_client is None:
            logger.error("SSM client required for find_stale_documents")
            return []

        try:
            client = await get_pipedrive_client_for_tenant(tenant_id, ssm_client)
        except Exception as e:
            logger.error(f"Failed to get Pipedrive client for pruning: {e}")
            return []

        # Note: PipedriveClient uses sync requests.Session which doesn't strictly require
        # explicit cleanup. However, we use try-finally for consistency with other pruners
        # (Canva, PostHog) and to support future migration to async httpx if needed.
        try:
            stale_doc_ids: list[str] = []

            # Check each entity type
            stale_doc_ids.extend(await self._find_stale_deals(client, db_pool))
            stale_doc_ids.extend(await self._find_stale_persons(client, db_pool))
            stale_doc_ids.extend(await self._find_stale_organizations(client, db_pool))
            stale_doc_ids.extend(await self._find_stale_products(client, db_pool))

            logger.info(f"Found {len(stale_doc_ids)} stale Pipedrive documents")
            return stale_doc_ids
        finally:
            # PipedriveClient uses sync requests.Session - close it for resource cleanup
            if hasattr(client, "session") and client.session:
                client.session.close()

    async def _find_stale_deals(
        self,
        client: PipedriveClient,
        db_pool: asyncpg.Pool,
    ) -> list[str]:
        """Find stale deal documents."""
        async with db_pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT id FROM documents WHERE source = $1",
                DocumentSource.PIPEDRIVE_DEAL.value,
            )

        if not rows:
            return []

        # Get all current deals from Pipedrive (offload sync HTTP to thread)
        try:
            active_ids = await asyncio.to_thread(_collect_all_deal_ids, client, PRUNE_BATCH_SIZE)
        except Exception as e:
            logger.warning(f"Failed to get deals for staleness check: {e}")
            return []

        # Safety guard: if API returns empty but we have indexed docs, abort
        # This protects against API errors/scope loss causing mass deletions
        if not active_ids and rows:
            logger.warning(
                "Pipedrive API returned no deals but we have indexed documents. "
                "Aborting staleness check to prevent mass deletion. "
                f"Indexed documents: {len(rows)}"
            )
            return []

        # Find stale documents
        stale_doc_ids: list[str] = []
        for row in rows:
            doc_id = row["id"]
            try:
                deal_id_str = doc_id.replace(PIPEDRIVE_DEAL_DOC_ID_PREFIX, "")
                deal_id = int(deal_id_str)
                if deal_id not in active_ids:
                    stale_doc_ids.append(doc_id)
            except (ValueError, TypeError):
                continue

        # Safety guard: abort if deletion ratio is too high (likely API issue)
        if rows and len(stale_doc_ids) / len(rows) >= MAX_DELETION_RATIO:
            logger.warning(
                f"Pipedrive deals staleness check would delete {len(stale_doc_ids)}/{len(rows)} "
                f"documents ({len(stale_doc_ids) / len(rows):.1%}). "
                "Aborting to prevent mass deletion due to potential API issue."
            )
            return []

        logger.info(f"Found {len(stale_doc_ids)} stale Pipedrive deals")
        return stale_doc_ids

    async def _find_stale_persons(
        self,
        client: PipedriveClient,
        db_pool: asyncpg.Pool,
    ) -> list[str]:
        """Find stale person documents."""
        async with db_pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT id FROM documents WHERE source = $1",
                DocumentSource.PIPEDRIVE_PERSON.value,
            )

        if not rows:
            return []

        # Get all current persons from Pipedrive (offload sync HTTP to thread)
        try:
            active_ids = await asyncio.to_thread(_collect_all_person_ids, client, PRUNE_BATCH_SIZE)
        except Exception as e:
            logger.warning(f"Failed to get persons for staleness check: {e}")
            return []

        # Safety guard: if API returns empty but we have indexed docs, abort
        if not active_ids and rows:
            logger.warning(
                "Pipedrive API returned no persons but we have indexed documents. "
                "Aborting staleness check to prevent mass deletion. "
                f"Indexed documents: {len(rows)}"
            )
            return []

        # Find stale documents
        stale_doc_ids: list[str] = []
        for row in rows:
            doc_id = row["id"]
            try:
                person_id_str = doc_id.replace(PIPEDRIVE_PERSON_DOC_ID_PREFIX, "")
                person_id = int(person_id_str)
                if person_id not in active_ids:
                    stale_doc_ids.append(doc_id)
            except (ValueError, TypeError):
                continue

        # Safety guard: abort if deletion ratio is too high (likely API issue)
        if rows and len(stale_doc_ids) / len(rows) >= MAX_DELETION_RATIO:
            logger.warning(
                f"Pipedrive persons staleness check would delete {len(stale_doc_ids)}/{len(rows)} "
                f"documents ({len(stale_doc_ids) / len(rows):.1%}). "
                "Aborting to prevent mass deletion due to potential API issue."
            )
            return []

        logger.info(f"Found {len(stale_doc_ids)} stale Pipedrive persons")
        return stale_doc_ids

    async def _find_stale_organizations(
        self,
        client: PipedriveClient,
        db_pool: asyncpg.Pool,
    ) -> list[str]:
        """Find stale organization documents."""
        async with db_pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT id FROM documents WHERE source = $1",
                DocumentSource.PIPEDRIVE_ORGANIZATION.value,
            )

        if not rows:
            return []

        # Get all current organizations from Pipedrive (offload sync HTTP to thread)
        try:
            active_ids = await asyncio.to_thread(
                _collect_all_organization_ids, client, PRUNE_BATCH_SIZE
            )
        except Exception as e:
            logger.warning(f"Failed to get organizations for staleness check: {e}")
            return []

        # Safety guard: if API returns empty but we have indexed docs, abort
        if not active_ids and rows:
            logger.warning(
                "Pipedrive API returned no organizations but we have indexed documents. "
                "Aborting staleness check to prevent mass deletion. "
                f"Indexed documents: {len(rows)}"
            )
            return []

        # Find stale documents
        stale_doc_ids: list[str] = []
        for row in rows:
            doc_id = row["id"]
            try:
                org_id_str = doc_id.replace(PIPEDRIVE_ORGANIZATION_DOC_ID_PREFIX, "")
                org_id = int(org_id_str)
                if org_id not in active_ids:
                    stale_doc_ids.append(doc_id)
            except (ValueError, TypeError):
                continue

        # Safety guard: abort if deletion ratio is too high (likely API issue)
        if rows and len(stale_doc_ids) / len(rows) >= MAX_DELETION_RATIO:
            logger.warning(
                f"Pipedrive organizations staleness check would delete {len(stale_doc_ids)}/{len(rows)} "
                f"documents ({len(stale_doc_ids) / len(rows):.1%}). "
                "Aborting to prevent mass deletion due to potential API issue."
            )
            return []

        logger.info(f"Found {len(stale_doc_ids)} stale Pipedrive organizations")
        return stale_doc_ids

    async def _find_stale_products(
        self,
        client: PipedriveClient,
        db_pool: asyncpg.Pool,
    ) -> list[str]:
        """Find stale product documents."""
        async with db_pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT id FROM documents WHERE source = $1",
                DocumentSource.PIPEDRIVE_PRODUCT.value,
            )

        if not rows:
            return []

        # Get all current products from Pipedrive (offload sync HTTP to thread)
        try:
            active_ids = await asyncio.to_thread(_collect_all_product_ids, client, PRUNE_BATCH_SIZE)
        except Exception as e:
            logger.warning(f"Failed to get products for staleness check: {e}")
            return []

        # Safety guard: if API returns empty but we have indexed docs, abort
        if not active_ids and rows:
            logger.warning(
                "Pipedrive API returned no products but we have indexed documents. "
                "Aborting staleness check to prevent mass deletion. "
                f"Indexed documents: {len(rows)}"
            )
            return []

        # Find stale documents
        stale_doc_ids: list[str] = []
        for row in rows:
            doc_id = row["id"]
            try:
                product_id_str = doc_id.replace(PIPEDRIVE_PRODUCT_DOC_ID_PREFIX, "")
                product_id = int(product_id_str)
                if product_id not in active_ids:
                    stale_doc_ids.append(doc_id)
            except (ValueError, TypeError):
                continue

        # Safety guard: abort if deletion ratio is too high (likely API issue)
        if rows and len(stale_doc_ids) / len(rows) >= MAX_DELETION_RATIO:
            logger.warning(
                f"Pipedrive products staleness check would delete {len(stale_doc_ids)}/{len(rows)} "
                f"documents ({len(stale_doc_ids) / len(rows):.1%}). "
                "Aborting to prevent mass deletion due to potential API issue."
            )
            return []

        logger.info(f"Found {len(stale_doc_ids)} stale Pipedrive products")
        return stale_doc_ids


# Singleton instance
pipedrive_pruner = PipedrivePruner()
