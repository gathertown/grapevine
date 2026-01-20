import logging
from collections.abc import Awaitable, Callable

import asyncpg

from src.clients.tenant_opensearch import tenant_opensearch_manager

logger = logging.getLogger(__name__)


class BasePruner:
    """Base class for handling document deletions across all data stores."""

    _instance = None

    def __new__(cls):
        """Singleton pattern implementation."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    async def delete_documents(
        self,
        document_ids: list[str],
        tenant_id: str,
        pool: asyncpg.Pool,
    ) -> int:
        """
        Delete multiple documents from all data stores.

        Args:
            document_ids: List of document IDs to delete
            tenant_id: The tenant ID
            conn: Existing tenant database connection to use
        Returns:
            Number of documents successfully deleted
        """
        if not document_ids:
            logger.info("No document IDs provided for deletion")
            return 0

        # Lazy import to avoid circular dependency
        from src.ingest.services.deletion_service import delete_documents_and_chunks

        # Use tenant-aware OpenSearch client and centralized deletion function
        async with tenant_opensearch_manager.acquire_client(tenant_id) as (
            opensearch_client,
            _index_alias,
        ):
            return await delete_documents_and_chunks(
                document_ids, tenant_id, opensearch_client, pool
            )

    async def delete_document(
        self,
        document_id: str,
        tenant_id: str,
        pool: asyncpg.Pool,
    ) -> bool:
        """
        Delete a document from all data stores (PostgreSQL, OpenSearch, and cascading chunks).

        Args:
            document_id: The document ID to delete
            tenant_id: The tenant ID
            conn: Existing tenant database connection to use

        Returns:
            True if deletion was successful, False otherwise
        """
        if not document_id:
            logger.warning("No document_id provided for deletion")
            return False

        logger.info(f"Starting complete deletion of document {document_id} for tenant {tenant_id}")

        try:
            # Lazy import to avoid circular dependency
            from src.ingest.services.deletion_service import delete_document_and_chunks

            # Use tenant-aware OpenSearch client and centralized deletion function
            async with tenant_opensearch_manager.acquire_client(tenant_id) as (
                opensearch_client,
                index_alias,
            ):
                await delete_document_and_chunks(document_id, tenant_id, opensearch_client, pool)
                return True

        except Exception as e:
            logger.error(f"Error deleting document {document_id}: {e}")
            return False

    async def delete_artifacts(
        self,
        conn: asyncpg.Connection,
        entity_type: str,
        entity_id: str,
    ) -> int:
        """
        Delete artifacts for a given entity.

        Args:
            conn: Database connection
            entity_type: The entity type (e.g., 'github_file', 'slack_message')
            entity_id: The entity ID

        Returns:
            Number of artifacts deleted
        """
        result = await conn.execute(
            "DELETE FROM ingest_artifact WHERE entity = $1 AND entity_id = $2",
            entity_type,
            entity_id,
        )
        deleted_count = int(result.split()[-1]) if result else 0
        logger.info(f"Deleted {deleted_count} artifacts for {entity_type} entity_id: {entity_id}")
        return deleted_count

    async def delete_entity(
        self,
        entity_id: str,
        tenant_id: str,
        db_pool: asyncpg.Pool,
        document_id_resolver: Callable[[str], str],
        custom_artifact_deletion: Callable[[asyncpg.Connection, str, str], Awaitable[int]]
        | None = None,
        entity_type: str | None = None,
    ) -> bool:
        """
        Template method for consistent entity deletion across all data stores.

        This method follows a standardized deletion flow:
        1. Delete artifacts from ingest_artifact table
        2. Resolve entity_id to document_id using provided resolver
        3. Delete document and cascading chunks from PostgreSQL and OpenSearch

        Args:
            entity_id: The entity identifier to delete
            tenant_id: The tenant ID
            db_pool: Database connection pool
            document_id_resolver: Function to resolve entity_id to document_id
            custom_artifact_deletion: Optional custom artifact deletion logic
            entity_type: Optional entity type for logging (e.g., 'github_file')

        Returns:
            True if deletion was successful, False otherwise
        """
        if not entity_id or not tenant_id:
            logger.warning(
                f"Incomplete entity deletion data: entity_id={entity_id}, tenant_id={tenant_id}"
            )
            return False

        entity_desc = f"{entity_type} " if entity_type else ""
        logger.info(f"Starting entity deletion: {entity_desc}{entity_id} for tenant {tenant_id}")

        try:
            async with db_pool.acquire() as conn:
                # 1. Delete artifacts (with optional custom logic)
                if custom_artifact_deletion:
                    artifacts_deleted = await custom_artifact_deletion(
                        conn, entity_type or "unknown", entity_id
                    )
                elif entity_type:
                    artifacts_deleted = await self.delete_artifacts(conn, entity_type, entity_id)
                else:
                    # Skip artifact deletion if no entity_type provided
                    artifacts_deleted = 0
                    logger.info("Skipping artifact deletion - no entity_type provided")

                # 2. Resolve entity_id to document_id
                document_id = document_id_resolver(entity_id)
                logger.info(f"Resolved {entity_desc}{entity_id} to document_id: {document_id}")

                # 3. Delete document and cascading chunks
                success = await self.delete_document(document_id, tenant_id, db_pool)

                if success:
                    logger.info(
                        f"✅ Successfully deleted {entity_desc}{entity_id} (artifacts: {artifacts_deleted}, document: {document_id})"
                    )
                else:
                    logger.warning(f"❌ Document deletion failed for {entity_desc}{entity_id}")

                return success

        except Exception as e:
            logger.error(f"❌ Error deleting {entity_desc}{entity_id}: {e}")
            return False
