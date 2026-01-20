#!/usr/bin/env python
"""
Interactive Langfuse Trace Analyzer and Chat Interface

This script provides a comprehensive interface for analyzing AI agent execution traces from Langfuse.
It displays traces in a readable format and opens a chat interface where users can ask GPT-4o
questions about the trace execution, tool calls, and agent reasoning.

Key Features:
- Parse Langfuse trace URLs and fetch complete trace data
- Display formatted trace overview with agent thinking and tool execution steps
- Extract and format tool call results with source, document ID, and content previews
- Chat interface with GPT-4o that has full access to trace context
- Support for browsing multiple traces from experiment results
- Complete numbered trace context for detailed GPT-4o analysis

Usage:
    # Single trace analysis (direct URL)
    python src/evals/chat_with_langfuse_trace.py "https://us.cloud.langfuse.com/trace/abc123"

    # Single trace analysis (project URL)
    python src/evals/chat_with_langfuse_trace.py "https://us.cloud.langfuse.com/project/xyz/traces/abc123"

    # Browse traces from experiment
    python src/evals/chat_with_langfuse_trace.py --experiment runs/experiment_20250716_051618-o3

Environment Variables Required:
    LANGFUSE_PUBLIC_KEY: Your Langfuse public API key
    LANGFUSE_SECRET_KEY: Your Langfuse secret API key
    LANGFUSE_HOST: Langfuse host URL (optional, defaults to https://cloud.langfuse.com)
    OPENAI_API_KEY: OpenAI API key for GPT-4o chat interface
"""

import argparse
import json
import os
import re
import sys
from typing import Any
from urllib.parse import urlparse

import openai
import requests
from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel

# Load environment variables for API access
load_dotenv()

# Initialize Rich console for beautiful terminal output
console = Console()


class LangfuseTraceChat:
    """
    Main class for analyzing Langfuse traces and providing interactive chat interface.
    """

    def __init__(self):
        """Initialize the trace chat interface with API credentials."""
        # Load Langfuse API credentials from environment
        self.langfuse_public_key = os.getenv("LANGFUSE_PUBLIC_KEY")
        self.langfuse_secret_key = os.getenv("LANGFUSE_SECRET_KEY")
        self.langfuse_host = os.getenv("LANGFUSE_HOST", "https://us.cloud.langfuse.com")

        # Load OpenAI API credentials
        self.openai_api_key = os.getenv("OPENAI_API_KEY")

        # Validate all required credentials are present
        if not all([self.langfuse_public_key, self.langfuse_secret_key]):
            raise ValueError(
                "Missing Langfuse credentials. Please set LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY"
            )

        if not self.openai_api_key:
            raise ValueError("Missing OpenAI API key. Please set OPENAI_API_KEY")

        # Initialize OpenAI client for chat functionality
        self.openai_client = openai.OpenAI(api_key=self.openai_api_key)

        # Initialize chat state variables
        self.trace_context = ""  # Complete context string sent to GPT
        self.conversation_history = []  # Chat message history

    def extract_trace_id(self, trace_url: str) -> tuple[str, str]:
        """Parse Langfuse trace URL to extract trace ID and host."""
        parsed = urlparse(trace_url)

        # Reconstruct base host URL
        host = f"{parsed.scheme}://{parsed.netloc}"

        # Try to extract trace ID from either URL format
        trace_id = None

        # Format 1: Direct trace URL - /trace/{trace-id}
        match = re.search(r"/trace/([a-f0-9-]+)", parsed.path)
        if match:
            trace_id = match.group(1)
        else:
            # Format 2: Project-based URL - /project/{project-id}/traces/{trace-id}
            match = re.search(r"/project/[^/]+/traces/([a-f0-9-]+)", parsed.path)
            if match:
                trace_id = match.group(1)
                console.print("[dim]Converting project URL to direct trace URL format[/dim]")

        if not trace_id:
            raise ValueError(
                f"Invalid trace URL format: {trace_url}. Expected /trace/{{id}} or /project/{{id}}/traces/{{trace-id}}"
            )

        return trace_id, host

    def fetch_trace_data(self, trace_id: str, host: str | None = None) -> dict[str, Any]:
        """Fetch complete trace data from Langfuse API."""
        # Use provided host or fall back to configured default
        api_host = host or self.langfuse_host

        # Construct Langfuse public API endpoint URL
        api_url = f"{api_host}/api/public/traces/{trace_id}"

        console.print(f"[cyan]Fetching trace data from: {api_url}[/cyan]")

        # Make authenticated request to Langfuse API
        response = requests.get(
            api_url,
            auth=(self.langfuse_public_key, self.langfuse_secret_key),  # type: ignore[arg-type]
            headers={"Content-Type": "application/json"},
        )

        if response.status_code != 200:
            raise Exception(f"Failed to fetch trace: {response.status_code} - {response.text}")

        return response.json()

    def extract_observations(
        self, trace_data: dict[str, Any]
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """Parse Langfuse observations to separate agent thinking steps from tool executions."""
        tool_calls = []
        agent_thoughts = []

        observations = trace_data.get("observations", [])

        for obs in observations:
            obs_type = obs.get("type", "")
            obs_name = obs.get("name", "")

            # Create standardized observation structure with all relevant fields
            standardized_obs = {
                "id": obs.get("id"),
                "name": obs.get("name"),
                "timestamp": obs.get("startTime"),
                "duration_ms": obs.get("latency"),
                "input": obs.get("input"),
                "output": obs.get("output"),
                "metadata": obs.get("metadata", {}),
                "model": obs.get("model"),
                "usage": obs.get("usage", {}),
                "type": obs_type,
            }

            # Classify observation as agent thinking step
            if "agent_think" in obs_name.lower() or "thinking" in obs_name.lower():
                agent_thoughts.append(standardized_obs)
                continue

            # Classify observation as tool call using multiple detection patterns
            is_tool_call = (
                # Pattern 1: Type is GENERATION and name contains "tool"
                (obs_type == "GENERATION" and "tool" in obs_name.lower())
                or
                # Pattern 2: Type is SPAN and name indicates tool execution
                (
                    obs_type == "SPAN"
                    and any(keyword in obs_name.lower() for keyword in ["tool", "execute", "call"])
                )
                or
                # Pattern 3: Metadata explicitly indicates tool
                bool(obs.get("metadata", {}).get("tool_name"))
                or
                # Pattern 4: Name matches known MCP tool patterns
                bool(
                    obs_name
                    and any(
                        pattern in obs_name
                        for pattern in [
                            "semantic_search",
                            "keyword_search",
                            "get_document",
                            "list_documents",
                        ]
                    )
                )
            )

            if is_tool_call:
                tool_calls.append(standardized_obs)

        # Sort both lists chronologically by timestamp
        tool_calls.sort(key=lambda x: x["timestamp"] or "")
        agent_thoughts.sort(key=lambda x: x["timestamp"] or "")

        return tool_calls, agent_thoughts

    def format_tool_call_summary(self, tool_call: dict[str, Any]) -> str:
        """Generate a concise one-line summary of a tool call's results."""
        # name is not used but kept for parity with sibling implementation
        _name = tool_call.get("name", "Unknown Tool")
        output = tool_call.get("output")

        if not output:
            return "→ No output"

        try:
            # Parse output JSON if it's a string, otherwise use as-is
            if isinstance(output, str):
                output_data = (
                    json.loads(output)
                    if output.startswith("{") or output.startswith("[")
                    else {"content": output}
                )
            else:
                output_data = output

            # Handle search results
            if isinstance(output_data, dict) and "results" in output_data:
                results = output_data["results"]
                count = output_data.get("count", len(results) if isinstance(results, list) else 0)

                if isinstance(results, list) and len(results) > 0:
                    # Get sources for summary
                    sources = set()
                    for result in results:
                        if isinstance(result, dict):
                            source = result.get("source", "unknown")
                            sources.add(source)

                    if sources:
                        return f"→ Found {count} results from {', '.join(sorted(sources))}"
                    else:
                        return f"→ Found {count} results"
                else:
                    return "→ No results found"

            # Handle document retrieval
            elif isinstance(output_data, dict) and (
                "content" in output_data or "document" in output_data
            ):
                content = output_data.get("content") or output_data.get("document", {}).get(
                    "content", ""
                )
                if content:
                    preview = str(content)[:100].replace("\n", " ")
                    return f"→ Retrieved document: '{preview}...'"
                else:
                    return "→ Retrieved document (no content preview)"

            # Handle list results
            elif isinstance(output_data, list):
                return f"→ Returned {len(output_data)} items"

            # Handle simple responses
            elif isinstance(output_data, dict):
                keys = list(output_data.keys())
                if keys:
                    return f"→ Response with keys: {', '.join(keys[:3])}{'...' if len(keys) > 3 else ''}"
                else:
                    return "→ Empty response"

            # Fallback
            else:
                preview = str(output_data)[:100].replace("\n", " ")
                return f"→ {preview}{'...' if len(str(output_data)) > 100 else ''}"

        except (json.JSONDecodeError, KeyError, AttributeError):
            # Fallback to string preview
            preview = str(output)[:100].replace("\n", " ")
            return f"→ {preview}{'...' if len(str(output)) > 100 else ''}"

    def format_agent_thinking(self, thought: dict[str, Any]) -> str | None:
        """
        Parse and format agent thinking steps for display. Returns a concise summary string
        of the agent's decision, tool intention, or reasoning. Returns None to skip generic steps.
        """
        output = thought.get("output")
        if output:
            try:
                # Parse the output if it's a JSON string
                if isinstance(output, str):
                    try:
                        output_data = json.loads(output)
                    except json.JSONDecodeError:
                        output_data = output
                else:
                    output_data = output

                if isinstance(output_data, dict):
                    # Decision-centric format
                    if "decision" in output_data:
                        decision = output_data["decision"]
                        if isinstance(decision, dict):
                            reasoning = decision.get("reasoning", "")
                            decision_type = decision.get("decision", "")

                            # Legacy tool_call format
                            if "tool_call" in decision:
                                tool_call = decision["tool_call"]
                                if isinstance(tool_call, dict):
                                    tool_name = tool_call.get("tool_name", "unknown_tool")
                                    tool_params = tool_call.get("tool_parameters", {})
                                    if tool_params:
                                        param_strs = []
                                        for key, value in tool_params.items():
                                            if isinstance(value, str) and len(value) > 30:
                                                param_strs.append(f"{key}='{value[:30]}...'")
                                            else:
                                                param_strs.append(f"{key}={value}")
                                        param_str = ", ".join(param_strs[:2])
                                        if len(tool_params) > 2:
                                            param_str += "..."
                                        return f"🤔 {tool_name}({param_str})"
                                    return f"🤔 {tool_name}()"

                            # Finish decision with final answer
                            if decision_type == "finish":
                                final_answer = decision.get("final_answer", "")
                                if final_answer:
                                    return f"🤔 Final answer: {str(final_answer)}"
                                return "🤔 Ready to provide final answer"

                            # Reasoning-only or other decisions
                            if reasoning and reasoning != "agent did some thinking":
                                clean_reasoning = reasoning.replace("\n", " ")
                                return f"🤔 {clean_reasoning}"
                            if decision_type == "continue":
                                return "🤔 Continuing analysis..."
                            if decision_type:
                                return f"🤔 Decision: {decision_type}"

                    # New tool_calls array format
                    if "tool_calls" in output_data:
                        tool_calls = output_data["tool_calls"]
                        if isinstance(tool_calls, list) and len(tool_calls) > 0:
                            tool_call = tool_calls[0]
                            if isinstance(tool_call, dict):
                                tool_name = tool_call.get("name", "unknown_tool")
                                tool_params = tool_call.get("parameters", {})
                                if tool_params:
                                    param_strs = []
                                    for key, value in tool_params.items():
                                        if isinstance(value, str) and len(value) > 50:
                                            param_strs.append(f"{key}='{value[:50]}...'")
                                        elif isinstance(value, dict) and len(value) == 0:
                                            param_strs.append(f"{key}={{}}")
                                        else:
                                            param_strs.append(f"{key}={value}")
                                    param_str = ", ".join(param_strs)
                                    return f"🤔 {tool_name}({param_str})"
                                return f"🤔 {tool_name}()"

                    # Pure reasoning format
                    if "reasoning" in output_data:
                        reasoning = output_data["reasoning"]
                        if reasoning and reasoning != "agent did some thinking":
                            clean_reasoning = str(reasoning).replace("\n", " ")
                            return f"🤔 {clean_reasoning}"

                    # Confidence only
                    if "confidence" in output_data:
                        confidence = output_data.get("confidence", "")
                        return f"🤔 Analysis complete (confidence: {confidence})"

                # Skip generic placeholder text
                output_str = str(output_data)
                if "agent did some thinking" in output_str and len(output_str) < 200:
                    return None

                # Fallback to string preview
                preview = str(output_data)[:80].replace("\n", " ")
                return f"🤔 {preview}{'...' if len(str(output_data)) > 80 else ''}"
            except Exception:
                preview = str(output)[:80].replace("\n", " ")
                return f"🤔 {preview}{'...' if len(str(output)) > 80 else ''}"
        return "🤔 Agent thinking step"

    def display_trace_overview(
        self,
        trace_data: dict[str, Any],
        tool_calls: list[dict[str, Any]],
        agent_thoughts: list[dict[str, Any]],
    ):
        """Display a detailed overview of the trace with decisions, parameters, and results."""
        # Basic trace info
        console.print("\n")
        console.print(
            Panel.fit(
                f"[bold cyan]Trace Overview[/bold cyan]\n"
                f"Trace ID: {trace_data.get('id')}\n"
                f"Duration: {trace_data.get('latency', 0) / 1000:.2f}s\n"
                f"Total Tokens: {trace_data.get('usage', {}).get('totalTokens', 0)}\n"
                f"Agent Thinking Steps: {len(agent_thoughts)}\n"
                f"Tool Calls: {len(tool_calls)}",
                title="📊 Trace Summary",
            )
        )

        # Create a chronological sequence of all events
        all_events: list[dict[str, Any]] = []

        # Add agent thoughts
        for i, thought in enumerate(agent_thoughts):
            all_events.append(
                {
                    "type": "thinking",
                    "timestamp": thought["timestamp"] or f"thinking_{i}",
                    "data": thought,
                    "index": i + 1,
                }
            )

        # Add tool calls
        for i, tool in enumerate(tool_calls):
            all_events.append(
                {
                    "type": "tool_call",
                    "timestamp": tool["timestamp"] or f"tool_{i}",
                    "data": tool,
                    "index": i + 1,
                }
            )

        # Sort chronologically
        all_events.sort(key=lambda x: x["timestamp"])

        # Display the sequence
        console.print("\n[bold]📋 Execution Sequence[/bold]")
        console.print()

        step_number = 1
        for event in all_events:
            if event["type"] == "thinking":
                thinking_summary = self.format_agent_thinking(event["data"])
                if thinking_summary:
                    console.print(
                        f"[bold cyan]Step {step_number}:[/bold cyan] [bold yellow]🤔 Agent Thinking[/bold yellow]"
                    )
                    console.print(f"  [bold]Decision:[/bold] {thinking_summary}")

                    # Show detailed reasoning and parameters if present
                    output = event["data"].get("output")
                    if output:
                        try:
                            if isinstance(output, str):
                                output_data = (
                                    json.loads(output) if output.startswith("{") else output
                                )
                            else:
                                output_data = output

                            if isinstance(output_data, dict):
                                # Full reasoning lines
                                if "reasoning" in output_data:
                                    reasoning = output_data["reasoning"]
                                    if reasoning:
                                        for line in str(reasoning).split("\n"):
                                            if line.strip():
                                                console.print(f"  [dim]{line.strip()}[/dim]")

                                # Confidence
                                if "confidence" in output_data:
                                    confidence = output_data["confidence"]
                                    console.print(f"  [bold]Confidence:[/bold] {confidence}")

                                # Tool parameters if available (tool_calls format)
                                if "tool_calls" in output_data:
                                    tool_calls_arr = output_data["tool_calls"]
                                    if isinstance(tool_calls_arr, list) and len(tool_calls_arr) > 0:
                                        tool_call = tool_calls_arr[0]
                                        if isinstance(tool_call, dict):
                                            tool_params = tool_call.get("parameters", {})
                                            if tool_params:
                                                console.print("  [bold]Tool Parameters:[/bold]")
                                                for key, value in tool_params.items():
                                                    if key == "reasoning":
                                                        console.print(f"    {key}: '{value}'")
                                                    elif isinstance(value, str) and len(value) > 80:
                                                        console.print(
                                                            f"    {key}: '{value[:80]}...'"
                                                        )
                                                    elif (
                                                        isinstance(value, dict) and len(value) == 0
                                                    ):
                                                        console.print(f"    {key}: {{}}")
                                                    else:
                                                        console.print(f"    {key}: {value}")
                        except Exception:
                            pass

                    console.print()
                    step_number += 1
            elif event["type"] == "tool_call":
                tool = event["data"]
                tool_name = tool["name"]
                duration = tool["duration_ms"]
                duration_str = f" ({duration}ms)" if duration else ""

                console.print(
                    f"[bold cyan]Step {step_number}:[/bold cyan] [bold green]🔧 Tool Execution: {tool_name}[/bold green]{duration_str}"
                )

                # Extract and display parameters from tool input
                tool_input = tool.get("input", {})
                if tool_input:
                    console.print("  [bold]Parameters:[/bold]")
                    if isinstance(tool_input, dict):
                        for key, value in tool_input.items():
                            if key == "reasoning":
                                console.print(f"    {key}: '{value}'")
                            elif isinstance(value, str) and len(value) > 60:
                                console.print(f"    {key}: '{value[:60]}...'")
                            elif isinstance(value, dict) and len(value) == 0:
                                console.print(f"    {key}: {{}}")
                            else:
                                console.print(f"    {key}: {value}")
                    else:
                        console.print(f"    {tool_input}")

                # Show detailed results
                summary = self.format_tool_call_summary(tool)
                console.print(f"  [bold]Results:[/bold] {summary}")

                # Show additional result details if available
                output = tool.get("output")
                if output:
                    try:
                        if isinstance(output, str):
                            output_data = json.loads(output) if output.startswith("{") else output
                        else:
                            output_data = output

                        if isinstance(output_data, dict) and "results" in output_data:
                            results = output_data["results"]
                            if isinstance(results, list) and len(results) > 0:
                                console.print("  [dim]All results:[/dim]")
                                for _i, result in enumerate(results):
                                    if isinstance(result, dict):
                                        desc_parts: list[str] = []
                                        source = result.get("source", "unknown")
                                        desc_parts.append(f"[{source}]")
                                        doc_id = result.get("id") or result.get("document_id")
                                        if doc_id:
                                            desc_parts.append(f"#{doc_id}")
                                        content_desc = ""
                                        if "content" in result:
                                            content_desc = (
                                                str(result["content"])[:80]
                                                .replace("\n", " ")
                                                .strip()
                                            )
                                        elif "chunk" in result:
                                            content_desc = (
                                                str(result["chunk"])[:80].replace("\n", " ").strip()
                                            )
                                        elif (
                                            "snippets" in result
                                            and isinstance(result["snippets"], list)
                                            and len(result["snippets"]) > 0
                                        ):
                                            snippet_text = result["snippets"][0].get("text", "")
                                            content_desc = (
                                                str(snippet_text)[:80].replace("\n", " ").strip()
                                            )
                                        elif "metadata" in result and isinstance(
                                            result["metadata"], dict
                                        ):
                                            metadata = result["metadata"]
                                            title = (
                                                metadata.get("issue_title")
                                                or metadata.get("pr_title")
                                                or metadata.get("title")
                                                or metadata.get("name")
                                                or ""
                                            )
                                            if title:
                                                content_desc = (
                                                    str(title)[:80].replace("\n", " ").strip()
                                                )
                                        if content_desc:
                                            desc_parts.append(f'"{content_desc}..."')
                                        console.print(f"    • {' '.join(desc_parts)}")
                    except Exception:
                        pass

                console.print()
                step_number += 1

    def build_complete_trace_context(
        self,
        trace_data: dict[str, Any],
        tool_calls: list[dict[str, Any]],
        agent_thoughts: list[dict[str, Any]],
        trace_info: dict[str, Any] | None = None,
    ) -> str:
        """Build comprehensive trace context for GPT-4o with complete data and numbered steps."""
        context_parts = []

        # Add question/answer context if available
        if trace_info:
            context_parts.append("=== QUESTION AND ANSWER CONTEXT ===")
            context_parts.append(f"Question ID: {trace_info.get('id', 'N/A')}")
            context_parts.append(f"Question: {trace_info.get('question', 'N/A')}")
            context_parts.append(f"Expected Answer: {trace_info.get('expected_answer', 'N/A')}")
            context_parts.append(f"Actual Answer: {trace_info.get('actual_answer', 'N/A')}")
            context_parts.append("")

        # Basic trace info
        context_parts.append("=== TRACE OVERVIEW ===")
        context_parts.append(f"Trace ID: {trace_data.get('id')}")
        context_parts.append(f"Duration: {trace_data.get('latency', 0) / 1000:.2f}s")
        context_parts.append(f"Total Tokens: {trace_data.get('usage', {}).get('totalTokens', 0)}")
        context_parts.append(f"Agent Thinking Steps: {len(agent_thoughts)}")
        context_parts.append(f"Tool Calls: {len(tool_calls)}")
        context_parts.append("")

        # Create chronological sequence for numbered steps
        all_events = []

        # Add agent thoughts
        for i, thought in enumerate(agent_thoughts):
            all_events.append(
                {
                    "type": "thinking",
                    "timestamp": thought["timestamp"] or f"thinking_{i}",
                    "data": thought,
                    "index": i + 1,
                }
            )

        # Add tool calls
        for i, tool in enumerate(tool_calls):
            all_events.append(
                {
                    "type": "tool_call",
                    "timestamp": tool["timestamp"] or f"tool_{i}",
                    "data": tool,
                    "index": i + 1,
                }
            )

        # Sort chronologically
        all_events.sort(key=lambda x: x["timestamp"])  # type: ignore[arg-type, return-value]

        # Build numbered execution sequence with COMPLETE data
        context_parts.append("=== COMPLETE EXECUTION SEQUENCE ===")
        context_parts.append("(Reference these steps by number in your responses)")
        context_parts.append("")

        step_number = 1
        for event in all_events:
            if event["type"] == "thinking":
                thought = event["data"]  # type: ignore[assignment]
                context_parts.append(f"Step {step_number}: AGENT THINKING")
                context_parts.append(f"  Duration: {thought['duration_ms']}ms")
                context_parts.append(f"  Model: {thought.get('model', 'N/A')}")

                # Include COMPLETE thinking output (full JSON)
                if thought.get("output"):
                    context_parts.append("  COMPLETE OUTPUT:")
                    output_str = str(thought["output"])
                    context_parts.append(f"  {output_str}")

                context_parts.append("")
                step_number += 1

            elif event["type"] == "tool_call":
                tool = event["data"]  # type: ignore[assignment]
                context_parts.append(f"Step {step_number}: TOOL EXECUTION - {tool['name']}")
                context_parts.append(f"  Duration: {tool['duration_ms']}ms")

                # Include COMPLETE input parameters
                if tool.get("input"):
                    context_parts.append("  COMPLETE INPUT:")
                    input_str = str(tool["input"])
                    context_parts.append(f"  {input_str}")

                # Include COMPLETE output results
                if tool.get("output"):
                    context_parts.append("  COMPLETE OUTPUT:")
                    output_str = str(tool["output"])
                    context_parts.append(f"  {output_str}")

                context_parts.append("")
                step_number += 1

        context_parts.append("=== INSTRUCTIONS FOR ASSISTANT ===")
        context_parts.append(
            "You have access to the complete trace execution with all data included."
        )
        context_parts.append(
            "When answering questions, reference steps by their numbers (e.g., 'In Step 3, the agent...')"
        )
        context_parts.append("All tool outputs, agent reasoning, and results are provided in full.")
        context_parts.append(
            "You can analyze patterns, debug issues, and provide detailed insights about the execution."
        )
        context_parts.append("")

        return "\n".join(context_parts)

    def start_chat(self, trace_context: str):
        """Start the chat interface."""
        console.print("\n" + "=" * 60)
        console.print("[bold green]💬 Chat Interface Started[/bold green]")
        console.print(
            "[dim]Ask questions about this trace. Type 'quit', 'exit', 'q' to exit.[/dim]"
        )
        console.print("=" * 60 + "\n")

        # Initialize conversation with system message
        self.conversation_history = [
            {
                "role": "system",
                "content": f"""You are an AI assistant analyzing a Langfuse trace of an AI agent's execution.

You have access to the complete trace information including:
- All agent thinking steps and reasoning
- All tool calls with their inputs and outputs
- Timing and performance data
- Token usage information

The user will ask you questions about this trace. Provide detailed, helpful answers based on the trace data.

Here is the complete trace context:

{trace_context}""",
            }
        ]

        while True:
            try:
                # Get user input
                user_input = console.input("\n[bold blue]You:[/bold blue] ").strip()

                # Check for exit commands
                if user_input.lower() in ["quit", "exit", "q"]:
                    console.print("\n[dim]Goodbye![/dim]")
                    break

                if not user_input:
                    continue

                # Add user message to conversation
                self.conversation_history.append({"role": "user", "content": user_input})

                # Get response from OpenAI
                console.print("\n[dim]Thinking...[/dim]")

                response = self.openai_client.chat.completions.create(
                    model="gpt-4o", messages=self.conversation_history, temperature=0.7
                )

                assistant_response = response.choices[0].message.content

                # Display response
                console.print(f"\n[bold green]Assistant:[/bold green] {assistant_response}")

                # Add assistant response to conversation history
                self.conversation_history.append(
                    {"role": "assistant", "content": assistant_response}
                )

            except KeyboardInterrupt:
                console.print("\n\n[dim]Chat interrupted. Goodbye![/dim]")
                break
            except Exception as e:
                console.print(f"\n[red]Error: {str(e)}[/red]")
                console.print("[dim]Please try again.[/dim]")

    def analyze_trace(self, trace_url: str, trace_info: dict[str, Any] | None = None):
        """Main workflow for analyzing a single Langfuse trace."""
        try:
            # Extract trace ID and host
            trace_id, host = self.extract_trace_id(trace_url)
            console.print(f"[green]✓[/green] Extracted trace ID: {trace_id}")

            # Fetch trace data
            trace_data = self.fetch_trace_data(trace_id, host)
            console.print("[green]✓[/green] Fetched trace data")

            # Extract observations
            tool_calls, agent_thoughts = self.extract_observations(trace_data)
            console.print(
                f"[green]✓[/green] Found {len(agent_thoughts)} agent thinking steps and {len(tool_calls)} tool calls"
            )

            if not tool_calls and not agent_thoughts:
                console.print(
                    "[yellow]⚠[/yellow] No tool calls or agent thoughts found in this trace"
                )
                return

            # Display trace overview
            self.display_trace_overview(trace_data, tool_calls, agent_thoughts)

            # Build complete context for chat
            trace_context = self.build_complete_trace_context(
                trace_data, tool_calls, agent_thoughts, trace_info
            )

            # Start chat interface
            self.start_chat(trace_context)

        except Exception as e:
            console.print(f"[red]Error: {str(e)}[/red]")
            return


def main():
    """Main entry point and command-line interface."""
    parser = argparse.ArgumentParser(
        description="Chat with a Langfuse trace - displays trace then opens chat interface",
        epilog="""
Examples:
  # Single trace mode
  python src/evals/chat_with_langfuse_trace.py "https://us.cloud.langfuse.com/trace/abc123"

  # Browse traces from experiment
  python src/evals/chat_with_langfuse_trace.py --experiment runs/experiment_20250716_051618-o3
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "trace_url",
        nargs="?",
        help="Langfuse trace URL to analyze and chat with (optional if using --experiment)",
    )

    parser.add_argument(
        "--experiment",
        "-e",
        help="Path to experiment directory or results.jsonl file to browse traces",
    )

    args = parser.parse_args()

    # Create chat interface
    try:
        chat = LangfuseTraceChat()

        if args.trace_url:
            # Single trace mode
            chat.analyze_trace(args.trace_url)
        else:
            console.print("[red]Error: Must provide a trace URL[/red]")
            parser.print_help()
            sys.exit(1)

    except ValueError as e:
        console.print(f"[red]Configuration Error: {str(e)}[/red]")
        sys.exit(1)
    except Exception as e:
        console.print(f"[red]Unexpected Error: {str(e)}[/red]")
        sys.exit(1)


if __name__ == "__main__":
    main()
