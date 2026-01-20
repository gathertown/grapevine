import json
import os
import re
from typing import Any

import typer
from rich.console import Console
from rich.table import Table

from src.evals.stats_core import (
    calculate_error_stats,
    calculate_grade_comparison_stats,
    calculate_grade_stats,
    calculate_human_grade_stats,
    calculate_parallel_tool_stats,
    calculate_thinking_time_stats,
    calculate_timing_stats,
    calculate_tool_usage_stats,
    calculate_turn_stats,
)
from src.evals.utils import RUNS_DIR


def find_all_experiments_chronologically():
    """Find all experiment directories sorted chronologically (oldest to newest)."""
    if not os.path.exists(RUNS_DIR):
        return []

    # Look for experiment directories (experiment_YYYYMMDD_HHMMSS)
    experiment_dirs = [
        os.path.join(RUNS_DIR, d)
        for d in os.listdir(RUNS_DIR)
        if os.path.isdir(os.path.join(RUNS_DIR, d)) and d.startswith("experiment_")
    ]

    if not experiment_dirs:
        return []

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

    return sorted(experiment_dirs, key=extract_timestamp)


app = typer.Typer()
console = Console()


def load_results(file_path: str) -> list[dict[str, Any]]:
    """Loads evaluation results from a .jsonl file."""
    if not os.path.exists(file_path):
        console.print(f"[bold red]Error:[/bold red] Results file not found: {file_path}")
        return []

    results = []
    with open(file_path) as f:
        for line in f:
            try:
                results.append(json.loads(line))
            except json.JSONDecodeError:
                console.print(f"[yellow]Warning: Could not parse line in {file_path}[/yellow]")

    return results


def load_summary(experiment_dir: str) -> dict[str, Any] | None:
    """Load summary.json file if it exists."""
    summary_file = os.path.join(experiment_dir, "summary.json")
    if os.path.exists(summary_file):
        try:
            with open(summary_file) as f:
                return json.load(f)
        except (json.JSONDecodeError, Exception) as e:
            console.print(f"[yellow]Warning: Could not load summary.json: {e}[/yellow]")
    return None


def print_error_summary(results: list[dict[str, Any]]):
    """Calculates and prints error summary statistics."""
    error_stats = calculate_error_stats(results)

    total_questions = error_stats["total_questions"]
    total_errors = error_stats["total_errors"]
    questions_with_errors = error_stats["questions_with_errors"]
    questions_with_errors_percentage = error_stats["questions_with_errors_percentage"]
    all_error_types = error_stats["error_types"]
    question_ids_with_errors = error_stats["question_ids_with_errors"]

    if total_errors == 0:
        table = Table(title="Error Summary", show_header=True, header_style="bold green")
        table.add_column("Status", style="green")
        table.add_row("No errors detected! 🎉")
        console.print(table)
        return

    # Create error summary table
    table = Table(title="Error Summary", show_header=True, header_style="bold red")
    table.add_column("Metric", style="dim", width=25)
    table.add_column("Value", justify="right")

    table.add_row("Total Errors", str(total_errors))
    table.add_row(
        "Questions with Errors",
        f"{questions_with_errors}/{total_questions} ({questions_with_errors_percentage:.1f}%)",
    )
    table.add_row("")

    # Error types breakdown
    table.add_row("[bold]Error Types[/bold]", "")
    for error_type, count in sorted(all_error_types.items(), key=lambda x: x[1], reverse=True):
        table.add_row(f"  {error_type}", str(count))

    if question_ids_with_errors:
        table.add_row("")
        table.add_row(
            "Question IDs with Errors", ", ".join(map(str, sorted(question_ids_with_errors)))
        )

    console.print(table)


def print_grade_distribution(distribution: dict[int, int], total: int):
    """Print a visual representation of grade distribution."""
    table = Table(title="Grade Distribution", show_header=True, header_style="bold cyan")
    table.add_column("Score", justify="center", style="cyan", no_wrap=True)
    table.add_column("Count", justify="right", style="magenta")
    table.add_column("Percentage", justify="right")
    table.add_column("Bar", justify="left")

    max_count = max(distribution.values()) if distribution.values() else 1

    for score in range(1, 6):
        count = distribution.get(score, 0)
        percentage = (count / total * 100) if total > 0 else 0
        bar_length = int((count / max_count) * 40) if max_count > 0 else 0
        bar = "█" * bar_length

        table.add_row(f"{score}/5", str(count), f"{percentage:.1f}%", bar)

    console.print(table)


def print_timing_stats(results: list[dict[str, Any]]):
    """Print timing statistics."""
    timing_stats = calculate_timing_stats(results)

    if timing_stats["count"] == 0:
        return

    table = Table(title="Timing Statistics", show_header=True, header_style="bold yellow")
    table.add_column("Metric", style="dim", width=25)
    table.add_column("Value", justify="right")

    table.add_row("Total Questions", str(timing_stats["count"]))
    table.add_row("Average Time per Question", f"{timing_stats['average']:.1f}s")
    table.add_row("Median Time", f"{timing_stats['median']:.1f}s")
    table.add_row("Min Time", f"{timing_stats['min']:.1f}s")
    table.add_row("Max Time", f"{timing_stats['max']:.1f}s")
    table.add_row("Total Time", f"{timing_stats['total']:.1f}s")

    console.print(table)


def print_human_grade_stats(results: list[dict[str, Any]]):
    """Print human grader statistics."""
    human_stats = calculate_human_grade_stats(results)

    if human_stats["count"] == 0:
        return

    # Overall statistics
    table = Table(title="Human Grade Statistics", show_header=True, header_style="bold blue")
    table.add_column("Metric", style="dim", width=20)
    table.add_column("Value", justify="right")

    table.add_row("Graded Questions", f"{human_stats['count']}/{len(results)}")
    table.add_row("Average Score", f"{human_stats['average']:.2f}/5")
    table.add_row("Median Score", f"{human_stats['median']:.1f}/5")
    table.add_row("Min Score", f"{human_stats['min']}/5")
    table.add_row("Max Score", f"{human_stats['max']}/5")

    # Show graders if available
    if human_stats["graders"]:
        table.add_row("")
        table.add_row("[bold]Graders[/bold]", "")
        for grader in human_stats["graders"]:
            table.add_row("  " + grader, "")

    console.print(table)
    console.print()

    # Grade distribution
    print_grade_distribution(human_stats["distribution"], human_stats["count"])


def print_grade_comparison(results: list[dict[str, Any]]):
    """Print comparison between human and LLM grades."""
    comparison_stats = calculate_grade_comparison_stats(results)

    if comparison_stats["count"] == 0:
        return

    table = Table(
        title="Human vs LLM Grade Comparison", show_header=True, header_style="bold magenta"
    )
    table.add_column("Metric", style="dim", width=30)
    table.add_column("Value", justify="right")

    table.add_row("Questions Compared", str(comparison_stats["count"]))
    table.add_row("")
    table.add_row("Human Average", f"{comparison_stats['human_avg']:.2f}/5")
    table.add_row("LLM Average", f"{comparison_stats['llm_avg']:.2f}/5")
    table.add_row("")
    table.add_row("Exact Agreement", f"{comparison_stats['agreement_exact']:.1f}%")
    table.add_row("Agreement Within ±1", f"{comparison_stats['agreement_within_1']:.1f}%")
    table.add_row("Mean Absolute Difference", f"{comparison_stats['mean_absolute_difference']:.2f}")

    console.print(table)


@app.command()
def main(
    results_path: str = typer.Argument(
        ..., help="Experiment name or path to experiment directory/results file"
    ),
):
    """Analyze evaluation results and display statistics."""

    # If it's just an experiment name (not a path), prepend RUNS_DIR
    if "/" not in results_path and "\\" not in results_path:
        # It's just a name, construct the full path
        results_path = os.path.join(RUNS_DIR, results_path)

    # Determine if path is a directory or file
    if os.path.isdir(results_path):
        results_file = os.path.join(results_path, "results.jsonl")
        experiment_dir = results_path
    else:
        results_file = results_path
        experiment_dir = os.path.dirname(results_path)

    # Load results
    results = load_results(results_file)
    if not results:
        console.print("[bold red]No results found to analyze.[/bold red]")
        raise typer.Exit(1)

    # Load summary if available
    summary = load_summary(experiment_dir)

    # Display experiment info
    console.print(
        f"\n[bold cyan]Experiment Analysis: {os.path.basename(experiment_dir)}[/bold cyan]"
    )
    console.print(f"Total Questions: {len(results)}")

    if summary:
        console.print(f"Model: {summary.get('model', 'Unknown')}")
        console.print(f"Grader Version: {summary.get('grader_version', 'Unknown')}")

    console.print()

    # Calculate and display LLM grade statistics
    grade_stats = calculate_grade_stats(results)

    if grade_stats["count"] > 0:
        # Overall statistics
        table = Table(title="LLM Grade Statistics", show_header=True, header_style="bold green")
        table.add_column("Metric", style="dim", width=20)
        table.add_column("Value", justify="right")

        table.add_row("Graded Questions", f"{grade_stats['count']}/{len(results)}")
        table.add_row("Average Score", f"{grade_stats['average']:.2f}/5")
        table.add_row("Median Score", f"{grade_stats['median']:.1f}/5")
        table.add_row("Min Score", f"{grade_stats['min']}/5")
        table.add_row("Max Score", f"{grade_stats['max']}/5")

        console.print(table)
        console.print()

        # Grade distribution
        print_grade_distribution(grade_stats["distribution"], grade_stats["count"])
        console.print()
    else:
        console.print("[yellow]No LLM graded questions found.[/yellow]\n")

    # Human grade statistics
    print_human_grade_stats(results)
    human_stats = calculate_human_grade_stats(results)
    if human_stats["count"] > 0:
        console.print()

        # Show comparison if both human and LLM grades exist
        if grade_stats["count"] > 0:
            print_grade_comparison(results)
            console.print()

    # Timing statistics
    print_timing_stats(results)
    console.print()

    # Error summary
    print_error_summary(results)

    # Tool usage statistics
    console.print("\n[bold magenta]Tool Usage Statistics[/bold magenta]")
    tool_stats = calculate_tool_usage_stats(results)

    # Always show basic stats if we have tool call counts
    if tool_stats["total_tool_calls"] > 0:
        console.print(f"[dim]Total tool calls: {tool_stats['total_tool_calls']}[/dim]")
        console.print(f"[dim]Average tools per question: {tool_stats['avg_tool_calls']:.1f}[/dim]")
        console.print(
            f"[dim]Median (p50) tools per question: {tool_stats['median_tool_calls']:.1f}[/dim]"
        )
        console.print(f"[dim]p95 tools per question: {tool_stats['p95_tool_calls']}[/dim]\n")

    # Show detailed breakdown if individual tool names are available
    if tool_stats["tool_breakdown"]:
        table = Table(show_header=True, header_style="bold magenta")
        table.add_column("Tool", style="dim")
        table.add_column("Usage Count", justify="right")
        table.add_column("Percentage", justify="right")

        sorted_tools = sorted(
            tool_stats["tool_breakdown"].items(), key=lambda x: x[1], reverse=True
        )
        for tool, count in sorted_tools:
            percentage = (
                (count / tool_stats["total_tool_calls"] * 100)
                if tool_stats["total_tool_calls"] > 0
                else 0
            )
            table.add_row(tool, str(count), f"{percentage:.1f}%")

        console.print(table)
    elif tool_stats["total_tool_calls"] == 0:
        console.print("[yellow]No tool usage data found.[/yellow]")
    else:
        console.print("[dim]Note: Individual tool names not available in this dataset[/dim]")

    # Parallel tool execution statistics
    console.print("\n[bold magenta]Parallel Tool Execution Statistics[/bold magenta]")
    parallel_stats = calculate_parallel_tool_stats(results)

    if parallel_stats["tool_calls_without_tracking"] > 0:
        console.print(
            f"[yellow]Note: {parallel_stats['tool_calls_without_tracking']} tool calls missing parallel tracking data. "
            f"Run a new experiment to see parallel execution statistics.[/yellow]"
        )
    elif parallel_stats["total_tool_calls"] > 0:
        table = Table(show_header=True, header_style="bold magenta")
        table.add_column("Metric", style="dim", width=30)
        table.add_column("Value", justify="right")

        table.add_row("Total Tool Calls", str(parallel_stats["total_tool_calls"]))
        table.add_row("Parallel Tool Calls", str(parallel_stats["parallel_tool_calls"]))
        table.add_row("Sequential Tool Calls", str(parallel_stats["sequential_tool_calls"]))
        table.add_row("Parallel Execution %", f"{parallel_stats['parallel_percentage']:.1f}%")

        if parallel_stats["total_batches"] > 0:
            table.add_row("")
            table.add_row("Total Parallel Batches", str(parallel_stats["total_batches"]))
            table.add_row("Avg Batch Size", f"{parallel_stats['avg_batch_size']:.1f}")

            # Show batch size distribution
            if parallel_stats["batch_size_distribution"]:
                table.add_row("")
                table.add_row("[bold]Batch Size Distribution[/bold]", "")
                for size, count in sorted(parallel_stats["batch_size_distribution"].items()):
                    table.add_row(f"  {size} tools in parallel", f"{count} batches")

        console.print(table)
    else:
        console.print("[yellow]No tool call data found.[/yellow]")

    # Turn count statistics
    console.print("\n[bold cyan]Turn Count Statistics[/bold cyan]")
    turn_stats = calculate_turn_stats(results)

    if turn_stats["total_turns"] > 0:
        console.print(f"[dim]Total turns across all questions: {turn_stats['total_turns']}[/dim]")
        console.print(f"[dim]Average turns per question: {turn_stats['avg_turns']:.1f}[/dim]")
        console.print(
            f"[dim]Median (p50) turns per question: {turn_stats['median_turns']:.1f}[/dim]"
        )
        console.print(f"[dim]p95 turns per question: {turn_stats['p95_turns']}[/dim]")
    else:
        console.print("[yellow]No turn count data found.[/yellow]")

    # Thinking time statistics
    console.print("\n[bold yellow]Thinking Time Statistics[/bold yellow]")
    thinking_stats = calculate_thinking_time_stats(results)

    if thinking_stats["total_thinking_time_ms"] > 0:
        console.print(
            f"[dim]Total thinking time: {thinking_stats['total_thinking_time_ms'] / 1000:.1f}s ({thinking_stats['total_thinking_time_ms']:.0f}ms)[/dim]"
        )
        console.print(
            f"[dim]Average thinking time per question: {thinking_stats['avg_thinking_time_ms']:.0f}ms ({thinking_stats['avg_thinking_time_ms'] / 1000:.1f}s)[/dim]"
        )
        console.print(
            f"[dim]Median (p50) thinking time: {thinking_stats['median_thinking_time_ms']:.0f}ms ({thinking_stats['median_thinking_time_ms'] / 1000:.1f}s)[/dim]"
        )
        console.print(
            f"[dim]p95 thinking time: {thinking_stats['p95_thinking_time_ms']:.0f}ms ({thinking_stats['p95_thinking_time_ms'] / 1000:.1f}s)[/dim]"
        )
    else:
        console.print("[yellow]No thinking time data found.[/yellow]")


if __name__ == "__main__":
    app()
