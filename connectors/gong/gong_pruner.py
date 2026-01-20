"""Gong pruner for handling stale document and artifact deletion during full syncs."""

from collections import defaultdict

import asyncpg

from connectors.base import BasePruner
from connectors.base.doc_ids import get_gong_call_doc_id, parse_gong_call_entity_id
from src.utils.logging import get_logger

logger = get_logger(__name__)


class GongPruner(BasePruner):
    """Singleton class for handling Gong stale entity deletions using database-driven approach."""

    async def prune_unmarked_entities(
        self,
        tenant_id: str,
        backfill_id: str,
        db_pool: asyncpg.Pool,
    ) -> dict[str, int]:
        """
        Delete all Gong artifacts that were not marked with the current backfill_id.

        This implements efficient stale entity detection at scale by:
        1. Querying database for all Gong entities not marked with current backfill_id
        2. Grouping by entity type for batch processing
        3. Deleting artifacts in batch operations
        4. Deleting documents (for calls) using BasePruner methods

        Args:
            tenant_id: The tenant ID
            backfill_id: The current backfill ID used to mark seen entities
            db_pool: Database connection pool

        Returns:
            Dictionary mapping entity type to count of deleted entities
        """
        if not backfill_id:
            logger.warning("No backfill_id provided for pruning, skipping")
            return {}

        logger.info(
            "Starting Gong stale entity pruning",
            tenant_id=tenant_id,
            backfill_id=backfill_id,
        )

        deletion_stats: dict[str, int] = defaultdict(int)

        async with db_pool.acquire() as conn:
            # Query for all stale Gong artifacts (efficient single query with indexes)
            stale_artifacts = await conn.fetch(
                """
                SELECT entity, entity_id
                FROM ingest_artifact
                WHERE entity LIKE 'gong_%'
                  AND (last_seen_backfill_id IS NULL OR last_seen_backfill_id != $1)
                """,
                backfill_id,
            )

            # Also query for stale Gong documents directly (double protection)
            stale_documents = await conn.fetch(
                """
                SELECT id
                FROM documents
                WHERE source = 'gong'
                  AND (last_seen_backfill_id IS NULL OR last_seen_backfill_id != $1)
                """,
                backfill_id,
            )

            if not stale_artifacts and not stale_documents:
                logger.info("No stale Gong entities or documents found", tenant_id=tenant_id)
                return deletion_stats

            # Group stale entities by type
            entities_by_type: dict[str, list[str]] = defaultdict(list)
            for row in stale_artifacts:
                entity_type = row["entity"]
                entity_id = row["entity_id"]
                entities_by_type[entity_type].append(entity_id)

            total_stale = sum(len(ids) for ids in entities_by_type.values())
            logger.info(
                "Found stale Gong entities",
                tenant_id=tenant_id,
                total_stale=total_stale,
                by_type={entity_type: len(ids) for entity_type, ids in entities_by_type.items()},
            )

            # Process each entity type
            for entity_type, entity_ids in entities_by_type.items():
                deleted_count = await self._delete_entities_by_type(
                    entity_type, entity_ids, tenant_id, db_pool
                )
                deletion_stats[entity_type] = deleted_count

            # Delete stale documents directly found in documents table
            if stale_documents:
                logger.info(
                    "Deleting stale Gong documents found in documents table",
                    tenant_id=tenant_id,
                    count=len(stale_documents),
                )
                for doc_row in stale_documents:
                    doc_id = doc_row["id"]
                    success = await self.delete_document(doc_id, tenant_id, db_pool)
                    if success:
                        deletion_stats["gong_document_direct"] = (
                            deletion_stats.get("gong_document_direct", 0) + 1
                        )

        logger.info(
            "Gong stale entity pruning completed",
            tenant_id=tenant_id,
            backfill_id=backfill_id,
            deletion_stats=dict(deletion_stats),
            total_deleted=sum(deletion_stats.values()),
        )

        return dict(deletion_stats)

    async def _delete_entities_by_type(
        self,
        entity_type: str,
        entity_ids: list[str],
        tenant_id: str,
        pool: asyncpg.Pool,
    ) -> int:
        """
        Delete entities of a specific type.

        For gong_call entities: delete both artifacts and documents.
        For other entities: only delete artifacts.

        Args:
            entity_type: The entity type (e.g., "gong_call", "gong_user")
            entity_ids: List of entity IDs to delete
            tenant_id: The tenant ID
            pool: Database connection pool

        Returns:
            Number of entities deleted
        """
        if not entity_ids:
            return 0

        logger.info(
            f"Deleting {len(entity_ids)} stale {entity_type} entities",
            tenant_id=tenant_id,
        )

        # Delete artifacts in batch (efficient for all entity types)
        result = await pool.execute(
            "DELETE FROM ingest_artifact WHERE entity = $1 AND entity_id = ANY($2::text[])",
            entity_type,
            entity_ids,
        )
        artifacts_deleted = int(result.split()[-1]) if result else 0
        logger.info(
            f"Deleted {artifacts_deleted} artifacts for {entity_type}",
            tenant_id=tenant_id,
        )

        # For gong_call entities, also delete the associated documents
        if entity_type == "gong_call":
            documents_deleted = await self._delete_call_documents(entity_ids, tenant_id, pool)
            logger.info(
                f"Deleted {documents_deleted} documents for {entity_type}",
                tenant_id=tenant_id,
            )

        return artifacts_deleted

    async def _delete_call_documents(
        self,
        call_entity_ids: list[str],
        tenant_id: str,
        pool: asyncpg.Pool,
    ) -> int:
        """
        Delete documents for Gong call entities in batches.

        Args:
            call_entity_ids: List of call entity IDs (e.g., "gong_call_1234567")
            tenant_id: The tenant ID
            pool: Database connection pool

        Returns:
            Number of documents successfully deleted
        """
        # Extract call IDs from entity IDs and resolve to document IDs
        document_ids: list[str] = []
        for entity_id in call_entity_ids:
            call_id = parse_gong_call_entity_id(entity_id)
            if call_id:
                document_ids.append(get_gong_call_doc_id(call_id))
            else:
                logger.warning(
                    f"Failed to parse call_id from entity_id: {entity_id}",
                    tenant_id=tenant_id,
                )

        if not document_ids:
            return 0

        return await self.delete_documents(document_ids, tenant_id, pool)


# Singleton instance
gong_pruner = GongPruner()
