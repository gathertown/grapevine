"""
Search utilities for evaluating and comparing search results.
"""

# Make imports conditional to avoid dependency issues
try:
    from .eval_searcher import (
        extract_sources_from_results,
        parse_eval_file,
        process_eval_queries,
        query_mcp_tool,
    )

    __all__ = [
        "parse_eval_file",
        "extract_sources_from_results",
        "query_mcp_tool",
        "process_eval_queries",
    ]
except ImportError:
    # Handle missing dependencies gracefully
    __all__ = []
