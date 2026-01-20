"""
Score analyzer for understanding how documents are scored in search.
Uses the actual search functions to analyze specific documents.
"""

import json
from typing import Any

from src.clients.supabase import get_global_db_connection
from src.mcp.tools.filters import SearchFilters
from src.mcp.tools.keyword_search import perform_keyword_search
from src.mcp.tools.semantic_search import perform_semantic_search
from src.utils.scoring import (
    format_score_components_for_analysis,
)


async def analyze_keyword_score(query: str, document_id: str) -> dict[str, Any]:
    """
    Analyze how a document would score for a keyword search query.

    Args:
        query: The search query
        document_id: The document ID to analyze

    Returns:
        Dictionary with score breakdown and analysis
    """
    import logging

    logger = logging.getLogger(__name__)

    logger.info("[SCORE_ANALYZER_DEBUG] analyze_keyword_score called:")
    logger.info(f"[SCORE_ANALYZER_DEBUG]   query: {query}")
    logger.info(f"[SCORE_ANALYZER_DEBUG]   document_id: {document_id}")

    # First, run full keyword search to find the document's real ranking
    try:
        # Do full search with higher limit to find the document's true ranking
        logger.info(
            "[SCORE_ANALYZER_DEBUG] Calling perform_keyword_search with limit=50, empty filters"
        )
        # For eval scripts, we need to create a mock context since we run outside MCP server
        from src.scripts.cli import MockContext

        mock_context = MockContext()

        full_results = await perform_keyword_search(
            context=mock_context,
            query=query,
            limit=50,
            filters=SearchFilters(
                sources=[], date_from=None, date_to=None, provenance=None, document_id=None
            ),
        )
        logger.info(
            f"[SCORE_ANALYZER_DEBUG] Full search returned {len(full_results.get('results', []))} results"
        )
    except Exception as e:
        logger.error(f"[SCORE_ANALYZER_DEBUG] Error in full search: {str(e)}")
        return {"error": f"Error running keyword search: {str(e)}", "document_id": document_id}

    # Find our target document in the results
    target_result = None
    document_position = -1

    logger.info(
        f"[SCORE_ANALYZER_DEBUG] Looking for document_id '{document_id}' in {len(full_results.get('results', []))} results"
    )

    for i, result in enumerate(full_results["results"]):
        if result["document_id"] == document_id:
            target_result = result
            document_position = i + 1
            logger.info(
                f"[SCORE_ANALYZER_DEBUG] Found target document at position {document_position}"
            )
            break

    if target_result is None:
        logger.info("[SCORE_ANALYZER_DEBUG] Document not found in top 50, trying targeted search")
        # Document not found in top 50 results, try a targeted search to get its score
        try:
            targeted_results = await perform_keyword_search(
                context=mock_context,
                query=query,
                limit=1,
                filters=SearchFilters(
                    sources=[],
                    date_from=None,
                    date_to=None,
                    provenance=None,
                    document_id=document_id,
                ),
            )
            if targeted_results["results"]:
                target_result = targeted_results["results"][0]
                document_position = 51  # Indicate it's beyond top 50
                logger.info(
                    "[SCORE_ANALYZER_DEBUG] Found target document via targeted search, position set to 51"
                )
        except Exception as e:
            logger.error(f"[SCORE_ANALYZER_DEBUG] Targeted search failed: {str(e)}")

    if target_result is None:
        # Document not found or doesn't match query
        return {
            "error": f"Document {document_id} not found or doesn't match query '{query}'",
            "document_id": document_id,
            "query": query,
            "search_type": "keyword",
        }

    # Document was found and matched the query
    result = target_result

    # Get additional metadata from database if needed
    conn = await get_global_db_connection()
    try:
        row = await conn.fetchrow(
            """
            SELECT
                source_created_at,
                metadata
            FROM documents
            WHERE id = $1
            """,
            document_id,
        )

        # Calculate age for display
        source_created_at = row["source_created_at"] if row else None
        if source_created_at:
            from datetime import UTC, datetime

            now = datetime.now(UTC)
            if source_created_at.tzinfo is None:
                source_created_at = source_created_at.replace(tzinfo=UTC)
            age_days = (now - source_created_at).days
        else:
            age_days = -1

        # Parse metadata
        metadata = row["metadata"] if row else {}
        if isinstance(metadata, str):
            metadata = json.loads(metadata)

    finally:
        await conn.close()

    # Use the accurate scoring function to get real component breakdown
    from src.mcp.tools.keyword_search import get_keyword_search_fields

    get_keyword_search_fields()
    # TODO: calculating keyword score components code is legacy and doesn't handle prod references impl
    # score_components = calculate_keyword_score_components(
    #     document_id=document_id,
    #     query=query,
    #     fields=fields,  # type: ignore  # TODO: Fix type mismatch between list[str] and dict
    #     filters=None,
    # )

    # Format components for detailed analysis using centralized function
    formatted_components = format_score_components_for_analysis(
        score_components={}, age_days=age_days, search_type="keyword"
    )

    return {
        "document_id": document_id,
        "source": result["source"],
        "metadata": result.get("metadata", metadata),
        "query": query,
        "search_type": "keyword",
        "found_in_search": True,
        "total_score": 0.0,  # score_components["total_score"],
        "components": formatted_components,
        "snippets": result.get("snippets", []),
        "ranking_position": document_position if document_position > 0 else None,
    }


async def analyze_semantic_score(query: str, document_id: str) -> dict[str, Any]:
    """
    Analyze how a document would score for a semantic search query.

    Args:
        query: The search query
        document_id: The document ID to analyze

    Returns:
        Dictionary with score breakdown and analysis
    """
    # Call perform_semantic_search with document_id filter
    try:
        # For eval scripts, we need to create a mock context since we run outside MCP server
        from src.scripts.cli import MockContext

        mock_context = MockContext()

        results = await perform_semantic_search(
            context=mock_context,
            query=query,
            limit=1,
            filters=SearchFilters(
                sources=[], date_from=None, date_to=None, provenance=None, document_id=document_id
            ),
        )
    except Exception as e:
        return {"error": f"Error running semantic search: {str(e)}", "document_id": document_id}

    if not results["results"]:
        # Document not found or has no chunks
        return {
            "error": f"Document {document_id} not found or has no chunks",
            "document_id": document_id,
            "query": query,
            "search_type": "semantic",
        }

    # Extract result
    result = results["results"][0]

    # Get additional metadata from database
    conn = await get_global_db_connection()
    try:
        row = await conn.fetchrow(
            """
            SELECT
                source,
                source_created_at,
                metadata
            FROM documents
            WHERE id = $1
            """,
            document_id,
        )

        # Calculate age for display
        source_created_at = row["source_created_at"] if row else None
        if source_created_at:
            from datetime import UTC

            # now = datetime.now(UTC)
            if source_created_at.tzinfo is None:
                source_created_at = source_created_at.replace(tzinfo=UTC)
            # age_days = (now - source_created_at).days
        # else:
        # age_days = -1

        # Parse metadata
        metadata = row["metadata"] if row else {}
        if isinstance(metadata, str):
            metadata = json.loads(metadata)

    finally:
        await conn.close()

    # The result from semantic_search already has the score components
    return {
        "document_id": document_id,
        "source": row["source"] if row else "unknown",
        "metadata": metadata,
        "chunk_metadata": result.get("metadata", {}),
        "chunk_content": result.get("chunk", "")[:500],  # First 500 chars
        "query": query,
        "search_type": "semantic",
        "total_score": result["score"],
        # --- Disabled in production b/c these score components are bloat
        # "components": {
        #     "semantic": {
        #         "weight": 0.4,  # From config
        #         "raw_score": result["semantic_score"],
        #         "weighted_score": result["semantic_score"] * 0.4,
        #         "distance": 1 - result["semantic_score"],  # Convert similarity back to distance
        #         "explanation": f"Semantic similarity: {result['semantic_score']:.3f}",
        #     },
        #     "recency": {
        #         "weight": 0.3,  # From config
        #         "raw_score": result["recency_component"] / 0.3,  # Calculate raw from component
        #         "weighted_score": result["recency_component"],
        #         "age_days": age_days,
        #         "explanation": f"Document is {age_days} days old",
        #     },
        #     "references": {
        #         "weight": 0.3,  # From config
        #         "raw_score": result["references_component"] / 0.3
        #         if result.get("references_component")
        #         else 0,
        #         "weighted_score": result.get("references_component", 0),
        #         "count": "unknown",  # Not directly available in semantic search result
        #         "explanation": "References calculated in search",
        #     },
        # },
    }


async def analyze_score(query: str, document_id: str, search_type: str) -> dict[str, Any]:
    """
    Analyze how a document would score for a given query.

    Args:
        query: The search query
        document_id: The document ID to analyze
        search_type: Either "keyword" or "semantic"

    Returns:
        Dictionary with score breakdown and analysis
    """
    if search_type == "keyword":
        return await analyze_keyword_score(query, document_id)
    elif search_type == "semantic":
        return await analyze_semantic_score(query, document_id)
    else:
        return {
            "error": f"Invalid search type: {search_type}. Must be 'keyword' or 'semantic'",
            "search_type": search_type,
        }
