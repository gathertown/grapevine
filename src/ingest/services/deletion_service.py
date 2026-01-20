"""
Document deletion utilities.
"""

import asyncio

import asyncpg

from src.clients.tenant_opensearch import TenantScopedOpenSearchClient
from src.clients.turbopuffer import get_turbopuffer_client
from src.ingest.references.update_referrers import (
    ReferrerUpdate,
    apply_referrer_updates_to_db,
    apply_referrer_updates_to_opensearch,
    prepare_referrer_updates_for_deletion,
)
from src.utils.logging import get_logger

logger = get_logger(__name__)


# Process document deletions in chunks to avoid overwhelming the system
DOCUMENT_DELETION_CHUNK_SIZE = 100
# Max 10 parallel deletions
delete_semaphore = asyncio.Semaphore(10)


async def delete_documents_and_chunks(
    document_ids: list[str],
    tenant_id: str,
    opensearch_client: TenantScopedOpenSearchClient,
    pool: asyncpg.Pool,
) -> int:
    """Delete multiple documents and their chunks from all storage systems."""

    deleted_count = 0

    for i in range(0, len(document_ids), DOCUMENT_DELETION_CHUNK_SIZE):
        chunk = document_ids[i : i + DOCUMENT_DELETION_CHUNK_SIZE]
        results = await asyncio.gather(
            *[
                delete_document_and_chunks(doc_id, tenant_id, opensearch_client, pool)
                for doc_id in chunk
            ],
            return_exceptions=True,
        )

        for result in results:
            if isinstance(result, Exception):
                logger.error(f"Error deleting document: {result}", tenant_id=tenant_id)
            else:
                deleted_count += 1

    return deleted_count


async def delete_document_and_chunks(
    document_id: str,
    tenant_id: str,
    opensearch_client: TenantScopedOpenSearchClient,
    pool: asyncpg.Pool,
):
    async with delete_semaphore:
        await _delete_document_and_chunks(document_id, tenant_id, opensearch_client, pool)


async def _delete_document_and_chunks(
    document_id: str,
    tenant_id: str,
    opensearch_client: TenantScopedOpenSearchClient,
    pool: asyncpg.Pool,
):
    """Delete a document and its chunks from all storage systems."""
    logger.info(f"Starting to delete document: {document_id}")
    doc_result = await pool.fetchrow(
        "SELECT reference_id, referenced_docs FROM documents WHERE id = $1",
        document_id,
    )

    if doc_result:
        # Prepare referrer updates for documents affected by this deletion
        reference_id = doc_result["reference_id"]
        referenced_docs: dict[str, int] = (
            doc_result["referenced_docs"] if isinstance(doc_result["referenced_docs"], dict) else {}
        )

        referrer_updates: list[ReferrerUpdate] = []
        # Apply referrer updates and delete the document in a single transaction
        async with pool.acquire() as conn, conn.transaction():
            if reference_id and referenced_docs:
                referrer_updates = await prepare_referrer_updates_for_deletion(
                    reference_id, referenced_docs, conn
                )

            if referrer_updates:
                await apply_referrer_updates_to_db(referrer_updates, conn)

            await conn.execute(
                "DELETE FROM document_permissions WHERE document_id = $1", document_id
            )

            await conn.execute("DELETE FROM documents WHERE id = $1", document_id)

        logger.info(f"✅ Deleted document from PostgreSQL: {document_id}")

        # Apply referrer updates to OpenSearch for affected documents
        # TODO: merge this with the deletion below into one bulk op
        if referrer_updates:
            await apply_referrer_updates_to_opensearch(
                referrer_updates, tenant_id, opensearch_client
            )

    # Finally, delete the document from OpenSearch and Turbopuffer in parallel
    async def delete_opensearch():
        await opensearch_client.delete_document(f"tenant-{tenant_id}", document_id)
        logger.info(f"✅ Deleted document from OpenSearch: {document_id}")

    async def delete_turbopuffer():
        turbopuffer_client = get_turbopuffer_client()
        await turbopuffer_client.delete_chunks(tenant_id, document_id)

    await asyncio.gather(delete_opensearch(), delete_turbopuffer())
