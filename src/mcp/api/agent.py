import asyncio
import base64
import json
import os
from typing import Any, cast

import newrelic.agent
from fastmcp.server.context import Context

from src.clients.openai import get_async_openai_client
from src.mcp.api.citation_resolver import replace_citations_with_deeplinks
from src.mcp.api.internal_tools.executor import execute_internal_linear_tool
from src.mcp.api.internal_tools.types import WRITE_TOOL_SCHEMAS, WriteToolType
from src.mcp.api.models import AgentDecision, FileAttachment
from src.mcp.api.tool_executor import (
    CallToolResponse,
    ErrorToolResponse,
    get_tool_executor,
)
from src.mcp.api.usage_tracking import report_usage_data
from src.mcp.middleware.org_context import (
    _acquire_pool_from_context,
    _extract_permission_principal_token_from_context,
    _extract_tenant_id_from_context,
)
from src.utils.config import (
    get_agent_context_window_buffer,
    get_agent_debug,
    get_agent_max_messages,
    get_agent_openai_timeout,
    get_agent_tool_timeout,
    get_context_window,
)
from src.utils.errors import (
    collect_openai_error,
    collect_timeout_error,
)
from src.utils.logging import get_logger
from src.utils.timeout import TimeoutError, with_timeout
from src.utils.token_counting import count_messages_tokens
from src.utils.tracing import create_agent_metadata, create_tool_metadata, trace_span

logger = get_logger(__name__)

# Configuration constants from centralized config
MAX_MESSAGES = get_agent_max_messages()
CONTEXT_WINDOW_BUFFER = get_agent_context_window_buffer()
AGENT_DEBUG = get_agent_debug()

# Timeout constants (in seconds)
OPENAI_TIMEOUT = get_agent_openai_timeout()  # OpenAI API calls
TOOL_TIMEOUT = get_agent_tool_timeout()  # MCP tool calls

AVAILABLE_TOOLS: dict[str, Any] = {}
OPENAI_TOOLS: list[dict[str, Any]] = []


def format_tool_response_message(call_id: str, result) -> dict:
    """Format a tool response as a message for the OpenAI Responses API."""

    # Format the result as a string for OpenAI
    output = json.dumps(result) if isinstance(result, dict) else str(result)

    return {"type": "function_call_output", "call_id": call_id, "output": output}


def process_files_to_message_content(files, query: str) -> dict[str, Any]:
    """Process files and create user message with file support for OpenAI API.

    Args:
        files: List of FileAttachment objects with name, mimetype, and content (base64)
        query: The text query to include in the message

    Returns:
        Dictionary representing the user message with content array for OpenAI API
    """
    user_message = {"role": "user", "content": []}
    # Add the text query
    user_message["content"].append({"type": "input_text", "text": query})  # type: ignore  # TODO fix type error here, auto-suppressed on 8/5/25

    # Process files if provided
    if files and len(files) > 0:
        for file in files:
            if file.mimetype.startswith("image/"):
                # Handle image files for OpenAI Vision API
                user_message["content"].append(  # type: ignore  # TODO fix type error here, auto-suppressed on 8/5/25
                    {
                        "type": "input_image",
                        "image_url": f"data:{file.mimetype};base64,{file.content}",
                    }
                )
            else:
                # Handle non-image files by adding their content as text
                try:
                    # Try to decode as text
                    if file.mimetype.startswith("text/"):
                        decoded_content = base64.b64decode(file.content).decode("utf-8")
                        user_message["content"].append(  # type: ignore  # TODO fix type error here, auto-suppressed on 8/5/25
                            {
                                "type": "input_text",
                                "text": f"\n\n**File: {file.name}**\n{decoded_content}",
                            }
                        )
                    else:
                        # For other file types, just mention the file
                        user_message["content"].append(  # type: ignore  # TODO fix type error here, auto-suppressed on 8/5/25
                            {
                                "type": "input_text",
                                "text": f"\n\n**File attached: {file.name} ({file.mimetype})**",
                            }
                        )
                except Exception as e:
                    logger.warning(f"Could not process file {file.name}: {e}")
                    user_message["content"].append(  # type: ignore  # TODO fix type error here, auto-suppressed on 8/5/25
                        {
                            "type": "input_text",
                            "text": f"\n\n**File attached: {file.name} ({file.mimetype}) - could not read content**",
                        }
                    )

    # If no files, use simple text format
    if not files or len(files) == 0:
        user_message = {"role": "user", "content": query}

    return user_message


def _create_decision_dict(decision_model: AgentDecision, reasoning_text: str) -> dict[str, Any]:
    """Create standardized decision dictionary for tracing and events."""
    decision_dict = {
        "reasoning": reasoning_text,
        "decision": decision_model.decision,
        "confidence": decision_model.confidence,
    }

    # Add final_answer if present (only when decision is 'finish')
    if decision_model.final_answer is not None:
        decision_dict["final_answer"] = decision_model.final_answer

    return decision_dict


def _is_guideline_violation_error(error: Exception) -> bool:
    """Check if an error is an OpenAI guideline violation error."""
    error_str = str(error).lower()
    return (
        "invalid_prompt" in error_str
        and "flagged as potentially violating our usage policy" in error_str
    )


async def _make_openai_call(
    request_params: dict[str, Any], reasoning_effort: str = "medium", verbosity: str | None = None
):
    """Make the OpenAI API call with consistent parameters and timeout."""

    async def api_call():
        openai_params = {
            **request_params,
            "text_format": AgentDecision,
            "reasoning": {"effort": reasoning_effort},
        }

        # Add verbosity if specified
        if verbosity is not None:
            openai_params["text"] = {"verbosity": verbosity}

        return await get_async_openai_client().responses.parse(**openai_params)

    response = await with_timeout(api_call(), OPENAI_TIMEOUT, "openai_api_call")
    report_usage_data(response)
    return response


def _process_response(
    response, reasoning_suffix: str = ""
) -> tuple[dict[str, Any], list[dict[str, Any]], str | None]:
    """Process OpenAI response and return standardized decision, tool_calls, response_id."""
    tool_calls = []
    if hasattr(response, "output") and response.output:
        for item in response.output:
            if hasattr(item, "type") and item.type == "function_call":
                tool_calls.append(item)

    if tool_calls:
        try:
            parsed_tool_calls = []
            for tool_call in tool_calls:
                tool_name = tool_call.name
                tool_parameters = json.loads(tool_call.arguments) if tool_call.arguments else {}

                parsed_tool_calls.append(
                    {
                        "name": tool_name,
                        "parameters": tool_parameters,
                        "call_id": getattr(tool_call, "call_id", None),
                    }
                )

            decision_model = response.output_parsed or AgentDecision(
                decision="continue", confidence="high", final_answer=None
            )
            decision = _create_decision_dict(
                decision_model, f"agent did some thinking{reasoning_suffix}"
            )

            if AGENT_DEBUG:
                tool_names = [tc["name"] for tc in parsed_tool_calls]
                logger.debug(f"OpenAI chose {len(parsed_tool_calls)} tools: {tool_names}")
                for tc in parsed_tool_calls:
                    logger.debug(f"Tool: {tc['name']}, Args: {tc['parameters']}")

            return decision, parsed_tool_calls, response.id

        except Exception as e:
            if AGENT_DEBUG:
                logger.debug(f"Error parsing tool call: {e}")
            decision_model = response.output_parsed or AgentDecision(
                decision="finish", confidence="low", final_answer=None
            )
            error_reasoning = f"Error parsing tool call: {e}"
            decision = _create_decision_dict(decision_model, error_reasoning)

            return decision, [], response.id
    else:
        # No tool calls, use structured output directly
        decision_model = response.output_parsed
        decision = _create_decision_dict(
            decision_model, f"agent did some thinking{reasoning_suffix}"
        )

        return decision, [], response.id


async def _agent_think(
    additional_messages: list[dict],
    previous_response_id: str | None = None,
    reasoning_effort: str = "medium",
    verbosity: str | None = None,
    model: str = "gpt-5",
    disable_tools: bool = False,
    write_tools: list[WriteToolType] | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]], str | None]:
    """Agent decides next action based on new messages since last call.

    Args:
        additional_messages: New messages to add to the conversation (tool outputs, user messages, etc.)
        previous_response_id: Previous response ID for state preservation
        reasoning_effort: OpenAI reasoning effort level ("minimal", "low", "medium", "high")
        verbosity: OpenAI verbosity level for response detail ("low", "medium", "high", or None)
        model: OpenAI model to use for the agent loop
        disable_tools: If True, disable tool calling (agent will only generate text responses)
        write_tools: List of write tools to enable (e.g., ['linear'])

    Returns:
        A tuple of (decision, tool_calls, response_id) where:
        - decision: Clean JSON response with reasoning, decision, confidence
        - tool_calls: List of tool call info if OpenAI chose to use tools, empty list otherwise
        - response_id: The response ID for state preservation
    """
    write_tools_list: list[WriteToolType] = write_tools or []

    # Build tools list locally for this request (don't mutate global state)
    global OPENAI_TOOLS
    if disable_tools:
        openai_tools = []
    else:
        # Start with base MCP tools
        openai_tools = list(OPENAI_TOOLS)

        # Add write tools as requested
        for tool_type in write_tools_list:
            tool_schemas = WRITE_TOOL_SCHEMAS.get(tool_type, [])
            openai_tools.extend(tool_schemas)

    async with trace_span(
        name="agent_think",
        input_data={
            "available_tools": [t["name"] for t in openai_tools],
            "additional_messages": additional_messages,
        },
        metadata=create_agent_metadata(
            step="thinking", available_tools=[t["name"] for t in openai_tools]
        ),
    ) as span:
        try:
            # Prepare request parameters with state preservation
            request_params = {
                "model": model,
                "tools": openai_tools,
                "tool_choice": "auto",  # Let OpenAI decide when to use tools
                "store": True,  # Enable state preservation
            }

            # Handle conversation continuation
            if previous_response_id:
                # Continue from previous response with additional messages
                request_params["previous_response_id"] = previous_response_id
                request_params["input"] = additional_messages

                if AGENT_DEBUG:
                    logger.debug(
                        f"Continuing from response_id: {previous_response_id} with {len(additional_messages)} additional messages"
                    )
            else:
                # Start new conversation with initial messages
                request_params["input"] = additional_messages
                if AGENT_DEBUG:
                    logger.debug(
                        f"Starting new conversation with {len(additional_messages)} messages"
                    )

            response = await _make_openai_call(request_params, reasoning_effort, verbosity)
            decision, tool_calls, response_id = _process_response(response)

            span.update(output={"decision": decision, "tool_calls": tool_calls})
            return decision, tool_calls, response_id

        except Exception as e:
            # Determine retry strategy based on error type
            is_guideline_violation = _is_guideline_violation_error(e)
            is_timeout = isinstance(e, TimeoutError)

            if is_guideline_violation or is_timeout:
                # Configure retry parameters based on error type
                if is_guideline_violation:
                    retry_delays = [2, 4, 8]  # 3 retries with exponential backoff
                    error_type = "guideline violation"
                    logger.info(
                        f"OpenAI API call flagged for guideline violation, attempting retries: {e}"
                    )
                else:  # is_timeout
                    retry_delays = [3, 6]  # 2 retries with 3 - 6s delay
                    error_type = "timeout"
                    logger.info(f"OpenAI API call timed out, attempting retry: {e}")

                last_error = e
                retry_count = len(retry_delays)

                # Unified retry loop
                for retry_attempt in range(retry_count):
                    delay = retry_delays[retry_attempt]
                    logger.info(
                        f"Retry attempt {retry_attempt + 1}/{retry_count} after {delay} seconds..."
                    )
                    await asyncio.sleep(delay)

                    try:
                        response = await _make_openai_call(
                            request_params, reasoning_effort, verbosity
                        )
                        decision, tool_calls, response_id = _process_response(
                            response, f" ({error_type} retry {retry_attempt + 1})"
                        )

                        logger.info(
                            f"{error_type.capitalize()} retry attempt {retry_attempt + 1}/{retry_count} succeeded!"
                        )
                        span.update(output={"decision": decision, "tool_calls": tool_calls})
                        return decision, tool_calls, response_id

                    except Exception as retry_error:
                        last_error = retry_error

                        # For guideline violations, only continue if same error type
                        if is_guideline_violation:
                            if _is_guideline_violation_error(retry_error):
                                logger.info(
                                    f"⚠️ Retry attempt {retry_attempt + 1}/{retry_count} also flagged for guideline violation: {retry_error}"
                                )
                                continue  # Continue to next retry attempt
                            else:
                                # Different error type, stop retrying
                                logger.error(
                                    f"❌ Retry attempt {retry_attempt + 1}/{retry_count} failed with different error: {retry_error}"
                                )
                                break
                        # For timeouts, always continue to next retry (if any)

                # All retries failed - collect error and return failure
                if is_guideline_violation:
                    collect_openai_error(last_error, attempt_count=retry_count + 1)
                    logger.error("❌ All retry attempts failed due to guideline violations")
                    error_model = AgentDecision(
                        decision="finish",
                        confidence="low",
                        final_answer="Tool call failed because we were flagged for potentially violating guidelines",
                    )
                    error_reasoning = "Tool call failed because we were flagged for potentially violating guidelines"
                else:  # is_timeout
                    collect_timeout_error("openai_timeout", OPENAI_TIMEOUT, e)
                    logger.error(f"❌ Timeout retry attempt failed: {last_error}")
                    error_model = AgentDecision(
                        decision="finish",
                        confidence="low",
                        final_answer=f"Request timed out after {OPENAI_TIMEOUT}s and retry also failed: {last_error}",
                    )
                    error_reasoning = f"Request timed out after {OPENAI_TIMEOUT}s and retry also failed: {last_error}"

                error_decision = _create_decision_dict(error_model, error_reasoning)
                span.update(output={"decision": error_decision, "tool_calls": []})
                return error_decision, [], None
            else:
                # Non-retryable error, handle normally
                collect_openai_error(e)

                # Record the error in New Relic
                newrelic.agent.record_exception()

                logger.error(f"Error in agent thinking: {e}")
                error_model = AgentDecision(
                    decision="finish",
                    confidence="low",
                    final_answer=f"Error in thinking process: {e}",
                )
                error_reasoning = f"Error in thinking process: {e}"
                error_decision = _create_decision_dict(error_model, error_reasoning)

                span.update(output={"decision": error_decision, "tool_calls": []})
                return error_decision, [], None


async def _initialize_mcp_tools():
    """
    Initialize the available tools from the tool executor.
    Only initializes once per process lifetime - subsequent calls are no-ops.
    Raises an exception if connection fails or no tools are discovered.
    """
    global AVAILABLE_TOOLS, OPENAI_TOOLS

    # Skip initialization if already done
    if AVAILABLE_TOOLS and OPENAI_TOOLS:
        logger.debug("MCP tools already initialized, skipping")
        return

    try:
        # Get the tool executor
        tool_executor = await get_tool_executor()

        # Get available tools from tool executor (already in OpenAI format)
        mcp_tools = tool_executor.get_available_tools()

        # Ensure we have at least one tool
        if not mcp_tools:
            raise RuntimeError("No tools discovered from tool executor")

        # Store tools - they're already in OpenAI format
        AVAILABLE_TOOLS = mcp_tools
        OPENAI_TOOLS = list(mcp_tools.values())

        # Write the openai_tools to src/debug_openai_tools.jsonc (pretty printed)
        tools_file_path = os.path.join(os.path.dirname(__file__), "debug_openai_tools.jsonc")
        with open(tools_file_path, "w") as f:
            f.write(
                "// THIS FILE IS GENERATED BY agent.py. DO NOT EDIT MANUALLY.\n// This file is useful for debugging the tools that we send to OpenAI from our agent. The agent will re-write this file with the latest tools every time it runs.\n"
            )
            json.dump(OPENAI_TOOLS, f, indent=2)

        logger.info(f"Initialized {len(AVAILABLE_TOOLS)} tools from tool executor")
        logger.info(f"Wrote {len(OPENAI_TOOLS)} OpenAI tools to {tools_file_path}")

    except Exception as e:
        logger.error(f"Failed to initialize tools from tool executor: {e}")
        raise


async def _execute_tool(
    tool_name: str, parameters: dict[str, Any], context: Context | None = None
) -> CallToolResponse:
    """
    Execute a specific tool with given parameters.
    Returns a ToolResponse with the result or error.

    Args:
        tool_name: Name of the tool to execute
        parameters: Tool parameters
        context: Optional FastMCP context for internal tools (e.g., Linear)
    """

    async with trace_span(
        name=f"execute_tool({tool_name})",
        input_data={"tool_name": tool_name, "parameters": parameters},
        metadata=create_tool_metadata(tool_name, parameters),
    ) as span:
        # Handle internal Linear tool separately
        if tool_name == "manage_linear_ticket":
            if not context:
                error_result = ErrorToolResponse(
                    tool_name=tool_name,
                    status="error",
                    error="Context required for Linear tool but not provided",
                    available_tools=list(AVAILABLE_TOOLS.keys()),
                )
                span.update(output=error_result)
                return error_result

            result = await execute_internal_linear_tool(
                parameters, context, list(AVAILABLE_TOOLS.keys())
            )
            span.update(output=result)
            return result

        # Handle regular MCP tools
        tool_executor = await get_tool_executor()
        try:
            mcp_result = await tool_executor.call_tool(tool_name, parameters)
        except Exception as e:
            error_result = ErrorToolResponse(
                tool_name=tool_name,
                status="error",
                error=f"Tool call failed: {str(e)}",
                available_tools=list(AVAILABLE_TOOLS.keys()),
            )
            span.update(output=error_result)
            return error_result

        if mcp_result["status"] == "success":
            span.update(output=mcp_result)
            return mcp_result

        error_msg = mcp_result["error"] if mcp_result["status"] == "error" else "Unknown error"

        # Check if this is a document_id validation error
        if (
            "document_id" in error_msg
            and ("validation" in error_msg.lower() or "pattern" in error_msg.lower())
            and "document_id" in parameters
        ):
            logger.warning(
                f"Document ID validation failed for '{parameters['document_id']}': {error_msg}"
            )
            logger.info(f"Retrying {tool_name} without document_id parameter")

            # Create new parameters without document_id
            retry_params = {k: v for k, v in parameters.items() if k != "document_id"}

            # Retry the tool call without document_id with built-in timeout
            try:
                retry_result = await tool_executor.call_tool(tool_name, retry_params)

                if retry_result["status"] == "success":
                    # Add note about removed document_id filter
                    retry_result_dict = dict(retry_result)
                    retry_result_dict["_note"] = (
                        f"Document ID filter '{parameters['document_id']}' was removed due to validation error"
                    )

                    span.update(output=retry_result_dict)
                    return retry_result
                else:
                    # Create new ErrorResponse with updated error message
                    updated_retry_result = ErrorToolResponse(
                        tool_name=retry_result["tool_name"],
                        status="error",
                        error=f"Original error: {error_msg}. Retry without document_id also failed: {retry_result['error'] if retry_result['status'] == 'error' else 'Unknown error'}",
                        available_tools=retry_result["available_tools"]
                        if retry_result["status"] == "error"
                        else list(AVAILABLE_TOOLS.keys()),
                    )
                    # Retry also failed, return updated error
                    span.update(output=updated_retry_result)
                    return updated_retry_result

            except Exception as retry_error:
                # Retry failed with exception
                error_result = ErrorToolResponse(
                    tool_name=tool_name,
                    status="error",
                    error=f"Original error: {error_msg}. Retry error: {str(retry_error)}",
                    available_tools=list(AVAILABLE_TOOLS.keys()),
                )
                span.update(output=error_result)
                return error_result
        else:
            # Not a document_id validation error, return as is
            error_result = ErrorToolResponse(
                tool_name=tool_name,
                status="error",
                error=error_msg,
                available_tools=list(AVAILABLE_TOOLS.keys()),
            )
            span.update(output=error_result)
            return error_result


async def stream_advanced_search_answer(
    query: str,
    system_prompt: str,
    context: Context,  # FastMCP context for database access (required for citation processing)
    previous_response_id: str | None = None,
    files: list[FileAttachment] | None = None,
    reasoning_effort: str = "medium",
    verbosity: str | None = None,
    output_format: str | None = None,
    model: str = "gpt-5",
    disable_tools: bool = False,
    disable_citations: bool = False,
    write_tools: list[WriteToolType] | None = None,
):
    """
    Main stream for the advanced search agent using message-based architecture.

    Args:
        query: The user's search query.
        system_prompt: System prompt to use for the agent.
        context: FastMCP context for database access (required for citation resolution).
        previous_response_id: Optional response ID to continue from previous conversation.
        files: Optional list of file attachments to include in the query.
        reasoning_effort: OpenAI reasoning effort level ("minimal", "low", "medium", "high").
        verbosity: OpenAI verbosity level for response detail ("low", "medium", "high", or None).
        output_format: Output format for citations ('slack' for Slack markdown, None for standard).
        model: OpenAI model to use for the agent loop
        disable_citations: If True, skip citation processing
        write_tools: List of write tools to enable (e.g., ['linear'])
    """

    await _initialize_mcp_tools()

    # Use clean async generator tracing utility
    async with trace_span(
        name="advanced_search_agent",
        input_data={"query": query},
        metadata=create_agent_metadata("orchestration"),
    ) as agent_span:
        # Yield trace info for Langfuse integration
        # TODO: check config for langfuse decision
        if os.getenv("DISABLE_LANGFUSE_TRACING", "false").lower() != "true":
            try:
                from src.utils.config import get_langfuse_host

                # Get trace ID from the span (only for real Langfuse spans, not NoOpSpan)
                if hasattr(agent_span, "trace_id") and agent_span.__class__.__name__ != "NoOpSpan":
                    trace_id = getattr(agent_span, "trace_id", None)
                    if trace_id:
                        trace_url = f"{get_langfuse_host().rstrip('/')}/trace/{trace_id}"
                        yield {
                            "type": "trace_info",
                            "data": {"trace_id": trace_id, "trace_url": trace_url},
                        }
            except Exception as e:
                logger.debug(f"Could not generate trace info: {e}")

        # Initialize conversation
        messages = [
            {"role": "system", "content": system_prompt},
        ]

        # Process files and create user message with file support
        user_message = process_files_to_message_content(files, query)
        messages.append(user_message)

        yield {"type": "status", "data": "🚀 Starting advanced agentic search..."}

        # Yield initial user message
        yield {"type": "message", "data": messages[1]}

        # Track response ID for state preservation (use passed parameter or None)
        current_response_id = previous_response_id

        # Track messages added since last agent call
        last_message_count = 0
        context_window = get_context_window(model)

        allowed_to_finish = False

        # Main agent loop
        while len(messages) < MAX_MESSAGES:
            additional_messages = messages[last_message_count:]

            # Agent thinks about what to do next
            decision, tool_calls, response_id = await _agent_think(
                additional_messages,
                current_response_id,
                reasoning_effort,
                verbosity,
                model,
                disable_tools,
                write_tools,
            )

            # Update current response ID for next iteration
            current_response_id = response_id
            if AGENT_DEBUG:
                logger.debug(f"Stored response_id for next iteration: {response_id}")

            # Update message tracking after adding assistant message
            last_message_count = len(messages)

            # Calculate context window usage percentage
            current_tokens = count_messages_tokens(messages, model)
            context_usage_percent = round((current_tokens / context_window) * 100, 1)

            # Add context window percentage to decision data
            decision_with_context = decision.copy()
            decision_with_context["context_usage_percent"] = context_usage_percent

            yield {"type": "agent_decision", "data": decision_with_context}

            if decision.get("decision") == "finish":
                # Check if agent has used at least one tool (skip if tools disabled)
                tool_responses = [
                    msg for msg in messages if msg.get("type") == "function_call_output"
                ]
                if not disable_tools and not tool_responses and not allowed_to_finish:
                    allowed_to_finish = True
                    yield {
                        "type": "status",
                        "data": "⚠️ Agent tried to finish without using any tools. Forcing a semantic search...",
                    }
                    # Override the decision to force a search
                    decision = {
                        "reasoning": "Must search the knowledge base before finishing",
                        "decision": "continue",
                        "confidence": "medium",
                    }
                    # Update the last message with the override
                    messages[-1]["content"] = json.dumps(decision)

                    # Yield tool_call event BEFORE execution
                    yield {
                        "type": "tool_call",
                        "data": {
                            "decision": decision,
                            "tool_name": "semantic_search",
                            "tool_parameters": {"query": query, "limit": 10},
                            "call_id": None,
                            "parallel_index": 0,
                            "total_parallel": 1,
                            "status": "starting",
                        },
                    }

                    # Now execute the semantic search
                    search_result = await _execute_tool(
                        "semantic_search", {"query": query, "limit": 10}, context
                    )

                    # Check context window before adding forced search result
                    buffer_size = int(context_window * CONTEXT_WINDOW_BUFFER)
                    max_allowed_tokens = context_window - buffer_size
                    current_tokens = count_messages_tokens(messages, model)

                    message = {"role": "assistant", "content": json.dumps(search_result)}
                    response_tokens = count_messages_tokens([message], model)
                    predicted_total = current_tokens + response_tokens

                    if predicted_total > max_allowed_tokens:
                        # Even the forced search result is too large
                        remaining_tokens = max_allowed_tokens - current_tokens
                        overflow_result_dict = {
                            "error": "context_window_overflow",
                            "message": f"Even the semantic search response is too large (would use {response_tokens} of {remaining_tokens} remaining tokens). Context window exhausted.",
                            "tool_name": "semantic_search",
                            "response_tokens": response_tokens,
                            "remaining_context": remaining_tokens,
                            "success": False,
                        }
                        search_result = ErrorToolResponse(
                            tool_name="semantic_search",
                            status="error",
                            error="context_window_overflow",
                            available_tools=list(AVAILABLE_TOOLS.keys()),
                        )
                        message["content"] = json.dumps(overflow_result_dict)
                        current_usage_percent = round((current_tokens / context_window) * 100, 1)
                        logger.warning(
                            f"Forced semantic search would overflow context window: {response_tokens} tokens (limit: {remaining_tokens}) - Current usage: {current_usage_percent}%"
                        )

                    messages.append(message)

                    # Yield only the tool_result (tool_call was already sent before execution)
                    yield {
                        "type": "tool_result",
                        "data": {
                            "tool_name": "semantic_search",
                            "call_id": None,
                            "parallel_index": 0,
                            "summary": "✅ Tool executed successfully"
                            if search_result.get("status") == "success"
                            else "❌ Tool execution failed",
                            "result": search_result,
                        },
                    }
                    yield {"type": "message", "data": message}
                else:
                    current_tokens = count_messages_tokens(messages, model)
                    current_usage_percent = round((current_tokens / context_window) * 100, 1)
                    yield {
                        "type": "status",
                        "data": f"✅ Agent decided to finish after {len(messages) - 1} messages - Context usage: {current_usage_percent}%",
                    }

                    # Extract final answer from structured output
                    final_answer_raw = decision.get("final_answer")
                    if final_answer_raw:
                        final_answer = final_answer_raw
                        # Skip citation processing if disabled
                        if not disable_citations:
                            yield {"type": "status", "data": "🔗 Processing citations..."}

                            # Process citations with database access
                            async with _acquire_pool_from_context(
                                context, readonly=True
                            ) as db_pool:
                                tenant_id = _extract_tenant_id_from_context(context)
                                permission_principal_token = (
                                    _extract_permission_principal_token_from_context(context)
                                )
                                if not tenant_id:
                                    raise RuntimeError("tenant_id not found in context")
                                final_answer = await replace_citations_with_deeplinks(
                                    final_answer_raw,
                                    db_pool,
                                    tenant_id,
                                    permission_principal_token,
                                    output_format,
                                )

                        yield {
                            "type": "final_answer",
                            "data": {
                                "answer": final_answer,
                                "response_id": current_response_id,
                            },
                        }
                    else:
                        yield {
                            "type": "final_answer",
                            "data": {
                                "answer": "No final answer provided in structured output",
                                "response_id": current_response_id,
                            },
                        }
                    break

            # Execute all tools concurrently
            tasks = []

            for i, tool_call in enumerate(tool_calls):
                # Yield tool_call event right before execution starts
                tool_call_data = {
                    "decision": decision,
                    "tool_name": tool_call["name"],
                    "tool_parameters": tool_call["parameters"],
                    "call_id": tool_call.get("call_id"),
                    "parallel_index": i,
                    "total_parallel": len(tool_calls),
                    "status": "starting",
                }
                yield {"type": "tool_call", "data": tool_call_data}

                # Now execute the tool
                task = _execute_tool(tool_call["name"], tool_call["parameters"], context)
                tasks.append(task)

            # Wait for all tools to complete
            results: list[CallToolResponse | BaseException] = await asyncio.gather(
                *tasks, return_exceptions=True
            )

            # Process each tool result
            for i, (tool_call, result) in enumerate(zip(tool_calls, results, strict=False)):
                tool_name = tool_call["name"]
                tool_params = tool_call["parameters"]
                call_id = tool_call.get("call_id")

                success = False

                # Handle exceptions from parallel execution and ensure result is CallToolResponse
                call_tool_response: CallToolResponse
                if isinstance(result, Exception):
                    call_tool_response = ErrorToolResponse(
                        tool_name=tool_name,
                        status="error",
                        error=f"Tool execution failed: {str(result)}",
                        available_tools=list(AVAILABLE_TOOLS.keys()),
                    )
                else:
                    # result is guaranteed to be CallToolResponse here
                    call_tool_response = cast(CallToolResponse, result)

                # Check if tool execution was successful
                if call_tool_response["status"] == "success":
                    success = True

                # Check if adding this tool response would exceed context window
                buffer_size = int(context_window * CONTEXT_WINDOW_BUFFER)
                max_allowed_tokens = context_window - buffer_size

                # Calculate current conversation size
                current_tokens = count_messages_tokens(messages, model)

                # Calculate size of the tool response we're about to add
                tool_response_msg = format_tool_response_message(
                    call_id=str(call_id), result=call_tool_response
                )
                response_tokens = count_messages_tokens([tool_response_msg], model)

                # Check if adding this response would overflow
                predicted_total = current_tokens + response_tokens

                if predicted_total > max_allowed_tokens:
                    # Replace with overflow error
                    remaining_tokens = max_allowed_tokens - current_tokens
                    overflow_result_dict = {
                        "error": "context_window_overflow",
                        "message": f"This tool response is too large to process (would use {response_tokens} of {remaining_tokens} remaining tokens). Try a more specific query, use search to find relevant sections, or request smaller chunks of information.",
                        "tool_name": tool_name,
                        "response_tokens": response_tokens,
                        "remaining_context": remaining_tokens,
                        "success": False,
                    }

                    # Create a minimal response message
                    tool_response_msg = format_tool_response_message(
                        call_id=call_id or "", result=overflow_result_dict
                    )

                    # Update call_tool_response for UI display
                    call_tool_response = ErrorToolResponse(
                        tool_name=tool_name,
                        status="error",
                        error="context_window_overflow",
                        available_tools=list(AVAILABLE_TOOLS.keys()),
                    )
                    success = False

                    current_usage_percent = round((current_tokens / context_window) * 100, 1)
                    logger.warning(
                        f"Tool response from {tool_name} would overflow context window: {response_tokens} tokens (limit: {remaining_tokens}) - Current usage: {current_usage_percent}%"
                    )

                messages.append(tool_response_msg)

                # Prepare tool call data for yield
                tool_call_data = {
                    "decision": decision,
                    "tool_name": tool_name,
                    "tool_parameters": tool_params,
                    "call_id": call_id,
                    "parallel_index": i,
                    "total_parallel": len(tool_calls),
                    "result_summary": "✅ Tool executed successfully"
                    if success
                    else f"❌ Error: {call_tool_response['error'] if call_tool_response['status'] == 'error' else 'Unknown'}",
                    "result": call_tool_response,
                }

                # Yield the tool result event (tool_call was already sent before execution)
                yield {
                    "type": "tool_result",
                    "data": {
                        "tool_name": tool_name,
                        "call_id": call_id,
                        "parallel_index": i,
                        "summary": tool_call_data["result_summary"],
                        "result": call_tool_response,
                    },
                }
                yield {"type": "message", "data": tool_response_msg}

        # Check if we hit the message limit
        if len(messages) >= MAX_MESSAGES:
            current_tokens = count_messages_tokens(messages, model)
            current_usage_percent = round((current_tokens / context_window) * 100, 1)
            yield {
                "type": "status",
                "data": f"⚠️ Reached message limit ({MAX_MESSAGES}), forcing finish... Context usage: {current_usage_percent}%",
            }
            yield {
                "type": "final_answer",
                "data": {
                    "answer": "I reached the message limit while searching for information. Please try a more specific query.",
                    "response_id": current_response_id,
                },
            }
