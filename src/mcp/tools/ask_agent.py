import asyncio
from typing import Annotated, Any, Literal

from fastmcp.server.context import Context
from pydantic import Field

from src.mcp.api.agent import stream_advanced_search_answer
from src.mcp.api.internal_tools.types import WriteToolType
from src.mcp.api.models import FileAttachment
from src.mcp.api.prompts import build_system_prompt
from src.mcp.mcp_instance import get_mcp
from src.mcp.middleware.org_context import (
    _extract_non_billable_from_context,
    _extract_tenant_id_from_context,
)
from src.utils.logging import get_logger
from src.utils.tenant_config import (
    get_tenant_company_context,
    get_tenant_company_name,
)
from src.utils.usage_tracker import get_usage_tracker

logger = get_logger(__name__)


async def _ask_agent_impl(
    context: Context,
    query: str,
    files: list[FileAttachment] | None = None,
    previous_response_id: str | None = None,
    output_format: str | None = None,
    agent_prompt_override: str | None = None,
    reasoning_effort: str = "medium",
    verbosity: str | None = None,
    model: str = "gpt-5",
    fast_mode_prompt: bool = False,
    disable_tools: bool = False,
    disable_citations: bool = False,
    write_tools: list[WriteToolType] | None = None,
) -> dict:
    """Internal implementation of ask_agent that can be reused by variants.

    Args:
        context: MCP context with tenant information
        query: User question
        files: Optional file attachments
        previous_response_id: Optional conversation history
        output_format: Optional output format (e.g., 'slack')
        agent_prompt_override: Optional system prompt override
        reasoning_effort: OpenAI reasoning effort level
        verbosity: OpenAI verbosity level
        model: Model to use (e.g., 'gpt-5', 'gpt-5-mini')
        fast_mode_prompt: If True, optimize prompt for speed over thoroughness
        disable_tools: If True, disable tool calling in the agent loop
        disable_citations: If True, disable citation instructions and processing
        write_tools: List of write tools to enable (e.g., ['linear'])
    """
    write_tools_list: list[WriteToolType] = write_tools or []
    logger.info("_ask_agent_impl - Starting")

    if not query:
        raise ValueError("query is required")

    # Extract tenant_id and non_billable flag from context
    logger.info("_ask_agent_impl - Extracting tenant_id from context")
    tenant_id = _extract_tenant_id_from_context(context)
    logger.info(f"_ask_agent_impl - Tenant ID: {tenant_id}")
    if not tenant_id:
        raise ValueError("tenant_id not found in context")

    non_billable = _extract_non_billable_from_context(context)

    # Check usage limits and record usage (early exit for gather-managed tenants or non-billable requests)
    import time

    usage_check_start = time.time()
    logger.info(f"_ask_agent_impl - Checking usage limits for tenant {tenant_id}")
    usage_tracker = get_usage_tracker()
    usage_result = await usage_tracker.check_and_record_usage(
        tenant_id=tenant_id,
        usage_metrics={"requests": 1},
        source_type="ask_agent",
        non_billable=non_billable,
    )
    usage_check_duration = time.time() - usage_check_start
    logger.info(
        f"_ask_agent_impl - Usage check complete for tenant {tenant_id}, "
        f"allowed: {usage_result.allowed}, duration: {usage_check_duration:.3f}s"
    )

    # Return usage limit message if limits exceeded
    if not usage_result.allowed:
        from src.utils.usage_limit_message import generate_usage_limit_message

        usage_message = await generate_usage_limit_message(tenant_id, usage_result)
        return {
            "answer": usage_message,
            "response_id": None,
            "events": [],
        }

    # Get tenant-specific company information
    logger.info("_ask_agent_impl - Fetching tenant company information")
    company_name, company_context_text = await asyncio.gather(
        get_tenant_company_name(tenant_id),
        get_tenant_company_context(tenant_id),
    )
    logger.info(f"_ask_agent_impl - Company info fetched: {company_name}")

    # Build system prompt with company information (or use override)
    logger.info("_ask_agent_impl - Building system prompt")
    if agent_prompt_override:
        system_prompt = agent_prompt_override
    else:
        system_prompt = await build_system_prompt(
            company_name=company_name,
            company_context_text=company_context_text,
            output_format=output_format,
            tenant_id=tenant_id,
            fast_mode_prompt=fast_mode_prompt,
            disable_citations=disable_citations,
            write_tools=write_tools_list,
        )
    logger.info("_ask_agent_impl - System prompt built")

    # Normalize files default
    attachments = files or []

    # Apply model override if provided
    # Stream events and collect the final answer
    logger.info("_ask_agent_impl - Starting advanced search answer streaming")
    final_answer: dict[str, Any] | None = None
    events: list[dict[str, Any]] = []

    async for event in stream_advanced_search_answer(
        query=query,
        system_prompt=system_prompt,
        context=context,
        previous_response_id=previous_response_id,
        files=attachments,
        reasoning_effort=reasoning_effort,
        verbosity=verbosity,
        output_format=output_format,
        model=model,
        disable_tools=disable_tools,
        disable_citations=disable_citations,
        write_tools=write_tools_list,
    ):
        # Keep small transcript (can be filtered further if needed)
        events.append(event)
        if event.get("type") == "final_answer":
            final_answer = event.get("data")

    # Normalize result
    if not final_answer:
        # Extract last status or agent_decision for context
        summary = next(
            (e for e in reversed(events) if e.get("type") in {"status", "agent_decision", "error"}),
            None,
        )
        return {
            "answer": "",
            "response_id": None,
            "events": events[-50:],  # cap transcript length
            "summary": summary,
        }

    return {
        "answer": final_answer.get("answer"),
        "response_id": final_answer.get("response_id"),
        "events": events[-50:],  # cap transcript length for response size
    }


@get_mcp().tool(
    description="""Ask the advanced agent a question and get a final answer.

This wraps the server's agentic search flow previously exposed at /ask. It executes internally and returns the final answer with embedded citation deeplinks and a compact event transcript for debugging or client-side streaming.

Returns:
- {"answer": string, "response_id": string | null, "events": list}
"""
)
async def ask_agent(
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
        Literal["minimal", "low", "medium", "high"] | None,
        Field(description="OpenAI reasoning effort level for GPT-5 thinking"),
    ] = None,
    verbosity: Annotated[
        Literal["low", "medium", "high"] | None,
        Field(description="OpenAI verbosity level for response detail"),
    ] = None,
    disable_tools: Annotated[
        bool | None,
        Field(
            description="If true, disable tool calling in the agent loop for faster text-only responses"
        ),
    ] = None,
    disable_citations: Annotated[
        bool | None,
        Field(
            description="If true, disable citation instructions and processing. Default is False."
        ),
    ] = None,
    write_tools: Annotated[
        list[WriteToolType] | None,
        Field(
            description="List of write tools to enable for the agent. Options: 'linear' for Linear ticket management. Default is empty list.",
        ),
    ] = None,
) -> dict:
    write_tools = write_tools or []
    logger.info("ask_agent - Tool execution starting")

    return await _ask_agent_impl(
        context=context,
        query=query,
        files=files,
        previous_response_id=previous_response_id,
        output_format=output_format,
        agent_prompt_override=agent_prompt_override,
        reasoning_effort=reasoning_effort or "medium",
        verbosity=verbosity,
        model="gpt-5",
        disable_tools=disable_tools or False,
        disable_citations=disable_citations or False,
        write_tools=write_tools,
    )
