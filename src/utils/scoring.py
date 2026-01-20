"""
Scoring utilities for search functions.
Provides consistent scoring logic across different search implementations.
"""

import math
from datetime import UTC, datetime
from typing import Any

from typing_extensions import TypedDict

# Search candidate expansion constants
# Used to fetch more candidates than requested to avoid limit-dependent scoring issues
MAX_SEARCH_CANDIDATES = 500

# --- SCORING CONSTANTS ---
# Used in both semantic and keyword search scoring

# References scoring is a piecewise function:
#   - 0-15 `referrer_score`: linear from 0.0 to 0.7
#   - 15-30 `referrer_score`: linear from 0.7 to 1.0
#   - 30+ `referrer_score`: capped at 1.0
REFS_SCORING_BREAKPOINT = 15  # breakpoint for the piecewise function
REFS_SCORING_BREAKPOINT_SCORE = 0.7  # output score at breakpoint^
REFS_SCORING_CAP = 30  # cap for the piecewise function
REFS_SCORING_CAP_SCORE = 1.0  # output score at cap^
REFS_SCORING_CAP_MINUS_BREAKPOINT = REFS_SCORING_CAP - REFS_SCORING_BREAKPOINT
REFS_SCORING_CAP_MINUS_BREAKPOINT_SCORE = REFS_SCORING_CAP_SCORE - REFS_SCORING_BREAKPOINT_SCORE

# Recency scoring:
#   - Documents from last 30 days get full recency weight
#   - Exponential falloff in recency scoring
RECENCY_SCORING_FULL_WEIGHT_DAYS = 30  # Documents from last 30 days get full recency weight
RECENCY_SCORING_DECAY_PERIOD_DAYS = 365  # Decay period for exponential falloff in recency scoring


def get_semantic_search_scoring_config() -> dict[str, Any]:
    """
    Get scoring configuration for semantic search.

    Returns:
        Dictionary with scoring weights and parameters
    """
    return {
        "recency_weight": 0.2,  # 20% from recency
        "query_weight": 0.6,  # 60% from semantic similarity
        "references_weight": 0.2,  # 20% from references
    }


def get_keyword_search_scoring_config() -> dict[str, Any]:
    """
    Get scoring configuration for keyword search.

    Returns:
        Dictionary with scoring weights and parameters
    """
    return {
        "recency_weight": 0.2,  # 20% from recency
        "query_weight": 0.6,  # 60% from underlying OpenSearch query scoring
        "references_weight": 0.2,  # 20% from references
    }


def build_semantic_search_sql_scoring(
    query_weight: float,
    recency_weight: float,
    references_weight: float,
) -> str:
    """
    Build the SQL scoring logic for semantic search.

    Args:
        query_weight: Weight for semantic similarity
        recency_weight: Weight for recency
        references_weight: Weight for references
        full_weight_days: Days for full recency weight
        decay_period_days: Decay period for recency
    """

    # Continue the existing CTE chain by adding another CTE, then final SELECT
    return f"""
    , scored_candidates AS (
        SELECT
            *,
            1 - distance as semantic_score,
            CASE
                WHEN source_created_at >= NOW() - INTERVAL '{RECENCY_SCORING_FULL_WEIGHT_DAYS} days' THEN 1.0
                ELSE EXP(-EXTRACT(EPOCH FROM (NOW() - source_created_at)) / (86400.0 * {RECENCY_SCORING_DECAY_PERIOD_DAYS}.0))
            END as recency_score,
            CASE
                WHEN COALESCE(referrer_score, 0) <= {REFS_SCORING_BREAKPOINT} THEN
                    (COALESCE(referrer_score, 0)::float / {REFS_SCORING_BREAKPOINT}) * {REFS_SCORING_BREAKPOINT_SCORE}
                ELSE
                    {REFS_SCORING_BREAKPOINT_SCORE} + ((COALESCE(referrer_score, 0)::float - {REFS_SCORING_BREAKPOINT}) / {REFS_SCORING_CAP_MINUS_BREAKPOINT}) * {REFS_SCORING_CAP_MINUS_BREAKPOINT_SCORE}
            END as references_score
        FROM top_candidates
    )
    SELECT
        *,
        recency_score * {recency_weight} as recency_component,
        references_score * {references_weight} as references_component,
        semantic_score * {query_weight} +
        recency_score * {recency_weight} +
        references_score * {references_weight} as score
    FROM scored_candidates
    """


def format_score_components_for_analysis(
    score_components: dict[str, Any], age_days: int, search_type: str
) -> dict[str, Any]:
    """
    Format score components for detailed analysis display.

    Args:
        score_components: Raw score components
        age_days: Document age in days
        search_type: Type of search (keyword/semantic)

    Returns:
        Formatted components for analysis
    """
    return {
        "query": {
            "weight": 0.6 if search_type == "semantic" else 0.4,
            "raw_score": score_components.get("query_component", 0)
            / (0.6 if search_type == "semantic" else 0.4),
            "weighted_score": score_components.get("query_component", 0),
            "explanation": f"{search_type.title()} relevance score",
        },
        "recency": {
            "weight": 0.2,
            "raw_score": score_components.get("recency_component", 0) / 0.2,
            "weighted_score": score_components.get("recency_component", 0),
            "age_days": age_days,
            "explanation": f"Document is {age_days} days old",
        },
        "references": {
            "weight": 0.2,
            "raw_score": score_components.get("references_component", 0) / 0.2,
            "weighted_score": score_components.get("references_component", 0),
            "referrer_score": score_components.get("referrer_score", 0),
            "explanation": f"referrer_score: {score_components.get('referrer_score', 0):.2f}",
        },
    }


class ScoreComponents(TypedDict):
    semantic_score: float
    recency_component: float
    references_component: float
    score: float


def calculate_in_memory_scores(
    distance: float,
    source_created_at: datetime | str | None,
    referrer_score: int | None,
    query_weight: float,
    recency_weight: float,
    references_weight: float,
) -> ScoreComponents:
    """
    Calculate semantic search scores in memory using the same logic as SQL scoring.

    Args:
        distance: Cosine distance from vector search (1 - cosine_similarity). Ranges from 0 to 2
        source_created_at: Document creation timestamp
        referrer_score: Number of references to this document
        query_weight: Weight for semantic similarity component
        recency_weight: Weight for recency component
        references_weight: Weight for references component

    Returns:
        Dictionary with all score components and final score
    """
    # Calculate semantic similarity score (convert distance to similarity)
    # Turbopuffer uses cosine distance, so similarity = 1 - distance
    semantic_score = 1.0 - distance

    # Parse source_created_at to datetime if needed
    if isinstance(source_created_at, str):
        source_created_at = datetime.fromisoformat(source_created_at.replace("Z", "+00:00"))
    elif source_created_at is None:
        source_created_at = datetime.now(UTC)

    # Calculate recency component using exponential decay
    days_since_creation = (datetime.now(UTC) - source_created_at).days
    if days_since_creation <= RECENCY_SCORING_FULL_WEIGHT_DAYS:
        recency_score = 1.0
    else:
        recency_score = math.exp(-days_since_creation / RECENCY_SCORING_DECAY_PERIOD_DAYS)

    # Calculate references component using piecewise linear function
    ref_score = referrer_score or 0
    if ref_score <= REFS_SCORING_BREAKPOINT:
        references_score = (ref_score / REFS_SCORING_BREAKPOINT) * REFS_SCORING_BREAKPOINT_SCORE
    elif ref_score <= REFS_SCORING_CAP:
        references_score = (
            REFS_SCORING_BREAKPOINT_SCORE
            + ((ref_score - REFS_SCORING_BREAKPOINT) / REFS_SCORING_CAP_MINUS_BREAKPOINT)
            * REFS_SCORING_CAP_MINUS_BREAKPOINT_SCORE
        )
    else:
        references_score = REFS_SCORING_CAP_SCORE

    # Calculate weighted components and final score
    semantic_component = semantic_score * query_weight
    recency_component = recency_score * recency_weight
    references_component = references_score * references_weight
    final_score = semantic_component + recency_component + references_component

    return {
        "semantic_score": semantic_score,
        "recency_component": recency_component,
        "references_component": references_component,
        "score": final_score,
    }


def add_score_breakdown_to_result(
    result: dict[str, Any], query: str, search_type: str, filters: dict[str, Any] | None = None
) -> dict[str, Any]:
    """
    Add detailed score breakdown to search result for evaluation.

    Args:
        result: Search result
        query: Search query
        search_type: Type of search
        filters: Search filters

    Returns:
        Result with detailed score breakdown
    """
    # Return the result as-is for now - this would need more detailed implementation
    # to extract score components from the existing result
    return result
