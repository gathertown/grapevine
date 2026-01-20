"""MCP Tools Package - All tool modules are imported here to register with the MCP server."""

from src.utils.feature_allowlist import FeatureKeys, is_feature_allowed_in_env
from src.utils.logging import get_logger

logger = get_logger(__name__)

__all__ = [
    "get_document",
    "get_document_metadata",
    "keyword_search",
    "semantic_search",
    "ask_agent",
    "ask_agent_streaming",
    "ask_agent_fast",
    "ask_data_warehouse",
    "execute_data_warehouse_sql",
    # review_pr_streaming is conditionally registered based on feature gate
]


def register_tools():
    """Register all tools with the MCP server."""
    # Import all tools to ensure their decorators execute and register with the MCP instance
    from . import (  # noqa: F401
        ask_agent,
        ask_agent_fast,
        ask_agent_streaming,
        ask_data_warehouse,
        execute_data_warehouse_sql,
        # These "unused" imports are intentional here for decorator registration
        get_document,
        get_document_metadata,
        keyword_search,
        semantic_search,
    )

    # Conditionally register PR reviewer tool based on feature gate
    if is_feature_allowed_in_env(FeatureKeys.MCP_TOOL_PR_REVIEWER):
        logger.info("PR reviewer tool is enabled, registering...")
        from . import review_pr_streaming  # noqa: F401
    else:
        logger.info(
            "PR reviewer tool is not enabled in this environment (use feature allowlist to enable)"
        )
