"""
TODO: CONN-274 this really shouldn't be an extractor
Tenant data deletion extractor that removes all tenant data from all storage systems.
"""

import asyncio
import logging

import asyncpg
from turbopuffer import NotFoundError

from connectors.base import BaseExtractor, TriggerIndexingCallback
from src.clients.tenant_opensearch import tenant_opensearch_manager
from src.jobs.models import TenantDataDeletionMessage

logger = logging.getLogger(__name__)


class TenantDataDeletionExtractor(BaseExtractor[TenantDataDeletionMessage]):
    """
    Extractor that deletes all tenant data from PostgreSQL, OpenSearch, and Turbopuffer.
    """

    source_name = "tenant_data_deletion"

    async def process_job(
        self,
        job_id: str,
        config: TenantDataDeletionMessage,
        db_pool: asyncpg.Pool,
        _trigger_indexing: TriggerIndexingCallback,
    ) -> None:
        """
        Process a tenant data deletion job.

        Args:
            job_id: The ingest job ID
            config: TenantDataDeletionMessage with tenant_id
            db_pool: Database connection pool
            trigger_indexing: Callback to trigger indexing (unused for deletion)
        """
        tenant_id = config.tenant_id

        logger.info(f"Starting tenant data deletion for tenant {tenant_id}")

        # Run all deletion steps in parallel
        await asyncio.gather(
            self._delete_postgres_documents(db_pool),
            self._delete_postgres_artifacts(db_pool),
            self._delete_from_opensearch(tenant_id),
            self._delete_from_turbopuffer(tenant_id),
        )

        logger.info(f"🗑️ Successfully completed tenant data deletion for tenant {tenant_id}")

    async def _delete_postgres_documents(self, db_pool: asyncpg.Pool) -> None:
        """Delete documents from PostgreSQL tenant database."""
        async with db_pool.acquire() as conn:
            documents_result = await conn.execute("DELETE FROM documents")
            logger.info(f"🗑️ Deleted documents from PostgreSQL: {documents_result}")

    async def _delete_postgres_artifacts(self, db_pool: asyncpg.Pool) -> None:
        """Delete ingest artifacts from PostgreSQL tenant database."""
        async with db_pool.acquire() as conn:
            artifacts_result = await conn.execute("DELETE FROM ingest_artifact")
            logger.info(f"🗑️ Deleted ingest artifacts from PostgreSQL: {artifacts_result}")

    async def _delete_from_opensearch(self, tenant_id: str) -> None:
        """Delete all documents from OpenSearch index while preserving index structure."""
        try:
            async with tenant_opensearch_manager.acquire_client(tenant_id) as (client, index_alias):
                # Delete all documents using delete_by_query
                response = await client.delete_by_query(
                    index=index_alias,
                    body={"query": {"match_all": {}}},
                )

                deleted_count = response.get("deleted", 0)
                logger.info(
                    f"🗑️ Deleted {deleted_count} documents from OpenSearch index {index_alias}"
                )

        except Exception as e:
            logger.error(f"Failed to delete from OpenSearch for tenant {tenant_id}: {e}")
            raise

    async def _delete_from_turbopuffer(self, tenant_id: str) -> None:
        """Delete all data from Turbopuffer namespace."""
        try:
            # Lazy import to avoid circular dependency
            from src.clients.turbopuffer import get_turbopuffer_client

            turbopuffer_client = get_turbopuffer_client()

            # Delete the namespace and all data in it
            await turbopuffer_client.delete_namespace(tenant_id)

        except NotFoundError:
            # Namespace doesn't exist, which means it's already deleted, or data was never indexed
            pass
        except Exception as e:
            logger.error(f"Failed to delete from Turbopuffer for tenant {tenant_id}: {e}")
            raise
