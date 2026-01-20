"""
Tracing utilities for Langfuse integration.
Provides clean patterns for async generators and regular functions.
"""

from contextlib import asynccontextmanager
from typing import Any

from langfuse import Langfuse

from src.utils.config import (
    get_grapevine_environment,
    get_langfuse_host,
    get_langfuse_public_key,
    get_langfuse_secret_key,
    get_tracing_enabled,
)
from src.utils.logging import get_logger

logger = get_logger(__name__)


# No-op span class
class NoOpSpan:
    def update(self, output: Any = None, **kwargs):
        pass


def get_configured_langfuse_client():
    """Get a properly configured Langfuse client with credentials from config."""
    host = get_langfuse_host()
    public_key = get_langfuse_public_key()
    secret_key = get_langfuse_secret_key()
    environment = get_grapevine_environment()

    # Log configuration status (without exposing secrets)
    if public_key and secret_key:
        logger.debug(
            f"Initializing Langfuse client with host: {host}, public_key: {public_key}, secret_key: {secret_key}, environment: {environment}"
        )
    else:
        logger.warning("Langfuse credentials not configured. Tracing may not work properly.")

    # Create Langfuse client directly with parameters
    return Langfuse(
        host=host, public_key=public_key, secret_key=secret_key, environment=environment
    )


@asynccontextmanager
async def trace_span(
    name: str,
    input_data: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
):
    """Context manager for creating nested spans.

    Ensures we yield at most once. Exceptions inside the body propagate normally.
    """
    if not get_tracing_enabled():
        yield NoOpSpan()
        return

    try:
        langfuse = get_configured_langfuse_client()
    except Exception as e:
        logger.warning(f"Failed to initialize Langfuse client: {e}. Falling back to no-op span.")
        yield NoOpSpan()
        return

    # Use the Langfuse context manager directly and yield once
    with langfuse.start_as_current_span(
        name=name, input=input_data, metadata=metadata or {}
    ) as span:
        yield span


def create_agent_metadata(
    step: str, available_tools: list | None = None, **extra_fields
) -> dict[str, Any]:
    """Create standardized metadata for agent operations."""
    metadata = {"agent_step": step, **extra_fields}

    if available_tools:
        metadata["available_tools"] = available_tools

    return metadata


def create_api_metadata(endpoint: str, **extra_fields) -> dict[str, Any]:
    """Create standardized metadata for API operations."""
    return {"endpoint": endpoint, "api_version": "v1", **extra_fields}


def create_tool_metadata(tool_name: str, parameters: dict[str, Any]) -> dict[str, Any]:
    """Create standardized metadata for tool operations."""
    return {"agent_step": "tool_execution", "tool_name": tool_name, "tool_parameters": parameters}
