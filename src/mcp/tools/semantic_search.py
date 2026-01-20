import asyncio
from typing import Annotated

from fastmcp.server.context import Context
from pydantic import Field
from typing_extensions import TypedDict

from connectors.base import TurbopufferChunkKey

# Company name will be injected at runtime
from connectors.base.document_source import DocumentSource
from src.clients.openai import get_openai_client
from src.clients.turbopuffer import get_turbopuffer_client
from src.mcp.mcp_instance import get_mcp
from src.mcp.middleware.org_context import acquire_connection_from_context
from src.mcp.tools.filters import SearchFilters, build_turbopuffer_filters, get_filter_description
from src.permissions.verifier import batch_verify_document_access
from src.utils.scoring import (
    MAX_SEARCH_CANDIDATES,
    calculate_in_memory_scores,
    get_semantic_search_scoring_config,
)
from src.utils.tracing import trace_span


class SemanticSearchResult(TypedDict):
    document_id: str
    chunk_id: str
    chunk: str
    score: float
    metadata: dict[str, object]


class SemanticSearchResultResponse(TypedDict):
    results: list[SemanticSearchResult]
    count: int


async def perform_semantic_search(
    context: Context,
    query: str,
    limit: int = 10,
    filters: SearchFilters = SearchFilters(),
) -> SemanticSearchResultResponse:
    """
    Core semantic search implementation that can be called from MCP tool or other functions.

    Args:
        context: The FastMCP context
        query: The search query
        limit: Maximum number of results to return
        filters: Search filters to apply

    Returns:
        Dictionary with search results
    """
    if not query:
        raise ValueError("query is required")

    # Ensure limit is within bounds
    limit = max(1, min(100, limit))

    # Get scoring configuration from utility
    scoring_config = get_semantic_search_scoring_config()
    recency_weight = scoring_config["recency_weight"]
    query_weight = scoring_config["query_weight"]
    references_weight = scoring_config["references_weight"]

    # Extract tenant_id from context
    tenant_id = context.get_state("tenant_id")
    if not tenant_id:
        raise RuntimeError(
            "tenant_id not found in tool context; ensure OrgContextMiddleware is enabled"
        )

    # Warm the turbopuffer cache in the background while we embed the query
    # OK to fire and forget here - warm_cache() never throws
    turbopuffer_client = get_turbopuffer_client()
    asyncio.create_task(turbopuffer_client.warm_cache(tenant_id))

    # Generate embedding for the query
    openai_client = get_openai_client()
    async with trace_span(
        name="create_embedding",
        input_data={"query": query},
    ) as span:
        query_embedding = await openai_client.create_embedding(query)
    if not query_embedding:
        raise ValueError("Failed to generate embedding for query")

    permission_principal_token = context.get_state("permission_principal_token")
    permission_audience = context.get_state("permission_audience")
    turbopuffer_filters = build_turbopuffer_filters(
        filters, permission_principal_token, permission_audience
    )

    # Query Turbopuffer for candidates (10x the limit for reranking)
    candidate_limit = min(limit * 10, MAX_SEARCH_CANDIDATES)

    # Include attributes we need for reranking and final results
    include_attributes: list[TurbopufferChunkKey] = [
        "id",
        "document_id",
        "source",
        "content",
        "metadata",
        "source_created_at",
    ]

    async with trace_span(
        name="query_turbopuffer",
        input_data={"tenant_id": tenant_id, "top_k": candidate_limit},
        metadata={"operation": "turbopuffer_query", "filters": str(turbopuffer_filters)},
    ) as span:
        turbopuffer_results = await turbopuffer_client.query_chunks(
            tenant_id=tenant_id,
            query_vector=query_embedding,
            top_k=candidate_limit,
            filters=turbopuffer_filters,
            include_attributes=include_attributes,
        )
        span.update(output={"result_count": len(turbopuffer_results)})

    if not turbopuffer_results:
        return {"results": [], "count": 0}

    # Now fetch document metadata (referrer_score) from PostgreSQL for reranking
    document_ids = [str(result.get("document_id", "")) for result in turbopuffer_results]

    async with trace_span(
        name="fetch_and_verify_docs",
        input_data={"document_count": len(document_ids)},
    ) as span:
        async with acquire_connection_from_context(context, readonly=True) as conn:
            # Fetch document metadata needed for scoring
            doc_metadata_query = """
                SELECT id, referrer_score
                FROM documents
                WHERE id = ANY($1::varchar[])
            """
            doc_rows = await conn.fetch(doc_metadata_query, document_ids)
            doc_metadata_map = {row["id"]: row for row in doc_rows}

            # Verify document permissions - this is the authoritative security check
            accessible_document_ids = await batch_verify_document_access(
                document_ids=document_ids,
                permission_token=permission_principal_token,
                permission_audience=permission_audience,
                conn=conn,
            )

        span.update(
            output={"rows_fetched": len(doc_rows), "accessible_count": len(accessible_document_ids)}
        )

    # Perform in-memory reranking with permission filtering
    results: list[SemanticSearchResult] = []
    for tp_result in turbopuffer_results:
        document_id = str(tp_result.get("document_id", ""))

        # Skip documents the user doesn't have access to
        if document_id not in accessible_document_ids:
            continue

        doc_metadata = doc_metadata_map.get(document_id, {})

        # Calculate all score components using centralized scoring logic
        distance = tp_result.get("$dist", 2.0)  # Fallback to max of 2.0
        source_created_at_raw = tp_result.get("source_created_at")
        source_created_at = (
            source_created_at_raw if isinstance(source_created_at_raw, (str, type(None))) else None
        )
        referrer_score = doc_metadata.get("referrer_score")

        scores = calculate_in_memory_scores(
            distance=distance,
            source_created_at=source_created_at,
            referrer_score=referrer_score,
            query_weight=query_weight,
            recency_weight=recency_weight,
            references_weight=references_weight,
        )

        chunk_metadata = tp_result.get("metadata")

        results.append(
            {
                "document_id": document_id,
                "chunk_id": str(tp_result.get("id", "")),
                "chunk": str(tp_result.get("content", "")),
                "score": float(scores["score"]),
                # We can enable these for debug, but don't send these in production tool response b/c they're just bloat
                # "semantic_score": float(scores["semantic_score"]),
                # "recency_component": float(scores["recency_component"]),
                # "references_component": float(scores["references_component"]),
                "metadata": chunk_metadata or {},
            }
        )

    # Sort by final score and limit results
    results.sort(key=lambda x: float(x["score"]), reverse=True)
    results = results[:limit]

    return {"results": results, "count": len(results)}


@get_mcp().tool(
    description=f"""Search your organization's internal context for conceptually similar text using AI embeddings.

Use this tool when you need to find documents that are semantically similar to your query, even if they don't contain the exact words. This uses OpenAI embeddings to understand meaning and context.

This tool differs from keyword search:
- semantic_search: Finds conceptually similar content (e.g., searching "API rate limit" might find documents about "throttling" or "quota exceeded")
- keyword_search: Finds exact term matches (e.g., searching "API rate limit" finds documents with those exact words)

Results are ranked by a combination of semantic similarity and recency, with more recent documents getting higher scores.

{get_filter_description()}

EXAMPLE: Find recent discussions about the chat project
```
{{
    "query": "chat",
    "filters": {{
        "sources": ["{DocumentSource.SLACK.value}", "{DocumentSource.GITHUB_PRS.value}", "{DocumentSource.NOTION.value}", "{DocumentSource.LINEAR.value}"],
        "date_from": "2025-06-01",
    }},
    "limit": 8
}}
```

EXAMPLE: Find standup updates from a specific week in a specific Slack channel
```
{{
    "query": "standup",
    "filters": {{
        "sources": ["{DocumentSource.SLACK.value}"],
        "provenance": "team-platform",
        "date_from": "2025-07-16",
        "date_to": "2025-07-23",
    }},
    "limit": 10
}}
```

EXAMPLE: Find login-related code in the codebase
```
{{
    "query": "auth",
    "filters": {{
        "sources": ["{DocumentSource.GITHUB_CODE.value}"],
        "provenance": "your-repo-name-here",
    }},
    "limit": 20
}}
```

EXAMPLE: Find conceptually similar feedback in custom collection
```
{{
    "query": "users complaining about slow performance",
    "filters": {{
        "sources": ["{DocumentSource.CUSTOM.value}"],
        "provenance": "customer-feedback",
    }},
    "limit": 10
}}
```

EXAMPLE: Search custom uploaded data (invoices, receipts, transactions, etc.)
```
{{
    "query": "invoice from Acme Corp",
    "filters": {{
        "sources": ["{DocumentSource.CUSTOM_DATA.value}"],
    }},
    "limit": 10
}}
```

Returns:
- Dict with search results: {{results: [{{document_id, chunk, score, semantic_score, recency_component, references_component, metadata}}], count}}
"""
)
async def semantic_search(
    context: Context,
    query: Annotated[
        str, Field(description="Natural language query to search for semantically similar content")
    ],
    limit: Annotated[int, Field(description="Max # of results to return", ge=1, le=100)] = 10,
    filters: Annotated[
        SearchFilters, Field(description="Filters to apply to this search to narrow down results")
    ] = SearchFilters(),
) -> SemanticSearchResultResponse:
    async with trace_span(
        name="semantic_search",
        input_data={"query": query, "limit": limit, "filters": str(filters)},
    ) as span:
        result = await perform_semantic_search(
            context=context, query=query, limit=limit, filters=filters
        )
        span.update(output={"count": result["count"]})
        return result
