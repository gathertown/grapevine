from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from connectors.base.base_ingest_artifact import ArtifactEntity, BaseIngestArtifact


class GitHubPullRequestArtifactMetadata(BaseModel):
    pr_number: int
    pr_title: str
    repository: str
    organization: str
    repo_id: int
    state: str
    merged: bool = False
    author: str | None = None
    assignees: list[str] = []
    labels: list[str] = []


class GitHubUser(BaseModel):
    """Normalized GitHub user data."""

    id: int | None = None
    login: str
    type: str | None = None


class GitHubComment(BaseModel):
    """Normalized GitHub comment data."""

    id: int
    body: str
    user: GitHubUser | None = None
    created_at: str | None = None
    updated_at: str | None = None
    html_url: str | None = None
    # For review comments
    path: str | None = None
    position: int | None = None
    line: int | None = None
    diff_hunk: str | None = None
    # To distinguish between issue and review comments
    comment_type: Literal["issue", "review"] = "issue"


class GitHubReview(BaseModel):
    """Normalized GitHub review data."""

    id: int
    body: str | None = None
    state: str  # APPROVED, CHANGES_REQUESTED, COMMENTED, DISMISSED
    user: GitHubUser | None = None
    submitted_at: str | None = None
    html_url: str | None = None
    commit_id: str | None = None


class GitHubFileChange(BaseModel):
    """Represents a file change in a PR."""

    filename: str
    status: str  # added, modified, removed, renamed
    additions: int
    deletions: int
    changes: int
    patch: str | None = None  # Unified diff content (limited to 3000 lines by GitHub)
    previous_filename: str | None = None  # For renamed files


class GitHubPullRequestData(BaseModel):
    """Normalized GitHub pull request data."""

    # Core fields
    id: int
    number: int
    title: str
    body: str | None = None
    state: str  # open, closed
    draft: bool = False
    merged: bool | None = False

    # Timestamps
    created_at: str | None = None
    updated_at: str | None = None
    closed_at: str | None = None
    merged_at: str | None = None

    # User info
    user: GitHubUser | None = None
    assignees: list[GitHubUser] = Field(default_factory=list)

    # Labels - just strings, not full objects
    labels: list[str] = Field(default_factory=list)

    @field_validator("labels", mode="before")
    @classmethod
    def normalize_labels(cls, v: Any) -> list[str]:
        """Normalize labels to list of strings."""
        if not v:
            return []
        result = []
        for label in v:
            if isinstance(label, str):
                result.append(label)
            elif isinstance(label, dict) and "name" in label:
                result.append(label["name"])
        return result

    # Stats
    commits: int | None = None
    additions: int | None = None
    deletions: int | None = None
    changed_files: int | None = None

    # References
    html_url: str | None = None
    head: dict[str, str] | None = None  # {ref, sha}
    base: dict[str, str] | None = None  # {ref, sha}


class GitHubPullRequestArtifactContent(BaseModel):
    source: Literal["github_pr"] = "github_pr"
    pr_data: GitHubPullRequestData
    comments: list[GitHubComment] = Field(default_factory=list)
    reviews: list[GitHubReview] = Field(default_factory=list)
    files: list[GitHubFileChange] = Field(default_factory=list)

    model_config = ConfigDict(json_encoders={datetime: lambda v: v.isoformat()})


class GitHubPullRequestArtifact(BaseIngestArtifact):
    """Typed GitHub pull request artifact with validated content and metadata."""

    entity: ArtifactEntity = ArtifactEntity.GITHUB_PR
    content: GitHubPullRequestArtifactContent
    metadata: GitHubPullRequestArtifactMetadata


# Event models for document processing
class GitHubPREventBase(BaseModel):
    """Base model for GitHub PR events."""

    event_type: str
    action: str
    actor: str
    actor_id: str
    actor_login: str
    timestamp: str
    formatted_time: str
    pr_number: int
    pr_title: str
    repository: str
    organization: str
    event_id: str | None = None


class GitHubPRCommentEvent(GitHubPREventBase):
    """Comment event on a PR."""

    comment_body: str
    comment_type: Literal["issue", "review"]


class GitHubPRReviewEvent(GitHubPREventBase):
    """Review submitted on a PR."""

    review_state: str  # APPROVED, CHANGES_REQUESTED, COMMENTED, DISMISSED
    review_body: str = ""


# Union type for all PR events
GitHubPREvent = GitHubPREventBase | GitHubPRCommentEvent | GitHubPRReviewEvent


class GitHubPRDocumentData(BaseModel):
    """Typed model for GitHub PR document data."""

    pr_number: int
    pr_title: str
    pr_url: str
    pr_body: str = ""
    pr_status: str
    pr_draft: bool = False
    pr_merged: bool = False
    pr_commits: int = 0
    pr_additions: int = 0
    pr_deletions: int = 0
    pr_changed_files: int = 0
    repository: str
    organization: str
    repo_spec: str
    actual_repo_id: int
    events: list[dict[str, Any]]  # Will be typed events
    files: list[dict[str, Any]] = Field(default_factory=list)  # File changes with diffs
    source: str = "github"
    source_created_at: str | None = None
    source_merged_at: str | None = None
    ingestion_timestamp: str
