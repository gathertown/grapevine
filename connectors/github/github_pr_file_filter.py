"""
Smart filtering logic for GitHub PR file changes.

Filters out generated files, lock files, and other files that shouldn't be indexed.
Uses the same plaintext detection as the file connector for consistency.
"""

import logging
from pathlib import Path
from typing import Any

from src.utils.filetype import is_plaintext_file

logger = logging.getLogger(__name__)

# Maximum limits for PR file indexing
MAX_FILES_PER_PR = 100
MAX_LINES_PER_FILE = 2000
MAX_TOTAL_LINES_PER_PR = 50000

# Directories to exclude (same as file connector)
IGNORE_DIRECTORIES = {
    ".git",
    ".github",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    ".venv",
    "venv",
    "env",
    "dist",
    "build",
    ".mypy_cache",
    ".tox",
    "htmlcov",
    ".idea",
    ".vscode",
    "out",
    "target",
    ".next",
    "vendor",
}

# PR-specific file patterns to exclude (lock files, minified files, etc.)
# These are in addition to what is_plaintext_file() already filters
PR_SPECIFIC_EXCLUSIONS = {
    # Lock files (even though some are plaintext, they're not useful for PR context)
    "package-lock.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "npm-shrinkwrap.json",
    "Gemfile.lock",
    "Cargo.lock",
    "go.sum",
    "poetry.lock",
    "Pipfile.lock",
    "composer.lock",
    # Minified files (not useful even if plaintext)
    ".min.js",
    ".min.css",
}


def should_exclude_file(filename: str) -> bool:
    """
    Check if a file should be excluded from PR indexing.

    Uses the same logic as the file connector (is_plaintext_file) plus
    PR-specific exclusions for lock files and minified files.

    Args:
        filename: Path to the file

    Returns:
        True if file should be excluded, False otherwise
    """
    path = Path(filename)

    # Check if any directory component is in ignore list
    if any(part in IGNORE_DIRECTORIES for part in path.parts):
        logger.debug(f"Excluding {filename} - matches ignored directory")
        return True

    # Check PR-specific exclusions (lock files, minified files)
    filename_lower = filename.lower()
    for exclusion in PR_SPECIFIC_EXCLUSIONS:
        if exclusion.lower() in filename_lower:
            logger.debug(f"Excluding {filename} - matches PR-specific exclusion: {exclusion}")
            return True

    # Use same plaintext detection as file connector
    # This already filters out binaries, images, etc.
    if not is_plaintext_file(filename):
        logger.debug(f"Excluding {filename} - not a plaintext file")
        return True

    return False


def truncate_diff(patch: str | None, max_lines: int = MAX_LINES_PER_FILE) -> str | None:
    """
    Truncate a diff to a maximum number of lines.

    Args:
        patch: The diff content
        max_lines: Maximum number of lines to keep

    Returns:
        Truncated diff with a message if truncated, or original if within limits
    """
    if not patch:
        return patch

    lines = patch.split("\n")
    if len(lines) <= max_lines:
        return patch

    # Keep first max_lines and add truncation message
    truncated = "\n".join(lines[:max_lines])
    truncated += f"\n\n... [Diff truncated - showing first {max_lines} of {len(lines)} lines]"
    logger.debug(f"Truncated diff from {len(lines)} to {max_lines} lines")
    return truncated


def filter_and_prepare_pr_files(
    files: list[dict[str, Any]],
    max_files: int = MAX_FILES_PER_PR,
    max_lines_per_file: int = MAX_LINES_PER_FILE,
    max_total_lines: int = MAX_TOTAL_LINES_PER_PR,
) -> list[dict[str, Any]]:
    """
    Filter and prepare PR files for indexing.

    This function:
    1. Filters out excluded files (lock files, binaries, generated code, etc.)
    2. Limits the total number of files
    3. Truncates large diffs
    4. Ensures we don't exceed total line limits

    Args:
        files: List of file change dictionaries from GitHub API
        max_files: Maximum number of files to index per PR
        max_lines_per_file: Maximum lines per file diff
        max_total_lines: Maximum total lines across all files

    Returns:
        Filtered and prepared list of file changes
    """
    if not files:
        return []

    logger.info(f"Filtering {len(files)} PR files")

    # Filter out excluded files
    filtered = []
    excluded_count = 0

    for file in files:
        filename = file.get("filename", "")
        if should_exclude_file(filename):
            excluded_count += 1
            continue

        # Skip files without patches (binary files, very large files)
        if not file.get("patch"):
            logger.debug(f"Skipping {filename} - no patch available (likely binary or too large)")
            excluded_count += 1
            continue

        filtered.append(file)

    if excluded_count > 0:
        logger.info(f"Excluded {excluded_count} files based on filtering rules")

    # Limit number of files
    if len(filtered) > max_files:
        logger.warning(
            f"PR has {len(filtered)} files after filtering, limiting to {max_files} files. "
            f"Prioritizing smaller files."
        )
        # Sort by total changes (smaller first) to prioritize more focused changes
        filtered.sort(key=lambda f: f.get("changes", 0))
        filtered = filtered[:max_files]

    # Truncate diffs and track total lines
    total_lines = 0
    prepared = []

    for file in filtered:
        patch = file.get("patch")
        if not patch:
            continue

        # Count lines in patch
        patch_lines = len(patch.split("\n"))

        # Check if adding this file would exceed total line limit
        if total_lines + patch_lines > max_total_lines:
            remaining_lines = max_total_lines - total_lines
            if remaining_lines > 50:  # Only include if we can show at least 50 lines
                file = file.copy()  # Don't modify original
                file["patch"] = truncate_diff(patch, remaining_lines)
                prepared.append(file)
                logger.warning(
                    f"Reached total line limit ({max_total_lines}), truncated last file {file['filename']}"
                )
            break

        # Truncate individual file if needed
        if patch_lines > max_lines_per_file:
            file = file.copy()  # Don't modify original
            file["patch"] = truncate_diff(patch, max_lines_per_file)
            patch_lines = max_lines_per_file

        prepared.append(file)
        total_lines += patch_lines

    logger.info(
        f"Prepared {len(prepared)} files for indexing (total ~{total_lines} lines of diffs) "
        f"from original {len(files)} files"
    )

    return prepared
