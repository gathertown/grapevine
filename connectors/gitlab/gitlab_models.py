"""GitLab backfill job configuration models."""

from typing import Literal

from pydantic import BaseModel

from connectors.base.models import BackfillIngestConfig


class GitLabMRBatch(BaseModel):
    """Metadata for a batch of GitLab MRs to process."""

    project_id: int
    project_path: str  # e.g., "group/project"
    mr_iids: list[int]


class GitLabBackfillRootConfig(BackfillIngestConfig, frozen=True):
    """Configuration for GitLab backfill root job.

    This job discovers all accessible projects and sends project-level jobs
    for MRs (and in the future, code files).
    """

    source: Literal["gitlab_backfill_root"] = "gitlab_backfill_root"
    # Optional: specific projects to backfill (format: "group/project")
    # If empty, discovers all accessible projects
    projects: list[str] = []
    # Optional: specific groups to backfill
    # If empty, discovers all accessible groups
    groups: list[str] = []


class GitLabMRBackfillProjectConfig(BackfillIngestConfig, frozen=True):
    """Configuration for GitLab MR backfill project job.

    This job enumerates all MRs in a project and sends batch jobs.
    """

    source: Literal["gitlab_mr_backfill_project"] = "gitlab_mr_backfill_project"
    project_id: int
    project_path: str  # e.g., "group/project"


class GitLabMRBackfillConfig(BackfillIngestConfig, frozen=True):
    """Configuration for GitLab MR backfill job.

    This job processes specific batches of MRs.
    """

    source: Literal["gitlab_mr_backfill"] = "gitlab_mr_backfill"
    mr_batches: list[GitLabMRBatch]


# ========== GitLab File Backfill Models ==========


class GitLabFileBatch(BaseModel):
    """Metadata for a batch of GitLab files to process."""

    project_id: int
    project_path: str  # e.g., "group/project"
    file_paths: list[str]  # Relative paths within the repository
    branch: str | None = None  # Optional branch name for stable links
    commit_sha: str | None = None  # Optional commit SHA for stable links


class GitLabFileBackfillProjectConfig(BackfillIngestConfig, frozen=True):
    """Configuration for GitLab file backfill project job.

    This job enumerates all files in a project and sends batch jobs.
    """

    source: Literal["gitlab_file_backfill_project"] = "gitlab_file_backfill_project"
    project_id: int
    project_path: str  # e.g., "group/project"


class GitLabFileBackfillConfig(BackfillIngestConfig, frozen=True):
    """Configuration for GitLab file backfill job.

    This job processes specific batches of files.
    """

    source: Literal["gitlab_file_backfill"] = "gitlab_file_backfill"
    file_batches: list[GitLabFileBatch]


# ========== GitLab Incremental Backfill Models ==========


class GitLabIncrBackfillConfig(BackfillIngestConfig, frozen=True):
    """Configuration for GitLab incremental backfill job.

    This job discovers projects and sends incremental project jobs
    for MRs and files that have changed since the last sync.
    """

    source: Literal["gitlab_incr_backfill"] = "gitlab_incr_backfill"
    # Optional: specific projects to backfill (format: "group/project")
    # If empty, discovers all accessible projects
    projects: list[str] = []
    # Optional: specific groups to backfill
    # If empty, discovers all accessible groups
    groups: list[str] = []


class GitLabMRIncrBackfillProjectConfig(BackfillIngestConfig, frozen=True):
    """Configuration for GitLab MR incremental backfill project job.

    This job fetches only MRs updated since the last sync for a project.
    """

    source: Literal["gitlab_mr_incr_backfill_project"] = "gitlab_mr_incr_backfill_project"
    project_id: int
    project_path: str  # e.g., "group/project"


class GitLabFileIncrBackfillProjectConfig(BackfillIngestConfig, frozen=True):
    """Configuration for GitLab file incremental backfill project job.

    This job fetches only files changed since the last synced commit.
    """

    source: Literal["gitlab_file_incr_backfill_project"] = "gitlab_file_incr_backfill_project"
    project_id: int
    project_path: str  # e.g., "group/project"
