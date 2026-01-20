"""Models for GitHub file processing in the ingest pipeline."""

from pydantic import BaseModel

from connectors.base.base_ingest_artifact import ArtifactEntity, BaseIngestArtifact


class GitHubFileContributor(BaseModel):
    """Contributor information for a GitHub file."""

    name: str
    email: str
    commit_count: int
    last_contribution_at: str | None = None  # May be None for shallow clones or missing Git history


class GitHubFileMetadata(BaseModel):
    """Metadata for GitHub file artifacts."""

    repository: str
    organization: str
    file_extension: str
    source_branch: str | None = None  # Optional branch name for stable links
    source_commit_sha: str | None = None  # Optional commit SHA for stable links


class GitHubFileContent(BaseModel):
    """Content model for GitHub file artifacts."""

    path: str
    content: str
    source_created_at: str | None = None  # May be None if file mtime/commit timestamp unavailable
    contributors: list[
        GitHubFileContributor
    ] = []  # Empty list when Git history unavailable (webhooks)
    contributor_count: int = 0
    organization: str = "unknown"
    repository: str | None = None  # May be None in malformed webhook payloads
    source_branch: str | None = None  # Optional branch name for stable links
    source_commit_sha: str | None = None  # Optional commit SHA for stable links


class GitHubFileArtifact(BaseIngestArtifact):
    """Artifact model for GitHub file data."""

    entity: ArtifactEntity = ArtifactEntity.GITHUB_FILE
    content: GitHubFileContent
    metadata: GitHubFileMetadata
