from typing import Annotated

from fastmcp.server.context import Context
from pydantic import Field

from src.mcp.api.internal_tools.types import WriteToolType
from src.mcp.api.models import FileAttachment
from src.mcp.mcp_instance import get_mcp
from src.mcp.tools.ask_agent import _ask_agent_impl
from src.utils.logging import get_logger

logger = get_logger(__name__)


@get_mcp().tool(
    description="""Ask the advanced agent a question and get a final answer (optimized for speed).

This is a faster variant of ask_agent. Use this when speed is more important than thoroughness.

Returns:
- {"answer": string, "response_id": string | null, "events": list}
"""
)
async def ask_agent_fast(
    context: Context,
    query: Annotated[str, Field(description="User question to answer with agentic search")],
    files: Annotated[
        list[FileAttachment] | None, Field(description="Optional file attachments")
    ] = None,
    previous_response_id: Annotated[
        str | None, Field(description="Optional prior response ID to continue the conversation")
    ] = None,
    output_format: Annotated[
        str | None, Field(description="Output format: 'slack' for Slack markdown formatting")
    ] = None,
    agent_prompt_override: Annotated[
        str | None, Field(description="Optional override for the system prompt")
    ] = None,
    reasoning_effort: Annotated[
        str,
        Field(
            description="Reasoning effort level: 'minimal', 'low', 'medium', 'high'. We recommend the default of `minimal` for speed.",
            default="minimal",
        ),
    ] = "minimal",
    verbosity: Annotated[
        str,
        Field(
            description="Verbosity level: 'low', 'medium', 'high'. We recommend the default of `low` for speed.",
            default="low",
        ),
    ] = "low",
    disable_citations: Annotated[
        bool,
        Field(
            description="If True, disable citation instructions and processing. Default is False.",
            default=False,
        ),
    ] = False,
    write_tools: Annotated[
        list[WriteToolType] | None,
        Field(
            description="List of write tools to enable for the agent. Options: 'linear' for Linear ticket management. Default is empty list.",
        ),
    ] = None,
) -> dict:
    """Fast variant of ask_agent optimized for speed."""
    write_tools = write_tools or []
    logger.info("ask_agent_fast - Tool execution starting")

    # Use the shared implementation with fast configuration
    return await _ask_agent_impl(
        context=context,
        query=query,
        files=files,
        previous_response_id=previous_response_id,
        output_format=output_format,
        agent_prompt_override=agent_prompt_override,
        reasoning_effort=reasoning_effort,  # Fast: defaults to `minimal`
        verbosity=verbosity,  # Fast: defaults to `low`
        # You'd think gpt-5-mini would be worth using here, but it seems to be noticeably worse at following instructions than gpt-5
        # which makes it bad at stuff like parallelizing tool calls. See more discussion at https://gather-town.slack.com/archives/C08BMCZK81F/p1762392387149029
        # In empirical testing, gpt-5 seems similarly fast to gpt-5-mini with these configs but has better accuracy.
        model="gpt-5",
        fast_mode_prompt=True,  # Fast: optimize system prompt for speed
        disable_citations=disable_citations,
        write_tools=write_tools,
    )
