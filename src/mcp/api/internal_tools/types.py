"""Types and constants for internal agent tools."""

from typing import Any, Literal

WriteToolType = Literal["linear"]

# Map of write tool names to their OpenAI tool schemas
WRITE_TOOL_SCHEMAS: dict[WriteToolType, list[dict[str, Any]]] = {}


def register_write_tool_schemas():
    """Register all write tool schemas. Called on module import."""
    from src.mcp.api.internal_tools.linear_tool import LINEAR_TOOL_SCHEMA

    WRITE_TOOL_SCHEMAS["linear"] = [LINEAR_TOOL_SCHEMA]


# Auto-register on import
register_write_tool_schemas()
