"""GitLab file artifact models for file ingestion."""

from pydantic import BaseModel

from connectors.base.base_ingest_artifact import ArtifactEntity, BaseIngestArtifact


class GitLabFileContributor(BaseModel):
    """Contributor information for a GitLab file."""

    name: str
    email: str
    commit_count: int
    last_contribution_at: str | None = None


class GitLabFileMetadata(BaseModel):
    """Metadata for a GitLab file artifact."""

    project_id: int
    project_path: str  # e.g., "group/subgroup/project"
    file_extension: str
    source_branch: str | None = None
    source_commit_sha: str | None = None


class GitLabFileContent(BaseModel):
    """Content model for a GitLab file artifact."""

    path: str
    content: str
    source_created_at: str | None = None
    contributors: list[GitLabFileContributor] = []
    contributor_count: int = 0
    project_id: int
    project_path: str
    source_branch: str | None = None
    source_commit_sha: str | None = None


class GitLabFileArtifact(BaseIngestArtifact):
    """Artifact representing a GitLab repository file."""

    entity: ArtifactEntity = ArtifactEntity.GITLAB_FILE
    content: GitLabFileContent
    metadata: GitLabFileMetadata
