"""New Relic instrumentation middleware for MCP server."""

from typing import Any

import newrelic.agent
from fastmcp.server.middleware import Middleware, MiddlewareContext
from fastmcp.server.middleware.middleware import CallNext


class NewRelicMiddleware(Middleware):
    """Middleware to add New Relic instrumentation for MCP tool calls."""

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
        # Extract tool name from the request parameters
        tool_name = context.message.name if hasattr(context.message, "name") else "unknown"
        # Extract tenant_id from FastMCP context (may be None)
        fastmcp_context = context.fastmcp_context
        tenant_id = None
        if fastmcp_context is not None:
            tenant_id = fastmcp_context.get_state("tenant_id")

        # Create a New Relic web transaction for this MCP tool call
        @newrelic.agent.web_transaction(name=f"MCP/{tool_name}")
        async def instrumented_tool_call():
            # Add custom attributes for better visibility
            newrelic.agent.add_custom_attribute("mcp.tool_name", tool_name)
            newrelic.agent.add_custom_attribute("tenant_id", tenant_id)

            # Add tool parameters (be careful not to log sensitive data)
            if hasattr(context.message, "arguments") and context.message.arguments:
                # Only log the argument keys, not values, to avoid sensitive data
                arg_keys = (
                    list(context.message.arguments.keys())
                    if isinstance(context.message.arguments, dict)
                    else []
                )
                newrelic.agent.add_custom_attribute("mcp.tool_args", ",".join(arg_keys))

            try:
                result = await call_next(context)

                # Mark transaction as successful
                newrelic.agent.add_custom_attribute("mcp.status", "success")

                # Add result metadata if available
                if isinstance(result, dict):
                    if "total_results" in result:
                        newrelic.agent.add_custom_attribute(
                            "mcp.total_results", result["total_results"]
                        )
                    if "results" in result and isinstance(result["results"], list):
                        newrelic.agent.add_custom_attribute(
                            "mcp.results_count", len(result["results"])
                        )

                return result
            except Exception as e:
                # Record the error in New Relic
                newrelic.agent.record_exception()
                newrelic.agent.add_custom_attribute("mcp.status", "error")
                newrelic.agent.add_custom_attribute("mcp.error_type", type(e).__name__)
                raise

        return await instrumented_tool_call()
