"""OpenSearch client utility for vector search operations."""

import re
from datetime import UTC, datetime
from typing import Any
from urllib.parse import unquote, urlparse

from opensearchpy import AsyncHttpConnection, AsyncOpenSearch, exceptions
from pydantic import BaseModel

from src.permissions.models import PermissionPolicy
from src.utils.logging import get_logger
from src.utils.rate_limiter import RateLimitedError, rate_limited
from src.utils.scoring import (
    RECENCY_SCORING_DECAY_PERIOD_DAYS,
    RECENCY_SCORING_FULL_WEIGHT_DAYS,
    REFS_SCORING_BREAKPOINT,
    REFS_SCORING_BREAKPOINT_SCORE,
    REFS_SCORING_CAP_MINUS_BREAKPOINT,
    REFS_SCORING_CAP_MINUS_BREAKPOINT_SCORE,
)

# We use basic authentication for all OpenSearch operations

logger = get_logger(__name__)


class OpenSearchDocument(BaseModel):
    """
    Pydantic model for OpenSearch documents. This should match `OPENSEARCH_INDEX_MAPPINGS`!
    """

    id: str
    content: str
    content_hash: str
    source: str
    document_id: str
    created_at: str
    source_created_at: str
    source_updated_at: str
    updated_at: str
    metadata: dict[str, Any]
    referrer_score: float

    # Optional fields that may be extracted from metadata
    repository: str | None = None
    organization: str | None = None
    file_path: str | None = None
    file_extension: str | None = None
    pr_title: str | None = None
    pr_number: int | None = None
    channel: str | None = None
    user: str | None = None
    page_title: str | None = None

    # Permissions fields
    permission_policy: PermissionPolicy | None = None
    permission_allowed_tokens: list[str] | None = None

    @classmethod
    def create(
        cls,
        doc_id: str,
        doc_content: str,
        content_hash: str,
        source: str,
        source_created_at: datetime,
        source_updated_at: datetime | None,
        metadata: dict[str, Any],
        referrer_score: float,
        permission_policy: PermissionPolicy | None = None,
        permission_allowed_tokens: list[str] | None = None,
    ) -> "OpenSearchDocument":
        # Convert datetimes to ISO format
        created_at_iso = source_created_at.isoformat()
        source_updated_at_iso = (
            source_updated_at.isoformat() if source_updated_at else source_created_at.isoformat()
        )
        updated_at_iso = datetime.now(UTC).isoformat()

        return cls(
            id=doc_id,
            content=doc_content,
            content_hash=content_hash,
            source=source,
            document_id=doc_id,
            created_at=created_at_iso,
            source_created_at=created_at_iso,
            source_updated_at=source_updated_at_iso,
            updated_at=updated_at_iso,
            metadata=metadata or {},
            referrer_score=referrer_score,
            repository=metadata.get("repository"),
            organization=metadata.get("organization"),
            file_path=metadata.get("file_path"),
            file_extension=metadata.get("file_extension"),
            pr_title=metadata.get("pr_title"),
            pr_number=metadata.get("pr_number"),
            channel=metadata.get("channel"),
            user=metadata.get("user"),
            page_title=metadata.get("page_title"),
            permission_policy=permission_policy,
            permission_allowed_tokens=permission_allowed_tokens,
        )


# This should match the OpenSearchDocument model!
# IMPORTANT: Update this OPENSEARCH_SANITY_CHECK_DOCUMENT whenever OPENSEARCH_INDEX_MAPPINGS changes!
OPENSEARCH_INDEX_MAPPINGS = {
    "content": {
        "type": "text",
        "analyzer": "standard",
    },
    "id": {"type": "keyword"},
    "document_id": {"type": "keyword"},
    "source": {"type": "keyword"},
    "referrer_score": {"type": "float"},
    "metadata": {"type": "object", "dynamic": True},
    "created_at": {"type": "date"},
    "updated_at": {"type": "date"},
    "pr_title": {"type": "text", "analyzer": "standard"},
    "pr_number": {"type": "integer"},
    "repository": {"type": "keyword"},
    "organization": {"type": "keyword"},
    "channel": {"type": "keyword"},
    "user": {"type": "keyword"},
    "page_title": {"type": "text", "analyzer": "standard"},
    "content_hash": {"type": "keyword"},
    "source_created_at": {"type": "date"},
    "source_updated_at": {"type": "date"},
    "file_path": {"type": "keyword"},
    "file_extension": {"type": "keyword"},
    # Cached permissions
    "permission_policy": {"type": "keyword"},
    "permission_allowed_tokens": {"type": "keyword"},
}

# Sanity check document for testing OpenSearch connectivity and permissions
OPENSEARCH_SANITY_CHECK_DOCUMENT = {
    "id": "sanity_check_doc",
    "content": "test document for sanity check",
    "content_hash": "sanity_check_hash",
    "source": "sanity_check",
    "document_id": "sanity_check_doc",
    "created_at": "2024-01-01T00:00:00Z",
    "source_created_at": "2024-01-01T00:00:00Z",
    "source_updated_at": "2024-01-01T00:00:00Z",
    "updated_at": "2024-01-01T00:00:00Z",
    "metadata": {"test": True},
    "referrer_score": 0.0,
    # Optional fields
    "repository": None,
    "organization": None,
    "file_path": None,
    "file_extension": None,
    "pr_title": None,
    "pr_number": None,
    "channel": None,
    "user": None,
    "page_title": None,
    # Permissions fields
    "permission_policy": None,
    "permission_allowed_tokens": None,
}


class OpenSearchClient:
    """A client for interacting with OpenSearch for vector search operations."""

    def __init__(self, url: str):
        """Initialize the OpenSearch client with basic authentication.

        Args:
            url: OpenSearch URL with embedded credentials.
                 Format: http://username:password@host:port or https://username:password@host:port
        """
        # Parse URL to extract components and credentials
        parsed_url = urlparse(url)
        use_ssl = parsed_url.scheme == "https"

        # Extract credentials from URL
        username = unquote(parsed_url.username) if parsed_url.username else None
        password = unquote(parsed_url.password) if parsed_url.password else None

        # Use dict format for hosts when using separate auth
        host_config = {
            "host": parsed_url.hostname,
            "port": parsed_url.port or (443 if use_ssl else 9200),
        }

        client_kwargs: dict[str, Any] = {
            "connection_class": AsyncHttpConnection,
            "use_ssl": use_ssl,
            "verify_certs": False,  # Disable SSL cert verification for development/testing
            "ssl_show_warn": False,
            "pool_maxsize": 20,
            "timeout": 30,  # default timeout is 10s, which can be too low for large docs during high load
        }

        # Configure basic authentication
        if username and password:
            logger.info("Using HTTP Basic Auth for OpenSearch")
            client_kwargs["http_auth"] = (username, password)
        else:
            raise RuntimeError(
                "OpenSearch URL must include username and password for basic authentication"
            )

        self.client = AsyncOpenSearch(hosts=[host_config], **client_kwargs)

    async def aclose(self):
        """Close the OpenSearch client and cleanup connections."""
        await self.client.close()

    @rate_limited()
    async def create_index(self, index_name: str) -> dict[str, Any]:
        """Create an index with vector field support.

        Args:
            index_name: Name of the index to create
            dimension: Dimension of vector embeddings
            mappings: Optional custom mappings

        Returns:
            Response from index creation
        """
        mappings = {"properties": OPENSEARCH_INDEX_MAPPINGS}

        settings = {
            "index": {
                # For reference, as of 8/22/25 the gather internal index is only ~1gb
                # Tenant indices aren't big enough to justify >1 shard
                "number_of_shards": 1,
                "number_of_replicas": 1,
                "mapping.total_fields.limit": 30000,
            }
        }

        try:
            return await self.client.indices.create(
                index=index_name, body={"settings": settings, "mappings": mappings}
            )
        except exceptions.RequestError as e:
            if "resource_already_exists_exception" in str(e):
                # Index already exists
                return {"acknowledged": True, "index": index_name, "already_existed": True}
            raise

    @rate_limited()
    async def index_document(self, index_name: str, document: OpenSearchDocument) -> dict[str, Any]:
        """Index a single document.

        Args:
            index_name: Name of the index
            document: OpenSearch document to index

        Returns:
            Index response
        """
        doc_id = document.id

        try:
            # Convert Pydantic model to dict for OpenSearch client
            document_dict = document.model_dump()

            response = await self.client.index(
                index=index_name,
                id=doc_id,
                body=document_dict,
                refresh=False,  # do NOT trigger or wait for the next refresh to complete, return ASAP
            )

            logger.debug(
                f"Index response: _id={response.get('_id')}, "
                f"result={response.get('result')}, "
                f"_version={response.get('_version')}"
            )

            return response
        except exceptions.TransportError as e:
            if e.status_code == 429:
                raise RateLimitedError(retry_after=60)
            raise

    @rate_limited()
    async def bulk_index_documents(
        self, index_name: str, documents: list[OpenSearchDocument]
    ) -> dict[str, Any]:
        """Index multiple documents using OpenSearch's bulk API.

        Args:
            index_name: Name of the index
            documents: List of OpenSearch documents to index

        Returns:
            Bulk index response
        """
        if not documents:
            return {"items": [], "errors": False}

        try:
            # Build bulk request body
            bulk_body = []
            for document in documents:
                # Action metadata
                bulk_body.append({"index": {"_index": index_name, "_id": document.id}})
                # Document data
                bulk_body.append(document.model_dump())

            response = await self.client.bulk(
                index=index_name,
                body=bulk_body,
                refresh=False,  # do NOT trigger or wait for the next refresh to complete, return ASAP
            )

            if response.get("errors"):
                # Log individual failures for debugging
                for item in response.get("items", []):
                    if "index" in item and item["index"].get("error"):
                        error = item["index"]["error"]
                        doc_id = item["index"]["_id"]
                        logger.error(f"Failed to index document {doc_id}: {error}")
                raise Exception(f"Failed to bulk index {len(documents)} documents in OpenSearch")

            return response

        except exceptions.TransportError as e:
            if e.status_code == 429:
                raise RateLimitedError(retry_after=60)
            raise

    @rate_limited()
    async def search_similar(
        self,
        index_name: str,
        query_vector: list[float],
        k: int = 10,
        filters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Search for similar documents using vector similarity.

        Args:
            index_name: Name of the index
            query_vector: Query embedding vector
            k: Number of results to return
            filters: Optional filters to apply

        Returns:
            List of similar documents with scores
        """
        query = {"size": k, "query": {"knn": {"embedding": {"vector": query_vector, "k": k}}}}

        # Add filters if provided
        if filters:
            query["query"] = {"bool": {"must": [query["query"]], "filter": filters}}

        try:
            response = await self.client.search(index=index_name, body=query)

            results = []
            for hit in response["hits"]["hits"]:
                result = {"id": hit["_id"], "score": hit["_score"], **hit["_source"]}
                results.append(result)

            return results
        except exceptions.TransportError as e:
            if e.status_code == 429:
                raise RateLimitedError(retry_after=60)
            raise

    @rate_limited()
    async def delete_index(self, index_name: str) -> dict[str, Any]:
        """Delete an index.

        Args:
            index_name: Name of the index to delete

        Returns:
            Deletion response
        """
        try:
            return await self.client.indices.delete(index=index_name)
        except exceptions.NotFoundError:
            return {"acknowledged": True, "index": index_name, "already_deleted": True}
        except exceptions.TransportError as e:
            if e.status_code == 429:
                raise RateLimitedError(retry_after=60)
            raise

    @rate_limited()
    async def delete_document(self, index_name: str, document_id: str) -> dict[str, Any]:
        """Delete a document from an index.

        Args:
            index_name: Name of the index
            document_id: ID of the document to delete

        Returns:
            Deletion response
        """
        try:
            return await self.client.delete(index=index_name, id=document_id)
        except exceptions.NotFoundError:
            return {"result": "not_found", "index": index_name, "id": document_id}
        except exceptions.TransportError as e:
            if e.status_code == 429:
                raise RateLimitedError(retry_after=60)
            raise

    async def index_exists(self, index_name: str) -> bool:
        """Check if an index exists.

        Args:
            index_name: Name of the index

        Returns:
            True if index exists, False otherwise
        """
        try:
            return await self.client.indices.exists(index=index_name)
        except exceptions.TransportError as e:
            if e.status_code == 429:
                raise RateLimitedError(retry_after=60)
            raise

    @rate_limited()
    async def keyword_search(
        self,
        index_name: str,
        query: str,
        fields: list[str],
        query_weight: float,
        recency_weight: float,
        references_weight: float,
        limit: int = 10,
        filters: dict[str, Any] | None = None,
        compose_variants: bool = True,
        advanced: bool = False,
    ) -> list[dict[str, Any]]:
        """Perform keyword search on text fields with `simple_query_string`.

        This implementation intentionally composes multiple keyword variants under a
        top-level bool.should (see `_build_composed_query`) to balance precision and
        recall, then wraps that query with a function_score to blend in recency.

        Design notes (what changed and why):
        - Phrase-first boosts (content only): If the full phrase appears in `content`,
          we give it a strong boost via `match_phrase` (and a near-phrase with slop=1).
          This ensures body text containing the full phrase outranks documents with
          partial/loose matches.
        - Title phrase boost (lower than content): If the full phrase appears in
          `metadata.page_title`, we add a smaller boost. This helps canonical pages
          without overpowering body matches.
        - AND / OR variants (neutral weight): We include `simple_query_string` variants
          that match both terms (AND) or any terms (OR) across all fields to preserve
          recall. Their boosts are neutral so they do not outweigh true phrase hits.
        - Recency blending: We normalize the OpenSearch score in a script_score and
          add an exponential time decay on `source_created_at`. Filters are placed
          under `filter` so they constrain results but do not affect scoring.

        The net effect is that exact/near phrases in content rank highest, exact phrase
        in title gets a helpful nudge, while looser AND/OR matches remain available but
        cannot dominate solely due to recency.

        Args:
            index_name: Name of the index
            query: Search query
            fields: Fields to search in.
            limit: Number of results to return
            filters: Optional filters to apply
            query_weight: Weight for query component (defaults to 0.4)
            recency_weight: Weight for recency component (defaults to 0.3)

        Returns:
            List of matching documents with scores
        """
        # IMPORTANT: when updating the implementation here, be sure to also update the description of
        # the @mcp.tool in `src/mcp/tools/keyword_search.py`!

        # Build query using extracted methods
        # If `advanced=True`, use simple_query_string directly to preserve operators
        # If `compose_variants=True` we assemble a bool.should with distinct clauses
        # (content phrase, near-phrase, title phrase, AND, OR). Otherwise we use a
        # single `simple_query_string` fallback.
        if advanced:
            # In advanced mode, pass query directly to preserve operators
            base_query = self._build_advanced_query(query, fields)
        else:
            base_query = (
                self._build_composed_query(query, fields)
                if compose_variants
                else self._build_base_query(query, fields)
            )
        functions = self._build_function_score_functions(
            query_weight,
            recency_weight,
            references_weight,
        )
        function_score_query = self._build_function_score_query(base_query, functions, filters)

        search_query = {
            "size": limit,
            "query": function_score_query,
        }

        # Request highlights for `content` to assist downstream display/debug. These
        # do not affect scoring.
        search_query["highlight"] = {
            "fields": {
                "content": {
                    "fragment_size": 300,  # Increased fragment size to capture more context
                    "number_of_fragments": 5,  # More fragments to ensure we capture all relevant matches
                    "boundary_chars": ".,!? \t\n",  # Break on natural boundaries
                    "max_analyzer_offset": 1000000,  # Increase for large documents
                    "type": "unified",  # Use unified highlighter for better performance
                }
            }
        }

        try:
            # Log query metadata without exposing user search terms
            query_metadata = self._extract_query_metadata(search_query)
            logger.info(
                f"[OPENSEARCH_DEBUG] Query sent to {index_name}: {query_metadata}, advanced={advanced}, query_length={len(query)}"
            )

            response = await self.client.search(index=index_name, body=search_query)

            logger.info(
                f"[OPENSEARCH_DEBUG] Response received for query (length: {len(query)}) on {index_name}: {response['hits']['total']['value']} total hits, {len(response['hits']['hits'])} returned"
            )
            if response["hits"]["hits"]:
                logger.info(
                    f"[OPENSEARCH_DEBUG] Top result: {response['hits']['hits'][0]['_id']} (score: {response['hits']['hits'][0]['_score']})"
                )

            results = []
            for hit in response["hits"]["hits"]:
                result = {"id": hit["_id"], "score": hit["_score"], **hit["_source"]}
                if "highlight" in hit:
                    result["highlights"] = hit["highlight"]
                results.append(result)

            return results
        except exceptions.TransportError as e:
            if e.status_code == 429:
                raise RateLimitedError(retry_after=60)
            raise

    def _extract_query_metadata(self, search_query: dict) -> str:
        """Extract safe metadata from search query for logging without exposing user data."""
        metadata = []

        # Basic query structure info
        if "query" in search_query and isinstance(search_query["query"], dict):
            query_keys = list(search_query["query"].keys())
            metadata.append(f"type: {query_keys[0] if query_keys else 'empty'}")

            # Count query clauses without exposing content
            if "bool" in search_query["query"]:
                bool_query = search_query["query"]["bool"]
                if "should" in bool_query:
                    metadata.append(f"should_clauses: {len(bool_query['should'])}")
                if "must" in bool_query:
                    metadata.append(f"must_clauses: {len(bool_query['must'])}")
                if "filter" in bool_query:
                    metadata.append(f"filters: {len(bool_query['filter'])}")

        # Other query components
        if "size" in search_query:
            metadata.append(f"size: {search_query['size']}")
        if "highlight" in search_query:
            metadata.append("highlighting: enabled")
        if "sort" in search_query:
            metadata.append(f"sort_fields: {len(search_query['sort'])}")

        return ", ".join(metadata) if metadata else "basic query"

    def _calculate_fuzzy_max_expansions(self, query: str, fields: list[str]) -> int:
        """Calculate dynamic fuzzy expansions based on query complexity."""
        # Rough estimate: split on spaces for term count
        estimated_terms = len(query.split())
        estimated_fields = len(fields)

        # Target staying well under 16,384 clause limit (already a very high limit)
        # Conservative estimate: terms × fields × fuzzy_expansions < 8,000
        # 50 is the default max_expansions for simple_query_string, which we'll use as our upper bound
        return min(50, max(1, 8000 // (estimated_terms * estimated_fields)))

    def _build_base_query(self, query: str, fields: list[str]) -> dict:
        """Build base simple_query_string query with dynamic fuzzy expansions."""
        max_expansions = self._calculate_fuzzy_max_expansions(query, fields)

        return {
            "simple_query_string": {
                "query": query,
                "fields": fields,
                "default_operator": "OR",
                "lenient": True,  # Skip fields where query doesn't match type
                "analyze_wildcard": True,  # Properly handle metadata.* wildcards
                "fuzzy_max_expansions": max_expansions,  # Dynamic based on query complexity
                "fuzzy_prefix_length": 0,
            }
        }

    def _strip_outer_quotes(self, s: str) -> str:
        """Strip outer quotes only if the entire string is quoted."""
        s = s.strip()
        if len(s) >= 2 and s[0] == s[-1] == '"':
            return s[1:-1]
        return s

    def _build_advanced_query(self, query: str, fields: list[str]) -> dict:
        """Build query for advanced mode that preserves OpenSearch operators."""
        max_expansions = self._calculate_fuzzy_max_expansions(query, fields)

        return {
            "simple_query_string": {
                "query": query,
                "fields": fields,
                "default_operator": "OR",  # Let explicit operators in the query take precedence
                "lenient": True,
                "analyze_wildcard": True,
                "fuzzy_max_expansions": max_expansions,
                "fuzzy_prefix_length": 0,
            }
        }

    def _build_should_clauses_for_keyword(self, keyword: str, fields: list[str]) -> list[dict]:
        """Build a list of should clauses combining phrase, near-phrase, AND and OR variants.

        Rationale and weights (detailed):
        - content phrase (boost=3.0): Highest precision signal; exact phrase in body.
        - content near-phrase (slop=1, boost=2.5): Very close variants like "leave the office".
        - title phrase (boost=1.6): Exact phrase in `metadata.page_title` gets a modest nudge.
        - AND variant (boost=1.0): Requires all tokens present; neutral weight for recall.
        - OR variant (boost=1.0): Broadest recall; neutral so it cannot dominate by itself.

        Only the content/title phrase clauses are explicitly boosted. AND/OR remain neutral
        to prevent one-token matches plus recency from overpowering phrase hits.
        """
        plain = self._strip_outer_quotes(keyword)
        max_expansions = self._calculate_fuzzy_max_expansions(plain, fields)
        tokens = [t for t in re.split(r"\s+", plain) if t]

        should: list[dict] = []

        # Strong phrase match ONLY in `content` field (boosted). We deliberately
        # avoid boosting phrases in other fields to keep body text primary.
        if len(tokens) >= 2:
            should.append({"match_phrase": {"content": {"query": plain, "boost": 3.0}}})
            # Near-phrase with small slop in `content`
            should.append({"match_phrase": {"content": {"query": plain, "slop": 1, "boost": 2.5}}})

            # Title exact-phrase boost (quoted) with lower boost than content so titles
            # help but do not outrank body matches on their own.
            title_phrase_clause = {
                "query": f'"{plain}"',
                "fields": ["metadata.page_title"],
                "default_operator": "OR",
                "lenient": True,
                "analyze_wildcard": True,
                "fuzzy_max_expansions": max_expansions,
                "fuzzy_prefix_length": 0,
                "boost": 1.6,
            }
            should.append({"simple_query_string": title_phrase_clause})

            # AND variant (neutral boost) - use default_operator AND instead of joining with " AND "
            and_clause = {
                "query": " ".join(
                    tokens
                ),  # Join with spaces, let default_operator handle the AND logic
                "fields": fields,
                "default_operator": "AND",  # This is the key fix - use AND as default_operator
                "lenient": True,
                "analyze_wildcard": True,
                "fuzzy_max_expansions": max_expansions,
                "fuzzy_prefix_length": 0,
                "boost": 1.0,
            }
            should.append({"simple_query_string": and_clause})

        # OR/default variant
        or_clause = {
            "query": plain,
            "fields": fields,
            "default_operator": "OR",
            "lenient": True,
            "analyze_wildcard": True,
            "fuzzy_max_expansions": max_expansions,
            "fuzzy_prefix_length": 0,
            "boost": 1.0,
        }
        should.append({"simple_query_string": or_clause})

        return should

    def _build_composed_query(self, keyword: str, fields: list[str]) -> dict:
        """Compose a bool.should of multiple variants for a more robust keyword match."""
        should = self._build_should_clauses_for_keyword(keyword, fields)
        return {"bool": {"should": should, "minimum_should_match": 1}}

    def _build_function_score_functions(
        self,
        query_weight: float,
        recency_weight: float,
        references_weight: float,
    ) -> list:
        """Build function score functions for query, recency, and references components.

        Scoring blend:
        - Query component: We normalize the raw OpenSearch score with
          `min(_score/50, 1.0)` and weight it by `query_weight`. The divisor controls
          how quickly the query signal saturates; 50 keeps room for separation across
          typical BM25 scores while preventing the query component from dwarfing other components.
        - Recency component: Exponential decay on `source_created_at` with a 30-day
          full-weight offset and a 365-day scale, weighted by `recency_weight`.
        - References component: Piecewise linear function applied to `referrer_score`
          field, weighted by `references_weight`.

        All functions use `score_mode=sum` and `boost_mode=replace` upstream so the
        final score is a straightforward sum of the weighted components.
        """
        functions = []

        # Add query scoring function if weight > 0
        if query_weight > 0:
            functions.append(
                {
                    "weight": query_weight,
                    "script_score": {
                        "script": "Math.min(_score / 50, 1.0)"  # Min-max normalization with cap at 50
                    },
                }
            )

        # Add recency scoring function if weight > 0. Prefer source_updated_at when present.
        if recency_weight > 0:
            # When source_updated_at exists, use it for decay
            functions.append(
                {
                    "weight": recency_weight,
                    "filter": {"exists": {"field": "source_updated_at"}},
                    "exp": {
                        "source_updated_at": {
                            # Stay at 1.0 within `offset`, then decay exponentially to 0.37 by `scale`
                            # https://docs.opensearch.org/latest/query-dsl/compound/function-score/#decay-functions
                            "origin": "now",
                            "scale": f"{RECENCY_SCORING_DECAY_PERIOD_DAYS}d",
                            "offset": f"{RECENCY_SCORING_FULL_WEIGHT_DAYS}d",
                            "decay": 0.37,
                        }
                    },
                }
            )
            # Fallback to source_created_at when updated_at is missing
            functions.append(
                {
                    "weight": recency_weight,
                    "filter": {"bool": {"must_not": [{"exists": {"field": "source_updated_at"}}]}},
                    "exp": {
                        "source_created_at": {
                            "origin": "now",
                            "scale": f"{RECENCY_SCORING_DECAY_PERIOD_DAYS}d",
                            "offset": f"{RECENCY_SCORING_FULL_WEIGHT_DAYS}d",
                            "decay": 0.37,
                        }
                    },
                }
            )

        # Add references scoring function if weight > 0
        if references_weight > 0:
            functions.append(
                {
                    "weight": references_weight,
                    "script_score": {
                        "script": {
                            # `referrer_score` should always exist, but check for safety
                            # See constants definition for scoring formula
                            "source": f"""
                                double score = doc['referrer_score'].size() > 0 ? doc['referrer_score'].value : 0.0;
                                if (score <= {REFS_SCORING_BREAKPOINT}) {{
                                    return (score / {REFS_SCORING_BREAKPOINT}) * {REFS_SCORING_BREAKPOINT_SCORE};
                                }} else {{
                                    return Math.min({REFS_SCORING_BREAKPOINT_SCORE} + ((score - {REFS_SCORING_BREAKPOINT}) / {REFS_SCORING_CAP_MINUS_BREAKPOINT}) * {REFS_SCORING_CAP_MINUS_BREAKPOINT_SCORE}, 1.0);
                                }}
                            """.strip()
                        }
                    },
                }
            )

        return functions

    def _build_function_score_query(
        self, base_query: dict, functions: list, filters: dict[str, Any] | None = None
    ) -> dict:
        """Build complete function_score query with optional filters."""
        function_score_query = {
            "function_score": {
                "query": base_query,
                "boost_mode": "replace",  # Replace original score with function scores
                "score_mode": "sum",  # Sum all function scores
                "functions": functions,
            }
        }

        if filters:
            return {"bool": {"must": [function_score_query], "filter": filters}}
        else:
            return function_score_query

    @rate_limited()
    async def bulk(
        self, index: str, body: list[dict[str, Any]], refresh: bool | str = False
    ) -> dict[str, Any]:
        """Perform bulk operations.

        Args:
            index: Index name
            body: List of operations to perform
            refresh: Whether to refresh the index after the operation

        Returns:
            Response from OpenSearch bulk API
        """
        try:
            return await self.client.bulk(index=index, body=body, refresh=refresh)
        except exceptions.TransportError as e:
            if e.status_code == 429:
                raise RateLimitedError(retry_after=60)
            raise

    @rate_limited()
    async def delete_by_query(
        self, index: str, body: dict[str, Any], refresh: bool | str = False
    ) -> dict[str, Any]:
        """Delete documents by query.

        Args:
            index: Index name
            body: Query to match documents to delete
            refresh: Whether to refresh the index after the operation

        Returns:
            Response from OpenSearch delete_by_query API
        """
        try:
            return await self.client.delete_by_query(index=index, body=body, refresh=refresh)
        except exceptions.TransportError as e:
            if e.status_code == 429:
                raise RateLimitedError(retry_after=60)
            raise

    @rate_limited()
    async def search(
        self, index: str, body: dict[str, Any], size: int | None = None
    ) -> dict[str, Any]:
        """Search documents with raw query.

        Args:
            index: Index name
            body: Query to search for documents
            size: Maximum number of results to return

        Returns:
            Response from OpenSearch search API
        """
        try:
            params: dict[str, Any] = {"index": index, "body": body}
            if size is not None:
                params["size"] = size
            return await self.client.search(**params)
        except exceptions.TransportError as e:
            if e.status_code == 429:
                raise RateLimitedError(retry_after=60)
            raise

    @rate_limited()
    async def index(
        self, index: str, body: dict[str, Any], refresh: bool | str = False
    ) -> dict[str, Any]:
        """Index a raw document.

        This is different from index_document() which takes an OpenSearchDocument.
        This method takes a raw dictionary and indexes it directly.

        Args:
            index: Index name
            body: Raw document to index
            refresh: Whether to refresh the index after the operation

        Returns:
            Response from OpenSearch index API
        """
        try:
            return await self.client.index(index=index, body=body, refresh=refresh)
        except exceptions.TransportError as e:
            if e.status_code == 429:
                raise RateLimitedError(retry_after=60)
            raise

    async def exists_alias(self, name: str) -> bool:
        """Check if alias exists.

        Args:
            name: Alias name

        Returns:
            True if alias exists, False otherwise
        """
        try:
            return await self.client.indices.exists_alias(name=name)
        except exceptions.TransportError as e:
            if e.status_code == 429:
                raise RateLimitedError(retry_after=60)
            raise

    async def put_alias(self, index: str, name: str) -> dict[str, Any]:
        """Create alias for index.

        Args:
            index: Index name
            name: Alias name

        Returns:
            Response from OpenSearch put_alias API
        """
        try:
            return await self.client.indices.put_alias(index=index, name=name)
        except exceptions.TransportError as e:
            if e.status_code == 429:
                raise RateLimitedError(retry_after=60)
            raise
