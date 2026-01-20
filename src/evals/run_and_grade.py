"""
This script runs eval questions through an agent and grades the responses.

Usage:
    # Run with local agent loop, staging MCP tools. Make sure you're authed with AWS (so you have a session token) and on staging VPN.
    # To get a remote (e.g. staging) MCP token, use `generate_mcp_token.py`. See also: `GATHER_INTERNAL_STAGING_TENANT_ID`
    $ REMOTE_MCP_TOKEN=xxxx python -m src.evals.run_and_grade --model gpt-5

    # Run with ask_agent tool from MCP
    $ python -m src.evals.run_and_grade --use-mcp-ask-agent
"""

import argparse
import asyncio
import json
import os
import re
import sys
import time
from datetime import UTC, datetime
from typing import Any, Literal

from fastmcp import Client

from src.evals.utils import RUNS_DIR

# Parse arguments early to check for --no-tracing flag
early_parser = argparse.ArgumentParser(add_help=False)
early_parser.add_argument(
    "--no-tracing",
    action="store_true",
)
early_args, _ = early_parser.parse_known_args()

DISABLE_TRACING = early_args.no_tracing
# Set environment variable before any imports if tracing is disabled
if DISABLE_TRACING:
    os.environ["DISABLE_LANGFUSE_TRACING"] = "true"

from rich.console import Console

from src.evals.cli import call_agent_directly, call_ask_agent_via_mcp
from src.evals.grader import GRADER_MODEL, GRADER_VERSION, grade_answer
from src.evals.stats import (
    print_error_summary,
    print_grade_distribution,
    print_timing_stats,
)
from src.evals.stats_core import (
    calculate_error_stats,
    calculate_grade_stats,
    calculate_parallel_tool_stats,
    calculate_thinking_time_stats,
    calculate_timing_stats,
    calculate_tool_usage_stats,
    calculate_turn_stats,
)
from src.mcp.tools import register_tools
from src.utils.config import (
    get_mcp_base_url,
    get_openai_api_key,
    get_remote_mcp_token,
    get_remote_mcp_url,
)
from src.utils.http_auth import BearerAuth

QUESTIONS_FILE_PATH = "src/evals/data/eval-gtw-1.json"

QUESTION_TIMEOUT = 480  # Max 8 minutes per question

# Register MCP tools so RemoteToolExecutor can find them
register_tools()


def sanitize_experiment_name(name: str) -> str:
    """
    Sanitizes experiment name for use in directory names.
    Replaces spaces with underscores and removes special characters.
    """
    # Replace spaces with underscores
    name = name.replace(" ", "_")
    # Remove any character that's not alphanumeric, underscore, or hyphen
    name = re.sub(r"[^a-zA-Z0-9_-]", "", name)
    return name


async def run_agent_for_question(
    question_data: dict[str, Any],
    console: Console,
    extract_search: bool = False,
    use_mcp: bool = False,
    model: str = "gpt-5",
) -> tuple[
    str,
    list[dict[str, Any]],
    int,
    dict[str, str] | None,
    list[dict[str, Any]] | None,
    list[dict[str, Any]],
    float,
]:
    """
    Runs the agent for a single question and returns the final answer, tool call history, turn count, trace info, search data, tool call details, and thinking time.
    """
    query = question_data.get("question")
    if not query:
        print(f"  [!] No question found in question_data: {question_data}")
        return "", [], 0, None, None, [], 0.0

    print(f"  [Q{question_data.get('id')}] Starting agent execution...")
    final_answer = ""
    tool_call_history = []
    turn_count = 0
    trace_info = None
    tool_call_details: list[dict[str, Any]] = []
    thinking_time_ms = 0.0

    try:
        # Create a wrapper console that prefixes output with question ID
        class QuestionPrefixConsole(Console):
            def __init__(self, base_console, question_id):
                super().__init__()
                self.base_console = base_console
                self.question_id = question_id

            def print(self, *args, **kwargs):
                # Add question ID prefix to all output
                if args:
                    prefixed_args = (f"  [Q{self.question_id}] {args[0]}",) + args[1:]
                    self.base_console.print(*prefixed_args, **kwargs)
                else:
                    self.base_console.print(*args, **kwargs)

        # Create prefixed console for this question
        q_console = QuestionPrefixConsole(console, question_data.get("id"))

        # Call the agent via the selected method
        if use_mcp:
            result = await call_ask_agent_via_mcp(
                query,
                q_console,
                verbose=False,  # Set to True if you want detailed tool output
                extract_search=extract_search,
            )
        else:
            result = await call_agent_directly(
                query,
                q_console,
                verbose=False,  # Set to True if you want detailed tool output
                extract_search=extract_search,
                model=model,
            )

        # Unpack results based on extract_search flag
        if extract_search:
            (
                final_answer_data,
                tool_calls_made,
                turn_count,
                trace_info,
                search_data,
                tool_call_details,
                thinking_time_ms,
            ) = result
        else:
            (
                final_answer_data,
                tool_calls_made,
                turn_count,
                trace_info,
                tool_call_details,
                thinking_time_ms,
            ) = result
            search_data = None

        # Extract answer text (same as query command)
        if isinstance(final_answer_data, dict):
            final_answer = final_answer_data.get("answer", str(final_answer_data))
        else:
            final_answer = final_answer_data

        # Use the detailed tool call history with tool names
        tool_call_history = tool_call_details if tool_call_details else []

        print(f"  [Q{question_data.get('id')}] Got final answer ({len(final_answer)} chars)")
        if trace_info:
            print(f"  [Q{question_data.get('id')}] Trace ID: {trace_info.get('trace_id')}")

    except TimeoutError:
        error_msg = f"Agent execution timed out after {QUESTION_TIMEOUT} seconds"
        print(f"❌ {error_msg} for question ID {question_data.get('id')}")
        return error_msg, tool_call_history, 0, None, None, [], 0.0
    except Exception as e:
        print(f"❌ Agent execution failed for question ID {question_data.get('id')}: {e}")
        import traceback

        traceback.print_exc()
        return f"Agent execution failed: {e}", tool_call_history, 0, None, None, [], 0.0

    return (
        final_answer,
        tool_call_history,
        turn_count,
        trace_info,
        search_data,
        tool_call_details,
        thinking_time_ms,
    )


async def process_question(
    question_data: dict[str, Any],
    console: Console,
    extract_search: bool = False,
    use_mcp: bool = False,
    model: str = "gpt-5",
) -> dict[str, Any]:
    """
    Processes a single question: runs the agent, gets the answer, and grades it.
    """
    question_id = question_data.get("id")
    question_text = question_data.get("question", "")
    print(
        f"\n[Starting Q{question_id}] {question_text[:80] if question_text else 'No question'}..."
    )
    start_time = time.time()

    # Initialize error tracking
    question_errors = []

    # Run agent
    agent_result = await run_agent_for_question(
        question_data, console, extract_search, use_mcp, model
    )

    # Unpack result - now returns 7 values
    (
        final_answer,
        tool_call_history,
        turn_count,
        trace_info,
        search_data,
        _tool_call_details,
        thinking_time_ms,
    ) = agent_result

    # Grade the answer
    expected_answer = question_data.get("expected_answer", "")
    actual_question = question_data.get("question", "")

    try:
        score = await grade_answer(final_answer, actual_question, expected_answer)
        grader_info = f"Graded with {GRADER_MODEL} using rubric {GRADER_VERSION}"
        print(f"  [Q{question_id}] ✓ Graded answer. Score: {score}/5")
    except Exception as e:
        print(f"  [Q{question_id}] ✗ Grading failed: {e}")
        score = -1
        grader_info = f"Grading failed: {str(e)}"
        question_errors.append(
            {
                "error_type": "grading_error",
                "error_message": str(e),
                "timestamp": datetime.now(UTC).isoformat(),
            }
        )

    # Prepare error summary
    error_summary = None
    if question_errors:
        error_types: dict[str, int] = {}
        for error in question_errors:
            error_type = error.get("error_type", "unknown")
            error_types[error_type] = error_types.get(error_type, 0) + 1
        error_summary = {"total_errors": len(question_errors), "error_types": error_types}

    end_time = time.time()

    # Calculate tool call count from detailed history
    # Each entry in tool_call_history represents one tool call
    actual_tool_call_count = len(tool_call_history)

    # Build result
    result = {
        **question_data,
        "actual_answer": final_answer,
        "tool_call_history": tool_call_history,
        "llm_grades": {GRADER_VERSION: {"score": score, "grader_info": grader_info}},
        "processing_time_seconds": round(end_time - start_time, 2),
        "thinking_time_ms": round(thinking_time_ms, 1),
        "tools_used": "all_available_from_mcp",
        "tool_call_count": actual_tool_call_count,
        "turn_count": turn_count,
        "model_info": {
            "model": model,
            "context_window": 128000,  # Default for corporate-context
        },
        "errors": question_errors,
        "error_summary": error_summary,
    }

    # Add search data if extracted
    if search_data:
        result["search_data"] = search_data

    # Add trace info if available
    if trace_info:
        result["trace_id"] = trace_info.get("trace_id")
        result["trace_url"] = trace_info.get("trace_url")

        # Display trace URL if tracing is enabled
        if not DISABLE_TRACING:
            print(f"  [Q{question_id}] Langfuse trace URL: {trace_info.get('trace_url', 'N/A')}")

    return result


async def run_experiment_with_concurrency(
    questions: list[dict[str, Any]],
    console: Console,
    concurrent_requests: int,
    extract_search: bool = False,
    use_mcp: bool = False,
    model: str = "gpt-5",
) -> list[dict[str, Any]]:
    """
    Runs the experiment with concurrency control.
    """
    results = []

    # Create semaphore to limit concurrent execution
    semaphore = asyncio.Semaphore(concurrent_requests)

    async def process_question_with_semaphore(question_data: dict[str, Any]) -> dict[str, Any]:
        """Wrapper that acquires semaphore before processing question."""
        async with semaphore:
            return await process_question(question_data, console, extract_search, use_mcp, model)

    # Create tasks with semaphore wrapper
    tasks = [process_question_with_semaphore(q) for q in questions]

    completed_count = 0
    for future in asyncio.as_completed(tasks):
        result = await future
        completed_count += 1
        results.append(result)

        print(
            f"\n✅ [{completed_count}/{len(questions)}] Completed question {result.get('id')} (Score: {result['llm_grades'][GRADER_VERSION]['score']})"
        )

    return results


async def main():
    """
    Main function to run the evaluation process.
    """
    parser = argparse.ArgumentParser(description="Run agent evaluation script.")
    parser.add_argument(
        "--model",
        "-m",
        type=str,
        default="gpt-5",
        help="Model to use for evaluation. Default: gpt-5",
    )
    parser.add_argument(
        "--no-tracing",
        action="store_true",
        help="Disable Langfuse tracing and skip authentication checks",
    )
    parser.add_argument(
        "--experiment-name",
        "-e",
        type=str,
        help="Optional experiment name to append to the output directory",
    )
    parser.add_argument(
        "--questions",
        "-q",
        type=str,
        help="Comma-separated list of specific question IDs to run (e.g., '1,3,5'). Default: run all questions",
    )
    parser.add_argument(
        "--concurrency",
        "-c",
        type=int,
        default=10,
        help="Maximum number of concurrent requests (default: 10)",
    )
    parser.add_argument(
        "--questions-file",
        "-f",
        type=str,
        default=QUESTIONS_FILE_PATH,
        help=f"Path to the questions file (default: {QUESTIONS_FILE_PATH})",
    )
    parser.add_argument(
        "--extract-search",
        action="store_true",
        help="Extract and save all search queries and results to a JSON file",
    )
    parser.add_argument(
        "--use-mcp-ask-agent",
        action="store_true",
        help="Use call_ask_agent_via_mcp instead of call_agent_directly (default: False, uses call_agent_directly)",
    )
    args = parser.parse_args()

    console = Console()

    # Validate concurrency argument
    if args.concurrency is not None and args.concurrency <= 0:
        print(f"❌ Error: Concurrency must be a positive integer, got: {args.concurrency}")
        return

    if DISABLE_TRACING:
        print("🚫 Tracing disabled - skipping Langfuse authentication")

    # Check OpenAI API key
    if not get_openai_api_key():
        print("❌ OPENAI_API_KEY environment variable is not set.")
        print("This is required for grading.")
        return

    print(f"🤖 Using model: {args.model}")

    # Display agent execution mode
    if args.use_mcp_ask_agent:
        print("🔌 Using call_ask_agent_via_mcp (remote agent execution)")
    else:
        print("🏠 Using call_agent_directly (local agent with remote tools)")

    # Build the run dir name
    if args.experiment_name:
        # When experiment name provided: experiment_{name}_{timestamp}
        sanitized_name = sanitize_experiment_name(args.experiment_name)
        base_dir_name = f"experiment_{sanitized_name}_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}"
    else:
        # When no experiment name: experiment_{timestamp}-{model}
        base_dir_name = f"experiment_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}-{args.model}"

    # Create runs directory if it doesn't exist
    os.makedirs(RUNS_DIR, exist_ok=True)

    # Create the experiment directory
    run_dir = os.path.join(RUNS_DIR, base_dir_name)
    os.makedirs(run_dir, exist_ok=True)

    print(f"📁 Results will be saved to: {run_dir}")

    # Load questions
    if not os.path.exists(args.questions_file):
        print(f"❌ Questions file not found: {args.questions_file}")
        return

    with open(args.questions_file) as f:
        all_questions = json.load(f)

    # Filter questions if specific IDs provided
    if args.questions:
        try:
            question_ids = [int(q.strip()) for q in args.questions.split(",")]
            all_questions = [q for q in all_questions if q.get("id") in question_ids]
            print(f"📋 Running {len(all_questions)} specific questions: {question_ids}")
        except ValueError:
            print("❌ Invalid question IDs format. Use comma-separated integers (e.g., '1,3,5')")
            return
    else:
        print(f"📋 Running all {len(all_questions)} questions")

    if not all_questions:
        print("❌ No questions to run after filtering")
        return

    # Set concurrent requests - limit to question count if fewer questions than concurrency
    concurrent_requests = min(args.concurrency, len(all_questions))

    # Check API server once before starting
    print("🔌 Checking API server connection...")
    # Note: API server check removed as check_api_server function doesn't exist
    print("⚠️  Skipping API server check - please ensure it's running on port 8000")

    # Authenticate with MCP once before parallel execution
    remote_bearer_token = get_remote_mcp_token()
    if remote_bearer_token:
        mcp_url = get_remote_mcp_url()
        print("🔐 Authenticating via bearer token with remote MCP server: {mcp_url}")
        auth: Literal["oauth"] | BearerAuth = BearerAuth(remote_bearer_token)
    else:
        mcp_url = get_mcp_base_url()
        print(f"🔐 Authenticating via OAuth with MCP server: {mcp_url}")
        auth = "oauth"

    try:
        async with Client(mcp_url, auth=auth) as client:
            await client.ping()
        print("✅ MCP authentication successful")
    except Exception as e:
        print(f"❌ MCP authentication failed: {e}")
        return

    # Run the experiment
    print("\n🚀 Starting evaluation...")
    print(f"📊 Total questions: {len(all_questions)}")
    print(
        f"🔄 Concurrency limit: {concurrent_requests} questions at a time"
        + (f" (requested: {args.concurrency})" if args.concurrency != 10 else " (default)")
    )
    print("\n" + "=" * 60)
    overall_start_time = time.time()

    try:
        results = await run_experiment_with_concurrency(
            all_questions,
            console,
            concurrent_requests,
            args.extract_search,
            args.use_mcp_ask_agent,
            args.model,
        )

        # Save results
        results_file = os.path.join(run_dir, "results.jsonl")
        with open(results_file, "w") as f:
            for result in results:
                f.write(json.dumps(result) + "\n")

        # Save search data separately if extracted
        if args.extract_search:
            search_file = os.path.join(run_dir, "search_extracts.json")
            all_search_data = []
            for result in results:
                if "search_data" in result:
                    all_search_data.append(
                        {
                            "question_id": result["id"],
                            "question": result["question"],
                            "searches": result["search_data"],
                        }
                    )

            with open(search_file, "w") as f:
                json.dump(all_search_data, f, indent=2)

            print(f"\n🔍 Search data saved to: {search_file}")

        # Calculate statistics using shared functions
        wall_clock_time = time.time() - overall_start_time
        grade_stats = calculate_grade_stats(results, GRADER_VERSION)
        timing_stats = calculate_timing_stats(results)
        tool_stats = calculate_tool_usage_stats(results)
        parallel_stats = calculate_parallel_tool_stats(results)
        turn_stats = calculate_turn_stats(results)
        thinking_stats = calculate_thinking_time_stats(results)
        error_stats = calculate_error_stats(results)

        # Build enhanced summary with all statistics
        summary = {
            "grading": {
                "total_questions": len(results),
                "graded_questions": grade_stats["count"],
                "average_score": round(grade_stats["average"], 2),
                "median_score": round(grade_stats["median"], 1),
                "min_score": grade_stats["min"],
                "max_score": grade_stats["max"],
                "score_distribution": grade_stats["distribution"],
            },
            "timing": {
                "wall_clock_time_seconds": round(wall_clock_time, 2),
                "total_processing_time_seconds": round(timing_stats["total"], 2),
                "avg_processing_time_per_question": round(timing_stats["average"], 2),
                "median_processing_time_per_question": round(timing_stats["median"], 2),
                "min_processing_time": round(timing_stats["min"], 2),
                "max_processing_time": round(timing_stats["max"], 2),
            },
            "tool_usage": {
                "total_tool_calls": tool_stats["total_tool_calls"],
                "avg_tool_calls_per_question": round(tool_stats["avg_tool_calls"], 1),
                "median_tool_calls_per_question": round(tool_stats["median_tool_calls"], 1),
                "p95_tool_calls_per_question": tool_stats["p95_tool_calls"],
                "parallel_execution_percentage": round(parallel_stats["parallel_percentage"], 1),
                "parallel_tool_calls": parallel_stats["parallel_tool_calls"],
                "sequential_tool_calls": parallel_stats["sequential_tool_calls"],
                "total_parallel_batches": parallel_stats["total_batches"],
                "avg_batch_size": round(parallel_stats["avg_batch_size"], 1),
            },
            "turns": {
                "total_turns": turn_stats["total_turns"],
                "avg_turns_per_question": round(turn_stats["avg_turns"], 1),
                "median_turns_per_question": round(turn_stats["median_turns"], 1),
                "p95_turns_per_question": turn_stats["p95_turns"],
            },
            "thinking_time": {
                "total_thinking_time_ms": round(thinking_stats["total_thinking_time_ms"], 1),
                "avg_thinking_time_ms": round(thinking_stats["avg_thinking_time_ms"], 1),
                "median_thinking_time_ms": round(thinking_stats["median_thinking_time_ms"], 1),
                "p95_thinking_time_ms": round(thinking_stats["p95_thinking_time_ms"], 1),
            },
            "errors": {
                "total_errors": error_stats["total_errors"],
                "questions_with_errors": error_stats["questions_with_errors"],
                "questions_with_errors_percentage": round(
                    error_stats["questions_with_errors_percentage"], 1
                ),
                "error_types": error_stats["error_types"],
            },
            "config": {
                "model": args.model,
                "grader_version": GRADER_VERSION,
                "concurrency": concurrent_requests,
            },
        }

        summary_file = os.path.join(run_dir, "summary.json")
        with open(summary_file, "w") as f:
            json.dump(summary, f, indent=2)

        # Display comprehensive statistics using Rich tables
        console.print("\n" + "=" * 80)
        console.print("[bold cyan]EVALUATION SUMMARY[/bold cyan]", justify="center")
        console.print("=" * 80 + "\n")

        # Display grade statistics with Rich tables
        from rich.table import Table

        # Overall grade statistics
        grade_table = Table(title="Grade Statistics", show_header=True, header_style="bold green")
        grade_table.add_column("Metric", style="dim", width=20)
        grade_table.add_column("Value", justify="right")
        grade_table.add_row("Graded Questions", f"{grade_stats['count']}/{len(results)}")
        grade_table.add_row("Average Score", f"{grade_stats['average']:.2f}/5")
        grade_table.add_row("Median Score", f"{grade_stats['median']:.1f}/5")
        grade_table.add_row("Min Score", f"{grade_stats['min']}/5")
        grade_table.add_row("Max Score", f"{grade_stats['max']}/5")
        console.print(grade_table)
        console.print()

        # Grade distribution
        print_grade_distribution(grade_stats["distribution"], grade_stats["count"])
        console.print()

        # Timing statistics
        print_timing_stats(results)
        console.print()

        # Tool usage statistics
        tool_table = Table(
            title="Tool Usage Statistics", show_header=True, header_style="bold magenta"
        )
        tool_table.add_column("Metric", style="dim", width=30)
        tool_table.add_column("Value", justify="right")
        tool_table.add_row("Total Tool Calls", str(tool_stats["total_tool_calls"]))
        tool_table.add_row("Avg Tools per Question", f"{tool_stats['avg_tool_calls']:.1f}")
        tool_table.add_row("Median Tools per Question", f"{tool_stats['median_tool_calls']:.1f}")
        tool_table.add_row("p95 Tools per Question", str(tool_stats["p95_tool_calls"]))
        console.print(tool_table)
        console.print()

        # Parallel tool execution statistics
        if parallel_stats["total_tool_calls"] > 0:
            parallel_table = Table(
                title="Parallel Tool Execution",
                show_header=True,
                header_style="bold magenta",
            )
            parallel_table.add_column("Metric", style="dim", width=30)
            parallel_table.add_column("Value", justify="right")
            parallel_table.add_row(
                "Parallel Tool Calls", str(parallel_stats["parallel_tool_calls"])
            )
            parallel_table.add_row(
                "Sequential Tool Calls", str(parallel_stats["sequential_tool_calls"])
            )
            parallel_table.add_row(
                "Parallel Execution %", f"{parallel_stats['parallel_percentage']:.1f}%"
            )
            if parallel_stats["total_batches"] > 0:
                parallel_table.add_row(
                    "Total Parallel Batches", str(parallel_stats["total_batches"])
                )
                parallel_table.add_row("Avg Batch Size", f"{parallel_stats['avg_batch_size']:.1f}")
            console.print(parallel_table)
            console.print()

        # Turn statistics
        turn_table = Table(
            title="Agent Turn Statistics", show_header=True, header_style="bold cyan"
        )
        turn_table.add_column("Metric", style="dim", width=30)
        turn_table.add_column("Value", justify="right")
        turn_table.add_row("Total Turns", str(turn_stats["total_turns"]))
        turn_table.add_row("Avg Turns per Question", f"{turn_stats['avg_turns']:.1f}")
        turn_table.add_row("Median Turns per Question", f"{turn_stats['median_turns']:.1f}")
        turn_table.add_row("p95 Turns per Question", str(turn_stats["p95_turns"]))
        console.print(turn_table)
        console.print()

        # Thinking time statistics
        thinking_table = Table(
            title="Thinking Time Statistics", show_header=True, header_style="bold yellow"
        )
        thinking_table.add_column("Metric", style="dim", width=30)
        thinking_table.add_column("Value", justify="right")
        thinking_table.add_row(
            "Total Thinking Time",
            f"{thinking_stats['total_thinking_time_ms'] / 1000:.1f}s ({thinking_stats['total_thinking_time_ms']:.0f}ms)",
        )
        thinking_table.add_row(
            "Avg Thinking Time",
            f"{thinking_stats['avg_thinking_time_ms']:.0f}ms ({thinking_stats['avg_thinking_time_ms'] / 1000:.1f}s)",
        )
        thinking_table.add_row(
            "Median Thinking Time",
            f"{thinking_stats['median_thinking_time_ms']:.0f}ms ({thinking_stats['median_thinking_time_ms'] / 1000:.1f}s)",
        )
        thinking_table.add_row(
            "p95 Thinking Time",
            f"{thinking_stats['p95_thinking_time_ms']:.0f}ms ({thinking_stats['p95_thinking_time_ms'] / 1000:.1f}s)",
        )
        console.print(thinking_table)
        console.print()

        # Error summary
        print_error_summary(results)
        console.print()

        # Configuration
        config_table = Table(title="Configuration", show_header=True, header_style="bold blue")
        config_table.add_column("Setting", style="dim", width=20)
        config_table.add_column("Value", justify="right")
        config_table.add_row("Model", args.model)
        config_table.add_row("Grader Version", GRADER_VERSION)
        config_table.add_row("Concurrency", str(concurrent_requests))
        config_table.add_row("Wall Clock Time", f"{wall_clock_time:.1f}s")
        console.print(config_table)

        console.print("\n" + "=" * 80)

    except Exception as e:
        print(f"\n❌ Evaluation failed with error: {e}")
        import traceback

        traceback.print_exc()
        return

    print(f"\n✅ Evaluation complete! Results saved to: {run_dir}")


if __name__ == "__main__":
    # Check required environment variables
    try:
        from src.utils.config import get_openai_api_key

        if not get_openai_api_key():
            print("❌ Error: OPENAI_API_KEY environment variable is not set.")
            print("   Please set OPENAI_API_KEY in your .env file.")
            sys.exit(1)
    except ImportError:
        print("❌ Error: Could not import config. Make sure src/utils/config.py exists.")
        sys.exit(1)

    asyncio.run(main())
