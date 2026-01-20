from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from connectors.base.base_ingest_artifact import ArtifactEntity, BaseIngestArtifact


class JiraIssueArtifactMetadata(BaseModel):
    issue_key: str  # e.g., "PROJ-123"
    issue_id: str  # Internal Jira ID
    issue_title: str
    project_key: str  # e.g., "PROJ"
    project_id: str  # Internal Jira project ID - this is the reference to related project artifact
    project_name: str
    status: str | None = None
    priority: str | None = None
    assignee: str | None = None  # Display name
    assignee_id: str | None = None  # Jira account ID
    reporter: str | None = None  # Display name
    reporter_id: str | None = None  # Jira account ID
    labels: list[str] = []
    issue_type: str | None = None  # Bug, Story, Task, etc.
    parent_issue_key: str | None = None  # For sub-tasks
    site_domain: str | None = None  # e.g., "company.atlassian.net"


class JiraIssueArtifactContent(BaseModel):
    issue_data: dict[str, Any]  # Full Jira issue JSON
    comments: list[dict[str, Any]] = []  # List of comments

    model_config = ConfigDict(json_encoders={datetime: lambda v: v.isoformat()})


class JiraUserArtifactContent(BaseModel):
    """Content for Jira user artifacts."""

    user_data: dict[str, Any]  # Full Jira user JSON

    model_config = ConfigDict(json_encoders={datetime: lambda v: v.isoformat()})


class JiraProjectArtifactContent(BaseModel):
    """Content for Jira project artifacts."""

    project_data: dict[str, Any]  # Full Jira project JSON

    model_config = ConfigDict(json_encoders={datetime: lambda v: v.isoformat()})


class JiraIssueArtifact(BaseIngestArtifact):
    """Typed Jira issue artifact with validated content and metadata."""

    entity: ArtifactEntity = ArtifactEntity.JIRA_ISSUE
    content: JiraIssueArtifactContent
    metadata: JiraIssueArtifactMetadata


class JiraUserArtifact(BaseIngestArtifact):
    """Typed Jira user artifact with validated content and blank metadata."""

    entity: ArtifactEntity = ArtifactEntity.JIRA_USER
    content: JiraUserArtifactContent
    metadata: dict[str, Any] = {}  # Blank metadata as specified


class JiraProjectArtifact(BaseIngestArtifact):
    """Typed Jira project artifact with validated content and blank metadata."""

    entity: ArtifactEntity = ArtifactEntity.JIRA_PROJECT
    content: JiraProjectArtifactContent
    metadata: dict[str, Any] = {}  # Blank metadata as specified
