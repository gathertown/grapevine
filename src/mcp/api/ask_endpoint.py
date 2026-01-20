"""REST API endpoint for asking questions via API key authentication."""

import json

from fastapi import APIRouter, Request, Response
from fastmcp.server.context import Context, set_context
from starlette.responses import JSONResponse

from src.mcp.mcp_instance import get_mcp
from src.mcp.utils.auth_middleware import authenticate_request
from src.utils.logging import get_logger

logger = get_logger(__name__)
router = APIRouter()

# Valid values for verbosity and levelOfThinking parameters
VALID_VERBOSITY_VALUES: set[str] = {"low", "medium", "high"}
VALID_LEVEL_OF_THINKING_VALUES: set[str] = {"minimal", "low", "medium", "high"}


@router.post("/ask")
async def ask_endpoint(request: Request) -> Response:
    """REST API endpoint for asking questions.

    Requires API key or JWT authentication via Authorization: Bearer header.
    Returns a simple answer string.
    """
    try:
        details, error_response = await authenticate_request(request)
        if error_response:
            return error_response

        # At this point, we have a valid tenant_id because error_response is None
        assert details is not None

        try:
            body = await request.json()
        except json.JSONDecodeError:
            return JSONResponse(
                {"error": "Invalid JSON in request body"},
                status_code=400,
            )

        query = body.get("query")
        if not query:
            return JSONResponse({"error": "query is required"}, status_code=400)

        # Extract new optional parameters
        fast = body.get("fast", False)
        prompt_override = body.get("promptOverride")
        verbosity = body.get("verbosity")
        level_of_thinking = body.get("levelOfThinking")

        # Validate parameter values
        validation_errors = []
        if verbosity is not None and verbosity not in VALID_VERBOSITY_VALUES:
            validation_errors.append(
                f"Invalid verbosity value '{verbosity}'. Must be one of: {', '.join(sorted(VALID_VERBOSITY_VALUES))}"
            )
        if (
            level_of_thinking is not None
            and level_of_thinking not in VALID_LEVEL_OF_THINKING_VALUES
        ):
            validation_errors.append(
                f"Invalid levelOfThinking value '{level_of_thinking}'. Must be one of: {', '.join(sorted(VALID_LEVEL_OF_THINKING_VALUES))}"
            )

        if validation_errors:
            return JSONResponse(
                {"error": "Validation error", "details": validation_errors},
                status_code=400,
            )

        mcp = get_mcp()
        context = Context(fastmcp=mcp)
        context.set_state("tenant_id", details.tenant_id)
        if details.permission_audience:
            context.set_state("permission_audience", details.permission_audience)
        if details.permission_principal_token:
            context.set_state("permission_principal_token", details.permission_principal_token)

        # Resources (DB, OpenSearch) are now acquired lazily via helper functions
        with set_context(context):
            tools = await mcp.get_tools()

            # Choose tool based on fast mode
            tool_name = "ask_agent_fast" if fast else "ask_agent"
            ask_tool = tools.get(tool_name)
            if not ask_tool:
                return JSONResponse({"error": f"{tool_name} tool not found"}, status_code=500)

            # Build tool arguments
            tool_args: dict[str, str | None] = {"query": query}
            if prompt_override is not None:
                tool_args["agent_prompt_override"] = prompt_override
            if verbosity is not None:
                tool_args["verbosity"] = verbosity
            if level_of_thinking is not None:
                tool_args["reasoning_effort"] = level_of_thinking

            result = await ask_tool.run(tool_args)
            content = result.content[0]

            answer = ""
            if hasattr(content, "text"):
                result_data = json.loads(content.text)
                answer = result_data.get("answer", "")

            return JSONResponse({"answer": answer})

    except Exception as e:
        logger.error("Error in /ask endpoint", error=str(e))
        return JSONResponse({"error": "Internal server error", "details": str(e)}, status_code=500)
