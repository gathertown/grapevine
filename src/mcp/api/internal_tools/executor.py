"""Executor for internal agent tools."""

from typing import Any

from fastmcp.server.context import Context

from src.mcp.api.internal_tools.linear_tool import execute_manage_linear_ticket
from src.mcp.api.tool_executor import (
    CallToolResponse,
    ErrorToolResponse,
    SuccessfulToolResponse,
)
from src.mcp.middleware.org_context import (
    _acquire_pool_from_context,
    _extract_tenant_id_from_context,
)
from src.utils.logging import get_logger

logger = get_logger(__name__)


async def execute_internal_linear_tool(
    parameters: dict[str, Any], context: Context, available_tools: list[str]
) -> CallToolResponse:
    """Execute the internal Linear ticket management tool.

    Args:
        parameters: Tool parameters (action, issue_identifier, etc.)
        context: FastMCP context for tenant and database access
        available_tools: List of available tool names for error messages

    Returns:
        CallToolResponse with success/error status
    """
    tool_name = "manage_linear_ticket"

    try:
        tenant_id = _extract_tenant_id_from_context(context)
        if not tenant_id:
            raise RuntimeError("tenant_id not found in context")

        async with _acquire_pool_from_context(context, readonly=False) as pool:
            result_dict = await execute_manage_linear_ticket(
                tenant_id=tenant_id, db_pool=pool, **parameters
            )

            success_result: SuccessfulToolResponse = {
                "tool_name": tool_name,
                "status": "success",
                "result": result_dict,
            }
            return success_result
    except Exception as e:
        logger.error(f"Error executing Linear tool: {e}")
        error_result = ErrorToolResponse(
            tool_name=tool_name,
            status="error",
            error=f"Linear tool execution failed: {str(e)}",
            available_tools=available_tools,
        )
        return error_result
