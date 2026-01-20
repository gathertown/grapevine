"""Utility for saving PR review results to files."""

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from src.pr_reviewer.models import ExistingReviewComment


def save_review_to_file(
    review_data: dict[str, Any],
    pr_number: int,
    output_dir: str = "reviews",
) -> str:
    """Save review to timestamped JSON file.

    Args:
        review_data: Review data with decision and comments
        pr_number: Pull request number
        output_dir: Directory to save reviews (default: "reviews")

    Returns:
        Path to saved file
    """
    # Create output directory if it doesn't exist
    reviews_dir = Path(output_dir)
    reviews_dir.mkdir(parents=True, exist_ok=True)

    # Generate timestamp in ISO format with hyphens
    timestamp = datetime.now().strftime("%Y-%m-%dT%H-%M-%S")

    # Create filename
    filename = f"pr-{pr_number}-{timestamp}.json"
    filepath = reviews_dir / filename

    # Write JSON with pretty formatting
    with open(filepath, "w") as f:
        json.dump(review_data, f, indent=2)

    return str(filepath)


def format_changes_for_display(changes: list[dict[str, Any]]) -> str:
    """Format Phase 1 changes for console display.

    Args:
        changes: List of change dictionaries from Phase 1

    Returns:
        Formatted string for console output
    """
    if not changes:
        return "No changes identified.\n"

    lines = []
    lines.append(f"\n📊 Identified Changes ({len(changes)}):\n")

    for i, change in enumerate(changes, 1):
        path = change.get("path", "unknown")
        line = change.get("line")
        line_range = change.get("lines")
        description = change.get("change", "")

        # Format location
        location = f"  {i}. 📄 {path}"
        if line:
            location += f":{line}"
        elif line_range:
            location += f":{line_range[0]}-{line_range[1]}"

        lines.append(location)
        lines.append(f"     {description}\n")

    return "\n".join(lines)


def format_insights_for_display(insights: list[dict[str, Any]]) -> str:
    """Format Phase 2 insights for console display.

    Args:
        insights: List of insight dictionaries from Phase 2

    Returns:
        Formatted string for console output
    """
    if not insights:
        return "No actionable insights found.\n"

    lines = []
    lines.append(f"\n🔍 Actionable Insights ({len(insights)}):\n")

    for i, insight in enumerate(insights, 1):
        path = insight.get("path", "unknown")
        line = insight.get("line")
        line_range = insight.get("lines")
        insight_text = insight.get("insight", "")
        sources = insight.get("sources", [])
        impact = insight.get("impact")
        confidence = insight.get("confidence")
        category = insight.get("category")
        source_agent = insight.get("source_agent", "unknown")

        # Format location with source agent, category, impact and confidence
        location = f"  {i}. 📄 {path}"
        if line:
            location += f":{line}"
        elif line_range:
            location += f":{line_range[0]}-{line_range[1]}"
        # Show source agent, category, impact, and confidence scores
        scores = []
        scores.append(f"agent:{source_agent}")
        if category:
            scores.append(f"category:{category}")
        if impact is not None:
            scores.append(f"impact:{impact}%")
        if confidence is not None:
            scores.append(f"conf:{confidence}%")
        if scores:
            location += f" ({', '.join(scores)})"

        lines.append(location)
        lines.append(f"     {insight_text}")

        lines.append("")
        if insight.get("impact_reason"):
            lines.append("     Impact Reason:")
            lines.append(f"     {insight.get('impact_reason')}")
        lines.append("     Confidence Reason:")
        lines.append(f"     {insight.get('confidence_reason', 'N/A')}\n")

        if sources:
            lines.append("     Sources:")
            for source in sources:
                lines.append(f"     - {source}")

        lines.append("")  # Empty line between insights

    return "\n".join(lines)


def format_review_for_display(review_data: dict[str, Any]) -> str:
    """Format review data for console display.

    Args:
        review_data: Review data with decision and comments

    Returns:
        Formatted string for console output
    """
    lines = []

    # Add decision
    decision = review_data.get("decision", "UNKNOWN")
    lines.append(f"\n📝 Review Decision: {decision}\n")

    # Add comments
    comments = review_data.get("comments", [])
    if comments:
        lines.append(f"Comments ({len(comments)}):\n")
        for comment in comments:
            path = comment.get("path", "")
            line_num = comment.get("line", "")
            line_range = comment.get("lines", "")
            body = comment.get("body", "")
            impact = comment.get("impact")
            confidence = comment.get("confidence")

            # Format location if available
            location = ""
            if path:
                location = f"  📄 {path}"
                if line_num:
                    location += f":{line_num}"
                elif line_range:
                    location += f":{line_range[0]}-{line_range[1]}"
                # Add impact and confidence scores if available
                scores = []
                if impact is not None:
                    scores.append(f"impact:{impact}%")
                if confidence is not None:
                    scores.append(f"conf:{confidence}%")
                if scores:
                    location += f" ({', '.join(scores)})"
                lines.append(location)

            # Format body with indentation
            lines.append("     Insight:")
            lines.append(f"     {body}")

            impact_reason = comment.get("impact_reason")
            if impact_reason is not None:
                lines.append("")
                lines.append("     Impact Reason:")
                lines.append(f"     {impact_reason}\n")

            confidence_reason = comment.get("confidence_reason")
            if confidence_reason is not None:
                lines.append("")
                lines.append("     Confidence Reason:")
                lines.append(f"     {confidence_reason}\n")
    else:
        lines.append("No comments.\n")

    return "\n".join(lines)


def format_existing_comment_for_prompt(
    comment: ExistingReviewComment, max_body_length: int = 1000
) -> str:
    """Format an existing review comment for display in prompts.

    Args:
        comment: Existing review comment to format
        max_body_length: Maximum length of comment body to include (default: 1000)

    Returns:
        Formatted string with location, username, and body wrapped in XML tags:
        "`path/to/file.ts:42` (by @username):\n<existing_review_comments>\ncomment body...\n</existing_review_comments>"

        The body is wrapped in XML tags to prevent markdown interpretation
        and prompt injection. XML special characters in bodies are escaped.
    """
    path = comment.get("path")
    line = comment.get("line")
    lines = comment.get("lines")
    body = comment.get("body", "")
    user = comment.get("user")
    username = user.get("login", "unknown") if user else "unknown"

    # Escape backticks in path to prevent markdown injection
    escaped_path = path.replace("`", "\\`") if path else None

    # Format location
    if escaped_path:
        if lines and isinstance(lines, list) and len(lines) >= 2:
            location = f"`{escaped_path}:{lines[0]}-{lines[-1]}`"
        elif line is not None:
            location = f"`{escaped_path}:{line}`"
        elif comment.get("position") is not None:
            location = f"`{escaped_path}:pos{comment.get('position')}`"
        else:
            location = f"`{escaped_path}`"
    else:
        location = "(general comment)"

    # Truncate body if too long
    body_preview = body[:max_body_length] + "..." if len(body) > max_body_length else body

    # Escape XML special characters in body to prevent XML injection
    escaped_body = body_preview.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    # Wrap body in XML tags to prevent markdown interpretation and prompt injection
    return f"{location} (by @{username}):\n<existing_review_comments>\n{escaped_body}\n</existing_review_comments>"
