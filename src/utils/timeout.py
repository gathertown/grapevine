"""
Timeout utilities for handling AI model, MCP, and network timeouts.
"""

import asyncio
import builtins
from collections.abc import Callable
from typing import Any

from src.utils.logging import get_logger

logger = get_logger(__name__)


class TimeoutError(Exception):
    """Custom timeout exception with context."""

    def __init__(self, operation: str, timeout: float, details: str = ""):
        self.operation = operation
        self.timeout = timeout
        self.details = details
        super().__init__(
            f"{operation} timed out after {timeout}s{f': {details}' if details else ''}"
        )


async def with_timeout[T](
    coro_or_func: Callable[..., T] | Any, timeout: float, operation_name: str, *args, **kwargs
) -> T:
    """
    Execute an async operation with timeout.

    Args:
        coro_or_func: Coroutine or async function to execute
        timeout: Timeout in seconds
        operation_name: Description of the operation for error messages
        *args, **kwargs: Arguments to pass to the function
        mcp_client: Optional MCP client to reset on timeout (for MCP operations)

    Returns:
        Result of the operation

    Raises:
        TimeoutError: If operation times out
    """
    try:
        # If it's a function, call it; if it's already a coroutine, use it directly
        coro = coro_or_func(*args, **kwargs) if callable(coro_or_func) else coro_or_func

        return await asyncio.wait_for(coro, timeout=timeout)  # type: ignore  # TODO fix type error here, auto-suppressed on 8/5/25

    except builtins.TimeoutError:
        logger.error(f"Operation '{operation_name}' timed out after {timeout}s")

        raise TimeoutError(operation_name, timeout)
    except Exception as e:
        logger.error(f"Operation '{operation_name}' failed: {e}")
        raise
