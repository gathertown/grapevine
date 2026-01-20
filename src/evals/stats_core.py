"""Core statistics calculation functions for evaluation results.

This module provides pure calculation functions that can be reused across
different scripts (run_and_grade.py, stats.py, etc.) without duplication.
"""

import statistics
from typing import Any


def calculate_grade_stats(results: list[dict[str, Any]], version: str = "v2") -> dict[str, Any]:
    """Calculate grade statistics for a specific grader version."""
    scores = []
    for result in results:
        llm_grades = result.get("llm_grades", {})
        if version in llm_grades:
            score = llm_grades[version].get("score", -1)
            if score >= 1:  # Valid score
                scores.append(score)

    if not scores:
        return {
            "count": 0,
            "average": 0,
            "min": 0,
            "max": 0,
            "median": 0,
            "distribution": dict.fromkeys(range(1, 6), 0),
        }

    return {
        "count": len(scores),
        "average": statistics.mean(scores),
        "min": min(scores),
        "max": max(scores),
        "median": statistics.median(scores),
        "distribution": {i: scores.count(i) for i in range(1, 6)},
    }


def calculate_timing_stats(results: list[dict[str, Any]]) -> dict[str, Any]:
    """Calculate timing statistics."""
    times = [
        r.get("processing_time_seconds", 0) for r in results if r.get("processing_time_seconds")
    ]

    if not times:
        return {
            "count": 0,
            "average": 0,
            "min": 0,
            "max": 0,
            "median": 0,
            "total": 0,
        }

    return {
        "count": len(results),
        "average": statistics.mean(times),
        "min": min(times),
        "max": max(times),
        "median": statistics.median(times),
        "total": sum(times),
    }


def calculate_tool_usage_stats(results: list[dict[str, Any]]) -> dict[str, Any]:
    """Calculate tool usage statistics."""
    tool_counts: dict[str, int] = {}
    total_tool_calls = 0
    tool_calls_per_question = []

    for result in results:
        tool_count = result.get("tool_call_count", 0)
        total_tool_calls += tool_count
        tool_calls_per_question.append(tool_count)

        # Count individual tools from history
        for tool_call in result.get("tool_call_history", []):
            tool_name = tool_call.get("tool_name", "unknown")
            if tool_name and tool_name != "unknown":
                tool_counts[tool_name] = tool_counts.get(tool_name, 0) + 1

    if not tool_calls_per_question:
        return {
            "total_tool_calls": 0,
            "avg_tool_calls": 0,
            "median_tool_calls": 0,
            "p95_tool_calls": 0,
            "tool_breakdown": {},
        }

    # Calculate percentiles
    sorted_counts = sorted(tool_calls_per_question)
    p95_index = int(len(sorted_counts) * 0.95)
    p95_tools = sorted_counts[p95_index] if p95_index < len(sorted_counts) else sorted_counts[-1]

    return {
        "total_tool_calls": total_tool_calls,
        "avg_tool_calls": total_tool_calls / len(results) if results else 0,
        "median_tool_calls": statistics.median(tool_calls_per_question),
        "p95_tool_calls": p95_tools,
        "tool_breakdown": tool_counts,
    }


def calculate_parallel_tool_stats(results: list[dict[str, Any]]) -> dict[str, Any]:
    """Calculate statistics about parallel vs sequential tool execution."""
    total_tool_calls = 0
    parallel_tool_calls = 0
    batch_sizes: list[int] = []
    batch_size_distribution: dict[int, int] = {}
    tool_calls_with_tracking = 0
    tool_calls_without_tracking = 0

    for result in results:
        tool_call_history = result.get("tool_call_history", [])
        for tool_call in tool_call_history:
            # Only count actual tool calls (skip explanation entries)
            if "tool_name" in tool_call:
                if "total_parallel" in tool_call:
                    tool_calls_with_tracking += 1
                    total_tool_calls += 1
                    total_parallel = tool_call["total_parallel"]

                    if total_parallel > 1:
                        parallel_tool_calls += 1
                        # Only count each batch once (when parallel_index == 0)
                        if tool_call.get("parallel_index", 0) == 0:
                            batch_sizes.append(total_parallel)
                            batch_size_distribution[total_parallel] = (
                                batch_size_distribution.get(total_parallel, 0) + 1
                            )
                else:
                    tool_calls_without_tracking += 1

    parallel_percentage = (
        (parallel_tool_calls / total_tool_calls * 100) if total_tool_calls > 0 else 0
    )
    avg_batch_size = statistics.mean(batch_sizes) if batch_sizes else 0

    return {
        "total_tool_calls": total_tool_calls,
        "parallel_tool_calls": parallel_tool_calls,
        "sequential_tool_calls": total_tool_calls - parallel_tool_calls,
        "parallel_percentage": parallel_percentage,
        "avg_batch_size": avg_batch_size,
        "batch_size_distribution": batch_size_distribution,
        "total_batches": len(batch_sizes),
        "tool_calls_with_tracking": tool_calls_with_tracking,
        "tool_calls_without_tracking": tool_calls_without_tracking,
    }


def calculate_turn_stats(results: list[dict[str, Any]]) -> dict[str, Any]:
    """Calculate turn count statistics."""
    turns_per_question = [result.get("turn_count", 0) for result in results]
    total_turns = sum(turns_per_question)

    if total_turns == 0 or not turns_per_question:
        return {
            "total_turns": 0,
            "avg_turns": 0,
            "median_turns": 0,
            "p95_turns": 0,
        }

    # Calculate p95 (95th percentile) for turns
    sorted_turns = sorted(turns_per_question)
    p95_index = int(len(sorted_turns) * 0.95)
    p95_turns = sorted_turns[p95_index] if p95_index < len(sorted_turns) else sorted_turns[-1]

    return {
        "total_turns": total_turns,
        "avg_turns": total_turns / len(results) if results else 0,
        "median_turns": statistics.median(turns_per_question),
        "p95_turns": p95_turns,
    }


def calculate_thinking_time_stats(results: list[dict[str, Any]]) -> dict[str, Any]:
    """Calculate thinking time statistics."""
    thinking_times = [result.get("thinking_time_ms", 0) for result in results]
    total_thinking_time = sum(thinking_times)

    if total_thinking_time == 0 or not thinking_times:
        return {
            "total_thinking_time_ms": 0,
            "avg_thinking_time_ms": 0,
            "median_thinking_time_ms": 0,
            "p95_thinking_time_ms": 0,
        }

    # Calculate p95 (95th percentile) for thinking time
    sorted_thinking = sorted(thinking_times)
    p95_index = int(len(sorted_thinking) * 0.95)
    p95_thinking = (
        sorted_thinking[p95_index] if p95_index < len(sorted_thinking) else sorted_thinking[-1]
    )

    return {
        "total_thinking_time_ms": total_thinking_time,
        "avg_thinking_time_ms": total_thinking_time / len(results) if results else 0,
        "median_thinking_time_ms": statistics.median(thinking_times),
        "p95_thinking_time_ms": p95_thinking,
    }


def calculate_error_stats(results: list[dict[str, Any]]) -> dict[str, Any]:
    """Calculate error statistics."""
    total_questions = len(results)
    total_errors = 0
    questions_with_errors = 0
    all_error_types: dict[str, int] = {}
    question_ids_with_errors: set[str | int] = set()

    for result in results:
        result_errors = result.get("errors", [])
        if result_errors:
            questions_with_errors += 1
            total_errors += len(result_errors)
            question_id = result.get("id")
            if question_id is not None:
                question_ids_with_errors.add(question_id)

            for error in result_errors:
                # Count by error type
                error_type = error.get("error_type", "unknown")
                all_error_types[error_type] = all_error_types.get(error_type, 0) + 1

    return {
        "total_questions": total_questions,
        "total_errors": total_errors,
        "questions_with_errors": questions_with_errors,
        "questions_with_errors_percentage": (
            (questions_with_errors / total_questions * 100) if total_questions > 0 else 0
        ),
        "error_types": all_error_types,
        "question_ids_with_errors": sorted(question_ids_with_errors),
    }


def calculate_human_grade_stats(results: list[dict[str, Any]]) -> dict[str, Any]:
    """Calculate grade statistics for human grader results."""
    scores = []
    graders: set[str] = set()

    for result in results:
        human_grade = result.get("human_grade")
        if human_grade:
            # Handle both old format (just a number) and new format (dict with grade/grader/notes)
            if isinstance(human_grade, dict):
                grade = human_grade.get("grade")
                grader = human_grade.get("grader")
                if grade and grade >= 1:
                    scores.append(grade)
                if grader:
                    graders.add(grader)
            elif isinstance(human_grade, (int, float)) and human_grade >= 1:
                scores.append(int(human_grade))

    if not scores:
        return {
            "count": 0,
            "average": 0,
            "min": 0,
            "max": 0,
            "median": 0,
            "distribution": dict.fromkeys(range(1, 6), 0),
            "graders": [],
        }

    return {
        "count": len(scores),
        "average": statistics.mean(scores),
        "min": min(scores),
        "max": max(scores),
        "median": statistics.median(scores),
        "distribution": {i: scores.count(i) for i in range(1, 6)},
        "graders": sorted(graders),
    }


def calculate_grade_comparison_stats(
    results: list[dict[str, Any]], llm_version: str = "v2"
) -> dict[str, Any]:
    """Compare human grades vs LLM grades when both exist."""
    human_scores = []
    llm_scores = []
    differences = []
    question_ids_compared: list[str | int] = []

    for result in results:
        # Get human grade
        human_grade = result.get("human_grade")
        human_score = None
        if human_grade:
            if isinstance(human_grade, dict):
                human_score = human_grade.get("grade")
            elif isinstance(human_grade, (int, float)):
                human_score = int(human_grade)

        # Get LLM grade
        llm_grades = result.get("llm_grades", {})
        llm_score = None
        if llm_version in llm_grades:
            llm_score = llm_grades[llm_version].get("score", -1)
            if llm_score < 1:
                llm_score = None

        # Only compare if both exist
        if human_score and llm_score and human_score >= 1 and llm_score >= 1:
            human_scores.append(human_score)
            llm_scores.append(llm_score)
            diff = abs(human_score - llm_score)
            differences.append(diff)
            question_id = result.get("id")
            if question_id is not None:
                question_ids_compared.append(question_id)

    if not human_scores or not llm_scores:
        return {
            "count": 0,
            "agreement_exact": 0,
            "agreement_within_1": 0,
            "mean_absolute_difference": 0,
            "human_avg": 0,
            "llm_avg": 0,
            "question_ids_compared": [],
        }

    # Calculate agreement rates
    exact_matches = sum(1 for h, l in zip(human_scores, llm_scores, strict=False) if h == l)
    within_1_matches = sum(1 for diff in differences if diff <= 1)

    return {
        "count": len(human_scores),
        "agreement_exact": (exact_matches / len(human_scores) * 100),
        "agreement_within_1": (within_1_matches / len(human_scores) * 100),
        "mean_absolute_difference": statistics.mean(differences),
        "human_avg": statistics.mean(human_scores),
        "llm_avg": statistics.mean(llm_scores),
        "question_ids_compared": question_ids_compared,
    }
