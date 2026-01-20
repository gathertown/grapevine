from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from connectors.base.base_ingest_artifact import ArtifactEntity, BaseIngestArtifact


class LinearIssueArtifactMetadata(BaseModel):
    issue_id: str
    issue_identifier: str
    issue_title: str
    team_id: str
    team_name: str
    status: str | None = None
    priority: str | None = None
    assignee: str | None = None
    labels: list[str] = []


class LinearIssueArtifactContent(BaseModel):
    issue_data: dict[str, Any]
    comments: list[dict[str, Any]] = []

    model_config = ConfigDict(json_encoders={datetime: lambda v: v.isoformat()})


class LinearIssueArtifact(BaseIngestArtifact):
    """Typed Linear issue artifact with validated content and metadata."""

    entity: ArtifactEntity = ArtifactEntity.LINEAR_ISSUE
    content: LinearIssueArtifactContent
    metadata: LinearIssueArtifactMetadata
