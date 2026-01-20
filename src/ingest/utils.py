"""
Utility functions for document processing and storage.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import sys
import time
import traceback
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, NamedTuple

if TYPE_CHECKING:
    from src.clients.turbopuffer import TurbopufferClient

from src.clients.tenant_opensearch import _tenant_opensearch_manager
from src.ingest.references.find_references import find_references_in_doc
from src.utils.config import get_config_value

project_root = Path(__file__).parent.parent
sys.path.append(str(project_root))

import asyncpg

from connectors.base import BaseChunk, BaseDocument
from src.clients.openai import get_openai_client
from src.clients.opensearch import OpenSearchDocument
from src.clients.tenant_db import tenant_db_manager
from src.clients.tenant_opensearch import TenantScopedOpenSearchClient
from src.clients.turbopuffer import get_turbopuffer_client
from src.ingest.references.calculate_referrers import calculate_referrer_score, calculate_referrers
from src.ingest.references.update_referrers import (
    ReferrerUpdate,
    apply_referrer_updates_to_db,
    apply_referrer_updates_to_opensearch,
    fetch_existing_referenced_docs,
    prepare_referrer_updates,
)
from src.permissions import DocumentPermissions, PermissionsService
from src.utils.logging import get_logger

logger = get_logger(__name__)

DEFAULT_INDEX_BATCH_SIZE = 10
TURBOPUFFER_CHUNK_BATCH_SIZE = 500  # Process chunks in batches to prevent CPU spinning

# Feature flag for incremental indexing (chunk_diff)
# When enabled, only new/changed chunks are embedded, saving embedding costs
# Set INCREMENTAL_INDEXING_ENABLED=false to disable and always do full reindexing
INCREMENTAL_INDEXING_ENABLED = get_config_value("INCREMENTAL_INDEXING_ENABLED", True)


def compute_chunk_diff(
    new_chunks: Sequence[BaseChunk[Any]],
    existing_chunk_hashes: dict[str, str],
) -> ChunkDiffResult:
    """Compute the diff between new chunks and existing chunks in Turbopuffer.

    This enables incremental indexing by identifying:
    - New chunks that need embedding
    - Changed chunks that need re-embedding
    - Unchanged chunks that can be skipped
    - Deleted chunks that should be removed

    Args:
        new_chunks: List of chunks generated for the current document version
        existing_chunk_hashes: Dict of chunk_id -> content_hash from Turbopuffer

    Returns:
        ChunkDiffResult with categorized chunks
    """
    new_chunk_list: list[BaseChunk] = []
    changed_chunk_list: list[BaseChunk] = []
    unchanged_chunk_ids: list[str] = []
    seen_chunk_ids: set[str] = set()

    for chunk in new_chunks:
        chunk_id = str(chunk.get_deterministic_id())
        chunk_hash = chunk.get_content_hash()
        seen_chunk_ids.add(chunk_id)

        existing_hash = existing_chunk_hashes.get(chunk_id)

        if existing_hash is None:
            # New chunk - needs embedding
            new_chunk_list.append(chunk)
        elif existing_hash != chunk_hash:
            # Changed chunk - needs re-embedding
            changed_chunk_list.append(chunk)
        else:
            # Unchanged chunk - skip embedding
            unchanged_chunk_ids.append(chunk_id)

    # Find deleted chunks (exist in Turbopuffer but not in new chunks)
    deleted_chunk_ids = [
        chunk_id for chunk_id in existing_chunk_hashes if chunk_id not in seen_chunk_ids
    ]

    return ChunkDiffResult(
        new_chunks=new_chunk_list,
        changed_chunks=changed_chunk_list,
        unchanged_chunk_ids=unchanged_chunk_ids,
        deleted_chunk_ids=deleted_chunk_ids,
    )


class ChunkDiffResult(NamedTuple):
    """Result of comparing new chunks against existing chunks in Turbopuffer."""

    new_chunks: list[BaseChunk]  # Chunks that don't exist in Turbopuffer
    changed_chunks: list[BaseChunk]  # Chunks with different content_hash
    unchanged_chunk_ids: list[str]  # IDs of chunks that haven't changed
    deleted_chunk_ids: list[str]  # IDs of chunks to delete from Turbopuffer


class PreparedDocumentData(NamedTuple):
    """Data prepared for a single document during batch processing."""

    document: BaseDocument
    chunks: list[BaseChunk]
    content_hash: str
    references: dict[str, int]
    referrers: dict[str, int]
    referrer_updates: list[ReferrerUpdate]
    referrer_score: float
    # Chunk diff info for incremental indexing (None = full reindex)
    chunk_diff: ChunkDiffResult | None = None


class BatchEmbeddingData(NamedTuple):
    """Mapping data for batch embedding results."""

    doc_id: str
    chunk_start_idx: int
    chunk_count: int


async def prepare_documents_batch(
    documents: Sequence[BaseDocument],
    readonly_db_pool: asyncpg.Pool,
    tenant_id: str,
    force_reprocess: bool = False,
) -> tuple[list[PreparedDocumentData], list[BaseChunk], list[BatchEmbeddingData]]:
    """Prepare all documents in parallel, collecting chunks for batch embedding.

    This function now supports incremental indexing: it fetches existing chunk hashes
    from Turbopuffer and computes a diff to only embed new/changed chunks.

    Args:
        documents: Documents to prepare for indexing
        readonly_db_pool: Database pool for reading existing state
        tenant_id: Tenant ID for accessing Turbopuffer
        force_reprocess: If True, skip deduplication checks

    Returns:
        - list of PreparedDocumentData for each document (with chunk_diff info)
        - list of chunks that need embedding (new + changed only)
        - list of BatchEmbeddingData for mapping embeddings back to documents
    """
    turbopuffer_client = get_turbopuffer_client()

    async def prepare_single_document(document: BaseDocument) -> PreparedDocumentData | None:
        """Prepare a single document's data. Returns None if the document does not need indexing."""
        doc_id = document.id
        metadata = document.get_metadata()
        content = document.get_content()
        try:
            content_hash = make_content_hash(content, metadata)

            # Check if document needs indexing
            needs_indexing = await should_index_postgres_document(
                doc_id, content_hash, readonly_db_pool, force_reprocess
            )

            if not needs_indexing:
                return None

            # Prepare referrers and referrer updates in parallel
            reference_id = document.get_reference_id()
            referrers_task = calculate_referrers(reference_id, readonly_db_pool)

            old_referenced_docs = await fetch_existing_referenced_docs(
                document.id, readonly_db_pool
            )
            new_referenced_docs = find_references_in_doc(document.get_content(), reference_id)
            referrer_updates_task = prepare_referrer_updates(
                readonly_db_pool=readonly_db_pool,
                reference_id=reference_id,
                old_referenced_docs=old_referenced_docs,
                new_referenced_docs=new_referenced_docs,
            )

            # Wait for all prep tasks
            referrers = await referrers_task
            referrer_updates = await referrer_updates_task
            referrer_score = calculate_referrer_score(referrers)

            # Create chunks and set default permissions
            chunks = document.to_embedding_chunks()

            # Populate chunk permissions immediately
            for chunk in chunks:
                document.populate_chunk_permissions(chunk)

            # Fetch existing chunk hashes from Turbopuffer for incremental indexing
            # (only if enabled, not force_reprocess, and chunks support deterministic IDs)
            chunk_diff: ChunkDiffResult | None = None
            if (
                INCREMENTAL_INDEXING_ENABLED
                and not force_reprocess
                and chunks
                and chunks[0].get_unique_key() is not None
            ):
                existing_hashes = await turbopuffer_client.get_existing_chunk_hashes(
                    tenant_id, doc_id
                )
                if existing_hashes:
                    chunk_diff = compute_chunk_diff(chunks, existing_hashes)
                    logger.debug(
                        f"Chunk diff for {doc_id}: {len(chunk_diff.new_chunks)} new, "
                        f"{len(chunk_diff.changed_chunks)} changed, "
                        f"{len(chunk_diff.unchanged_chunk_ids)} unchanged, "
                        f"{len(chunk_diff.deleted_chunk_ids)} deleted"
                    )

            return PreparedDocumentData(
                document=document,
                chunks=chunks,
                content_hash=content_hash,
                references=new_referenced_docs,
                referrers=referrers,
                referrer_updates=referrer_updates,
                referrer_score=referrer_score,
                chunk_diff=chunk_diff,
            )

        except Exception as e:
            logger.error(f"❌ Error preparing document {document.id}: {e}")
            raise

    # Prepare all documents in parallel
    tasks = [prepare_single_document(doc) for doc in documents]
    prepared_docs_raw = await asyncio.gather(*tasks)

    # Filter out None results (docs that don't need indexing) and collect batch embedding data
    prepared_docs = [doc for doc in prepared_docs_raw if doc is not None]
    all_chunks: list[BaseChunk] = []
    batch_embedding_data: list[BatchEmbeddingData] = []

    for doc_data in prepared_docs:
        # Only include chunks that need embedding (new + changed)
        if doc_data.chunk_diff is not None:
            chunks_to_embed = doc_data.chunk_diff.new_chunks + doc_data.chunk_diff.changed_chunks
        else:
            # No diff info = full reindex
            chunks_to_embed = doc_data.chunks

        batch_embedding_data.append(
            BatchEmbeddingData(
                doc_id=doc_data.document.id,
                chunk_start_idx=len(all_chunks),
                chunk_count=len(chunks_to_embed),
            )
        )
        all_chunks.extend(chunks_to_embed)

    return prepared_docs, all_chunks, batch_embedding_data


async def update_all_document_permissions(
    documents: Sequence[BaseDocument],
    readwrite_db_pool: asyncpg.Pool,
) -> None:
    """Update permissions for all documents, regardless of whether they need re-indexing.

    This ensures permission changes (e.g., workspace selection changes) are applied
    immediately, even if the document content hasn't changed.

    Args:
        documents: List of documents to update permissions for
        readwrite_db_pool: Database connection pool
    """
    if not documents:
        return

    from src.permissions.models import DocumentPermissions
    from src.permissions.service import PermissionsService

    # Prepare permissions list for all documents
    permissions_list = []
    for document in documents:
        permissions_list.append(
            DocumentPermissions(
                document_id=document.id,
                permission_policy=document.permission_policy,
                permission_allowed_tokens=document.permission_allowed_tokens,
            )
        )

    # Batch upsert all permissions
    async with readwrite_db_pool.acquire() as conn:
        await PermissionsService.batch_upsert_document_permissions(
            permissions_list=permissions_list,
            conn=conn,
        )


async def update_all_document_backfill_ids(
    documents: Sequence[BaseDocument],
    readwrite_db_pool: asyncpg.Pool,
    backfill_id: str,
) -> None:
    """Update last_seen_backfill_id for all documents.

    This ensures all documents seen during a backfill are marked, even if their
    content hasn't changed, so they won't be pruned as stale.

    Args:
        documents: List of documents to update
        readwrite_db_pool: Database connection pool
        backfill_id: The current backfill ID to mark documents with
    """
    if not documents:
        return

    doc_ids = [doc.id for doc in documents]

    async with readwrite_db_pool.acquire() as conn:
        result = await conn.execute(
            """
            UPDATE documents
            SET last_seen_backfill_id = $1
            WHERE id = ANY($2)
            """,
            backfill_id,
            doc_ids,
        )
        updated_count = int(result.split()[-1]) if result else 0
        logger.info(
            f"Updated last_seen_backfill_id for {updated_count}/{len(doc_ids)} documents",
            backfill_id=backfill_id,
        )


async def update_all_opensearch_permissions(
    documents: Sequence[BaseDocument],
    tenant_id: str,
    opensearch_client: TenantScopedOpenSearchClient,
) -> None:
    """Update permissions in OpenSearch for all documents.

    This ensures permission changes are reflected in search results immediately.

    Args:
        documents: List of documents to update permissions for
        tenant_id: Tenant ID
        opensearch_client: OpenSearch client
    """
    if not documents:
        return

    index_name = f"tenant-{tenant_id}"

    # Prepare bulk update operations for permissions only
    update_ops: list[dict[str, Any]] = []
    for document in documents:
        # Prepare partial update for just the permission fields
        update_ops.append(
            {
                "update": {
                    "_index": index_name,
                    "_id": document.id,
                }
            }
        )
        update_ops.append(
            {
                "doc": {
                    "permission_policy": document.permission_policy,
                    "permission_allowed_tokens": document.permission_allowed_tokens,
                },
                "doc_as_upsert": True,  # Create document with just permissions if it doesn't exist
            }
        )

    # Execute bulk update
    try:
        response = await opensearch_client.client.bulk(body=update_ops)
        if response.get("errors", False):
            items = response.get("items", [])
            errors = [item for item in items if "error" in item.get("update", {})]

            if errors:
                logger.warning(
                    f"Some OpenSearch permission updates failed for {len(documents)} documents",
                    errors=errors,
                    source=documents[0].get_source() if documents else "unknown",
                    tenant_id=tenant_id,
                )
        else:
            logger.debug(
                f"Successfully updated OpenSearch permissions for {len(documents)} documents"
            )
    except Exception as e:
        logger.error(
            f"Failed to update OpenSearch permissions for {len(documents)} documents: {e}",
            exc_info=True,
        )


async def gen_and_store_embeddings(
    documents: Sequence[BaseDocument],
    tenant_id: str,
    readonly_db_pool: asyncpg.Pool,
    force_reindex: bool = False,
    turbopuffer_only: bool = False,
    backfill_id: str | None = None,
):
    """Background task to generate embeddings and store documents with batched processing."""
    openai_client = get_openai_client()
    source = documents[0].get_source() if documents else "unknown"

    try:
        logger.info(
            f"🚛 Background task started: Processing {len(documents)} documents from {source} "
            f"for tenant {tenant_id} with batching"
        )

        async with (
            _tenant_opensearch_manager.acquire_client(tenant_id) as (opensearch_client, _),
            tenant_db_manager.acquire_pool(tenant_id) as readwrite_db_pool,
        ):
            # Phase 0: Always update permissions and backfill_id for ALL documents, even those skipped for re-indexing
            # This ensures permission changes (e.g., workspace selection) and backfill tracking are applied immediately
            perm_update_start = time.time()
            update_tasks = [
                update_all_document_permissions(documents, readwrite_db_pool),
            ]

            # Update last_seen_backfill_id for all documents if backfill_id is provided
            # This prevents pruning of documents that don't need re-indexing
            if backfill_id:
                update_tasks.append(
                    update_all_document_backfill_ids(documents, readwrite_db_pool, backfill_id)
                )

            if not turbopuffer_only:
                update_tasks.append(
                    update_all_opensearch_permissions(documents, tenant_id, opensearch_client)
                )

            await asyncio.gather(*update_tasks)
            perm_update_duration = time.time() - perm_update_start
            logger.info(
                f"⏱️ Updated permissions{' and backfill IDs' if backfill_id else ''} for {len(documents)} documents in {perm_update_duration:.2f}s"
            )

            # Phase 1: Prepare all documents in parallel (maintains current parallelization)
            # This now includes fetching existing chunk hashes for incremental indexing
            prep_start_time = time.time()
            prepared_docs, all_chunks, batch_embedding_data = await prepare_documents_batch(
                documents, readonly_db_pool, tenant_id, force_reindex
            )
            prep_duration = time.time() - prep_start_time
            logger.info(f"⏱️ Prep phase: {prep_duration:.2f}s for {len(documents)} documents")

            # Phase 2: Batch embed all chunks across documents
            embeddings_map: dict[
                str, list[list[float]]
            ] = {}  # doc_id -> list of embeddings matching the order of chunks
            if all_chunks:
                embed_start_time = time.time()
                logger.info(
                    f"Batch embedding {len(all_chunks)} chunks across {len(batch_embedding_data)} documents"
                )
                all_chunk_contents = [chunk.get_content() for chunk in all_chunks]
                all_embeddings = await openai_client.create_embeddings_batch(all_chunk_contents)

                # Map embeddings back to documents
                for doc_id, chunk_start_idx, chunk_count in batch_embedding_data:
                    doc_embeddings = all_embeddings[chunk_start_idx : chunk_start_idx + chunk_count]
                    embeddings_map[doc_id] = doc_embeddings

                embed_duration = time.time() - embed_start_time
                logger.info(
                    f"⏱️ Batch embedding completed: {embed_duration:.2f}s for {len(all_chunks)} chunks"
                )

            # Phase 3: Execute batched writes in parallel (3 concurrent operations)
            write_tasks = [batch_turbopuffer_write(prepared_docs, embeddings_map, tenant_id)]
            if not turbopuffer_only:
                write_tasks.append(
                    batch_postgres_write(prepared_docs, readwrite_db_pool, backfill_id)
                )
                write_tasks.append(
                    batch_opensearch_write(prepared_docs, tenant_id, opensearch_client)
                )

            write_start_time = time.time()
            await asyncio.gather(*write_tasks)
            write_duration = time.time() - write_start_time
            logger.info(f"⏱️ Batch writes completed: {write_duration:.2f}s")

    except Exception as e:
        logger.error(
            f"❌ Critical error processing documents from {source}: {e}. Full traceback: {traceback.format_exc()}"
        )
        raise

    # Aggregate results (all successful if we get here, since exceptions would be raised)
    total_docs = len(documents)
    docs_processed = len(prepared_docs)
    docs_skipped = total_docs - docs_processed

    # Log success/failure counts for NR metrics
    logger.info(
        f"Finished batch processing documents from {source}",
        successful=docs_processed,
        failed=0,
        skipped=docs_skipped,
    )


def make_content_hash(content: str, metadata: dict[str, Any]) -> str:
    content_and_metadata = {"content": content, "metadata": metadata}
    return hashlib.sha256(json.dumps(content_and_metadata, sort_keys=True).encode()).hexdigest()


async def should_index_postgres_document(
    doc_id: str,
    content_hash: str,
    readonly_db_pool: asyncpg.Pool,
    force_reprocess: bool = False,
) -> bool:
    """Check if a document should be indexed into Postgres. Skip docs where the new and old content hashes are the same.

    Returns:
        - True if the document should be indexed, otherwise False
    """
    if force_reprocess:
        return True

    try:
        async with readonly_db_pool.acquire() as conn:
            existing_doc = await conn.fetchrow(
                "SELECT content_hash FROM documents WHERE id = $1",
                doc_id,
            )

            return not (existing_doc and existing_doc["content_hash"] == content_hash)
    except Exception as e:
        logger.error(f"Failed to check existing document state: {e}")
        return True


async def index_opensearch_document(
    document: BaseDocument,
    content_hash: str,
    opensearch_client: TenantScopedOpenSearchClient,
    index_name: str,
    referrer_score: float = 0.0,
):
    content = document.get_content()

    opensearch_doc = OpenSearchDocument.create(
        document.id,
        content,
        content_hash,
        document.get_source(),
        document.get_source_created_at(),
        document.source_updated_at,
        document.get_metadata(),
        referrer_score,
        permission_policy=document.permission_policy,
        permission_allowed_tokens=document.permission_allowed_tokens,
    )

    logger.debug(
        f"Indexing document {document.id} with content_hash={content_hash}, has_content={bool(content)}, content_length={len(content) if content else 0}"
    )

    response = await opensearch_client.index_document(index_name, opensearch_doc)

    if response.get("errors", False):
        raise Exception(f"Failed to index document {document.id} in OpenSearch: {response}")

    logger.info(f"✅ Successfully indexed document {document.id} in OpenSearch")


async def batch_postgres_write(
    prepared_docs: list[PreparedDocumentData],
    readwrite_db_pool: asyncpg.Pool,
    backfill_id: str | None = None,
) -> None:
    """Batch write all documents to PostgreSQL in a single transaction (no chunks table)."""
    # Collect all documents that need indexing
    if not prepared_docs:
        logger.info("No documents need PostgreSQL indexing")
        return

    db_start_time = time.time()

    # Prepare all document data for batch insertion before acquiring connection
    document_records: list[
        tuple[str, str, str, str, str, datetime, datetime, str, str, str, float, str | None]
    ] = []
    for doc_data in prepared_docs:
        document = doc_data.document

        document_records.append(
            (
                document.id,
                document.get_content(),
                doc_data.content_hash,
                json.dumps(document.get_metadata()),
                document.get_source(),
                document.get_source_created_at(),
                document.source_updated_at,
                document.get_reference_id(),
                json.dumps(doc_data.references),
                json.dumps(doc_data.referrers),
                calculate_referrer_score(doc_data.referrers),
                backfill_id,
            )
        )

    # Prepare permissions list
    permissions_list = [
        DocumentPermissions(
            document_id=doc_data.document.id,
            permission_policy=doc_data.document.permission_policy,
            permission_allowed_tokens=doc_data.document.permission_allowed_tokens,
        )
        for doc_data in prepared_docs
    ]

    # Collect all referrer updates from all documents
    all_referrer_updates: list[ReferrerUpdate] = []
    for doc_data in prepared_docs:
        all_referrer_updates.extend(doc_data.referrer_updates)

    # Collect ALL document IDs we'll touch (direct updates + referrer updates)
    all_touched_doc_ids = set()

    # Documents we're inserting/updating directly
    for doc_data in prepared_docs:
        all_touched_doc_ids.add(doc_data.document.id)

    # Documents we'll update via referrer updates
    for update in all_referrer_updates:
        all_touched_doc_ids.add(update.document_id)

    # Sort all document IDs so we can acquire locks in a consistent order
    sorted_all_doc_ids = sorted(all_touched_doc_ids)

    logger.info(f"Batch indexing {len(prepared_docs)} documents in PostgreSQL...")

    async with readwrite_db_pool.acquire() as conn:
        acquired_db_conn_duration = time.time() - db_start_time

        # Wrap documents and permissions in a transaction for atomicity (FK constraint)
        async with conn.transaction():
            # Acquire advisory locks for ALL document IDs we'll touch (direct + referrer updates)
            # in sorted order to prevent deadlocks between index workers.
            # Automatically released at transaction end.
            if sorted_all_doc_ids:
                # PostgreSQL has a limit of 1664 parameters per query, so we need to batch
                max_params_per_query = 1664
                for batch_start in range(0, len(sorted_all_doc_ids), max_params_per_query):
                    batch_end = min(batch_start + max_params_per_query, len(sorted_all_doc_ids))
                    batch_ids = sorted_all_doc_ids[batch_start:batch_end]

                    placeholders = [
                        f"pg_advisory_xact_lock(hashtext(${i + 1}))" for i in range(len(batch_ids))
                    ]
                    await conn.execute(f"SELECT {', '.join(placeholders)}", *batch_ids)

            # Batch insert all documents in a single operation
            await conn.executemany(
                """
                INSERT INTO documents (id, content, content_hash, metadata, source, source_created_at, source_updated_at, reference_id, referenced_docs, referrers, referrer_score, last_seen_backfill_id)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
                ON CONFLICT (id) DO UPDATE SET
                    content = EXCLUDED.content,
                    content_hash = EXCLUDED.content_hash,
                    metadata = EXCLUDED.metadata,
                    source_created_at = EXCLUDED.source_created_at,
                    source_updated_at = EXCLUDED.source_updated_at,
                    reference_id = EXCLUDED.reference_id,
                    referenced_docs = EXCLUDED.referenced_docs,
                    referrers = EXCLUDED.referrers,
                    referrer_score = EXCLUDED.referrer_score,
                    last_seen_backfill_id = EXCLUDED.last_seen_backfill_id,
                    updated_at = CURRENT_TIMESTAMP
                """,
                document_records,
            )

            logger.info(
                f"✅ Successfully batch indexed {len(prepared_docs)} documents in PostgreSQL"
            )

            # Insert permissions (already prepared above)
            await PermissionsService.batch_upsert_document_permissions(
                permissions_list=permissions_list,
                conn=conn,
            )

            logger.info(
                f"✅ Successfully batch upserted permissions for {len(prepared_docs)} documents"
            )

            if all_referrer_updates:
                await apply_referrer_updates_to_db(all_referrer_updates, conn)

    write_duration = time.time() - db_start_time - acquired_db_conn_duration
    total_referrer_updates = len(all_referrer_updates)

    logger.info(
        f"⏱️ Batch Postgres write for {len(prepared_docs)} docs ({total_referrer_updates} referrer updates): {acquired_db_conn_duration:.2f}s to acquire conn, {write_duration:.2f}s to complete"
    )


async def batch_opensearch_write(
    prepared_docs: list[PreparedDocumentData],
    tenant_id: str,
    opensearch_client: TenantScopedOpenSearchClient,
) -> None:
    """Batch write all documents to OpenSearch."""
    if not prepared_docs:
        logger.info("No documents need OpenSearch indexing")
        return

    index_name = f"tenant-{tenant_id}"

    # Prepare all documents for bulk indexing
    opensearch_docs = []
    for doc_data in prepared_docs:
        opensearch_doc = OpenSearchDocument.create(
            doc_data.document.id,
            doc_data.document.get_content(),
            doc_data.content_hash,
            doc_data.document.get_source(),
            doc_data.document.get_source_created_at(),
            doc_data.document.source_updated_at,
            doc_data.document.get_metadata(),
            doc_data.referrer_score,
            permission_policy=doc_data.document.permission_policy,
            permission_allowed_tokens=doc_data.document.permission_allowed_tokens,
        )
        opensearch_docs.append(opensearch_doc)

    logger.info(f"Bulk indexing {len(opensearch_docs)} documents in OpenSearch...")

    # Bulk index all documents
    response = await opensearch_client.bulk_index_documents(index_name, opensearch_docs)

    if response.get("errors", False):
        raise Exception(f"Failed to bulk index documents in OpenSearch: {response}")

    logger.info(f"✅ Bulk indexed {len(opensearch_docs)} documents in OpenSearch")

    # Collect all referrer updates from all documents
    all_referrer_updates: list[ReferrerUpdate] = []
    for doc_data in prepared_docs:
        all_referrer_updates.extend(doc_data.referrer_updates)

    # Apply all referrer updates in a single batch
    if all_referrer_updates:
        await apply_referrer_updates_to_opensearch(
            all_referrer_updates, tenant_id, opensearch_client
        )

    logger.info(f"✅ Batch OpenSearch write completed for {len(prepared_docs)} documents")


async def batch_turbopuffer_write(
    prepared_docs: list[PreparedDocumentData],
    embeddings_map: dict[str, list[list[float]]],
    tenant_id: str,
) -> None:
    """Batch write all document chunks to Turbopuffer.

    This function now supports incremental indexing:
    - For documents with chunk_diff info, only new/changed chunks are written
    - Deleted chunks are removed
    - Unchanged chunks are skipped entirely

    Args:
        prepared_docs: Documents with their chunks and optional chunk_diff info
        embeddings_map: Map of doc_id -> embeddings for chunks that were embedded
        tenant_id: Tenant identifier
    """
    if not prepared_docs:
        logger.info("No documents need Turbopuffer indexing")
        return

    turbopuffer_client = get_turbopuffer_client()

    # Separate documents into incremental vs full reindex
    incremental_docs: list[PreparedDocumentData] = []
    full_reindex_docs: list[PreparedDocumentData] = []

    for doc_data in prepared_docs:
        if doc_data.chunk_diff is not None:
            incremental_docs.append(doc_data)
        else:
            full_reindex_docs.append(doc_data)

    # Stats for logging
    total_new_chunks = 0
    total_changed_chunks = 0
    total_unchanged_chunks = 0
    total_deleted_chunks = 0
    total_full_reindex_chunks = 0

    # Handle incremental updates
    if incremental_docs:
        # Collect chunks to delete
        all_deleted_chunk_ids: list[str] = []

        # Collect chunks to upsert (new + changed)
        incremental_chunks_data: list[tuple[str, list[BaseChunk], list[list[float]]]] = []

        for doc_data in incremental_docs:
            chunk_diff = doc_data.chunk_diff
            assert chunk_diff is not None  # Type narrowing

            doc_id = doc_data.document.id
            all_deleted_chunk_ids.extend(chunk_diff.deleted_chunk_ids)

            # Get embeddings for new + changed chunks
            if doc_id in embeddings_map:
                chunks_to_upsert = chunk_diff.new_chunks + chunk_diff.changed_chunks
                embeddings = embeddings_map[doc_id]

                if chunks_to_upsert:
                    incremental_chunks_data.append((doc_id, chunks_to_upsert, embeddings))

            # Update stats
            total_new_chunks += len(chunk_diff.new_chunks)
            total_changed_chunks += len(chunk_diff.changed_chunks)
            total_unchanged_chunks += len(chunk_diff.unchanged_chunk_ids)
            total_deleted_chunks += len(chunk_diff.deleted_chunk_ids)

        # Delete removed chunks
        if all_deleted_chunk_ids:
            logger.info(f"Deleting {len(all_deleted_chunk_ids)} removed chunks from Turbopuffer")
            await turbopuffer_client.delete_chunks_by_ids(tenant_id, all_deleted_chunk_ids)

        # Upsert new/changed chunks (using incremental upsert, not delete+upsert)
        if incremental_chunks_data:
            await _upsert_chunks_incremental(turbopuffer_client, tenant_id, incremental_chunks_data)

    # Handle full reindex documents (no chunk_diff = legacy behavior)
    if full_reindex_docs:
        doc_chunks_data: list[tuple[str, list[BaseChunk], list[list[float]]]] = []

        for doc_data in full_reindex_docs:
            doc_id = doc_data.document.id
            if doc_id in embeddings_map:
                embeddings = embeddings_map[doc_id]
                doc_chunks_data.append((doc_id, doc_data.chunks, embeddings))
                total_full_reindex_chunks += len(doc_data.chunks)

        if doc_chunks_data:
            logger.info(
                f"Full reindex: {len(full_reindex_docs)} docs ({total_full_reindex_chunks} chunks)"
            )
            # Use existing index_chunks which does delete+upsert
            await turbopuffer_client.index_chunks(
                tenant_id, doc_chunks_data, batch_size=TURBOPUFFER_CHUNK_BATCH_SIZE
            )

    # Log summary
    if incremental_docs:
        logger.info(
            f"✅ Incremental Turbopuffer write: {total_new_chunks} new, "
            f"{total_changed_chunks} changed, {total_unchanged_chunks} unchanged (skipped), "
            f"{total_deleted_chunks} deleted"
        )
    if full_reindex_docs:
        logger.info(
            f"✅ Full Turbopuffer reindex: {len(full_reindex_docs)} docs, "
            f"{total_full_reindex_chunks} chunks"
        )


async def _upsert_chunks_incremental(
    turbopuffer_client: TurbopufferClient,
    tenant_id: str,
    doc_chunks_data: list[tuple[str, list[BaseChunk], list[list[float]]]],
) -> None:
    """Upsert chunks without deleting existing chunks first.

    Used for incremental indexing where we know exactly which chunks to update.
    """
    from turbopuffer.types import RowParam

    from connectors.base import TURBOPUFFER_CHUNK_SCHEMA

    namespace = turbopuffer_client._get_namespace(tenant_id)

    # Prepare all upsert rows
    upsert_rows: list[RowParam] = []
    for _doc_id, chunks, embeddings in doc_chunks_data:
        for chunk, embedding in zip(chunks, embeddings, strict=False):
            upsert_rows.append(chunk.to_turbopuffer_chunk(embedding))

    if not upsert_rows:
        return

    # Batch upsert if needed
    batch_size = TURBOPUFFER_CHUNK_BATCH_SIZE
    total_chunks = len(upsert_rows)

    for batch_start in range(0, total_chunks, batch_size):
        batch_end = min(batch_start + batch_size, total_chunks)
        batch_rows = upsert_rows[batch_start:batch_end]

        await namespace.write(
            upsert_rows=batch_rows,
            distance_metric="cosine_distance",
            schema=TURBOPUFFER_CHUNK_SCHEMA,
        )

        if total_chunks > batch_size:
            logger.debug(
                f"Incremental upsert progress: {batch_end}/{total_chunks} chunks "
                f"({batch_end * 100.0 / total_chunks:.1f}%)"
            )

    logger.debug(f"✅ Incremental upsert completed: {total_chunks} chunks")
