"""Turbopuffer client utility for vector search operations."""

import json
from typing import TypedDict, cast

from turbopuffer import NOT_GIVEN, AsyncTurbopuffer
from turbopuffer.lib.namespace import AsyncNamespace
from turbopuffer.types import Filter, RankBy, RowParam

from connectors.base import TURBOPUFFER_CHUNK_SCHEMA, BaseChunk, TurbopufferChunkKey
from src.utils.config import get_config_value, get_grapevine_environment
from src.utils.logging import get_logger

logger = get_logger(__name__)

# Our own extension of turbopuffer's RowDict type that optionally includes some common fields queried from turbopuffer
ChunkRowDict = TypedDict(
    "ChunkRowDict",
    {
        "id": str,
        "$dist": float,
        "content": str | None,
        "metadata": dict[str, object] | None,
        "document_id": str | None,
        "notion_block_ids": list[str] | None,
    },
)

MAX_TOP_K = 1200  # https://turbopuffer.com/docs/query#param-top_k


class TurbopufferClient:
    """A client for interacting with Turbopuffer for vector chunk storage."""

    def __init__(self):
        """Initialize the Turbopuffer client.

        Raises:
            ValueError: If required environment variables are not set.
        """
        api_key = get_config_value("TURBOPUFFER_API_KEY")
        region = get_config_value("TURBOPUFFER_REGION")

        if not api_key:
            raise ValueError("TURBOPUFFER_API_KEY environment variable is required")
        if not region:
            raise ValueError("TURBOPUFFER_REGION environment variable is required")

        self.client = AsyncTurbopuffer(api_key=api_key, region=region)
        self.namespace_prefix = f"{get_grapevine_environment()}-"
        logger.info(
            f"Initialized Turbopuffer client with region: {region} and namespace prefix: '{self.namespace_prefix}'"
        )

    async def aclose(self) -> None:
        """Close the underlying Turbopuffer client and cleanup connections."""
        await self.client.close()

    def _get_namespace(self, tenant_id: str) -> AsyncNamespace:
        """Get the namespace name for a given tenant."""
        return self.client.namespace(f"{self.namespace_prefix}tenant-{tenant_id}-chunks")

    async def index_chunks(
        self,
        tenant_id: str,
        doc_chunks_data: list[tuple[str, list[BaseChunk], list[list[float]]]],
        batch_size: int | None = None,
    ):
        """Index chunks with their embeddings into Turbopuffer.
        Deletes all existing chunks for the documents and indexes the new ones.

        Args:
            tenant_id: The tenant identifier
            doc_chunks_data: List of tuples containing (doc_id, chunks, embeddings)
            batch_size: Optional batch size for splitting large documents. If a document has
                       >= batch_size chunks, it will be processed with delete-once-then-batch-upsert
                       to prevent hanging this process (e.g. spinning on 10k+ chunks)
        """
        if not doc_chunks_data:
            logger.warning("No document chunk data provided")
            return

        namespace = self._get_namespace(tenant_id)

        # Check if we need to use batching for any large documents
        has_large_docs = batch_size and any(
            len(chunks) >= batch_size for _, chunks, _ in doc_chunks_data
        )

        if not has_large_docs:
            # Use the original atomic delete+upsert pattern for all documents
            await self._index_chunks_atomic(namespace, doc_chunks_data)
        else:
            # Type narrowing: if has_large_docs is true, batch_size must be non-None
            assert batch_size is not None

            # Split into small docs (atomic) and large docs (batched)
            small_docs = [
                (doc_id, chunks, embeddings)
                for doc_id, chunks, embeddings in doc_chunks_data
                if len(chunks) < batch_size
            ]
            large_docs = [
                (doc_id, chunks, embeddings)
                for doc_id, chunks, embeddings in doc_chunks_data
                if len(chunks) >= batch_size
            ]

            # Process small docs atomically
            if small_docs:
                await self._index_chunks_atomic(namespace, small_docs)

            # Process large docs with batching
            for doc_id, chunks, embeddings in large_docs:
                await self._index_chunks_batched(namespace, doc_id, chunks, embeddings, batch_size)

    async def _index_chunks_atomic(
        self,
        namespace: AsyncNamespace,
        doc_chunks_data: list[tuple[str, list[BaseChunk], list[list[float]]]],
    ):
        """Index chunks atomically with delete+upsert in a single write call."""
        # Collect all document IDs for deletion
        doc_ids = [doc_id for doc_id, _, _ in doc_chunks_data]

        # Prepare chunk records for batch upsert across all documents
        # We use Mapping[] instead of dict[] b/c it's covariant in its value type
        upsert_rows: list[RowParam] = []
        total_chunks = 0

        for doc_id, chunks, embeddings in doc_chunks_data:
            if not chunks:
                logger.warning(f"No chunks provided for document {doc_id}")
                continue

            for chunk, embedding in zip(chunks, embeddings, strict=False):
                upsert_rows.append(chunk.to_turbopuffer_chunk(embedding))

            total_chunks += len(chunks)

        try:
            await namespace.write(
                # First, delete all existing chunks for all documents
                # https://turbopuffer.com/docs/write#param-delete_by_filter
                delete_by_filter=("document_id", "In", doc_ids),
                # Then, upsert all new chunks
                upsert_rows=upsert_rows,
                distance_metric="cosine_distance",
                schema=TURBOPUFFER_CHUNK_SCHEMA,
            )

            logger.info(
                f"✅ Successfully indexed {total_chunks} chunks for {len(doc_ids)} documents in Turbopuffer"
            )

        except Exception as e:
            logger.error(
                f"❌ Failed to index chunks for {len(doc_ids)} documents in Turbopuffer: {e}"
            )
            raise

    async def _index_chunks_batched(
        self,
        namespace: AsyncNamespace,
        doc_id: str,
        chunks: list[BaseChunk],
        embeddings: list[list[float]],
        batch_size: int,
    ):
        """Index a large document's chunks using delete-once-then-batch-upsert pattern."""
        total_chunks = len(chunks)
        logger.info(
            f"Indexing large document {doc_id} with {total_chunks} chunks using batched upsert "
            f"(batch_size={batch_size})"
        )

        try:
            # Step 1: Delete all existing chunks for this document once
            await namespace.write(
                delete_by_filter=("document_id", "Eq", doc_id),
            )

            # Step 2: Upsert chunks in batches
            chunks_processed = 0
            for batch_start in range(0, total_chunks, batch_size):
                batch_end = min(batch_start + batch_size, total_chunks)
                batch_chunks = chunks[batch_start:batch_end]
                batch_embeddings = embeddings[batch_start:batch_end]

                # Prepare upsert rows for this batch
                upsert_rows: list[RowParam] = []
                for chunk, embedding in zip(batch_chunks, batch_embeddings, strict=False):
                    upsert_rows.append(chunk.to_turbopuffer_chunk(embedding))

                # Upsert this batch (no delete)
                await namespace.write(
                    upsert_rows=upsert_rows,
                    distance_metric="cosine_distance",
                    schema=TURBOPUFFER_CHUNK_SCHEMA,
                )

                chunks_processed += len(batch_chunks)
                logger.info(
                    f"Turbopuffer batched upsert progress for {doc_id}: {chunks_processed}/{total_chunks} "
                    f"chunks ({chunks_processed * 100.0 / total_chunks:.1f}%)"
                )

            logger.info(
                f"✅ Successfully indexed {total_chunks} chunks for document {doc_id} in Turbopuffer "
                f"(batched)"
            )

        except Exception as e:
            logger.error(
                f"❌ Failed to index chunks for document {doc_id} in Turbopuffer (batched): {e}"
            )
            raise

    async def warm_cache(self, tenant_id: str):
        """
        Warm the cache for a tenant. This method never throws.
        https://turbopuffer.com/docs/warm-cache
        """
        namespace = self._get_namespace(tenant_id)
        try:
            await namespace.hint_cache_warm()
        except Exception as e:
            # Suppress errors here - we don't care about a warming hint failing
            logger.warning(f"Failed to warm turbopuffer cache for tenant {tenant_id}: {e}")

    async def query_chunks(
        self,
        tenant_id: str,
        query_vector: list[float] | None,
        top_k: int = 10,
        filters: Filter | None = None,
        include_attributes: list[TurbopufferChunkKey] | None = None,
    ) -> list[ChunkRowDict]:
        """Query for chunks using vector similarity or metadata-based ranking.

        Args:
            tenant_id: The tenant identifier
            query_vector: Query embedding vector for similarity search. If None, ranks by `updated_at desc`.
            top_k: Number of results to return
            filters: Optional filters for the query
            include_attributes: Optional list of attributes to include in results.
                                If `metadata` is included, it will be parsed from a JSON string to a dictionary.

        Returns:
            List of matching chunks with metadata
        """
        namespace = self._get_namespace(tenant_id)

        # Default include attributes
        if include_attributes is None:
            include_attributes = [
                "id",
                "document_id",
                "content",
                "metadata",
            ]

        if top_k > MAX_TOP_K:
            logger.warning(
                f"Turbopuffer query_chunks top_k is greater than {MAX_TOP_K}, setting to {MAX_TOP_K}"
            )
        top_k = min(top_k, MAX_TOP_K)

        try:
            # Choose ranking method based on whether query_vector is provided
            rank_by: RankBy = (
                ("vector", "ANN", query_vector)
                if query_vector is not None
                else ("updated_at", "desc")
            )
            response = await namespace.query(
                rank_by=rank_by,
                top_k=top_k,
                filters=filters or NOT_GIVEN,
                include_attributes=include_attributes,
            )
            if not response.rows:
                return []

            results: list[ChunkRowDict] = []
            for row in response.rows:
                result = row.to_dict()
                # ChunkRowDict always guarantees a parsed `metadata`, so parse it here
                if "metadata" in result and result.get("metadata"):
                    try:
                        result["metadata"] = json.loads(str(result["metadata"]))
                    except json.JSONDecodeError:
                        logger.error(
                            f"❌ Failed to parse metadata for chunk {result['id']}: {result['metadata']}"
                        )
                        result["metadata"] = {
                            "INVALID_METADATA": f"Failed to parse metadata! Original value: {result['metadata']}"
                        }
                results.append(
                    # should be a safe cast given the parsing above
                    cast(ChunkRowDict, result)
                )

            logger.info(f"✅ Successfully queried {len(results)} chunks from Turbopuffer")
            return results

        except Exception as e:
            logger.error(f"❌ Failed to query chunks from Turbopuffer: {e}")
            raise

    async def get_existing_chunk_hashes(self, tenant_id: str, doc_id: str) -> dict[str, str]:
        """Get existing chunk IDs and content hashes for a document.

        Used for incremental indexing to determine which chunks have changed.

        For large documents (>MAX_TOP_K chunks), we use cursor-based pagination
        by advancing a filter on the updated_at attribute. This handles any
        number of chunks without hitting the Turbopuffer query limit.

        See: https://turbopuffer.com/docs/query#pagination

        Args:
            tenant_id: The tenant identifier
            doc_id: The document ID to fetch chunks for

        Returns:
            Dict mapping chunk_id -> content_hash for all existing chunks.
            Returns empty dict on error (triggers full reindex).
        """
        namespace = self._get_namespace(tenant_id)
        result: dict[str, str] = {}
        last_updated_at: str | None = None
        page_count = 0

        try:
            while True:
                page_count += 1

                # Build filter: always filter by document_id, optionally by updated_at for pagination
                if last_updated_at is None:
                    query_filter: Filter = ("document_id", "Eq", doc_id)
                else:
                    # Paginate by filtering for older chunks than what we've seen
                    # https://turbopuffer.com/docs/query#pagination
                    query_filter = cast(
                        Filter,
                        (
                            "And",
                            [
                                ("document_id", "Eq", doc_id),
                                ("updated_at", "Lt", last_updated_at),
                            ],
                        ),
                    )

                response = await namespace.query(
                    rank_by=("updated_at", "desc"),
                    top_k=MAX_TOP_K,
                    filters=query_filter,
                    include_attributes=["id", "content_hash", "updated_at"],
                )

                if not response.rows:
                    break

                # Process rows and track last updated_at for pagination
                for row in response.rows:
                    row_dict = row.to_dict()
                    chunk_id = row_dict.get("id")
                    content_hash = row_dict.get("content_hash")
                    updated_at = row_dict.get("updated_at")

                    if chunk_id and content_hash:
                        result[str(chunk_id)] = str(content_hash)

                    # Track the oldest updated_at we've seen for the next page
                    if updated_at:
                        last_updated_at = str(updated_at)

                # If we got fewer than MAX_TOP_K, we've fetched all chunks
                if len(response.rows) < MAX_TOP_K:
                    break

                logger.debug(
                    f"Pagination: fetched page {page_count} for doc {doc_id}, "
                    f"total chunks so far: {len(result)}"
                )

            if page_count > 1:
                logger.debug(
                    f"Fetched {len(result)} existing chunk hashes for large document {doc_id} "
                    f"({page_count} pages)"
                )
            else:
                logger.debug(f"Fetched {len(result)} existing chunk hashes for document {doc_id}")

            return result

        except Exception as e:
            logger.warning(
                f"Failed to fetch existing chunk hashes for {doc_id}: {e}. "
                "Will proceed with full re-index."
            )
            return {}

    async def delete_chunks(self, tenant_id: str, doc_id: str):
        """Delete all chunks for a document from Turbopuffer."""
        namespace = self._get_namespace(tenant_id)
        await namespace.write(
            delete_by_filter=("document_id", "Eq", doc_id),
        )

        logger.info(f"✅ Successfully deleted chunks for document {doc_id} from Turbopuffer")

    async def delete_chunks_by_ids(self, tenant_id: str, chunk_ids: list[str]):
        """Delete specific chunks by their IDs from Turbopuffer.

        Args:
            tenant_id: The tenant identifier
            chunk_ids: List of chunk IDs to delete
        """
        if not chunk_ids:
            return

        namespace = self._get_namespace(tenant_id)
        await namespace.write(
            delete_by_filter=("id", "In", chunk_ids),
        )

        logger.debug(f"Deleted {len(chunk_ids)} specific chunks from Turbopuffer")

    async def namespace_exists(self, tenant_id: str) -> bool:
        """Check if a namespace exists for a tenant.

        Args:
            tenant_id: The tenant identifier

        Returns:
            True if the namespace exists, False otherwise
        """
        namespace = self._get_namespace(tenant_id)
        return await namespace.exists()

    async def delete_namespace(self, tenant_id: str):
        """Delete the namespace and all data in it for a tenant.

        If the namespace doesn't exist, this is a no-op and logs accordingly.
        """
        namespace = self._get_namespace(tenant_id)

        # Check if namespace exists first to avoid unnecessary retries
        if not await namespace.exists():
            logger.info(
                f"Turbopuffer namespace for tenant {tenant_id} does not exist, skipping deletion"
            )
            return

        await namespace.delete_all()
        logger.info(f"✅ Deleted turbopuffer namespace for tenant {tenant_id}")


# Global client instance
_turbopuffer_client: TurbopufferClient | None = None


def get_turbopuffer_client() -> TurbopufferClient:
    """Get or create a global TurbopufferClient instance."""
    global _turbopuffer_client
    if _turbopuffer_client is None:
        _turbopuffer_client = TurbopufferClient()
    return _turbopuffer_client


async def close_turbopuffer_client() -> None:
    """Close the global TurbopufferClient instance if it exists.

    This properly closes the underlying aiohttp session to prevent
    "Unclosed client session" warnings.
    """
    global _turbopuffer_client
    if _turbopuffer_client is not None:
        await _turbopuffer_client.aclose()
        _turbopuffer_client = None
