"""Simple tracking context manager and wrapper function for MCP tool calls.

This module provides both a context manager and a wrapper function for tracking
MCP tool calls that can be easily integrated into both middleware and direct
tool execution.
"""

import inspect
import time
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

import newrelic.agent

from src.utils.logging import get_logger

logger = get_logger(__name__)

T = TypeVar("T")


def track_invalid_tool(tool_name: str) -> None:
    """Track an invalid tool call attempt.

    Args:
        tool_name: Name of the invalid tool that was requested
    """
    newrelic.agent.record_custom_metric("Custom/MCPTool/InvalidTool/Count", 1)
    logger.warning(
        "Invalid MCP tool requested",
        tool_name=tool_name,
        status="invalid",
    )


async def track_tool_call(
    tool_name: str,
    tool_func: Callable[[], T | Awaitable[T]],
    parameters: dict[str, Any] | None = None,
    tenant_id: str | None = None,
) -> T:
    """Execute a tool function with tracking.

    This function wraps tool execution with automatic metrics and logging.
    It handles both sync and async functions transparently.

    Args:
        tool_name: Name of the tool being called
        tool_func: Function to execute (can be sync or async)
        parameters: Tool parameters (for logging keys only)
        tenant_id: Tenant ID for context

    Returns:
        The result from the tool function

    Raises:
        Any exception raised by the tool function
    """
    start_time = time.perf_counter()
    parameters = parameters or {}
    status = "error"  # Default to error, will be set to success if completed
    error: BaseException | None = None
    result: T | None = None

    try:
        # Execute the tool function
        tool_result = tool_func()

        # Handle async results
        if inspect.isawaitable(tool_result):
            result = await tool_result
        else:
            result = tool_result

        # Mark as successful
        status = "success"

        return result

    except BaseException as e:
        # Capture the error (includes Exception and asyncio.CancelledError)
        error = e
        raise
    finally:
        # Always record metrics and logs
        duration_ms = (time.perf_counter() - start_time) * 1000

        # NewRelic custom metrics
        newrelic.agent.record_custom_metrics(
            [
                ("Custom/MCPTool/All/Count", 1),
                (f"Custom/MCPTool/{tool_name}/Count", 1),
                (f"Custom/MCPTool/All/{status.capitalize()}", 1),
                (f"Custom/MCPTool/{tool_name}/{status.capitalize()}", 1),
                ("Custom/MCPTool/All/DurationMS", duration_ms),
                (f"Custom/MCPTool/{tool_name}/DurationMS", duration_ms),
            ]
        )

        if status == "error" and error:
            # Record exception in NewRelic
            newrelic.agent.notice_error()

        # Structured logging
        log_data = {
            "tool_name": tool_name,
            "status": status,
            "duration_ms": duration_ms,
            "parameter_keys": list(parameters.keys()) if parameters else [],
        }

        if tenant_id:
            log_data["tenant_id"] = tenant_id

        # Extract result count if available
        if (
            status == "success"
            and isinstance(result, dict)
            and "results" in result
            and isinstance(result["results"], list)
        ):
            log_data["result_count"] = len(result["results"])

        if status == "success":
            logger.info(f"MCP tool call result: {status}", **log_data)
        else:
            if error:
                log_data["error_type"] = type(error).__name__
                log_data["error_message"] = str(error)
            logger.error(f"MCP tool call result: {status}", **log_data)
