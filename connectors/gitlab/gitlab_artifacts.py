"""GitLab MR artifact models for normalized data storage."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from connectors.base.base_ingest_artifact import ArtifactEntity, BaseIngestArtifact


class GitLabMRArtifactMetadata(BaseModel):
    """Metadata for GitLab MR artifacts."""

    mr_iid: int  # Internal ID within project
    mr_title: str
    project_path: str  # e.g., "group/project"
    project_id: int
    state: str  # opened, closed, merged
    merged: bool = False
    author: str | None = None
    assignees: list[str] = Field(default_factory=list)
    reviewers: list[str] = Field(default_factory=list)
    labels: list[str] = Field(default_factory=list)


class GitLabUser(BaseModel):
    """Normalized GitLab user data."""

    id: int | None = None
    username: str
    name: str | None = None
    avatar_url: str | None = None
    web_url: str | None = None


class GitLabNote(BaseModel):
    """Normalized GitLab note/comment data."""

    id: int
    body: str
    author: GitLabUser | None = None
    created_at: str | None = None
    updated_at: str | None = None
    system: bool = False  # True for system-generated notes
    noteable_type: str | None = None
    resolvable: bool = False
    resolved: bool = False


class GitLabApproval(BaseModel):
    """Normalized GitLab approval data."""

    user: GitLabUser
    approved_at: str | None = None


class GitLabDiffRef(BaseModel):
    """Reference to a diff in GitLab."""

    base_sha: str | None = None
    head_sha: str | None = None
    start_sha: str | None = None


class GitLabDiff(BaseModel):
    """Normalized GitLab diff/file change data."""

    old_path: str
    new_path: str
    a_mode: str | None = None
    b_mode: str | None = None
    new_file: bool = False
    renamed_file: bool = False
    deleted_file: bool = False
    diff: str | None = None  # Unified diff content


class GitLabPipeline(BaseModel):
    """Normalized GitLab pipeline status."""

    id: int
    status: str  # success, failed, running, pending, canceled, skipped
    ref: str | None = None
    sha: str | None = None
    web_url: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


class GitLabMergeRequestData(BaseModel):
    """Normalized GitLab merge request data."""

    # Core fields
    id: int  # Global ID
    iid: int  # Internal ID within project
    title: str
    description: str | None = None
    state: str  # opened, closed, merged
    draft: bool = False
    merged: bool = False

    # Timestamps
    created_at: str | None = None
    updated_at: str | None = None
    closed_at: str | None = None
    merged_at: str | None = None

    # User info
    author: GitLabUser | None = None
    assignees: list[GitLabUser] = Field(default_factory=list)
    reviewers: list[GitLabUser] = Field(default_factory=list)
    merged_by: GitLabUser | None = None

    # Labels - just strings
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
    changes_count: int | None = None
    user_notes_count: int | None = None

    # References
    web_url: str | None = None
    source_branch: str | None = None
    target_branch: str | None = None
    source_project_id: int | None = None
    target_project_id: int | None = None

    # Merge info
    merge_commit_sha: str | None = None
    squash_commit_sha: str | None = None
    sha: str | None = None  # Head commit SHA

    # Pipeline info
    head_pipeline: GitLabPipeline | None = None


class GitLabMRArtifactContent(BaseModel):
    """Content of a GitLab MR artifact."""

    source: Literal["gitlab_mr"] = "gitlab_mr"
    mr_data: GitLabMergeRequestData
    notes: list[GitLabNote] = Field(default_factory=list)
    approvals: list[GitLabApproval] = Field(default_factory=list)
    diffs: list[GitLabDiff] = Field(default_factory=list)

    model_config = ConfigDict(json_encoders={datetime: lambda v: v.isoformat()})


class GitLabMRArtifact(BaseIngestArtifact):
    """Typed GitLab merge request artifact with validated content and metadata."""

    entity: ArtifactEntity = ArtifactEntity.GITLAB_MR
    content: GitLabMRArtifactContent
    metadata: GitLabMRArtifactMetadata


# Event models for document processing
class GitLabMREventBase(BaseModel):
    """Base model for GitLab MR events."""

    event_type: str
    action: str
    actor: str
    actor_username: str
    timestamp: str
    formatted_time: str
    mr_iid: int
    mr_title: str
    project_path: str
    event_id: str | None = None


class GitLabMRNoteEvent(GitLabMREventBase):
    """Note/comment event on an MR."""

    note_body: str
    system: bool = False


class GitLabMRApprovalEvent(GitLabMREventBase):
    """Approval event on an MR."""

    pass


# Union type for all MR events
GitLabMREvent = GitLabMREventBase | GitLabMRNoteEvent | GitLabMRApprovalEvent


class GitLabMRDocumentData(BaseModel):
    """Typed model for GitLab MR document data."""

    mr_iid: int
    mr_title: str
    mr_url: str
    mr_description: str = ""
    mr_state: str
    mr_draft: bool = False
    mr_merged: bool = False
    mr_changes_count: int = 0
    project_path: str
    project_id: int
    source_branch: str | None = None
    target_branch: str | None = None
    events: list[dict[str, Any]]  # Serialized events
    diffs: list[dict[str, Any]] = Field(default_factory=list)  # File changes with diffs
    source: str = "gitlab"
    source_created_at: str | None = None
    source_merged_at: str | None = None
    ingestion_timestamp: str
