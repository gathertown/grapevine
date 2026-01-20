"""Pydantic models for GitHub job configurations."""

from typing import Literal

from pydantic import BaseModel

from connectors.base.models import BackfillIngestConfig


class GitHubPRBatch(BaseModel):
    """Metadata for a batch of GitHub PRs to process."""

    org_or_owner: str
    repo_name: str
    repo_id: int
    pr_numbers: list[int]


class GitHubPRBackfillRootConfig(BackfillIngestConfig, frozen=True):
    source: Literal["github_pr_backfill_root"] = "github_pr_backfill_root"
    repositories: list[str] = []
    organizations: list[str] = []


class GitHubPRBackfillRepoConfig(BackfillIngestConfig, frozen=True):
    source: Literal["github_pr_backfill_repo"] = "github_pr_backfill_repo"
    repo_full_name: str
    repo_id: int


class GitHubPRBackfillConfig(BackfillIngestConfig, frozen=True):
    source: Literal["github_pr_backfill"] = "github_pr_backfill"
    pr_batches: list[GitHubPRBatch]


class GitHubFileBatch(BaseModel):
    """Metadata for a batch of GitHub files to process."""

    org_or_owner: str
    repo_name: str
    file_paths: list[str]  # Relative paths within the repository
    branch: str | None = None  # Optional branch name for stable links
    commit_sha: str | None = None  # Optional commit SHA for stable links


class GitHubFileBackfillRootConfig(BackfillIngestConfig, frozen=True):
    source: Literal["github_file_backfill_root"] = "github_file_backfill_root"
    repositories: list[str] = []
    organizations: list[str] = []


class GitHubFileBackfillConfig(BackfillIngestConfig, frozen=True):
    source: Literal["github_file_backfill"] = "github_file_backfill"
    file_batches: list[GitHubFileBatch]
