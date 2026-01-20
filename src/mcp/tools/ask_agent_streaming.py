import asyncio
import json
from typing import Annotated, Any, Literal

from fastmcp.server.context import Context
from pydantic import Field

from src.mcp.api.agent import stream_advanced_search_answer
from src.mcp.api.models import FileAttachment
from src.mcp.api.prompts import build_system_prompt
from src.mcp.mcp_instance import get_mcp
from src.mcp.middleware.org_context import (
    _extract_non_billable_from_context,
    _extract_tenant_id_from_context,
)
from src.utils.tenant_config import (
    get_tenant_company_context,
    get_tenant_company_name,
)
from src.utils.usage_tracker import get_usage_tracker


def create_simplified_event(event: dict[str, Any]) -> dict[str, Any]:
    """Create a simplified, clean event for client consumption.

    TEMPORARY / STOPGAP: This function exists to provide a cleaner streaming interface
    until we have a full streaming solution integrated into the core agent architecture.

    IMPORTANT: The event types handled here must be kept in sync with the event types
    yielded by stream_advanced_search_answer() in src/mcp/api/agent.py. Currently
    supported types include:
    - "status" (string message)
    - "tool_call" (dict with tool_name, tool_parameters, result_summary)
    - "tool_result" (dict with summary)
    - "final_answer" (dict with answer, response_id)
    - "message" (dict with role)

    When adding new event types to agent.py, ensure this function is updated accordingly.
    """
    event_type = event.get("type")
    data = event.get("data")

    # Base event structure
    simplified = {"type": event_type, "timestamp": asyncio.get_event_loop().time()}

    # Simplify based on event type
    if event_type == "status":
        simplified["message"] = str(data) if data else ""

    elif event_type == "tool_call":
        if isinstance(data, dict):
            simplified["tool"] = data.get("tool_name", "unknown")
            simplified["query"] = data.get("tool_parameters", {}).get("query", "")
            # Check status first (for new "starting" events)
            status = data.get("status")
            if status == "starting":
                simplified["result"] = "starting"
            else:
                # Fallback to result_summary for backwards compatibility
                result = data.get("result_summary", "")
                if "✅" in result:
                    simplified["result"] = "success"
                elif "❌" in result:
                    simplified["result"] = "error"
                else:
                    simplified["result"] = "unknown"

    elif event_type == "tool_result":
        if isinstance(data, dict):
            summary = data.get("summary", "")
            if "✅" in summary:
                simplified["result"] = "success"
            elif "❌" in summary:
                simplified["result"] = "error"
            else:
                simplified["result"] = "completed"
            # Include brief message
            simplified["message"] = summary[:100] + "..." if len(summary) > 100 else summary

    elif event_type == "final_answer":
        if isinstance(data, dict):
            answer = data.get("answer", "")
            simplified["preview"] = answer[:200] + "..." if len(answer) > 200 else answer
            simplified["response_id"] = data.get("response_id")

    elif event_type == "message":
        if isinstance(data, dict):
            simplified["role"] = data.get("role", "unknown")

    else:
        # For unknown types, include minimal data
        simplified["data"] = str(data)[:100] + "..." if len(str(data)) > 100 else str(data)

    return simplified


# TODO(AIVP-410): Merge with the `ask_agent` API - Slackbot should be able to support a streaming tool response.
# This is essentially duplicated from the `ask_agent` tool, with some modifications for streaming.
# We should remove this duplication and push the streaming back to `ask_agent`, however
# we'll likely also need to modify the Slackbot handler. Exposing this as a separate tool
# for now so that we can test Gather <-> Grapevine integration.
@get_mcp().tool(
    description="""Ask the advanced agent a question and get a final answer with optional citations.

This wraps the server's agentic search flow previously exposed at /ask. It executes internally and returns the final answer and a compact event transcript for debugging or client-side streaming.

Returns:
- {"answer": string, "response_id": string | null, "citations": list | null, "events": list}
"""
)
async def ask_agent_streaming(
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
    disable_citations: Annotated[
        bool | None,
        Field(
            description="If true, disable citation instructions and processing. Default is False."
        ),
    ] = None,
) -> dict:
    if not query:
        raise ValueError("query is required")

    tenant_id = _extract_tenant_id_from_context(context)
    if not tenant_id:
        raise ValueError("tenant_id not found in context")

    non_billable = _extract_non_billable_from_context(context)

    # Check usage limits and record usage (early exit for gather-managed tenants or non-billable requests)
    usage_tracker = get_usage_tracker()
    usage_result = await usage_tracker.check_and_record_usage(
        tenant_id=tenant_id,
        usage_metrics={"requests": 1},
        source_type="ask_agent_streaming",
        non_billable=non_billable,
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

    company_name, company_context_text = await asyncio.gather(
        get_tenant_company_name(tenant_id),
        get_tenant_company_context(tenant_id),
    )

    # Build system prompt with company information (or use override)
    if agent_prompt_override:
        system_prompt = agent_prompt_override
    else:
        system_prompt = await build_system_prompt(
            company_name=company_name,
            company_context_text=company_context_text,
            output_format=output_format,
            tenant_id=tenant_id,
            disable_citations=disable_citations or False,
        )

    attachments = files or []

    # Stream events and collect the final answer
    final_answer: dict[str, Any] | None = None
    events: list[dict[str, Any]] = []

    # Send each event via context - we'll send down each event to the client,
    # so that it can process the events realtime
    async for event in stream_advanced_search_answer(
        query=query,
        system_prompt=system_prompt,
        context=context,
        previous_response_id=previous_response_id,
        files=attachments,
        reasoning_effort=reasoning_effort or "medium",
        verbosity=verbosity,
        output_format=output_format,
        model="gpt-5",
        disable_citations=disable_citations or False,
    ):
        # Create simplified, clean event for client consumption
        simplified_event = create_simplified_event(event)

        # Send a streaming update to the client as clean JSON
        await context.info(json.dumps(simplified_event))

        # Also collect events for final response
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
