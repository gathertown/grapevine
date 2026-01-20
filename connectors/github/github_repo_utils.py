"""Utility functions for GitHub repository operations."""

import asyncio
import time
from pathlib import Path
from typing import NamedTuple

from src.clients.github import GitHubClient
from src.utils.logging import get_logger

logger = get_logger(__name__)


class CloneResult(NamedTuple):
    """Result of cloning a repository with metadata."""

    repo_path: Path
    commit_sha: str
    branch: str | None


def parse_repo_url(repo_url: str) -> dict[str, str]:
    """Parse GitHub repository URL to extract owner and repo name."""
    # Remove trailing .git if present
    if repo_url.endswith(".git"):
        repo_url = repo_url[:-4]

    # Handle different URL formats
    if repo_url.startswith("https://github.com/"):
        parts = repo_url.replace("https://github.com/", "").split("/")
    elif repo_url.startswith("git@github.com:"):
        parts = repo_url.replace("git@github.com:", "").split("/")
    else:
        raise ValueError(f"Invalid GitHub repository URL: {repo_url}")

    if len(parts) < 2:
        raise ValueError(f"Could not parse repository URL: {repo_url}")

    return {"owner": parts[0], "name": parts[1]}


async def clone_repository(
    repo_url: str, github_client: GitHubClient, temp_dir: str
) -> CloneResult:
    """Clone a GitHub repository using a blobless partial clone.

    This performs a partial clone with --filter=blob:none, which fetches all commit
    and tree objects but defers downloading file blobs until they are needed. This
    significantly reduces clone time and disk usage for large repositories.

    IMPORTANT: The repository is cloned with --no-checkout, meaning the working
    directory will be empty after cloning. Callers MUST perform a checkout operation:
    - Use sparse checkout to check out only specific files (recommended)
    - Use full checkout (git checkout) to check out all files

    Args:
        repo_url: GitHub repository URL (https://github.com/owner/repo)
        github_client: Authenticated GitHub client for repository access
        temp_dir: Temporary directory where the repository will be cloned

    Returns:
        CloneResult with repo_path, commit_sha, and branch information
    """
    repo_info = parse_repo_url(repo_url)
    repo_path = Path(temp_dir) / repo_info["name"]

    # If it's an HTTPS URL, add authentication
    authenticated_url = repo_url
    if repo_url.startswith("https://github.com/"):
        # Use different authentication format based on token type
        if github_client.is_app_authenticated():
            # GitHub App installation token requires x-access-token format
            authenticated_url = repo_url.replace(
                "https://github.com/", f"https://x-access-token:{github_client._token}@github.com/"
            )
        else:
            # PAT token uses token as username
            authenticated_url = repo_url.replace(
                "https://github.com/", f"https://{github_client._token}@github.com/"
            )

    # Clone with no checkout and blob filtering to minimize download
    # --filter=blob:none fetches commit history without file contents
    # Files will be checked out later (either sparse or full)
    clone_cmd = [
        "git",
        "clone",
        "--no-checkout",
        "--filter=blob:none",
        authenticated_url,
        str(repo_path),
    ]

    # Log the original URL without authentication token
    logger.info(f"Cloning repository with blobless partial clone: {repo_url}")
    clone_start = time.perf_counter()

    process = await asyncio.create_subprocess_exec(
        *clone_cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    stdout, stderr = await process.communicate()

    if process.returncode != 0:
        error_msg = stderr.decode() if stderr else "Unknown error"
        raise RuntimeError(f"Failed to clone repository: {error_msg}")

    clone_duration = time.perf_counter() - clone_start

    # Log git's stderr output which contains progress info (objects received, pack size, etc)
    git_output = stderr.decode().strip() if stderr else ""

    logger.info(f"Successfully cloned repository metadata to: {repo_path} in {clone_duration:.2f}s")

    # Get commit SHA and branch information after cloning
    commit_sha = await _get_commit_sha(repo_path)
    branch = await _get_branch_name(repo_path)

    # Get diagnostic info about what was cloned to understand performance characteristics
    commit_count = await _get_commit_count(repo_path)
    ref_count = await _get_ref_count(repo_path)

    logger.info(
        f"Repository cloned - SHA: {commit_sha}, branch: {branch or 'unknown'}, "
        f"commits: {commit_count}, refs: {ref_count}"
    )

    # Log git output details if available (contains objects received, pack info, etc)
    if git_output:
        # Git output can be multi-line, so log the key stats
        logger.info(f"Git clone details: {git_output}")

    return CloneResult(repo_path=repo_path, commit_sha=commit_sha, branch=branch)


async def _get_commit_sha(repo_path: Path) -> str:
    """Get the current commit SHA from a git repository."""
    try:
        cmd = ["git", "-C", str(repo_path), "rev-parse", "HEAD"]
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        stdout, stderr = await process.communicate()

        if process.returncode != 0:
            logger.warning(f"Failed to get commit SHA: {stderr.decode()}")
            return ""

        return stdout.decode().strip()
    except Exception as e:
        logger.warning(f"Error getting commit SHA: {e}")
        return ""


async def _get_branch_name(repo_path: Path) -> str | None:
    """Get the current branch name from a git repository."""
    try:
        # Try symbolic-ref first (works for normal branches)
        cmd = ["git", "-C", str(repo_path), "symbolic-ref", "--short", "HEAD"]
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        stdout, stderr = await process.communicate()

        if process.returncode == 0:
            branch = stdout.decode().strip()
            return branch if branch else None

        # If symbolic-ref fails, try rev-parse for detached HEAD
        cmd = ["git", "-C", str(repo_path), "rev-parse", "--abbrev-ref", "HEAD"]
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        stdout, stderr = await process.communicate()

        if process.returncode == 0:
            branch = stdout.decode().strip()
            # Return None for HEAD (detached HEAD state) since branch is optional
            return None if branch == "HEAD" else branch

        logger.debug(f"Could not determine branch: {stderr.decode()}")
        return None

    except Exception as e:
        logger.debug(f"Error getting branch name: {e}")
        return None


async def _get_commit_count(repo_path: Path) -> int:
    """Get total commit count for the repository."""
    try:
        cmd = [
            "git",
            "-C",
            str(repo_path),
            "rev-list",
            "--count",
            "--all",  # Count all commits across all branches
        ]

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        stdout, stderr = await process.communicate()

        if process.returncode == 0:
            return int(stdout.decode().strip())
        else:
            logger.debug(f"Could not get commit count: {stderr.decode()}")
            return 0

    except Exception as e:
        logger.debug(f"Error getting commit count: {e}")
        return 0


async def _get_ref_count(repo_path: Path) -> int:
    """Get total ref count (branches + tags) for the repository."""
    try:
        cmd = [
            "git",
            "-C",
            str(repo_path),
            "show-ref",
        ]

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        stdout, stderr = await process.communicate()

        if process.returncode == 0:
            # Count number of lines in output (each line is one ref)
            refs = stdout.decode().strip().split("\n")
            return len([ref for ref in refs if ref])  # Filter out empty lines
        else:
            logger.debug(f"Could not get ref count: {stderr.decode()}")
            return 0

    except Exception as e:
        logger.debug(f"Error getting ref count: {e}")
        return 0
