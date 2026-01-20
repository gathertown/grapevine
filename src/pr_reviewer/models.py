"""Data models for PR reviewer."""

from typing import Any, TypedDict


class GitHubUser(TypedDict, total=False):
    """GitHub user information."""

    login: str
    id: int
    type: str


class ExistingReviewComment(TypedDict, total=False):
    """Existing review comment from GitHub PR.

    This represents a review comment that has already been posted on a PR.
    Fields are optional to handle variations in GitHub API responses.
    """

    id: int
    body: str
    created_at: str | None
    updated_at: str | None
    user: GitHubUser | None
    path: str  # Required for review comments
    position: int | None
    line: int | None  # Single line number
    lines: list[int] | None  # Range of lines [start, end]
    url: str
    diff_hunk: str | None
    comment_type: str  # "review" for review comments


class DiffChunk:
    """Represents a chunk of changes in a diff."""

    def __init__(
        self,
        filename: str,
        line_start: int,
        line_end: int,
        patch: str,
        status: str,
    ):
        self.filename = filename
        self.line_start = line_start
        self.line_end = line_end
        self.patch = patch
        self.status = status

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "filename": self.filename,
            "lineNumStart": self.line_start,
            "lineNumEnd": self.line_end,
            "patch": self.patch,
            "status": self.status,
        }
