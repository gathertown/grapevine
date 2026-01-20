"""Utility for fetching file contents from GitHub."""

from typing import Any

from src.clients.github import GitHubClient
from src.utils.logging import get_logger

logger = get_logger(__name__)


async def fetch_file_contents_with_context(
    github_client: GitHubClient,
    repo_spec: str,
    pr_data: dict[str, Any],
    changed_files: list[dict[str, Any]],
) -> dict[str, str]:
    """Fetch full file contents for all changed files in the PR.

    Args:
        github_client: Initialized GitHub client
        repo_spec: Repository in "owner/repo" format
        pr_data: PR metadata dictionary containing head ref
        changed_files: List of changed file dictionaries from get_pr_files

    Returns:
        Dictionary mapping filename to full file content
    """
    file_contents: dict[str, str] = {}

    # Get the head ref (SHA) to fetch files from the PR branch
    head_sha = pr_data.get("head", {}).get("sha")
    if not head_sha:
        logger.warning("No head SHA found in PR data, cannot fetch file contents")
        return file_contents

    logger.info(f"Fetching file contents for {len(changed_files)} changed files")

    for file_info in changed_files:
        filename = file_info.get("filename")
        status = file_info.get("status")

        if not filename:
            continue

        # Skip removed files (they don't exist in the head ref)
        if status == "removed":
            logger.debug(f"Skipping removed file: {filename}")
            continue

        try:
            # Fetch full file content from the PR's head ref
            content = github_client.get_file_content(repo_spec, filename, ref=head_sha)

            if content:
                file_contents[filename] = content
                logger.debug(f"Fetched content for {filename}: {len(content)} chars")
            else:
                logger.warning(f"No content returned for {filename}")

        except Exception as e:
            logger.error(f"Error fetching content for {filename}: {e}")
            # Continue with other files even if one fails
            continue

    logger.info(f"Successfully fetched {len(file_contents)} file contents")
    return file_contents
