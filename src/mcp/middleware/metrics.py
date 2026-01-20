"""Prometheus metrics middleware for MCP server."""

import time
from typing import Any

from fastmcp.server.middleware import Middleware, MiddlewareContext
from fastmcp.server.middleware.middleware import CallNext
from prometheus_client import Counter, Histogram, generate_latest

from src.mcp.tracking import track_tool_call

# Define Prometheus metrics
mcp_tool_requests_total = Counter(
    "mcp_tool_requests_total", "Total number of MCP tool requests", ["tool", "status"]
)

mcp_tool_duration_seconds = Histogram(
    "mcp_tool_duration_seconds",
    "Duration of MCP tool requests in seconds",
    ["tool"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)

mcp_tool_errors_total = Counter(
    "mcp_tool_errors_total", "Total number of MCP tool errors", ["tool", "error_type"]
)


class MetricsMiddleware(Middleware):
    """Middleware to collect Prometheus metrics for MCP tool calls."""

    async def on_call_tool(
        self,
        context: MiddlewareContext[Any],
        call_next: CallNext[Any, Any],
    ) -> Any:
        """
        Hook called when a tool is being executed.

        Args:
            context: The middleware context containing the tool call parameters
            call_next: Function to call the next middleware or handler

        Returns:
            The tool execution result
        """
        # Extract tool name and parameters from the request
        tool_name = context.message.name if hasattr(context.message, "name") else "unknown"
        parameters = context.message.arguments if hasattr(context.message, "arguments") else {}

        # Extract tenant_id if available in context
        tenant_id = getattr(context, "tenant_id", None)

        # Track start time for Prometheus metrics
        start_time = time.perf_counter()

        try:
            # Execute the tool with tracking
            result = await track_tool_call(
                tool_name=tool_name,
                tool_func=lambda: call_next(context),
                parameters=parameters,
                tenant_id=tenant_id,
            )

            # Also update Prometheus metrics (keeping backward compatibility)
            mcp_tool_requests_total.labels(tool=tool_name, status="success").inc()
            mcp_tool_duration_seconds.labels(tool=tool_name).observe(
                time.perf_counter() - start_time
            )

            return result
        except Exception as e:
            # Update Prometheus error metrics
            mcp_tool_requests_total.labels(tool=tool_name, status="error").inc()
            mcp_tool_errors_total.labels(tool=tool_name, error_type=type(e).__name__).inc()
            mcp_tool_duration_seconds.labels(tool=tool_name).observe(
                time.perf_counter() - start_time
            )
            raise


def get_metrics() -> bytes:
    """
    Generate Prometheus metrics in text format.

    Returns:
        Metrics in Prometheus text format
    """
    return generate_latest()
