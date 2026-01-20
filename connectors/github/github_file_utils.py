"""Utility functions for GitHub file processing."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from connectors.github.github_file_artifacts import GitHubFileContributor

logger = logging.getLogger(__name__)


def format_file_size(size_bytes: int) -> str:
    """Convert bytes to human-readable format.

    Returns:
        Human-readable file size string (e.g., "1.5 MB", "256 KB")
    """
    if size_bytes == 0:
        return "0 bytes"

    units = ["bytes", "KB", "MB", "GB", "TB"]
    size = float(size_bytes)
    unit_index = 0

    while size >= 1000 and unit_index < len(units) - 1:
        size /= 1000
        unit_index += 1

    if unit_index == 0:
        return f"{int(size)} {units[unit_index]}"
    else:
        return f"{size:.1f} {units[unit_index]}"


def generate_binary_file_metadata_content(
    file_path: str,
    organization: str,
    repository: str,
    file_size_bytes: int | None = None,
    contributors: list[GitHubFileContributor] | None = None,
    last_modified: str | None = None,
) -> str:
    """Generate metadata content for binary files.

    Args:
        file_path: Relative path to the file in the repository
        organization: GitHub organization/owner name
        repository: Repository name
        file_size_bytes: File size in bytes (optional)
        contributors: List of file contributors (optional)
        last_modified: Last modified timestamp (optional)

    Returns:
        Formatted metadata string for binary files
    """
    file_name = Path(file_path).name

    lines = [
        f"File: {file_name}",
        f"Path: {file_path}",
        f"Repository: {organization}/{repository}",
    ]

    if file_size_bytes is not None:
        lines.append(f"Size: {format_file_size(file_size_bytes)}")

    if last_modified:
        lines.append(f"Modified: {last_modified}")

    if contributors:
        contributor_names = [c.name for c in contributors]
        if contributor_names:
            lines.append(f"Contributors: {', '.join(contributor_names[:5])}")
            if len(contributor_names) > 5:
                lines.append(f"(and {len(contributor_names) - 5} more)")

    lines.append("")
    lines.append("Note: This is a non-text file. Content preview is not available.")

    return "\n".join(lines)
