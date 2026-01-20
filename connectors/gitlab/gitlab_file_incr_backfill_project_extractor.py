"""GitLab file incremental backfill project extractor.

This extractor fetches only files that have changed since the last synced commit.
"""

import base64
import binascii
import logging
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import asyncpg

from connectors.base import BaseExtractor, TriggerIndexingCallback
from connectors.base.base_ingest_artifact import get_gitlab_file_entity_id
from connectors.base.document_source import DocumentSource
from connectors.gitlab.gitlab_client_factory import get_gitlab_client_for_tenant
from connectors.gitlab.gitlab_file_artifacts import (
    GitLabFileArtifact,
    GitLabFileContent,
    GitLabFileContributor,
    GitLabFileMetadata,
)
from connectors.gitlab.gitlab_models import GitLabFileIncrBackfillProjectConfig
from connectors.gitlab.gitlab_sync_service import GitLabSyncService
from src.clients.ssm import SSMClient
from src.ingest.utils import DEFAULT_INDEX_BATCH_SIZE

logger = logging.getLogger(__name__)

# Maximum file size to process (1MB)
MAX_FILE_SIZE_BYTES = 1024 * 1024

# Binary file extensions to skip
BINARY_EXTENSIONS = {
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".ico",
    ".svg",
    ".webp",
    ".bmp",
    ".tiff",
    ".pdf",
    ".zip",
    ".tar",
    ".gz",
    ".rar",
    ".7z",
    ".exe",
    ".dll",
    ".so",
    ".dylib",
    ".bin",
    ".dat",
    ".db",
    ".sqlite",
    ".woff",
    ".woff2",
    ".ttf",
    ".eot",
    ".otf",
    ".mp3",
    ".mp4",
    ".wav",
    ".avi",
    ".mov",
    ".mkv",
    ".webm",
}


class GitLabFileIncrBackfillProjectExtractor(BaseExtractor[GitLabFileIncrBackfillProjectConfig]):
    """
    Extracts only files that have changed since the last synced commit.
    """

    source_name = "gitlab_file_incr_backfill_project"

    def __init__(self, ssm_client: SSMClient) -> None:
        super().__init__()
        self.ssm_client = ssm_client

    async def process_job(
        self,
        job_id: str,
        config: GitLabFileIncrBackfillProjectConfig,
        db_pool: asyncpg.Pool,
        trigger_indexing: TriggerIndexingCallback,
    ) -> None:
        logger.info(
            f"Processing GitLab file incremental backfill for project {config.project_path}"
        )

        sync_service = GitLabSyncService(db_pool)
        gitlab_client = await get_gitlab_client_for_tenant(
            config.tenant_id, self.ssm_client, per_page=100
        )

        try:
            # Get last synced commit SHA for this project
            last_synced_commit = await sync_service.get_file_synced_commit(config.project_id)

            if last_synced_commit is None:
                logger.info(
                    f"No previous file sync for project {config.project_path}, "
                    "skipping incremental (use full backfill first)"
                )
                return

            logger.info(f"Last synced commit: {last_synced_commit}")

            # Get the default branch
            default_branch = await gitlab_client.get_default_branch(config.project_id)
            logger.info(f"Default branch: {default_branch}")

            # Fetch the last synced commit directly by SHA to get its authored_date
            try:
                last_commit_info = await gitlab_client.get_commit(
                    config.project_id, last_synced_commit
                )
            except Exception as e:
                error_str = str(e).lower()
                # Check if commit doesn't exist (404) vs other API errors
                if "404" in error_str or "not found" in error_str:
                    # Commit not found (force push, branch reset, etc.)
                    # Clear the stale cursor - user should run full backfill
                    logger.warning(
                        f"Last synced commit {last_synced_commit} not found in repository "
                        f"for project {config.project_path}. This may be due to a force push "
                        "or branch reset. Clearing stale cursor - run full backfill to re-sync."
                    )
                    await sync_service.clear_file_synced_commit(config.project_id)
                else:
                    # Other API failure - don't clear cursor, retry later
                    logger.warning(
                        f"Could not fetch commit {last_synced_commit} for project "
                        f"{config.project_path}: {e}. Skipping incremental sync - will retry on next run."
                    )
                return

            since_date = last_commit_info.get("authored_date")

            new_commits = await gitlab_client.get_repository_commits(
                config.project_id,
                ref=default_branch,
                since=since_date,
            )

            # Filter out the commit we already processed
            new_commits = [c for c in new_commits if c.get("id") != last_synced_commit]

            if not new_commits:
                logger.info(f"No new commits since {last_synced_commit}")
                return

            logger.info(f"Found {len(new_commits)} new commits since last sync")

            # Collect all changed file paths from new commits
            changed_files: set[str] = set()
            latest_commit_sha = None

            for commit in new_commits:
                commit_sha = commit.get("id")
                if not commit_sha:
                    continue
                if latest_commit_sha is None:
                    latest_commit_sha = commit_sha  # First commit is the latest

                try:
                    diffs = await gitlab_client.get_commit_diff(config.project_id, commit_sha)
                    for diff in diffs:
                        # Skip deleted files - they no longer exist and would fail API calls
                        if diff.get("deleted_file"):
                            continue

                        # Add new/modified/renamed files
                        if diff.get("new_path"):
                            changed_files.add(diff["new_path"])
                except Exception as e:
                    logger.warning(f"Failed to get diff for commit {commit_sha}: {e}")

            logger.info(f"Found {len(changed_files)} changed files to process")

            # Process changed files
            artifacts: list[GitLabFileArtifact] = []
            entity_ids: list[str] = []
            failed_files: list[str] = []

            for file_path in changed_files:
                try:
                    artifact = await self._create_file_artifact(
                        job_id,
                        gitlab_client,
                        config.project_id,
                        config.project_path,
                        file_path,
                        default_branch,
                    )
                    if artifact:
                        artifacts.append(artifact)
                        entity_ids.append(artifact.entity_id)

                        # Store in batches
                        if len(artifacts) >= 50:
                            await self.store_artifacts_batch(db_pool, artifacts)
                            logger.info(f"Stored {len(artifacts)} file artifacts")
                            artifacts = []

                except Exception as e:
                    logger.error(f"Failed to process file {file_path}: {e}")
                    failed_files.append(file_path)
                    continue

            # Store remaining artifacts
            if artifacts:
                await self.store_artifacts_batch(db_pool, artifacts)
                logger.info(f"Stored {len(artifacts)} file artifacts")

            # Trigger indexing
            for i in range(0, len(entity_ids), DEFAULT_INDEX_BATCH_SIZE):
                batch_ids = entity_ids[i : i + DEFAULT_INDEX_BATCH_SIZE]
                await trigger_indexing(
                    batch_ids,
                    DocumentSource.GITLAB_CODE,
                    config.tenant_id,
                    config.backfill_id,
                    config.suppress_notification,
                )

            # Only update sync cursor if all files were processed successfully
            # This ensures failed files will be retried in the next incremental sync
            if latest_commit_sha and not failed_files:
                await sync_service.set_file_synced_commit(config.project_id, latest_commit_sha)
                logger.info(f"Updated file sync cursor to commit: {latest_commit_sha}")
            elif failed_files:
                logger.warning(
                    f"Not updating file sync cursor due to {len(failed_files)} failed files. "
                    "These will be retried in the next sync."
                )

            logger.info(
                f"Completed incremental file sync for {config.project_path}: "
                f"{len(entity_ids)} files processed"
            )

        finally:
            await gitlab_client.aclose()

    async def _create_file_artifact(
        self,
        job_id: str,
        gitlab_client,
        project_id: int,
        project_path: str,
        file_path: str,
        branch: str | None,
    ) -> GitLabFileArtifact | None:
        """Create a GitLabFileArtifact from file data."""
        try:
            # Skip binary files
            ext = Path(file_path).suffix.lower()
            if ext in BINARY_EXTENSIONS:
                logger.debug(f"Skipping binary file: {file_path}")
                return None

            # Get file content
            file_data = await gitlab_client.get_file_content(project_id, file_path, ref=branch)

            if not file_data:
                logger.warning(f"No file data returned for {file_path}")
                return None

            # Check file size
            size = file_data.get("size", 0)
            if size > MAX_FILE_SIZE_BYTES:
                logger.debug(f"Skipping large file ({size} bytes): {file_path}")
                return None

            # Decode base64 content
            encoded_content = file_data.get("content", "")
            try:
                content = base64.b64decode(encoded_content).decode("utf-8")
            except (binascii.Error, UnicodeDecodeError) as e:
                logger.debug(f"Skipping non-text file {file_path}: {e}")
                return None

            # Skip empty files
            if not content.strip():
                logger.debug(f"Skipping empty file: {file_path}")
                return None

            # Get file blame for contributors (optional)
            contributors: list[GitLabFileContributor] = []
            contributor_count = 0
            try:
                blame_data = await gitlab_client.get_file_blame(project_id, file_path, ref=branch)
                contributors, contributor_count = self._extract_contributors(blame_data)
            except Exception as e:
                logger.debug(f"Could not fetch blame for {file_path}: {e}")

            # Get last commit info
            source_created_at = None
            commit_sha = file_data.get("commit_id") or file_data.get("last_commit_id")
            try:
                commits = await gitlab_client.get_repository_commits(
                    project_id, path=file_path, ref=branch
                )
                if commits:
                    source_created_at = commits[0].get("committed_date")
            except Exception as e:
                logger.debug(f"Could not fetch commits for {file_path}: {e}")

            entity_id = get_gitlab_file_entity_id(project_id=project_id, file_path=file_path)

            artifact = GitLabFileArtifact(
                entity_id=entity_id,
                ingest_job_id=UUID(job_id),
                content=GitLabFileContent(
                    path=file_path,
                    content=content,
                    source_created_at=source_created_at,
                    contributors=contributors,
                    contributor_count=contributor_count,
                    project_id=project_id,
                    project_path=project_path,
                    source_branch=branch,
                    source_commit_sha=commit_sha,
                ),
                metadata=GitLabFileMetadata(
                    project_id=project_id,
                    project_path=project_path,
                    file_extension=ext,
                    source_branch=branch,
                    source_commit_sha=commit_sha,
                ),
                source_updated_at=datetime.now(tz=UTC),
            )

            return artifact

        except Exception as e:
            logger.error(f"Error creating file artifact for {file_path}: {e}")
            raise

    def _extract_contributors(
        self, blame_data: list[dict]
    ) -> tuple[list[GitLabFileContributor], int]:
        """Extract unique contributors from blame data."""
        contributor_map: dict[str, dict] = {}

        for blame_chunk in blame_data:
            commit = blame_chunk.get("commit", {})
            commit_sha = commit.get("id", "")
            author_name = commit.get("author_name", "Unknown")
            author_email = commit.get("author_email", "")
            committed_date = commit.get("committed_date")

            key = author_email or author_name
            if key in contributor_map:
                contributor_map[key]["commit_shas"].add(commit_sha)
                if committed_date:
                    existing_date = contributor_map[key].get("last_contribution_at")
                    if not existing_date or committed_date > existing_date:
                        contributor_map[key]["last_contribution_at"] = committed_date
            else:
                contributor_map[key] = {
                    "name": author_name,
                    "email": author_email,
                    "commit_shas": {commit_sha},
                    "last_contribution_at": committed_date,
                }

        contributors = [
            GitLabFileContributor(
                name=c["name"],
                email=c["email"],
                commit_count=len(c["commit_shas"]),
                last_contribution_at=c["last_contribution_at"],
            )
            for c in contributor_map.values()
        ]

        contributors.sort(key=lambda c: c.commit_count, reverse=True)

        return contributors, len(contributors)
