"""GitLab file backfill extractor.

This extractor processes specific batches of files, fetching their content
and creating artifacts for indexing.
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
from connectors.gitlab.gitlab_models import GitLabFileBackfillConfig, GitLabFileBatch
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


class GitLabFileBackfillExtractor(BaseExtractor[GitLabFileBackfillConfig]):
    """
    Extracts GitLab files from specific batches of file paths.
    This is a child job of GitLabFileBackfillProjectExtractor.
    """

    source_name = "gitlab_file_backfill"

    def __init__(self, ssm_client: SSMClient):
        super().__init__()
        self.ssm_client = ssm_client

    async def process_job(
        self,
        job_id: str,
        config: GitLabFileBackfillConfig,
        db_pool: asyncpg.Pool,
        trigger_indexing: TriggerIndexingCallback,
    ) -> None:
        logger.info(f"Processing {len(config.file_batches)} file batches for job {job_id}")

        # Get GitLab client for this tenant
        gitlab_client = await get_gitlab_client_for_tenant(config.tenant_id, self.ssm_client)

        try:
            # Process all file batches
            all_file_entity_ids: list[str] = []

            for batch_idx, file_batch in enumerate(config.file_batches):
                logger.info(
                    f"Processing batch {batch_idx + 1}/{len(config.file_batches)}: "
                    f"{len(file_batch.file_paths)} files from {file_batch.project_path}"
                )

                batch_entity_ids = await self._process_file_batch(
                    job_id, gitlab_client, file_batch, db_pool
                )
                all_file_entity_ids.extend(batch_entity_ids)

            logger.info(
                f"Successfully processed {len(all_file_entity_ids)} file artifacts for job {job_id}"
            )

            # Trigger indexing in batches
            for i in range(0, len(all_file_entity_ids), DEFAULT_INDEX_BATCH_SIZE):
                batched_entity_ids = all_file_entity_ids[i : i + DEFAULT_INDEX_BATCH_SIZE]
                await trigger_indexing(
                    batched_entity_ids,
                    DocumentSource.GITLAB_CODE,
                    config.tenant_id,
                    config.backfill_id,
                    config.suppress_notification,
                )

            logger.info(
                f"Successfully triggered index job for {len(all_file_entity_ids)} files "
                f"from job {job_id}"
            )

        finally:
            await gitlab_client.aclose()

    async def _process_file_batch(
        self,
        job_id: str,
        gitlab_client,
        file_batch: GitLabFileBatch,
        db_pool: asyncpg.Pool,
    ) -> list[str]:
        """Process a specific batch of files from a project."""
        try:
            project_id = file_batch.project_id
            project_path = file_batch.project_path
            file_paths = file_batch.file_paths
            branch = file_batch.branch

            # Fetch file content and create artifacts
            entity_ids = []
            artifacts_batch = []

            for file_path in file_paths:
                try:
                    artifact = await self._create_file_artifact(
                        job_id, gitlab_client, project_id, project_path, file_path, branch
                    )
                    if artifact:
                        artifacts_batch.append(artifact)
                        entity_ids.append(artifact.entity_id)

                        # Store artifacts in batches
                        if len(artifacts_batch) >= 50:
                            await self.store_artifacts_batch(db_pool, artifacts_batch)
                            logger.info(f"Stored {len(artifacts_batch)} file artifacts")
                            artifacts_batch = []

                except Exception as e:
                    logger.error(f"Failed to process file {file_path} from {project_path}: {e}")
                    # Continue with other files rather than failing the whole batch
                    continue

            if artifacts_batch:
                await self.store_artifacts_batch(db_pool, artifacts_batch)
                logger.info(f"Stored {len(artifacts_batch)} file artifacts")

            logger.info(
                f"Completed processing batch from {project_path} with {len(entity_ids)} files"
            )
            return entity_ids

        except Exception as e:
            logger.error(f"Failed to process file batch from {file_batch.project_path}: {e}")
            raise

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

            # Get last commit info for source_created_at
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
            return None

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

            # Use email as key for deduplication
            key = author_email or author_name
            if key in contributor_map:
                # Track unique commit SHAs to avoid overcounting blame chunks
                contributor_map[key]["commit_shas"].add(commit_sha)
                # Update last contribution if this is more recent
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

        # Sort by commit count descending
        contributors.sort(key=lambda c: c.commit_count, reverse=True)

        return contributors, len(contributors)
