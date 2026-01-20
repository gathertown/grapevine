"""Direct tool executor for MCP tools without network overhead."""

import json
from abc import ABC, abstractmethod
from typing import Any, Literal, TypedDict

import httpx
from fastmcp import Client

from mcp.types import CallToolResult
from src.mcp.mcp_instance import get_mcp
from src.mcp.tracking import track_invalid_tool, track_tool_call
from src.utils.config import get_remote_mcp_token, get_remote_mcp_url
from src.utils.http_auth import BearerAuth
from src.utils.logging import get_logger

logger = get_logger(__name__)


class SuccessfulToolResponse(TypedDict):
    tool_name: str
    status: Literal["success"]
    result: dict[str, Any]


class ErrorToolResponse(TypedDict):
    tool_name: str
    status: Literal["error"]
    error: str
    available_tools: list[str]


CallToolResponse = SuccessfulToolResponse | ErrorToolResponse


class BaseToolExecutor(ABC):
    """Abstract base class for tool executors with shared logic."""

    def __init__(self):
        self.tools_data: dict[str, dict[str, Any]] | None = None

    @abstractmethod
    async def _execute_tool(
        self, tool_name: str, parameters: dict[str, Any] | None
    ) -> CallToolResult:
        """Execute the tool and return the result. Must be implemented by subclasses."""
        pass

    def _check_initialized(self, method_name: str):
        """Verify tools are initialized, raise RuntimeError if not."""
        if self.tools_data is None:
            raise RuntimeError(
                f"{self.__class__.__name__} not initialized. Use {self.__class__.__name__}.create() instead."
            )

    @staticmethod
    def _should_skip_tool(tool_name: str) -> bool:
        """Determine if a tool should be filtered out from agent execution."""
        return tool_name in (
            "ask_agent",
            "ask_agent_streaming",
            "ask_agent_fast",
            "review_pr_streaming",
        )

    async def _initialize_tools(self):
        """Format local FastMCP tools for OpenAI (shared by both executors).

        This method is the single source of truth for tool initialization.
        Both DirectToolExecutor and RemoteToolExecutor use this to ensure
        consistent tool definitions based on the local codebase.
        """
        local_tools = await get_mcp().get_tools()
        if not local_tools:
            raise RuntimeError("No tools discovered from local MCP - did you register_tools?")
        formatted_tools = {}

        for tool in local_tools.values():
            # Skip filtered tools
            if BaseToolExecutor._should_skip_tool(tool.name):
                continue

            # Get the original schema from the FastMCP FunctionTool object
            original_schema = tool.parameters

            # Prepare the parameters schema for OpenAI strict mode
            parameters_schema = {**original_schema}
            parameters_schema["additionalProperties"] = False  # Required for strict mode

            # If properties exist, make all of them required (required for strict mode)
            if "properties" in parameters_schema and parameters_schema["properties"]:
                parameters_schema["required"] = list(parameters_schema["properties"].keys())

                # Remove title, default, and description from properties with $ref (required for strict mode)
                for _prop_name, prop_schema in parameters_schema["properties"].items():
                    if isinstance(prop_schema, dict) and "$ref" in prop_schema:
                        for field_to_remove in ["title", "default", "description"]:
                            prop_schema.pop(field_to_remove, None)

            # If object $defs exist, process all object defs for strict mode too
            if "$defs" in parameters_schema and parameters_schema["$defs"]:
                for _def_name, def_schema in parameters_schema["$defs"].items():
                    if isinstance(def_schema, dict) and def_schema.get("type") == "object":
                        def_schema["additionalProperties"] = False
                        if "properties" in def_schema and def_schema["properties"]:
                            def_schema["required"] = list(def_schema["properties"].keys())

            # Convert to OpenAI function format
            formatted_tools[tool.name] = {
                "type": "function",
                "name": tool.name,
                "description": tool.description,
                "parameters": parameters_schema,
                "strict": True,
            }

        self.tools_data = formatted_tools

    @staticmethod
    def _parse_tool_result(result: CallToolResult) -> dict[str, Any]:
        """Parse JSON result from MCP tool response."""
        content = result.content[0]
        # MCP tool results are always TextContent with JSON
        return json.loads(content.text)  # type: ignore[union-attr]

    def _create_tool_not_found_error(self, tool_name: str) -> ErrorToolResponse:
        """Create an error response for missing tools."""
        track_invalid_tool(tool_name)
        available_tools = list(self.tools_data.keys()) if self.tools_data else []
        return ErrorToolResponse(
            tool_name=tool_name,
            status="error",
            error=f"Tool '{tool_name}' not found",
            available_tools=available_tools,
        )

    def get_available_tools(self) -> dict[str, dict[str, Any]]:
        """Get the dictionary of available tools in OpenAI format."""
        self._check_initialized("get_available_tools")
        return self.tools_data  # type: ignore  # Already checked by _check_initialized

    async def call_tool(
        self, tool_name: str, parameters: dict[str, Any] | None = None
    ) -> CallToolResponse:
        """Execute a tool and return the result."""
        self._check_initialized("call_tool")

        if tool_name not in self.tools_data:  # type: ignore  # Already checked
            return self._create_tool_not_found_error(tool_name)

        try:
            result: CallToolResult = await track_tool_call(
                tool_name=tool_name,
                tool_func=lambda: self._execute_tool(tool_name, parameters),
                parameters=parameters,
            )

            tool_result = self._parse_tool_result(result)

            return SuccessfulToolResponse(
                tool_name=tool_name,
                status="success",
                result=tool_result,
            )

        except Exception as e:
            # The tracker has already recorded the error
            available_tools = list(self.tools_data.keys()) if self.tools_data else []
            return ErrorToolResponse(
                tool_name=tool_name,
                status="error",
                error=str(e),
                available_tools=available_tools,
            )


class DirectToolExecutor(BaseToolExecutor):
    """Execute MCP tools directly without network calls."""

    def __init__(self):
        super().__init__()
        self.tools = None

    @classmethod
    async def create(cls):
        """Create and initialize a DirectToolExecutor instance."""
        instance = cls()
        instance.tools = await get_mcp().get_tools()

        await instance._initialize_tools()
        return instance

    async def _execute_tool(
        self, tool_name: str, parameters: dict[str, Any] | None
    ) -> CallToolResult:
        """Execute a FastMCP tool directly."""
        if self.tools is None:
            raise RuntimeError("Tools not initialized")

        tool_func = self.tools[tool_name]
        return await tool_func.run(parameters or {})


class RemoteToolExecutor(BaseToolExecutor):
    """Execute MCP tools via remote MCP server HTTP calls.

    Tool definitions are initialized from the local codebase (same as DirectToolExecutor).
    The remote server is only used for tool execution, not discovery.
    """

    def __init__(self, mcp_url: str, auth: httpx.Auth):
        super().__init__()
        self.mcp_url = mcp_url
        self.auth = auth

    @classmethod
    async def create(cls, mcp_url: str, bearer_token: str):
        """Create and initialize a RemoteToolExecutor instance."""
        auth = BearerAuth(bearer_token)
        instance = cls(mcp_url, auth)
        await instance._initialize_tools()
        return instance

    async def _execute_tool(
        self, tool_name: str, parameters: dict[str, Any] | None
    ) -> CallToolResult:
        """Execute a tool via remote MCP client."""
        async with Client(self.mcp_url, auth=self.auth) as client:
            return await client.call_tool(tool_name, arguments=parameters or {})


# Global instance
_tool_executor: BaseToolExecutor | None = None


async def get_tool_executor() -> BaseToolExecutor:
    """Get the global tool executor instance.

    Returns DirectToolExecutor by default, or RemoteToolExecutor if REMOTE_MCP_TOKEN is set.

    Both executors use the local codebase as the source of truth for tool definitions.
    The only difference is where tool execution happens (local vs remote MCP server).

    Environment variables for remote tools:
    - REMOTE_MCP_URL: URL of remote MCP server
    - REMOTE_MCP_TOKEN: Bearer token for authentication with remote MCP server
    """
    global _tool_executor
    if _tool_executor is None:
        mcp_url = get_remote_mcp_url()
        bearer_token = get_remote_mcp_token()
        if bearer_token:
            logger.info(f"Initializing RemoteToolExecutor with URL: {mcp_url}")
            _tool_executor = await RemoteToolExecutor.create(mcp_url, bearer_token)
        else:
            logger.info("Initializing DirectToolExecutor for local tool execution")
            _tool_executor = await DirectToolExecutor.create()

    return _tool_executor
