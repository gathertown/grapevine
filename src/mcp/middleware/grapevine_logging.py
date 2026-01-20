"""MCP middleware for setting up logging context from request context.

This middleware extracts relevant information from the FastMCP request context
(like tenant_id) and sets it up in the logging contextvars so that all
subsequent logging calls in the request automatically include this context.
"""

from __future__ import annotations

import json
import time
from typing import Any

from fastmcp.server.middleware import Middleware, MiddlewareContext
from fastmcp.server.middleware.middleware import CallNext

from src.utils.logging import LogContext, clear_log_context, get_logger

logger = get_logger(__name__)


class GrapevineLoggingMiddleware(Middleware):
    """Middleware that sets up logging context from FastMCP request context.

    Replaces FastMCP's LoggingMiddleware and StructuredLoggingMiddleware.

    This middleware:
    1. Clears any existing logging context at the start of each request
    2. Extracts tenant_id from the FastMCP context if available
    3. Sets up the logging context so all loggers in the request include this info
    4. Logs MCP message start/end
    5. Ensures proper cleanup after the request
    """

    def __init__(self, include_payloads: bool = True, max_payload_length: int = 1000):
        """Initialize the middleware.

        Args:
            include_payloads: Whether to include message payloads in logs
            max_payload_length: Maximum length of payload to log (prevents huge logs)
        """
        self.include_payloads = include_payloads
        self.max_payload_length = max_payload_length

    async def on_message(self, context: MiddlewareContext, call_next: CallNext) -> Any:
        """Log MCP messages with structured logging and set up logging context.

        Args:
            context: The middleware context
            call_next: Function to call the next middleware/handler
        """
        # Clear any existing logging context at start of request
        clear_log_context()

        # Extract tenant_id from FastMCP context (may be None)
        fastmcp_context = context.fastmcp_context
        tenant_id = None
        if fastmcp_context is not None:
            tenant_id = fastmcp_context.get_state("tenant_id")

        # Extract tool name from message if it's a tools/call request
        tool_name_attr = {}
        if context.method == "tools/call" and hasattr(context.message, "name"):
            tool_name_attr["tool_name"] = context.message.name

        with LogContext(
            tenant_id=tenant_id,
            source=context.source,
            type=context.type,
            method=context.method,
            **tool_name_attr,
        ):
            # Add payload if requested
            payload_attrs = {}
            if self.include_payloads and hasattr(context.message, "__dict__"):
                payload = "<non-serializable>"
                try:
                    payload = json.dumps(context.message.__dict__, default=str)
                    if len(payload) > self.max_payload_length:
                        payload = payload[: self.max_payload_length] + "..."
                except (TypeError, ValueError):
                    pass
                payload_attrs = {"payload": payload}

            logger.info("Processing MCP message", **payload_attrs)

            start_time = time.time()
            try:
                result = await call_next(context)
                duration_ms = (time.time() - start_time) * 1000
                logger.info(
                    "Completed MCP message",
                    result_type=type(result).__name__ if result else None,
                    duration_ms=round(duration_ms, 2),
                )
                return result
            except Exception as e:
                duration_ms = (time.time() - start_time) * 1000
                logger.error(
                    "Failed MCP message",
                    error_type=type(e).__name__,
                    error_message=str(e),
                    duration_ms=round(duration_ms, 2),
                )
                raise

    async def __call__(self, middleware_context: MiddlewareContext, call_next: CallNext) -> Any:
        """Process the request and set up logging context.

        Args:
            middleware_context: The middleware context
            call_next: Function to call the next middleware/handler
        """
        return await self.on_message(middleware_context, call_next)
