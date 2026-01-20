import asyncio
import glob
import json
import os
import re
from datetime import datetime
from typing import Any

import typer
from fastmcp import Client
from fastmcp.server.context import Context
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.text import Text

from src.evals.utils import GATHER_INTERNAL_STAGING_TENANT_ID, RUNS_DIR
from src.mcp.api.agent import stream_advanced_search_answer
from src.mcp.api.prompts import build_system_prompt
from src.mcp.mcp_instance import get_mcp
from src.utils.config import (
    get_mcp_base_url,
    get_openai_api_key,
)
from src.utils.tenant_config import get_tenant_company_context, get_tenant_company_name

app = typer.Typer(
    help="Corporate Context CLI for querying the knowledge base",
    add_completion=False,
    rich_markup_mode="rich",
)


def setup_model_config(model: str, console: Console):
    """Shared model configuration setup."""
    try:
        # Check OpenAI API key if using OpenAI model
        if model == "o3" and not get_openai_api_key():
            console.print(
                "[bold red]Error:[/bold red] OPENAI_API_KEY environment variable is not set."
            )
            console.print("This is required when using --model o3.")
            raise typer.Exit(1)

        console.print(f"[cyan]Using model: {model}[/cyan]")
    except Exception as e:
        console.print(f"[bold red]Error:[/bold red] Failed to set model configuration: {e}")
        raise typer.Exit(1)


def handle_tool_call_event(event: dict, tool_calls_made: int, verbose: bool, console: Console):
    """Handle tool call events."""
    tool_data = event["data"]
    tool_name = tool_data.get("tool_name", tool_data.get("tool_used", "unknown"))

    if verbose:
        console.rule(f"[bold]Tool Call {tool_calls_made}", style="grey70")

        # Show tool parameters
        tool_params = tool_data.get("tool_parameters", {})
        if tool_params:
            params_json = json.dumps(tool_params, indent=2)
            console.print(
                Panel(
                    Syntax(params_json, "json", theme="monokai", line_numbers=False),
                    title=f"[bold]Tool Call: [magenta]{tool_name}[/magenta]",
                    title_align="left",
                    border_style="magenta",
                )
            )

        # Show result summary
        result_summary = tool_data.get("result_summary", "No result summary.")
        console.print(
            Panel(
                Text(result_summary),
                title="[bold]Tool Result[/bold]",
                title_align="left",
                border_style="green" if "✅" in result_summary else "red",
            )
        )
        console.print("")
    else:
        # Show brief info about the tool call in non-verbose mode
        tool_params = tool_data.get("tool_parameters", {})
        brief_params = ""
        if tool_params:
            if "query" in tool_params:
                brief_params = f"query: {tool_params['query'][:30]}..."
            elif "document_id" in tool_params:
                brief_params = f"document_id: {tool_params['document_id']}"

        console.print(f"[magenta]🔧 {tool_name}[/magenta] {brief_params}")


def extract_search_entry_from_tool_call(
    data: dict[str, Any],
    tool_calls_made: int,
    search_data: list[dict] | None,
    verbose: bool = False,
    console: Console | None = None,
) -> None:
    """Extract search query data from a tool_call event and add to search_data list."""
    if search_data is None:
        return

    tool_name = data.get("tool_name", "")
    if tool_name in ["semantic_search", "keyword_search"]:
        search_entry = {
            "tool": tool_name,
            "parameters": data.get("tool_parameters", {}),
            "timestamp": data.get("timestamp", ""),
            "tool_call_id": tool_calls_made - 1,
        }
        search_data.append(search_entry)
        if verbose and console:
            console.print(f"[dim]Captured search tool call #{len(search_data)}: {tool_name}[/dim]")


def process_tool_result_documents(data: dict, search_data: list[dict] | None) -> None:
    """Process tool result and add document data to the most recent search entry."""
    if search_data is None or not isinstance(data, dict) or "result" not in data:
        return

    # Find the most recent search entry without a result
    for i in range(len(search_data) - 1, -1, -1):
        if "result" not in search_data[i]:
            result_data = data["result"]
            documents = []
            sources = []

            # Unwrap result if needed
            if isinstance(result_data, dict) and "result" in result_data:
                actual_result = result_data["result"]
            else:
                actual_result = result_data

            # Extract documents from various possible structures
            if isinstance(actual_result, list):
                documents = actual_result
            elif isinstance(actual_result, dict):
                documents = (
                    actual_result.get("results", [])
                    or actual_result.get("documents", [])
                    or actual_result.get("items", [])
                )
                sources = actual_result.get("sources", [])

            # Process documents to extract only needed fields
            processed_documents = []
            for doc in documents[:10]:
                if isinstance(doc, dict):
                    processed_doc = {
                        "id": doc.get("document_id") or doc.get("id"),
                        "score": doc.get("score"),
                        "source": doc.get("source") or doc.get("metadata", {}).get("source"),
                        "metadata": doc.get("metadata", {}),
                    }
                    processed_documents.append(processed_doc)

            search_data[i]["result"] = {
                "sources_count": len(sources),
                "sources": sources[:10] if sources else [],
                "documents_count": len(documents),
                "documents": processed_documents,
            }
            break


def process_agent_event(
    event: dict[str, Any],
    tool_call_history: list[dict[str, Any]],
    tool_calls_made: int,
    pending_tool_calls: dict[int, dict[str, Any]],
    search_data: list[dict[str, Any]] | None,
    trace_info: dict[str, str] | None,
    final_answer: dict[str, Any] | None,
    turn_count: int,
    console: Console,
    verbose: bool,
    extract_search: bool,
) -> tuple[
    list[dict[str, Any]],
    int,
    dict[int, dict[str, Any]],
    list[dict[str, Any]] | None,
    dict[str, str] | None,
    dict[str, Any] | None,
    int,
]:
    """
    Process a single agent event and update state accordingly.

    Returns tuple of: (tool_call_history, tool_calls_made, pending_tool_calls,
                       search_data, trace_info, final_answer, turn_count)
    """
    event_type = event.get("type")
    data = event.get("data")

    if event_type == "tool_call":
        tool_calls_made += 1

        # Store tool call data for detailed history, keyed by parallel_index
        if isinstance(data, dict):
            parallel_index = data.get("parallel_index", 0)
            pending_tool_calls[parallel_index] = {
                "tool_name": data.get("tool_name", data.get("tool_used", "unknown")),
                "tool_parameters": data.get("tool_parameters", {}),
                "result_summary": data.get("result_summary", "No result summary."),
                "parallel_index": parallel_index,
                "total_parallel": data.get("total_parallel", 1),
            }

        handle_tool_call_event(event, tool_calls_made, verbose, console)

        # Extract search data if requested
        if extract_search and isinstance(data, dict):
            extract_search_entry_from_tool_call(
                data, tool_calls_made, search_data, verbose, console
            )

    elif event_type == "tool_result":
        # Add detailed result to the pending tool call, matched by parallel_index
        if isinstance(data, dict):
            parallel_index = data.get("parallel_index", 0)
            tool_call_data = pending_tool_calls.pop(parallel_index, None)
            if tool_call_data is not None:
                tool_call_data["result"] = data.get("result", {})
                tool_call_history.append(tool_call_data)

        # Extract search data if requested
        if isinstance(data, dict) and extract_search:
            process_tool_result_documents(data, search_data)

    elif event_type == "status":
        console.print(f"[dim]{data}[/dim]")

    elif event_type == "tool_call_explanation":
        # Add explanation as separate entry in tool call history
        if isinstance(data, str):
            tool_call_history.append({"explanation": data})

            if verbose:
                console.print(
                    Panel(
                        Text(data),
                        title="[bold blue]🤔 Reasoning[/bold blue]",
                        title_align="left",
                        border_style="blue",
                    )
                )

    elif event_type == "trace_info":
        trace_info = data

    elif event_type == "total_time":
        console.print(f"[dim]Total time: {data:.2f}s[/dim]")

    elif event_type == "final_answer":
        final_answer = data

    elif event_type == "agent_decision":
        # Count each agent decision as a turn
        turn_count += 1

    return (
        tool_call_history,
        tool_calls_made,
        pending_tool_calls,
        search_data,
        trace_info,
        final_answer,
        turn_count,
    )


async def call_ask_agent_via_mcp(
    query: str,
    console: Console,
    verbose: bool,
    extract_search: bool = False,
):
    """Call ask_agent via MCP and return the response - returns final_answer, tool_calls_made, trace_info, and optionally search_data."""

    # Get MCP base URL
    mcp_url = get_mcp_base_url()

    try:
        async with Client(mcp_url, auth="oauth") as client:
            mcp_response = await client.call_tool("ask_agent", arguments={"query": query})

            # Extract and parse the tool result from MCP response
            try:
                result = json.loads(mcp_response.content[0].text)
            except (KeyError, IndexError, json.JSONDecodeError, TypeError) as e:
                console.print(f"[bold red]Error:[/bold red] Failed to parse MCP response: {e}")
                if verbose:
                    console.print(f"[dim]Raw response: {mcp_response}[/dim]")
                raise typer.Exit(1)

            # Extract data from the ask_agent tool result
            answer = result.get("answer", "")
            response_id = result.get("response_id")
            events = result.get("events", [])

            # Process events for display and search extraction
            tool_call_history: list[dict[str, Any]] = []
            tool_calls_made: int = 0
            pending_tool_calls: dict[int, dict[str, Any]] = {}
            search_data: list[dict[str, Any]] | None = [] if extract_search else None
            trace_info: dict[str, str] | None = None
            final_answer_data: dict[str, Any] | None = None
            turn_count: int = 0

            for event in events:
                (
                    tool_call_history,
                    tool_calls_made,
                    pending_tool_calls,
                    search_data,
                    trace_info,
                    final_answer_data,
                    turn_count,
                ) = process_agent_event(
                    event,
                    tool_call_history,
                    tool_calls_made,
                    pending_tool_calls,
                    search_data,
                    trace_info,
                    final_answer_data,
                    turn_count,
                    console,
                    verbose,
                    extract_search,
                )

            # Construct final answer response similar to HTTP API
            final_answer = {"answer": answer, "response_id": response_id}

            # Calculate metrics
            tool_calls_count = len([tc for tc in tool_call_history if "explanation" not in tc])
            thinking_time_ms = (
                0.0  # TODO: Track from OpenAI usage.output_tokens_details if available
            )

            if extract_search:
                return (
                    final_answer,
                    tool_calls_count,
                    turn_count,
                    trace_info,
                    search_data,
                    tool_call_history,
                    thinking_time_ms,
                )
            return (
                final_answer,
                tool_calls_count,
                turn_count,
                trace_info,
                tool_call_history,
                thinking_time_ms,
            )

    except Exception as e:
        console.print(f"[bold red]Error calling ask_agent via MCP: {str(e)}[/bold red]")
        raise typer.Exit(1)


async def call_agent_directly(
    query: str,
    console: Console,
    verbose: bool,
    extract_search: bool = False,
    model: str = "gpt-5",
):
    """
    Call an agent loop directly (local agent with remote tools). Used with the `run_and_grade.py` script.
    This agent logic is based on `ask_agent` and can be updated accordingly for whatever agent loop you want
    to test with that script.
    """
    # Get tenant_id from environment or use hardcoded value for testing
    tenant_id = os.environ.get("TENANT_ID", GATHER_INTERNAL_STAGING_TENANT_ID)

    # Create context properly (same pattern as ask_endpoint.py)
    mcp = get_mcp()
    context = Context(fastmcp=mcp)
    context.set_state("tenant_id", tenant_id)
    context.set_state("non_billable", True)  # Mark as non-billable for testing

    # Get tenant-specific company information
    company_name, company_context_text = await asyncio.gather(
        get_tenant_company_name(tenant_id),
        get_tenant_company_context(tenant_id),
    )

    # Build fast mode system prompt
    system_prompt = await build_system_prompt(
        company_name=company_name,
        company_context_text=company_context_text,
        output_format=None,
        tenant_id=tenant_id,
        fast_mode_prompt=True,
    )

    # Stream events and collect the final answer
    final_answer: dict[str, Any] | None = None
    events: list[dict[str, Any]] = []
    tool_call_history: list[dict[str, Any]] = []
    tool_calls_made: int = 0
    pending_tool_calls: dict[int, dict[str, Any]] = {}
    trace_info: dict[str, str] | None = None
    search_data: list[dict[str, Any]] | None = [] if extract_search else None
    turn_count: int = 0

    try:
        async for event in stream_advanced_search_answer(
            query=query,
            system_prompt=system_prompt,
            context=context,
            previous_response_id=None,
            files=None,
            reasoning_effort="minimal",
            verbosity="low",
            output_format=None,
            model=model,
        ):
            # Keep transcript
            events.append(event)

            # Process event using shared helper
            (
                tool_call_history,
                tool_calls_made,
                pending_tool_calls,
                search_data,
                trace_info,
                final_answer,
                turn_count,
            ) = process_agent_event(
                event,
                tool_call_history,
                tool_calls_made,
                pending_tool_calls,
                search_data,
                trace_info,
                final_answer,
                turn_count,
                console,
                verbose,
                extract_search,
            )

        # Construct final answer response
        if final_answer:
            answer_text = final_answer.get("answer", "")
            response_id = final_answer.get("response_id")
        else:
            answer_text = ""
            response_id = None

        final_answer_dict = {"answer": answer_text, "response_id": response_id}

        # Calculate metrics
        tool_calls_count = len([tc for tc in tool_call_history if "explanation" not in tc])
        thinking_time_ms = 0.0  # TODO: Track from OpenAI usage.output_tokens_details if available

        if extract_search:
            return (
                final_answer_dict,
                tool_calls_count,
                turn_count,
                trace_info,
                search_data,
                tool_call_history,
                thinking_time_ms,
            )
        return (
            final_answer_dict,
            tool_calls_count,
            turn_count,
            trace_info,
            tool_call_history,
            thinking_time_ms,
        )

    except Exception as e:
        console.print(f"[bold red]Error calling agent directly: {str(e)}[/bold red]")
        raise typer.Exit(1)


@app.command()
def query(
    question: str = typer.Argument(..., help="The question to ask the agent"),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Show the complete conversation including all messages (system prompts, user queries, agent decisions, and tool responses)",
    ),
    model: str = typer.Option(
        "o3",
        "--model",
        "-m",
        help="Model to use for the query. Options: qwen3-32b, qwen3-14b, qwen3-8b, qwen3-1.7b, qwen3-0.6b, o3",
    ),
    extract_search: bool = typer.Option(
        False, "--extract-search", help="Extract and display search queries and results"
    ),
):
    """
    Run a single query against the agent search system.

    Examples:
        python -m src query "What are the recent updates?"

        python -m src query "Show me GitHub issues" --verbose

        python -m src query "What discussions happened today?" --model o3
    """
    console = Console()

    # Setup model configuration
    setup_model_config(model, console)

    console.print("[cyan]Using all available tools from MCP[/cyan]")
    console.print(f"[bold cyan]Question:[/bold cyan] {question}")
    console.print("")

    async def run_query():
        try:
            console.print("[bold green]Agent is thinking...[/bold green]")

            result = await call_ask_agent_via_mcp(
                question, console, verbose, extract_search=extract_search
            )

            # Unpack based on extract_search
            if extract_search:
                (
                    final_answer,
                    tool_calls_made,
                    turn_count,
                    trace_info,
                    search_data,
                    tool_call_details,
                    thinking_time_ms,
                ) = result
            else:
                (
                    final_answer,
                    tool_calls_made,
                    turn_count,
                    trace_info,
                    tool_call_details,
                    thinking_time_ms,
                ) = result
                search_data = None

            # Display final answer
            console.print("\n[bold green]Final Answer:[/bold green]")

            # Handle structured final_answer response
            if isinstance(final_answer, dict):
                answer_text = final_answer.get("answer", str(final_answer))
                response_id = final_answer.get("response_id")

                console.print(answer_text)

                if response_id:
                    console.print(f"\n[bold cyan]Response ID:[/bold cyan] {response_id}")
            else:
                console.print(final_answer)

            console.print(f"\n[dim]Total tool calls made: {tool_calls_made}[/dim]")

            # Display trace URL if tracing is enabled and available
            if trace_info and os.getenv("DISABLE_LANGFUSE_TRACING", "false").lower() != "true":
                console.print(
                    f"\n[bold blue]Langfuse Trace URL:[/bold blue] {trace_info.get('trace_url', 'N/A')}"
                )

            # Display search data if extracted
            if extract_search and search_data:
                console.print("\n[bold cyan]Search Queries Extracted:[/bold cyan]")
                for i, search in enumerate(search_data, 1):
                    console.print(f"\n[yellow]Search {i}:[/yellow]")
                    console.print(f"  Tool: [magenta]{search.get('tool')}[/magenta]")
                    params = search.get("parameters", {})
                    if params.get("query"):
                        console.print(f'  Query: "{params["query"]}"')
                    if params.get("filters"):
                        console.print(f"  Filters: {json.dumps(params['filters'], indent=2)}")

                    result_info = search.get("result", {})
                    if result_info:
                        console.print(
                            f"  Results: {result_info.get('sources_count', 0)} sources, {result_info.get('documents_count', 0)} documents"
                        )
                        # Show first few results
                        docs = result_info.get("documents", [])
                        if docs and verbose:
                            console.print("  Sample results:")
                            for doc in docs[:3]:
                                console.print(
                                    f"    - ID: {doc.get('id')}, Score: {doc.get('score', 'N/A')}, Source: {doc.get('source', 'N/A')}"
                                )

                # Save to file if desired
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                search_file = f"search_extract_{timestamp}.json"

                # Clean up search data before saving (remove temporary flags)
                clean_search_data = []
                for search in search_data:
                    clean_entry = {k: v for k, v in search.items() if not k.startswith("_")}
                    clean_search_data.append(clean_entry)

                with open(search_file, "w") as f:
                    json.dump(
                        {
                            "question": question,
                            "searches": clean_search_data,
                            "timestamp": timestamp,
                        },
                        f,
                        indent=2,
                    )
                console.print(f"\n[green]Search data saved to: {search_file}[/green]")

        except Exception as e:
            console.print(f"\n[bold red]Error running query: {e}[/bold red]")
            raise typer.Exit(1)

    try:
        asyncio.run(run_query())
    except KeyboardInterrupt:
        console.print("\n[yellow]Query interrupted by user[/yellow]")
        raise typer.Exit(0)


@app.command()
def run_experiment(
    verbose: bool = typer.Option(
        False, "--verbose", "-v", help="Show detailed output from the evaluation script."
    ),
    model: str = typer.Option(
        "o3",
        "--model",
        "-m",
        help="Model to use for evaluation. Options: qwen3-32b, qwen3-14b, qwen3-8b, qwen3-1.7b, qwen3-0.6b, o3",
    ),
    experiment_name: str = typer.Option(
        None,
        "--experiment-name",
        "-e",
        help="Optional experiment name to append to the output directory",
    ),
    no_tracing: bool = typer.Option(
        False, "--no-tracing", help="Disable Langfuse tracing and skip authentication checks"
    ),
    concurrency: int = typer.Option(
        10,
        "--concurrency",
        "-c",
        help="Maximum number of concurrent questions to process (default: 10)",
    ),
    extract_search: bool = typer.Option(
        False,
        "--extract-search",
        help="Extract and save all search queries and results to a JSON file",
    ),
):
    """
    Kicks off the agent evaluation script (evals/run_and_grade.py).
    """
    console = Console()

    # Always check OpenAI API key - needed for grading even if using Qwen3 for agent
    try:
        from src.utils.config import get_openai_api_key

        if not get_openai_api_key():
            console.print(
                "[bold red]Error:[/bold red] OPENAI_API_KEY environment variable is not set."
            )
            console.print("This is required for grading (we always use GPT-4o for grading).")
            console.print("Please set OPENAI_API_KEY in your .env file.")
            raise typer.Exit(1)
    except ImportError:
        console.print(
            "[bold red]Error:[/bold red] Could not import config. Make sure .env file exists."
        )
        raise typer.Exit(1)

    # Build command arguments to run as module
    import sys

    cmd_args = [sys.executable, "-m", "src.evals.run_and_grade", "--model", model]

    # Add experiment name if provided
    if experiment_name:
        cmd_args.extend(["--experiment-name", experiment_name])

    # Add no-tracing flag if provided
    if no_tracing:
        cmd_args.append("--no-tracing")

    # Add concurrency if different from default
    if concurrency != 10:
        cmd_args.extend(["--concurrency", str(concurrency)])

    # Add extract-search flag if provided
    if extract_search:
        cmd_args.append("--extract-search")

    console.print(f"[bold cyan]Starting evaluation with model: {model}...[/bold cyan]")
    if experiment_name:
        console.print(f"[cyan]Experiment name: {experiment_name}[/cyan]")
    if no_tracing:
        console.print("[yellow]Tracing disabled[/yellow]")
    else:
        console.print("[cyan]Trace URLs will be displayed automatically[/cyan]")
    if extract_search:
        console.print("[green]🔍 Search extraction enabled - will save queries and results[/green]")
    console.print("[cyan]Using all available tools from MCP[/cyan]")
    console.print(f"[bold cyan]Running: {' '.join(cmd_args)}[/bold cyan]")

    try:
        import subprocess

        if verbose:
            # In verbose mode, stream the output directly.
            process = subprocess.Popen(
                cmd_args,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                bufsize=1,
            )
            if process.stdout is None:
                raise RuntimeError("stdout should not be None")
            for line in iter(process.stdout.readline, ""):
                console.print(line, end="")
            process.stdout.close()
            return_code = process.wait()
        else:
            # In non-verbose mode, show progress and final summary.
            process = subprocess.Popen(
                cmd_args,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                bufsize=1,
            )

            if process.stdout is None:
                raise RuntimeError("stdout should not be None")

            full_output = []
            summary_output = []
            summary_started = False

            with console.status("[bold green]Running evaluation...[/bold green]"):
                for line in iter(process.stdout.readline, ""):
                    full_output.append(line)
                    stripped_line = line.strip()

                    # Always show permutation info and question processing lines
                    if (
                        stripped_line.startswith("-> Processing Question")
                        or "Running Permutation" in stripped_line
                        or stripped_line.startswith("--- PERMUTATION")
                        or "Tool Set:" in stripped_line
                    ):
                        console.print(line, end="")

                    if "--- EVALUATION SUMMARY ---" in stripped_line:
                        summary_started = True

                    if summary_started:
                        summary_output.append(line)

            return_code = process.wait()

            # After the spinner, print the summary if successful
            if return_code == 0:
                if summary_output:
                    console.print("".join(summary_output))
            else:
                # On failure, print the full output for debugging.
                console.print("\n[bold red]Evaluation failed. Full output:[/bold red]")
                console.print("".join(full_output))

        if return_code:
            console.print(
                f"\n[bold red]Evaluation script failed with return code {return_code}.[/bold red]"
            )
            raise typer.Exit(code=return_code)

        console.print("\n[bold green]Evaluation script finished successfully.[/bold green]")

    except Exception as e:
        console.print(f"\n[bold red]An error occurred while running the script: {e}[/bold red]")
        raise typer.Exit(1)


@app.command()
def stats(
    results_path: str = typer.Argument(
        None,
        help="Path to the experiment directory or results file to analyze. If not provided, the latest experiment will be used.",
    ),
):
    """
    Analyzes the results of a previous evaluation run.
    """
    console = Console()

    target_path = results_path
    if not target_path:
        console.print(
            f"[cyan]No results path specified. Finding the latest experiment in '{RUNS_DIR}'...[/cyan]"
        )
        try:
            if not os.path.exists(RUNS_DIR):
                console.print(
                    f"[bold red]Error:[/bold red] The '{RUNS_DIR}' directory does not exist."
                )
                raise typer.Exit(1)

            # Look for experiment directories (experiment_YYYYMMDD_HHMMSS)
            experiment_dirs = [
                os.path.join(RUNS_DIR, d)
                for d in os.listdir(RUNS_DIR)
                if os.path.isdir(os.path.join(RUNS_DIR, d)) and d.startswith("experiment_")
            ]

            if not experiment_dirs:
                console.print(
                    f"[bold red]Error:[/bold red] No experiment directories found in '{RUNS_DIR}'."
                )
                raise typer.Exit(1)

            # Sort by the timestamp in the directory name (experiment_YYYYMMDD_HHMMSS)
            def extract_timestamp(dir_path):
                dir_name = os.path.basename(dir_path)
                try:
                    # Use regex to find timestamp pattern (YYYYMMDD_HHMMSS) anywhere in the name
                    match = re.search(r"\d{8}_\d{6}", dir_name)
                    if match:
                        return match.group()
                    return "00000000_000000"  # fallback if no timestamp found
                except:
                    return "00000000_000000"  # fallback for malformed names

            target_path = max(experiment_dirs, key=extract_timestamp)
            console.print(f"[cyan]Found latest experiment: {os.path.basename(target_path)}[/cyan]")
        except Exception as e:
            console.print(
                f"[bold red]An error occurred while finding the latest experiment: {e}[/bold red]"
            )
            raise typer.Exit(1)

    try:
        import sys

        command = [
            sys.executable,
            "-m",
            "src.evals.stats",
            target_path,
        ]
        import subprocess

        subprocess.run(command, check=True)
    except subprocess.CalledProcessError as e:
        console.print(
            f"\n[bold red]Analysis script failed with return code {e.returncode}.[/bold red]"
        )
        raise typer.Exit(code=e.returncode)
    except Exception as e:
        console.print(
            f"\n[bold red]An error occurred while running the analysis script: {e}[/bold red]"
        )
        raise typer.Exit(1)


@app.command()
def review(
    run_path: str = typer.Argument(
        None,
        help="Path to the experiment directory or results file to review. If not provided, the latest experiment will be used.",
    ),
):
    """
    Shows a step-by-step trace and grade for each question in an agent evaluation run.
    """
    console = Console()

    target_path = run_path
    if not target_path:
        console.print(
            f"[cyan]No results path specified. Finding the latest experiment in '{RUNS_DIR}'...[/cyan]"
        )
        try:
            if not os.path.exists(RUNS_DIR):
                console.print(
                    f"[bold red]Error:[/bold red] The '{RUNS_DIR}' directory does not exist."
                )
                raise typer.Exit(1)

            # Look for experiment directories (experiment_YYYYMMDD_HHMMSS)
            experiment_dirs = [
                os.path.join(RUNS_DIR, d)
                for d in os.listdir(RUNS_DIR)
                if os.path.isdir(os.path.join(RUNS_DIR, d)) and d.startswith("experiment_")
            ]

            if not experiment_dirs:
                console.print(
                    f"[bold red]Error:[/bold red] No experiment directories found in '{RUNS_DIR}'."
                )
                raise typer.Exit(1)

            # Sort by the timestamp in the directory name (experiment_YYYYMMDD_HHMMSS)
            def extract_timestamp(dir_path):
                dir_name = os.path.basename(dir_path)
                try:
                    # Use regex to find timestamp pattern (YYYYMMDD_HHMMSS) anywhere in the name
                    match = re.search(r"\d{8}_\d{6}", dir_name)
                    if match:
                        return match.group()
                    return "00000000_000000"  # fallback if no timestamp found
                except:
                    return "00000000_000000"  # fallback for malformed names

            target_path = max(experiment_dirs, key=extract_timestamp)
            console.print(f"[cyan]Found latest experiment: {os.path.basename(target_path)}[/cyan]")
        except Exception as e:
            console.print(
                f"[bold red]An error occurred while finding the latest experiment: {e}[/bold red]"
            )
            raise typer.Exit(1)

    try:
        import subprocess
        import sys

        command = [
            sys.executable,
            "-m",
            "src.evals.review",
            target_path,
        ]
        subprocess.run(command, check=True)
    except subprocess.CalledProcessError as e:
        console.print(
            f"\n[bold red]Review script failed with return code {e.returncode}.[/bold red]"
        )
        raise typer.Exit(code=e.returncode)
    except Exception as e:
        console.print(
            f"\n[bold red]An error occurred while running the review script: {e}[/bold red]"
        )
        raise typer.Exit(1)


@app.command()
def search_eval(
    eval_file: str = typer.Argument(..., help="Path to the evaluation JSONL file"),
    output: str = typer.Option(
        None,
        "--output",
        "-o",
        help="Output file path. If not specified, generates timestamped filename",
    ),
    verbose: bool = typer.Option(
        False, "--verbose", "-v", help="Show detailed progress information"
    ),
):
    """
    Evaluate search queries from a JSONL file and compare results.

    Processes queries from an evaluation file through MCP search tools
    and outputs comparison results.

    Examples:
        python -m src search-eval /path/to/eval.jsonl

        python -m src search-eval eval.jsonl -o results.jsonl

        python -m src search-eval eval.jsonl --verbose
    """
    console = Console()

    # Check if file exists
    import os

    if not os.path.exists(eval_file):
        console.print(f"[bold red]Error:[/bold red] File not found: {eval_file}")
        raise typer.Exit(1)

    console.print(f"[bold cyan]Processing evaluation file:[/bold cyan] {eval_file}")

    async def run_evaluation():
        from src.evals.search_utils import process_eval_queries

        # Quick check to show number of queries
        try:
            with open(eval_file) as f:
                queries = [json.loads(line) for line in f if line.strip()]
                console.print(f"[bold green]Found {len(queries)} queries to process[/bold green]")
        except Exception as e:
            console.print(f"[yellow]Note: Could not preview query count: {e}[/yellow]")

        def progress_callback(message: str):
            if verbose:
                console.print(f"[dim]{message}[/dim]")

        try:
            with console.status("[bold green]Running search evaluation...[/bold green]"):
                output_path = await process_eval_queries(
                    eval_file, output, progress_callback if verbose else None
                )

            console.print("[bold green]✓[/bold green] Evaluation complete!")
            console.print(f"[cyan]Results saved to:[/cyan] {output_path}")

            # Show summary statistics
            with open(output_path) as f:
                lines = f.readlines()
                total_queries = len(lines)

                total_original = 0
                total_new = 0
                sources_found = set()

                for line in lines:
                    result = json.loads(line)
                    total_original += len(result.get("original_gather", []))
                    total_new += result.get("results_count", 0)
                    sources_found.update(result.get("sources_found", []))

                console.print("\n[bold cyan]Summary:[/bold cyan]")
                console.print(f"  Total queries: {total_queries}")
                console.print(f"  Original results: {total_original}")
                console.print(f"  New results: {total_new}")
                console.print(f"  Sources found: {', '.join(sorted(sources_found))}")

        except Exception as e:
            console.print(f"[bold red]Error during evaluation: {e}[/bold red]")
            raise typer.Exit(1)

    try:
        asyncio.run(run_evaluation())
    except KeyboardInterrupt:
        console.print("\n[yellow]Evaluation interrupted by user[/yellow]")
        raise typer.Exit(0)


@app.command()
def rerun_original_gather(
    input_file: str = typer.Argument(..., help="Input JSONL file with original gather results"),
    output_name: str = typer.Option(
        "rerun_gather",
        "--output-name",
        "-o",
        help="Name for output file (without .jsonl extension)",
    ),
):
    """
    Re-run queries from an evaluation file using current MCP tools.

    Takes an existing evaluation JSONL file with original gather results and re-runs
    all the queries using the current keyword_search and semantic_search tools.
    The output maintains the same format but with updated gather_results.

    Examples:
        python -m src rerun-original-gather simplified_eval.jsonl

        python -m src rerun-original-gather old_results.jsonl --output-name new_baseline
    """
    console = Console()

    try:
        from pathlib import Path

        input_path = Path(input_file)
        if not input_path.exists():
            console.print(f"[bold red]Error:[/bold red] Input file {input_file} does not exist")
            raise typer.Exit(1)

        if input_path.suffix != ".jsonl":
            console.print("[bold red]Error:[/bold red] Input file must be a .jsonl file")
            raise typer.Exit(1)

        console.print(f"[cyan]Re-running queries from:[/cyan] {input_file}")
        console.print(f"[cyan]Output name:[/cyan] {output_name}")

        # Call the rerun function
        import asyncio

        from src.evals.rerun_original_gather import rerun_queries

        output_file = asyncio.run(rerun_queries(input_path, output_name))
        console.print(f"✅ [green]Successfully re-ran queries and saved to:[/green] {output_file}")

    except ImportError as e:
        console.print(f"[bold red]Error:[/bold red] Failed to import rerun module: {e}")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[bold red]Error:[/bold red] {e}")
        raise typer.Exit(1)


@app.command()
def view(
    jsonl_file: str | None = typer.Argument(
        None,
        help="Path to the JSONL results file to view. If not provided, uses the most recent file.",
    ),
    port: int = typer.Option(8888, "--port", "-p", help="Port to run the local server on"),
) -> None:
    """
    View search evaluation results in a web browser.

    Opens an interactive HTML viewer for analyzing search evaluation results.
    If no file is specified, automatically uses the most recent result file.

    Examples:
        python -m src view  # Uses most recent file

        python -m src view search_eval_results.jsonl

        python -m src view results.jsonl --port 9000
    """
    console = Console()

    # If no file specified, find the most recent one
    if jsonl_file is None:
        # Look in the results directory first
        results_dir = os.path.join(os.path.dirname(__file__), "results")
        pattern = os.path.join(results_dir, "search_eval_results_*.jsonl")
        files = glob.glob(pattern)

        # Also check the root directory for backward compatibility
        root_pattern = "search_eval_results_*.jsonl"
        root_files = glob.glob(root_pattern)
        files.extend(root_files)

        if not files:
            console.print("[bold red]Error:[/bold red] No search eval results found.")
            console.print(f"[yellow]Looked in: {results_dir} and current directory[/yellow]")
            console.print(
                "[yellow]Run 'python -m src search-eval' first to generate results.[/yellow]"
            )
            raise typer.Exit(1)

        # Get the most recent file based on modification time
        jsonl_file = max(files, key=os.path.getmtime)
        console.print(f"[cyan]Using most recent file: {os.path.basename(jsonl_file)}[/cyan]")

    if not os.path.exists(jsonl_file):
        console.print(f"[bold red]Error:[/bold red] File not found: {jsonl_file}")
        raise typer.Exit(1)

    # Get absolute paths
    jsonl_file_abs = os.path.abspath(jsonl_file)
    viewer_path = os.path.join(
        os.path.dirname(__file__), "search_utils", "mcp_comparison_viewer.html"
    )

    if not os.path.exists(viewer_path):
        console.print(f"[bold red]Error:[/bold red] Viewer HTML not found at: {viewer_path}")
        raise typer.Exit(1)

    # Create a simple HTTP server to serve the files
    import http.server
    import socketserver
    import threading
    import webbrowser
    from functools import partial

    class CustomHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args, jsonl_path=None, **kwargs):
            self.jsonl_path = jsonl_path
            super().__init__(*args, **kwargs)

        def do_GET(self):
            if self.path == "/data.jsonl":
                # Serve the JSONL file
                try:
                    with open(self.jsonl_path, "rb") as f:
                        self.send_response(200)
                        self.send_header("Content-type", "application/json")
                        self.send_header("Access-Control-Allow-Origin", "*")
                        self.end_headers()
                        self.wfile.write(f.read())
                except Exception as e:
                    self.send_error(500, f"Error reading file: {e}")
            elif self.path == "/" or self.path == "/viewer.html":
                # Serve the viewer HTML
                try:
                    with open(viewer_path, "rb") as f:
                        self.send_response(200)
                        self.send_header("Content-type", "text/html")
                        self.end_headers()
                        self.wfile.write(f.read())
                except Exception as e:
                    self.send_error(500, f"Error reading viewer: {e}")
            else:
                super().do_GET()

        def do_POST(self):
            if self.path == "/analyze-score":
                # Handle score analysis request
                try:
                    import asyncio
                    import json

                    # Read the POST data
                    content_length = int(self.headers.get("Content-Length", 0))
                    post_data = self.rfile.read(content_length).decode("utf-8")

                    # Parse JSON data
                    data = json.loads(post_data)
                    query = data.get("query", "")
                    document_id = data.get("document_id", "")
                    search_type = data.get("search_type", "keyword")

                    if not query or not document_id:
                        self.send_response(400)
                        self.send_header("Content-type", "application/json")
                        self.send_header("Access-Control-Allow-Origin", "*")
                        self.end_headers()
                        error_response = json.dumps({"error": "Missing query or document_id"})
                        self.wfile.write(error_response.encode())
                        return

                    # Import and run the score analyzer
                    from src.evals.search_utils.score_analyzer import analyze_score

                    # Run the async function
                    result = asyncio.run(analyze_score(query, document_id, search_type))

                    # Send response
                    self.send_response(200)
                    self.send_header("Content-type", "application/json")
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.end_headers()
                    self.wfile.write(json.dumps(result).encode())

                except Exception as e:
                    self.send_response(500)
                    self.send_header("Content-type", "application/json")
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.end_headers()
                    error_response = json.dumps({"error": str(e)})
                    self.wfile.write(error_response.encode())
            elif self.path == "/search-by-url":
                # Handle URL-to-document-ID search request
                try:
                    import asyncio
                    import json

                    # Read the POST data
                    content_length = int(self.headers.get("Content-Length", 0))
                    post_data = self.rfile.read(content_length).decode("utf-8")

                    # Parse JSON data
                    data = json.loads(post_data)
                    url = data.get("url", "")

                    if not url:
                        self.send_response(400)
                        self.send_header("Content-type", "application/json")
                        self.send_header("Access-Control-Allow-Origin", "*")
                        self.end_headers()
                        error_response = json.dumps({"error": "Missing URL"})
                        self.wfile.write(error_response.encode())
                        return

                    # Search for document by URL
                    from src.clients.supabase import get_global_db_connection

                    async def search_by_url(url: str):
                        conn = await get_global_db_connection()
                        try:
                            # Try various URL fields in metadata
                            # Handle GitHub PRs
                            if "github.com" in url and "/pull/" in url:
                                # Extract PR URL parts
                                import re

                                match = re.match(
                                    r"https://github.com/([^/]+)/([^/]+)/pull/(\d+)", url
                                )
                                if match:
                                    owner, repo, pr_num = match.groups()
                                    # Search by repository and PR number
                                    row = await conn.fetchrow(
                                        """
                                        SELECT id FROM documents
                                        WHERE source = 'github'
                                        AND metadata->>'repository' = $1
                                        AND metadata->>'pr_number' = $2
                                        LIMIT 1
                                        """,
                                        f"{owner}/{repo}",
                                        pr_num,
                                    )
                                    if row:
                                        return row["id"]

                            # Try generic URL search in various metadata fields
                            row = await conn.fetchrow(
                                """
                                SELECT id FROM documents
                                WHERE metadata->>'issue_url' = $1
                                   OR metadata->>'page_url' = $1
                                   OR metadata->>'pr_url' = $1
                                   OR metadata->>'url' = $1
                                   OR metadata->>'link' = $1
                                   OR metadata->>'permalink' = $1
                                LIMIT 1
                                """,
                                url,
                            )
                            if row:
                                return row["id"]

                            # Try partial URL match
                            row = await conn.fetchrow(
                                """
                                SELECT id FROM documents
                                WHERE metadata::text LIKE $1
                                LIMIT 1
                                """,
                                f"%{url}%",
                            )
                            if row:
                                return row["id"]

                            return None
                        finally:
                            await conn.close()

                    # Run the async function
                    document_id = asyncio.run(search_by_url(url))

                    # Send response
                    self.send_response(200 if document_id else 404)
                    self.send_header("Content-type", "application/json")
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.end_headers()

                    if document_id:
                        self.wfile.write(json.dumps({"document_id": document_id}).encode())
                    else:
                        self.wfile.write(
                            json.dumps(
                                {"error": "Document not found", "document_id": None}
                            ).encode()
                        )

                except Exception as e:
                    self.send_response(500)
                    self.send_header("Content-type", "application/json")
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.end_headers()
                    error_response = json.dumps({"error": str(e)})
                    self.wfile.write(error_response.encode())
            else:
                self.send_error(404, "Not found")

        def do_OPTIONS(self):
            # Handle CORS preflight requests
            self.send_response(200)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.end_headers()

        def log_message(self, format, *args):
            # Suppress normal logging
            pass

    # Create handler with the JSONL file path
    handler = partial(CustomHTTPRequestHandler, jsonl_path=jsonl_file_abs)

    console.print(f"[cyan]Starting local server on port {port}...[/cyan]")

    # Start server in a separate thread
    httpd = socketserver.TCPServer(("", port), handler)
    server_thread = threading.Thread(target=httpd.serve_forever)
    server_thread.daemon = True
    server_thread.start()

    # Open browser
    url = f"http://localhost:{port}"
    console.print(f"[green]Opening browser at: {url}[/green]")
    console.print(f"[yellow]Viewing: {jsonl_file}[/yellow]")
    console.print("\n[dim]Press Ctrl+C to stop the server[/dim]")

    webbrowser.open(url)

    # Keep server running
    try:
        while True:
            import time

            time.sleep(1)
    except KeyboardInterrupt:
        console.print("\n[yellow]Shutting down server...[/yellow]")
        httpd.shutdown()
        raise typer.Exit(0)


@app.callback()
def callback():
    """
    Corporate Context CLI - Query your knowledge base
    """
    pass


def main():
    """Main entry point that delegates to the appropriate command."""
    app()


if __name__ == "__main__":
    main()
