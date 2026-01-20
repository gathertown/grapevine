"""
Shared utility functions for GitHub PR extractors.

This module contains normalization functions shared between GitHub webhook
and backfill extractors to avoid code duplication.
"""

import logging
from typing import Any, Literal

from connectors.github.github_artifacts import (
    GitHubComment,
    GitHubFileChange,
    GitHubPullRequestData,
    GitHubReview,
    GitHubUser,
)
from connectors.github.github_pr_file_filter import filter_and_prepare_pr_files

logger = logging.getLogger(__name__)


def normalize_user(user_data: dict[str, Any] | None) -> GitHubUser | None:
    """Normalize user data into GitHubUser model."""
    if not user_data or not isinstance(user_data, dict):
        return None

    user_id = user_data.get("id")
    login = user_data.get("login")

    if not user_id or not login:
        return None

    return GitHubUser(
        id=user_id,
        login=login,
        type=user_data.get("type"),
    )


def normalize_pr_data(pr_data: dict[str, Any]) -> GitHubPullRequestData:
    """Normalize raw PR data from API or webhook into structured format."""
    # Extract user data
    user = normalize_user(pr_data.get("user")) if pr_data.get("user") else None

    # Extract assignees
    assignees = []
    for assignee in pr_data.get("assignees", []):
        if isinstance(assignee, dict):
            normalized_user = normalize_user(assignee)
            if normalized_user:
                assignees.append(normalized_user)

    # Extract labels (just names)
    labels = []
    for label in pr_data.get("labels", []):
        if isinstance(label, dict) and "name" in label:
            labels.append(label["name"])
        elif isinstance(label, str):
            labels.append(label)

    # Extract head and base refs
    head = None
    if pr_data.get("head"):
        head = {
            "ref": pr_data["head"].get("ref", ""),
            "sha": pr_data["head"].get("sha", ""),
        }

    base = None
    if pr_data.get("base"):
        base = {
            "ref": pr_data["base"].get("ref", ""),
            "sha": pr_data["base"].get("sha", ""),
        }

    return GitHubPullRequestData(
        id=pr_data.get("id", 0),
        number=pr_data.get("number", 0),
        title=pr_data.get("title", ""),
        body=pr_data.get("body"),
        state=pr_data.get("state", "open"),
        draft=pr_data.get("draft", False),
        merged=pr_data.get("merged", False),
        created_at=pr_data.get("created_at"),
        updated_at=pr_data.get("updated_at"),
        closed_at=pr_data.get("closed_at"),
        merged_at=pr_data.get("merged_at"),
        user=user,
        assignees=assignees,
        labels=labels,
        commits=pr_data.get("commits"),
        additions=pr_data.get("additions"),
        deletions=pr_data.get("deletions"),
        changed_files=pr_data.get("changed_files"),
        html_url=pr_data.get("html_url") or pr_data.get("url"),
        head=head,
        base=base,
    )


def normalize_comments(comments: list[dict[str, Any]]) -> list[GitHubComment]:
    """Normalize raw comments into GitHubComment models."""
    normalized = []
    for comment in comments:
        comment_id = comment.get("id")
        if not comment_id:
            continue

        # Determine comment type based on presence of certain fields
        comment_type: Literal["issue", "review"] = "issue"
        if (
            comment.get("comment_type") == "review"
            or "path" in comment
            or "position" in comment
            or "diff_hunk" in comment
        ):
            comment_type = "review"

        normalized.append(
            GitHubComment(
                id=comment_id,
                body=comment.get("body", ""),
                user=normalize_user(comment.get("user")),
                created_at=comment.get("created_at"),
                updated_at=comment.get("updated_at"),
                html_url=comment.get("html_url") or comment.get("url"),
                path=comment.get("path"),
                position=comment.get("position"),
                line=comment.get("line"),
                diff_hunk=comment.get("diff_hunk"),
                comment_type=comment_type,
            )
        )

    return normalized


def normalize_reviews(reviews: list[dict[str, Any]]) -> list[GitHubReview]:
    """Normalize raw reviews into GitHubReview models."""
    normalized = []
    for review in reviews:
        review_id = review.get("id")
        if not review_id:
            continue

        normalized.append(
            GitHubReview(
                id=review_id,
                body=review.get("body"),
                state=review.get("state", "COMMENTED"),
                user=normalize_user(review.get("user")),
                submitted_at=review.get("submitted_at") or review.get("created_at"),
                html_url=review.get("html_url") or review.get("url"),
                commit_id=review.get("commit_id"),
            )
        )

    return normalized


def normalize_files(raw_files: list[dict[str, Any]], pr_number: int) -> list[GitHubFileChange]:
    """Normalize file changes for a PR.

    Args:
        raw_files: Raw file data from GitHub API
        pr_number: PR number (for logging)

    Returns:
        List of normalized GitHubFileChange models
    """
    try:
        if not raw_files:
            logger.debug(f"No files found for PR #{pr_number}")
            return []

        # Apply smart filtering to exclude generated files, binaries, etc.
        filtered_files = filter_and_prepare_pr_files(raw_files)

        # Normalize into GitHubFileChange models
        normalized = []
        for file in filtered_files:
            normalized.append(
                GitHubFileChange(
                    filename=file["filename"],
                    status=file["status"],
                    additions=file["additions"],
                    deletions=file["deletions"],
                    changes=file["changes"],
                    patch=file.get("patch"),
                    previous_filename=file.get("previous_filename"),
                )
            )

        logger.debug(
            f"Normalized {len(normalized)} file changes for PR #{pr_number} "
            f"(filtered from {len(raw_files)} total files)"
        )
        return normalized

    except Exception as e:
        logger.error(f"Failed to normalize file changes for PR #{pr_number}: {e}")
        # Don't fail the entire PR artifact if we can't normalize files
        return []
