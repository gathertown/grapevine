import asyncio
import logging
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import asyncpg
from pydantic import BaseModel

from connectors.base import (
    BaseExtractor,
    BaseIngestArtifact,
    TriggerIndexingCallback,
    get_github_file_entity_id,
    get_github_pr_entity_id,
)
from connectors.base.document_source import DocumentSource
from connectors.github.github_artifacts import (
    GitHubComment,
    GitHubFileChange,
    GitHubPullRequestArtifact,
    GitHubPullRequestArtifactContent,
    GitHubPullRequestArtifactMetadata,
    GitHubReview,
)
from connectors.github.github_file_artifacts import (
    GitHubFileArtifact,
    GitHubFileContent,
    GitHubFileMetadata,
)
from connectors.github.github_file_utils import generate_binary_file_metadata_content
from connectors.github.github_pr_pruner import github_pr_pruner
from connectors.github.github_pruner import github_pruner
from connectors.github.github_utils import (
    normalize_comments,
    normalize_files,
    normalize_pr_data,
)
from src.clients.github import GitHubClient
from src.clients.github_factory import get_github_client_for_tenant
from src.clients.ssm import SSMClient

logger = logging.getLogger(__name__)


class GitHubWebhookConfig(BaseModel):
    body: dict[str, Any]
    headers: dict[str, str]
    tenant_id: str


class GitHubWebhookExtractor(BaseExtractor[GitHubWebhookConfig]):
    source_name = "github_webhook"

    def __init__(self, ssm_client: SSMClient):
        super().__init__()
        self.ssm_client = ssm_client

    async def get_github_client(self, tenant_id: str) -> GitHubClient:
        """Get GitHubClient for the specified tenant."""
        return await get_github_client_for_tenant(tenant_id, self.ssm_client)

    async def process_job(
        self,
        job_id: str,
        config: GitHubWebhookConfig,
        db_pool: asyncpg.Pool,
        trigger_indexing: TriggerIndexingCallback,
    ) -> None:
        """
        Process a GitHub webhook ingest job.

        Args:
            job_id: The ingest job ID
            config: Job configuration specific to GitHub webhooks
            db_pool: Database connection pool
            trigger_indexing: Callback to trigger indexing for entity IDs (takes entity_ids, source, tenant_id)

        Raises:
            Exception: If processing fails
        """
        payload = config.body
        headers = config.headers
        event_type = headers.get("x-github-event", "")

        logger.info(
            f"Processing GitHub webhook job {job_id} for tenant {config.tenant_id} (event: {event_type})"
        )

        artifacts: list[BaseIngestArtifact] = []

        if event_type == "push":
            artifacts = await self._handle_push_event(job_id, payload, db_pool, config.tenant_id)
        elif event_type in [
            "pull_request",
            "pull_request_review",
            "pull_request_review_comment",
            "issue_comment",
        ]:
            artifacts = await self._handle_pr_events(
                job_id, payload, event_type, config.tenant_id, db_pool
            )
        else:
            logger.info(f"Ignoring unsupported GitHub event type: {event_type}")

        # Store all artifacts
        if artifacts:
            await self.store_artifacts_batch(db_pool, artifacts)

            pr_ids = [a.entity_id for a in artifacts if isinstance(a, GitHubPullRequestArtifact)]
            file_ids = [a.entity_id for a in artifacts if isinstance(a, GitHubFileArtifact)]

            # Trigger indexing for both PR and file artifacts in parallel
            indexing_tasks = []
            if pr_ids:
                indexing_tasks.append(
                    trigger_indexing(pr_ids, DocumentSource.GITHUB_PRS, config.tenant_id)
                )
            if file_ids:
                indexing_tasks.append(
                    trigger_indexing(file_ids, DocumentSource.GITHUB_CODE, config.tenant_id)
                )

            if indexing_tasks:
                await asyncio.gather(*indexing_tasks)

        logger.info(
            f"Successfully processed GitHub webhook job {job_id}, created {len(artifacts)} artifacts"
        )

    async def _handle_push_event(
        self, job_id: str, payload: dict[str, Any], db_pool: asyncpg.Pool, tenant_id: str
    ) -> list[BaseIngestArtifact]:
        """Handle push events and extract file changes."""
        ref = payload.get("ref", "")
        repository = payload.get("repository", {})
        default_branch = repository.get("default_branch", "main")
        expected_ref = f"refs/heads/{default_branch}"

        if ref != expected_ref:
            logger.info(f"Ignoring push to non-default branch: {ref} (default: {expected_ref})")
            return []

        repo_name = repository.get("name", "")
        repo_full_name = repository.get("full_name", "")
        organization = repository.get("owner", {}).get("login", "")

        if not repo_name or not repo_full_name:
            logger.warning("Incomplete repository data in push event")
            return []

        configured_repos: list[str] = []  # TODO: support or remove configured_repos
        if configured_repos and repo_full_name not in configured_repos:
            logger.info(
                f"Ignoring push event for unconfigured repository: {repo_full_name} "
                f"(configured: {configured_repos})"
            )
            return []

        commits = payload.get("commits", [])
        if not commits:
            logger.info("No commits found in push event")
            return []

        head_commit = payload.get("head_commit", {})
        commit_timestamp = head_commit.get("timestamp", datetime.now(tz=UTC).isoformat())
        commit_sha = head_commit.get("id", "")

        # Extract branch name from ref (format: refs/heads/branch-name)
        branch = None
        if ref.startswith("refs/heads/"):
            branch = ref.replace("refs/heads/", "", 1)

        file_changes = {}  # file_path -> change_type

        for commit in commits:
            added = commit.get("added", [])
            modified = commit.get("modified", [])
            removed = commit.get("removed", [])

            for file_path in added:
                file_changes[file_path] = "added"

            for file_path in modified:
                file_changes[file_path] = "modified"

            for file_path in removed:
                file_changes[file_path] = "removed"

        if not file_changes:
            logger.info("No file changes found in push event")
            return []

        logger.info(f"Found {len(file_changes)} file changes: {list(file_changes.keys())}")

        artifacts: list[BaseIngestArtifact] = []
        github_client = await self.get_github_client(tenant_id)

        for file_path, change_type in file_changes.items():
            try:
                if change_type == "removed":
                    success = await github_pruner.delete_file(
                        file_path=file_path,
                        repo_name=repo_name,
                        organization=organization,
                        tenant_id=tenant_id,
                        db_pool=db_pool,
                    )
                    if success:
                        logger.info(f"Successfully pruned file: {file_path}")
                    else:
                        logger.warning(f"Failed to prune file: {file_path}")
                else:
                    content = github_client.get_file_content(repo_full_name, file_path)

                    # If we couldn't fetch content (e.g., binary file or error), generate metadata content
                    if content is None:
                        content = generate_binary_file_metadata_content(
                            file_path=file_path,
                            organization=organization,
                            repository=repo_name,
                            # TODO: use actual file size from API
                            file_size_bytes=None,
                            # TODO AIVP-470 fix github_webhook contributors
                            contributors=None,
                            last_modified=commit_timestamp,
                        )

                    artifact = await self._create_file_artifact(
                        job_id,
                        file_path,
                        content,
                        repo_name,
                        organization,
                        commit_timestamp,
                        source_branch=branch,
                        source_commit_sha=commit_sha,
                    )
                    artifacts.append(artifact)

            except Exception as e:
                logger.error(f"Error processing file {file_path}: {e}")
                raise

        logger.info(f"Created {len(artifacts)} artifacts from push event")
        return artifacts

    async def _handle_pr_events(
        self,
        job_id: str,
        payload: dict[str, Any],
        event_type: str,
        tenant_id: str,
        db_pool: asyncpg.Pool,
    ) -> list[BaseIngestArtifact]:
        """Handle PR-related events."""
        try:
            action = payload.get("action", "")

            if action == "deleted" and event_type == "pull_request":
                return await self._handle_pr_deletion(payload, tenant_id, db_pool)

            pr_data = payload.get("pull_request")
            if not pr_data and event_type == "issue_comment":
                issue_data = payload.get("issue")
                if issue_data and "pull_request" in issue_data:
                    repo = payload.get("repository", {})
                    owner = repo.get("owner", {}).get("login", "")
                    repo_name = repo.get("name", "")
                    pr_number = issue_data.get("number")

                    if owner and repo_name and pr_number:
                        pr_data = issue_data
                    else:
                        logger.warning("Missing data to fetch PR for issue_comment event")
                        return []

            if not pr_data:
                logger.warning(f"No PR data found in {event_type} event")
                return []

            pr_number = pr_data.get("number")
            pr_title = pr_data.get("title", "")
            repository = payload.get("repository", {})
            repo_name = repository.get("name", "")
            repo_id = repository.get("id", "")
            organization = repository.get("owner", {}).get("login", "")

            if not pr_number or not repo_id:
                logger.warning("Incomplete PR event data")
                return []

            normalized_event = self._normalize_webhook_event(event_type, action)
            if not normalized_event:
                logger.info(f"Skipping noisy webhook event: {event_type}.{action}")
                return []

            # Normalize the PR data from webhook payload
            normalized_pr = normalize_pr_data(pr_data)

            # Fetch comments and files
            repo_full_name = f"{organization}/{repo_name}"
            normalized_comments: list[GitHubComment] = []
            normalized_reviews: list[GitHubReview] = []
            normalized_files: list[GitHubFileChange] = []

            github_client = await self.get_github_client(tenant_id)

            # Fetch comments
            raw_comments = github_client.get_pr_comments(repo_full_name, pr_number)
            normalized_comments = normalize_comments(raw_comments)

            # Fetch file changes
            raw_files = github_client.get_pr_files(repo_full_name, pr_number)
            normalized_files = normalize_files(raw_files, pr_number)

            entity_id = get_github_pr_entity_id(repo_id=str(repo_id), pr_number=pr_number)

            content = GitHubPullRequestArtifactContent(
                pr_data=normalized_pr,
                comments=normalized_comments,
                reviews=normalized_reviews,
                files=normalized_files,
            )

            metadata = GitHubPullRequestArtifactMetadata(
                pr_number=pr_number,
                pr_title=pr_title,
                repository=repo_name,
                organization=organization,
                repo_id=repo_id,
                state=normalized_pr.state,
                merged=normalized_pr.merged or False,
                author=normalized_pr.user.login if normalized_pr.user else None,
                assignees=[a.login for a in normalized_pr.assignees],
                labels=normalized_pr.labels,
            )

            artifact = GitHubPullRequestArtifact(
                entity_id=entity_id,
                ingest_job_id=UUID(job_id),
                content=content,
                metadata=metadata,
                # This isn't 100% precise but close enough, assuming we process this webhook event promptly.
                # We do pull PR comments fresh from the API.
                source_updated_at=datetime.now(tz=UTC),
            )

            return [artifact]

        except Exception as e:
            logger.error(f"Error processing PR event: {e}")
            return []

    async def _handle_pr_deletion(
        self, payload: dict[str, Any], tenant_id: str, db_pool: asyncpg.Pool
    ) -> list[BaseIngestArtifact]:
        """Handle PR deletion events using GitHubPRPruner."""
        try:
            pr_data = payload.get("pull_request", {})
            repository = payload.get("repository", {})

            pr_number = pr_data.get("number")
            repo_id = str(repository.get("id", ""))
            repo_name = repository.get("name", "")
            organization = repository.get("owner", {}).get("login", "")

            if not pr_number or not repo_id:
                logger.warning("Incomplete PR deletion event data")
                return []

            logger.info(
                f"PR deleted: #{pr_number} in {organization}/{repo_name} (repo_id: {repo_id})"
            )

            success = await github_pr_pruner.delete_pr(
                repo_id=repo_id,
                pr_number=pr_number,
                tenant_id=tenant_id,
                db_pool=db_pool,
            )

            if success:
                logger.info(f"Successfully processed PR deletion for #{pr_number}")
            else:
                logger.error(f"Failed to process PR deletion for #{pr_number}")

            return []

        except Exception as e:
            logger.error(f"Error processing PR deletion: {e}")
            return []

    async def _create_file_artifact(
        self,
        job_id: str,
        file_path: str,
        content: str,
        repo_name: str,
        organization: str,
        commit_timestamp: str,
        source_branch: str | None = None,
        source_commit_sha: str | None = None,
    ) -> GitHubFileArtifact:
        """
        Create a GitHubFileArtifact from file content.

        Args:
            content: The content of the file. This should have been freshly pulled from API.
            source_branch: Optional branch name for stable links
            source_commit_sha: Optional commit SHA for stable links
        """
        entity_id = get_github_file_entity_id(
            organization=organization, repository=repo_name, file_path=file_path
        )

        file_extension = ""
        if "." in file_path:
            file_extension = file_path.rsplit(".", 1)[-1]

        file_content = GitHubFileContent(
            path=file_path,
            content=content,
            source_created_at=commit_timestamp,
            # TODO AIVP-470 fix github_webhook contributors
            contributors=[],
            contributor_count=0,
            organization=organization,
            repository=repo_name,
            source_branch=source_branch,
            source_commit_sha=source_commit_sha,
        )

        metadata = GitHubFileMetadata(
            repository=repo_name,
            organization=organization,
            file_extension=file_extension,
            source_branch=source_branch,
            source_commit_sha=source_commit_sha,
        )

        artifact = GitHubFileArtifact(
            entity_id=entity_id,
            ingest_job_id=UUID(job_id),
            content=file_content,
            metadata=metadata,
            # We always pull GitHub files fresh from the API, so we can set source_updated_at to now()
            source_updated_at=datetime.now(tz=UTC),
        )

        return artifact

    def _normalize_webhook_event(self, event_type: str, action: str) -> tuple[str, str] | None:
        """
        Normalize webhook events to match API source behavior.

        Args:
            event_type: Raw webhook event type
            action: Raw webhook action

        Returns:
            Tuple of (normalized_event_type, normalized_action) or None to skip
        """
        if event_type == "pull_request":
            if action in ["opened", "closed", "merged", "edited", "deleted"]:
                return (event_type, action)
        elif event_type == "pull_request_review":
            if action == "submitted":
                return (event_type, action)
        elif event_type == "pull_request_review_comment":
            if action in ["created", "edited", "deleted"]:
                return (event_type, "created")
        elif event_type == "issue_comment" and action in ["created", "edited", "deleted"]:
            return (event_type, "created")

        return None
