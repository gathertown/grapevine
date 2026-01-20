import json
import os
import subprocess
import sys

import typer
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.text import Text

# Add the project root to the path so we can import from src
project_root = os.path.join(os.path.dirname(__file__), "..", "..")
sys.path.insert(0, project_root)

from src.evals.utils import RUNS_DIR, find_latest_experiment


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
            # Extract timestamp from experiment_20250616_215150 format
            timestamp_part = dir_name.replace("experiment_", "").split("-")[
                0
            ]  # Remove model suffix if present
            return timestamp_part
        except:
            return "00000000_000000"  # fallback for malformed names

    return sorted(experiment_dirs, key=extract_timestamp)


def find_experiment_index(current_experiment_dir, all_experiments):
    """Find the index of the current experiment in the chronologically sorted list."""
    current_path = os.path.abspath(current_experiment_dir)
    for i, exp_dir in enumerate(all_experiments):
        if os.path.abspath(exp_dir) == current_path:
            return i
    return -1


def load_tool_call_histories(experiment_dir: str) -> dict:
    """Loads tool call history from the tool_calls.jsonl file in the experiment directory."""
    histories = {}  # type: ignore[var-annotated]
    tool_calls_file = os.path.join(experiment_dir, "tool_calls.jsonl")

    if not os.path.exists(tool_calls_file):
        return histories

    with open(tool_calls_file) as f:
        for line in f:
            try:
                data = json.loads(line)
                question_id = data.get("question_id")
                if question_id is not None:
                    histories[question_id] = {
                        "tool_call_history": data.get("tool_calls", []),
                        "final_answer": data.get("final_answer", "N/A"),
                    }
            except json.JSONDecodeError:
                continue
    return histories


def get_llm_grade_versions(run_data: dict) -> list[str]:
    """Get all LLM grader versions found in the run data."""
    llm_grades = run_data.get("llm_grades", {})
    versions = list(llm_grades.keys())

    # Include legacy scores if they exist (either standalone or alongside versioned grades)
    has_legacy_scores = run_data.get("score", -1) != -1
    has_versioned_scores = bool(llm_grades)

    # If we have legacy scores but they're not already covered by versioned grades, add legacy
    if has_legacy_scores and not has_versioned_scores:
        versions = ["legacy"]
    elif has_legacy_scores and has_versioned_scores:
        # For mixed experiments, always show both legacy and versioned grades
        versions.append("legacy")

    return sorted(versions)


def get_llm_grade_for_version(run_data: dict, version: str) -> int:
    """Get the LLM grade for a specific version, falling back to legacy 'score' field."""
    llm_grades = run_data.get("llm_grades", {})
    if version in llm_grades:
        return llm_grades[version].get("score", -1)
    # Fall back to legacy score field for backwards compatibility
    if version == "legacy" and "score" in run_data:
        return run_data.get("score", -1)
    return -1


def extract_readable_timestamp(experiment_name: str) -> str:
    """Extract human-readable timestamp from experiment directory name."""
    if not experiment_name or not experiment_name.startswith("experiment_"):
        return ""

    try:
        # Extract timestamp part from experiment_20250719_204709-o3 format
        timestamp_part = experiment_name.replace("experiment_", "").split("-")[0]

        # Parse YYYYMMDD_HHMMSS format
        if len(timestamp_part) >= 15 and "_" in timestamp_part:
            date_part, time_part = timestamp_part.split("_", 1)

            # Extract date components
            year = date_part[:4]
            month = date_part[4:6]
            day = date_part[6:8]

            # Extract time components
            hour = time_part[:2]
            minute = time_part[2:4]
            second = time_part[4:6]

            return f"{year}-{month}-{day} {hour}:{minute}:{second}"
    except:
        pass

    return ""


def display_run(
    console: Console,
    run_data: dict,
    run_index: int,
    total_runs: int,
    experiment_name: str | None = None,
):
    """Displays a formatted trace for a single agent run."""

    question_id = run_data.get("id")
    query = run_data.get("question", "No query found")
    tool_call_history = run_data.get("tool_call_history", [])
    tool_calls = [tc for tc in tool_call_history if "explanation" not in tc]
    final_answer = run_data.get(
        "final_answer", run_data.get("actual_answer", "No final answer recorded.")
    )
    trace_url = run_data.get("trace_url")

    # Count tool calls (they should be direct tool calls in the new format)
    tool_call_count = len(tool_calls) if tool_calls else run_data.get("tool_call_count", 0)

    # Extract readable timestamp
    readable_timestamp = extract_readable_timestamp(experiment_name) if experiment_name else ""

    title_parts = [
        f"[bold]Question {run_index}/{total_runs}[/bold]",
        f"ID: {question_id}",
        f"Tool Calls: {tool_call_count}",
    ]

    if experiment_name:
        title_parts.insert(0, f"[dim]{experiment_name}[/dim]")

    if "tool_permutation" in run_data:
        tool_perm = ", ".join(run_data["tool_permutation"])
        title_parts.append(f"Tools: [cyan]{tool_perm}[/cyan]")

    console.rule("  |  ".join(title_parts), style="white")

    console.print(
        Panel(
            query,
            title="[bold green]User Query[/bold green]",
            title_align="left",
            border_style="green",
        )
    )

    if not tool_calls:
        console.print(
            Panel(
                "No tool calls were made in this run.",
                title="[bold yellow]Execution Trace[/bold yellow]",
                border_style="yellow",
            )
        )
    else:
        tool_call_counter = 0
        for tool_call_history_item in tool_call_history:
            # If this is an explanation, show it and skip the rest of the loop
            if "explanation" in tool_call_history_item:
                console.print(
                    Panel(
                        Text(tool_call_history_item["explanation"]),
                        title="[bold blue]🤔 Explanation[/bold blue]",
                        title_align="left",
                        border_style="blue",
                    )
                )
                continue

            tool_call_counter += 1

            # Handle the new format where tool_calls are direct tool call data
            tool_name = tool_call_history_item.get("tool_name", "Unknown Tool")
            tool_params = tool_call_history_item.get("tool_parameters", {})
            result_summary = tool_call_history_item.get("result_summary", "No result summary.")
            result_data = tool_call_history_item.get("result", {})
            parallel_index = tool_call_history_item.get("parallel_index", 0)
            total_parallel = tool_call_history_item.get("total_parallel", 1)

            # Create rule title with parallel indicator if applicable
            if total_parallel > 1:
                rule_title = f"[bold]Tool Call {tool_call_counter} [cyan]⚡ Parallel ({parallel_index + 1} of {total_parallel})[/cyan]"
            else:
                rule_title = f"[bold]Tool Call {tool_call_counter}"

            console.rule(rule_title, style="grey70")

            params_json = json.dumps(tool_params, indent=2)

            console.print(
                Panel(
                    Syntax(params_json, "json", theme="monokai", line_numbers=False),
                    title=f"[bold]Tool Call: [magenta]{tool_name}[/magenta]",
                    title_align="left",
                    border_style="magenta",
                )
            )

            # Show the detailed tool result if available, otherwise fall back to summary
            if result_data and result_data != {}:
                # Create a truncated version of the result
                truncated_result = {}
                was_truncated = False

                # Handle different types of tool responses
                if "results" in result_data and isinstance(result_data["results"], list):
                    # For search tools, show count and first few results (truncated)
                    results = result_data["results"]
                    truncated_result["count"] = result_data.get("count", len(results))
                    truncated_result["results_shown"] = min(10, len(results))  # Show max 10 results

                    if len(results) > 10:
                        was_truncated = True

                    truncated_results = []
                    for _i, result in enumerate(results[:10]):  # Only first 10 results
                        truncated_res = {}
                        if "id" in result:
                            truncated_res["id"] = result["id"]
                        if "score" in result:
                            truncated_res["score"] = result["score"]
                        if "content" in result:
                            # Truncate content to first 200 characters
                            content = result["content"]
                            if len(content) > 200:
                                truncated_res["content"] = content[:200] + "..."
                                was_truncated = True
                            else:
                                truncated_res["content"] = content
                        if "highlights" in result:
                            truncated_res["highlights"] = result["highlights"]
                        truncated_results.append(truncated_res)

                    truncated_result["results"] = truncated_results
                    if len(results) > 10:
                        truncated_result["note"] = f"... and {len(results) - 10} more results"
                else:
                    # For other tools, just truncate the JSON to reasonable size
                    result_str = json.dumps(result_data, indent=2)
                    if len(result_str) > 1000:
                        truncated_result = {
                            "note": "Large response truncated",
                            "preview": result_str[:500] + "...",
                        }
                        was_truncated = True
                    else:
                        truncated_result = result_data

                # Determine the appropriate title
                if was_truncated:
                    title = "[bold]Tool Result (Truncated)[/bold]"
                else:
                    title = "[bold]Tool Result[/bold]"

                result_json = json.dumps(truncated_result, indent=2)
                console.print(
                    Panel(
                        Syntax(
                            result_json, "json", theme="monokai", line_numbers=False, word_wrap=True
                        ),
                        title=title,
                        title_align="left",
                        border_style="green",
                    )
                )
            else:
                console.print(
                    Panel(
                        Text(result_summary),
                        title="[bold]Tool Result[/bold]",
                        title_align="left",
                        border_style="green" if "✅" in result_summary else "red",
                    )
                )

    console.print(
        Panel(
            Text(final_answer),
            title="[bold green]📝 Final Agent Answer[/bold green]",
            title_align="left",
            border_style="green",
        )
    )

    # Display expected answer if available
    expected_answer = run_data.get("expected_answer", run_data.get("answer"))
    if expected_answer:
        console.print(
            Panel(
                Text(expected_answer),
                title="[bold cyan]📋 Expected Answer[/bold cyan]",
                title_align="left",
                border_style="cyan",
            )
        )

    # Display Langfuse trace URL if available
    if trace_url:
        console.print(
            f"[bold cyan]🔍 Langfuse Trace:[/bold cyan] [link={trace_url}]{trace_url}[/link]"
        )

    # Display question ID one more time before grades
    if readable_timestamp:
        console.print(
            f"[bold white]📝 Question ID: {question_id} [dim]({readable_timestamp})[/dim][/bold white]"
        )
    else:
        console.print(f"[bold white]📝 Question ID: {question_id}[/bold white]")

    # Display LLM grades for all versions
    llm_versions = get_llm_grade_versions(run_data)

    for version in llm_versions:
        score = get_llm_grade_for_version(run_data, version)
        grade_reasoning = ""

        # Try to get grade reasoning from the versioned data
        llm_grades = run_data.get("llm_grades", {})
        if version in llm_grades:
            grade_reasoning = llm_grades[version].get("grade_reasoning", "")

        # Fall back to legacy grade_reasoning field
        if not grade_reasoning and version == "legacy":
            grade_reasoning = run_data.get("grade_reasoning", "")

        grade_color = "red"
        version_label = "LLM Grade (v1)" if version == "legacy" else f"LLM Grade ({version})"

        if score is None or score == -1:
            grade_title = f"{version_label}: N/A"
            grade_color = "yellow"
        elif score >= 4:
            grade_title = f"✅ {version_label}: {score}/5"
            grade_color = "green"
        elif score >= 3:
            grade_title = f"⚠️ {version_label}: {score}/5"
            grade_color = "yellow"
        else:
            grade_title = f"❌ {version_label}: {score}/5"

        if grade_reasoning:
            console.print(
                Panel(
                    Text(grade_reasoning),
                    title=f"[bold {grade_color}]{grade_title}[/bold {grade_color}]",
                    title_align="left",
                    border_style=grade_color,
                )
            )
        else:
            console.print(f"[bold {grade_color}]{grade_title}[/bold {grade_color}]")

    # Display human grade if available
    human_grade_data = run_data.get("human_grade")
    if human_grade_data is not None:
        # Handle both old format (just number) and new format (dict with grade and grader)
        if isinstance(human_grade_data, dict):
            human_grade = human_grade_data.get("grade")
            grader = human_grade_data.get("grader", "Unknown")
            notes = human_grade_data.get("notes")
        else:
            human_grade = human_grade_data
            grader = "Unknown"
            notes = None

        if human_grade is not None:
            human_grade_color = (
                "green" if human_grade >= 4 else "yellow" if human_grade >= 3 else "red"
            )
            console.print(
                f"[bold {human_grade_color}]👤 Human Grade: {human_grade}/5[/bold {human_grade_color}] [dim]by {grader}[/dim]"
            )

            # Display notes if available
            if notes:
                console.print(
                    Panel(
                        Text(notes),
                        title="[bold]📝 Human Notes[/bold]",
                        title_align="left",
                        border_style=human_grade_color,
                    )
                )

    # Display error summary for this question
    question_errors = run_data.get("errors", [])
    if question_errors:
        console.print()

        # Count error types for this question
        error_types = {}  # type: ignore[var-annotated]
        error_tools = set()

        for error in question_errors:
            error_type = error.get("error_type", "unknown")
            error_types[error_type] = error_types.get(error_type, 0) + 1

            tool_name = error.get("context", {}).get("tool_name")
            if tool_name:
                error_tools.add(tool_name)

        # Create error summary text
        error_summary_lines = [f"🚨 {len(question_errors)} error(s) occurred during this question:"]

        # Add error type breakdown
        if error_types:
            error_summary_lines.append("")
            error_summary_lines.append("Error Types:")
            for error_type, count in sorted(error_types.items(), key=lambda x: x[1], reverse=True):
                error_summary_lines.append(f"  • {error_type}: {count}")

        # Add affected tools
        if error_tools:
            error_summary_lines.append("")
            error_summary_lines.append("Affected Tools:")
            for tool_name in sorted(error_tools):
                error_summary_lines.append(f"  • {tool_name}")

        error_summary_text = "\n".join(error_summary_lines)

        console.print(
            Panel(
                Text(error_summary_text),
                title="[bold red]⚠️  Error Summary[/bold red]",
                title_align="left",
                border_style="red",
            )
        )


def get_git_user_info():
    """Get git user name and email."""
    try:
        name = subprocess.check_output(["git", "config", "user.name"], text=True).strip()
        email = subprocess.check_output(["git", "config", "user.email"], text=True).strip()
        return f"{name} <{email}>"
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "Unknown User"


def save_results(results_file_path: str, all_runs: list):
    """Save the updated results back to the file."""
    try:
        with open(results_file_path, "w") as f:
            for run in all_runs:
                f.write(json.dumps(run) + "\n")
        return True
    except Exception as e:
        print(f"Error saving results: {e}")
        return False


def load_experiment_data(run_path: str, console: Console):
    """Load experiment data from a given path. Returns (all_runs, experiment_dir, results_file_path)."""
    if not os.path.exists(run_path):
        console.print(f"[bold red]Error:[/bold red] Run path not found at '{run_path}'.")
        return None, None, None

    all_runs = []

    # Determine if it's a directory or file
    results_file_path = None
    if os.path.isdir(run_path):
        experiment_dir = run_path
        results_file = os.path.join(experiment_dir, "results.jsonl")
        results_file_path = results_file

        if not os.path.exists(results_file):
            console.print(
                f"[bold red]Error:[/bold red] No results.jsonl found in directory '{run_path}'."
            )
            return None, None, None

        # Load results from the single results.jsonl file
        try:
            with open(results_file) as f:
                all_runs = [json.loads(line) for line in f if line.strip()]
        except json.JSONDecodeError:
            console.print(
                f"[bold red]Error:[/bold red] Invalid JSON in results file: {results_file}"
            )
            return None, None, None

    elif os.path.isfile(run_path):
        # Single results file
        experiment_dir = os.path.dirname(run_path)
        results_file_path = run_path
        try:
            with open(run_path) as f:
                all_runs = [json.loads(line) for line in f if line.strip()]
        except json.JSONDecodeError:
            console.print(f"[bold red]Error:[/bold red] Invalid JSON in run file: {run_path}")
            return None, None, None
    else:
        console.print(
            f"[bold red]Error:[/bold red] Path '{run_path}' is not a valid file or directory."
        )
        return None, None, None

    if not all_runs:
        console.print(
            "[bold yellow]Warning:[/bold yellow] No valid runs found in the specified path."
        )
        return None, None, None

    # Load tool call histories and merge with results
    tool_histories = load_tool_call_histories(experiment_dir)

    merged_runs = []
    for grade_data in all_runs:
        # If tool history is not in the grade data, load it from the tool_calls.jsonl file
        if "tool_call_history" not in grade_data:
            current_question_id = grade_data.get("id")
            if current_question_id in tool_histories:
                history_data = tool_histories[current_question_id]
                grade_data["tool_call_history"] = history_data.get("tool_call_history", [])
                # Use the final_answer from tool_calls.jsonl if actual_answer is not present
                if not grade_data.get("actual_answer") and history_data.get("final_answer"):
                    grade_data["final_answer"] = history_data["final_answer"]

        merged_runs.append(grade_data)

    all_runs = merged_runs

    # Sort by question ID for consistent order (same as stats.py)
    all_runs = sorted(all_runs, key=lambda r: r.get("id", 0))

    return all_runs, experiment_dir, results_file_path


def main(
    run_path: str | None = typer.Argument(
        None,
        help="Experiment name or path to experiment directory/results file. If not provided, uses the latest experiment.",
    ),
    question_id: int | None = typer.Option(
        None, "--question-id", "-q", help="Jump to a specific question ID"
    ),
):
    """
    Renders a step-by-step review of an agent evaluation run from an experiment directory or results.jsonl file.
    """
    console = Console()

    # Get all experiments for navigation
    all_experiments = find_all_experiments_chronologically()
    current_experiment_index = -1

    # If no path provided, find the latest experiment
    if run_path is None:
        run_path = find_latest_experiment(RUNS_DIR)
        if run_path is None:
            console.print(
                f"[bold red]Error:[/bold red] No experiment directories found in '{RUNS_DIR}' folder."
            )
            console.print("Run an experiment first or specify a path explicitly.")
            raise typer.Exit(1)
        console.print(f"[dim]No path provided, using latest experiment: {run_path}[/dim]\n")
    else:
        # If it's just an experiment name (not a path), prepend RUNS_DIR
        if "/" not in run_path and "\\" not in run_path:
            # It's just a name, construct the full path
            run_path = os.path.join(RUNS_DIR, run_path)

    # Find current experiment index
    if all_experiments:
        current_experiment_index = find_experiment_index(run_path, all_experiments)

    # Load initial experiment data
    all_runs, experiment_dir, results_file_path = load_experiment_data(run_path, console)
    if all_runs is None:
        raise typer.Exit(1)

    # Find the starting index based on question_id if provided
    current_index = 0
    if question_id is not None:
        for i, run in enumerate(all_runs):
            if run.get("id") == question_id:
                current_index = i
                console.print(
                    f"[dim]Jumping to question ID {question_id} (position {i + 1}/{len(all_runs)})[/dim]\n"
                )
                break
        else:
            console.print(
                f"[bold yellow]Warning:[/bold yellow] Question ID {question_id} not found. Starting from the beginning."
            )
            console.print(
                f"Available question IDs: {[run.get('id') for run in all_runs[:10]]}"
                + ("..." if len(all_runs) > 10 else "")
            )
            console.input("Press Enter to continue...")
            console.print()
    while True:
        sys.stdout.write("\033c")
        sys.stdout.flush()
        run_data = all_runs[current_index]

        # Get current experiment name for display
        current_experiment_name = os.path.basename(run_path) if run_path else None
        display_run(console, run_data, current_index + 1, len(all_runs), current_experiment_name)

        prompt_parts = []
        default_action = ""

        if current_index < len(all_runs) - 1:
            prompt_parts.append("[bold](n)[/bold]ext")
            default_action = "n"
        if current_index > 0:
            prompt_parts.append("[bold](p)[/bold]revious")

        # Add run navigation options
        if all_experiments and current_experiment_index >= 0:
            if current_experiment_index < len(all_experiments) - 1:
                prompt_parts.append("[bold](nr)[/bold] next run")
            if current_experiment_index > 0:
                prompt_parts.append("[bold](pr)[/bold] prev run")

        prompt_parts.append("[bold](g)[/bold]rade")
        prompt_parts.append("[bold](q)[/bold]uit")

        prompt = " | ".join(prompt_parts)
        action = (console.input(f"\n{prompt}: ") or default_action).lower()

        if action == "q":
            break
        elif action == "p":
            if current_index > 0:
                current_index -= 1
        elif action == "n":
            if current_index < len(all_runs) - 1:
                current_index += 1
        elif action == "nr":
            # Next run - move to next experiment chronologically
            if (
                all_experiments
                and current_experiment_index >= 0
                and current_experiment_index < len(all_experiments) - 1
            ):
                current_experiment_index += 1
                new_run_path = all_experiments[current_experiment_index]
                console.print(
                    f"[cyan]Loading next experiment: {os.path.basename(new_run_path)}[/cyan]"
                )

                # Load the new experiment data
                all_runs, experiment_dir, results_file_path = load_experiment_data(
                    new_run_path, console
                )
                if all_runs is not None:
                    run_path = new_run_path
                    current_index = 0  # Start at the beginning of the new run
                else:
                    # Revert if loading failed
                    current_experiment_index -= 1
                    console.print(
                        "[red]Failed to load next experiment, staying on current one[/red]"
                    )
                    console.input("Press Enter to continue...")
        elif action == "pr":
            # Previous run - move to previous experiment chronologically
            if all_experiments and current_experiment_index >= 0 and current_experiment_index > 0:
                current_experiment_index -= 1
                new_run_path = all_experiments[current_experiment_index]
                console.print(
                    f"[cyan]Loading previous experiment: {os.path.basename(new_run_path)}[/cyan]"
                )

                # Load the new experiment data
                all_runs, experiment_dir, results_file_path = load_experiment_data(
                    new_run_path, console
                )
                if all_runs is not None:
                    run_path = new_run_path
                    current_index = 0  # Start at the beginning of the new run
                else:
                    # Revert if loading failed
                    current_experiment_index += 1
                    console.print(
                        "[red]Failed to load previous experiment, staying on current one[/red]"
                    )
                    console.input("Press Enter to continue...")
        elif action == "g":
            # Prompt for human grade
            current_human_grade_data = all_runs[current_index].get("human_grade")
            if current_human_grade_data is not None:
                # Handle both old format (just number) and new format (dict with grade and grader)
                if isinstance(current_human_grade_data, dict):
                    current_grade = current_human_grade_data.get("grade")
                    current_grader = current_human_grade_data.get("grader", "Unknown")
                    current_notes = current_human_grade_data.get("notes")
                    console.print(
                        f"[yellow]Current human grade: {current_grade}/5 by {current_grader}[/yellow]"
                    )
                    if current_notes:
                        console.print(f"[yellow]Current notes: {current_notes}[/yellow]")
                else:
                    console.print(
                        f"[yellow]Current human grade: {current_human_grade_data}/5[/yellow]"
                    )

            try:
                human_grade_input = console.input(
                    "Enter human grade (1-5) or press Enter to skip: "
                ).strip()
                if human_grade_input:
                    human_grade = int(human_grade_input)
                    if 1 <= human_grade <= 5:
                        grader_info = get_git_user_info()

                        # Prompt for optional notes
                        notes_input = console.input(
                            "Enter notes (optional) or press Enter to skip: "
                        ).strip()

                        # Create the human grade data
                        human_grade_data = {"grade": human_grade, "grader": grader_info}

                        # Add notes if provided
                        if notes_input:
                            human_grade_data["notes"] = notes_input

                        all_runs[current_index]["human_grade"] = human_grade_data

                        if results_file_path and save_results(results_file_path, all_runs):
                            console.print(
                                f"[green]✅ Human grade {human_grade}/5 saved by {grader_info}![/green]"
                            )
                            if notes_input:
                                console.print(f"[green]📝 Notes saved: {notes_input}[/green]")
                        else:
                            console.print(
                                f"[yellow]⚠️ Human grade {human_grade}/5 set but not saved to file.[/yellow]"
                            )
                    else:
                        console.print("[red]❌ Grade must be between 1 and 5[/red]")
                        console.input("Press Enter to continue...")
            except ValueError:
                console.print("[red]❌ Invalid grade. Please enter a number between 1 and 5.[/red]")
                console.input("Press Enter to continue...")

    sys.stdout.write("\033c")
    sys.stdout.flush()
    console.rule(f"[bold]End of Review: {len(all_runs)} questions processed[/bold]", style="cyan")


if __name__ == "__main__":
    typer.run(main)
