import logging
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import asyncpg

from connectors.base import BaseExtractor, TriggerIndexingCallback, get_github_pr_entity_id
from connectors.base.document_source import DocumentSource
from connectors.github.github_artifacts import (
    GitHubPullRequestArtifact,
    GitHubPullRequestArtifactContent,
    GitHubPullRequestArtifactMetadata,
)
from connectors.github.github_models import GitHubPRBackfillConfig, GitHubPRBatch
from connectors.github.github_utils import (
    normalize_comments,
    normalize_files,
    normalize_pr_data,
    normalize_reviews,
)
from src.clients.github import GitHubClient
from src.clients.github_factory import get_github_client_for_tenant
from src.clients.ssm import SSMClient
from src.ingest.utils import DEFAULT_INDEX_BATCH_SIZE

logger = logging.getLogger(__name__)


class GitHubPRBackfillExtractor(BaseExtractor[GitHubPRBackfillConfig]):
    """
    Extracts GitHub PRs from specific batches of PR numbers.
    This is a child job of GitHubPRBackfillRootExtractor.
    """

    source_name = "github_pr_backfill"

    def __init__(self, ssm_client: SSMClient):
        super().__init__()
        self.ssm_client = ssm_client

    async def process_job(
        self,
        job_id: str,
        config: GitHubPRBackfillConfig,
        db_pool: asyncpg.Pool,
        trigger_indexing: TriggerIndexingCallback,
    ) -> None:
        logger.info(f"Processing {len(config.pr_batches)} PR batches for job {job_id}")

        # Get GitHub client for this tenant
        github_client = await get_github_client_for_tenant(config.tenant_id, self.ssm_client)

        # Process all PR batches
        all_pr_entity_ids: list[str] = []

        for batch_idx, pr_batch in enumerate(config.pr_batches):
            logger.info(
                f"Processing batch {batch_idx + 1}/{len(config.pr_batches)}: "
                f"{len(pr_batch.pr_numbers)} PRs from {pr_batch.org_or_owner}/{pr_batch.repo_name}"
            )

            batch_entity_ids = await self._process_pr_batch(
                job_id, github_client, pr_batch, db_pool
            )
            all_pr_entity_ids.extend(batch_entity_ids)

        logger.info(
            f"Successfully processed {len(all_pr_entity_ids)} PR artifacts for job {job_id}"
        )

        # Trigger indexing in batches
        for i in range(0, len(all_pr_entity_ids), DEFAULT_INDEX_BATCH_SIZE):
            batched_entity_ids = all_pr_entity_ids[i : i + DEFAULT_INDEX_BATCH_SIZE]
            await trigger_indexing(
                batched_entity_ids,
                DocumentSource.GITHUB_PRS,
                config.tenant_id,
                config.backfill_id,
                config.suppress_notification,
            )

        logger.info(
            f"Successfully triggered index job for {len(all_pr_entity_ids)} PRs from job {job_id}"
        )

        # Normally we would track completion of the ingest job here via `increment_backfill_done_ingest_jobs`
        # (and also index jobs), but github_pr is a special case - we only use github_file to track github backfills.
        # See `github_pr_backfill_root.py` for more context.

    async def _process_pr_batch(
        self,
        job_id: str,
        github_client: GitHubClient,
        pr_batch: GitHubPRBatch,
        db_pool: asyncpg.Pool,
    ) -> list[str]:
        """Process a specific batch of PRs from a repository."""
        try:
            repo_spec = f"{pr_batch.org_or_owner}/{pr_batch.repo_name}"
            pr_numbers = pr_batch.pr_numbers

            # Fetch PR data with comments and reviews using GraphQL
            # This is much more efficient than REST API as it fetches PR + comments + reviews
            # in a single query per PR instead of scanning all repo comments
            pr_data_with_files: list[tuple[dict[str, Any], list[dict[str, Any]]]] = []

            for pr_number in pr_numbers:
                pr_data = github_client.get_pull_request_with_comments_graphql(repo_spec, pr_number)
                if pr_data:
                    # Fetch file changes for this PR
                    raw_files = github_client.get_pr_files(repo_spec, pr_number)
                    # Keep pr_data and raw_files as separate items in tuple
                    pr_data_with_files.append((pr_data, raw_files))
                else:
                    # If we can't fetch a PR, fail the entire batch so it can be retried
                    error_msg = f"Could not fetch PR #{pr_number} from {repo_spec}"
                    logger.error(error_msg)
                    raise RuntimeError(error_msg)

            logger.info(
                f"Fetched {len(pr_data_with_files)} PRs with comments and files from {repo_spec}"
            )

            # Log comment and review distribution (GraphQL already included them)
            prs_with_comments = sum(
                1 for pr_data, _ in pr_data_with_files if pr_data.get("comments")
            )
            total_comments = sum(
                len(pr_data.get("comments", [])) for pr_data, _ in pr_data_with_files
            )
            prs_with_reviews = sum(1 for pr_data, _ in pr_data_with_files if pr_data.get("reviews"))
            total_reviews = sum(
                len(pr_data.get("reviews", [])) for pr_data, _ in pr_data_with_files
            )
            logger.info(
                f"Distribution: {prs_with_comments}/{len(pr_data_with_files)} PRs have comments "
                f"(total: {total_comments}), {prs_with_reviews}/{len(pr_data_with_files)} PRs have reviews "
                f"(total: {total_reviews})"
            )

            # Create and store artifacts
            entity_ids = []
            artifacts_batch = []

            for pr_data, raw_files in pr_data_with_files:
                artifact = self._create_pr_artifact(
                    job_id,
                    pr_data,
                    pr_batch.org_or_owner,
                    pr_batch.repo_name,
                    pr_batch.repo_id,
                    raw_files,
                )

                if artifact:
                    artifacts_batch.append(artifact)
                    entity_ids.append(artifact.entity_id)

                    # Store artifacts in batches
                    if len(artifacts_batch) >= 50:
                        await self.store_artifacts_batch(db_pool, artifacts_batch)
                        logger.info(f"Stored {len(artifacts_batch)} PR artifacts")
                        artifacts_batch = []

            if artifacts_batch:
                await self.store_artifacts_batch(db_pool, artifacts_batch)
                logger.info(f"Stored {len(artifacts_batch)} PR artifacts")

            logger.info(f"Completed processing batch from {repo_spec} with {len(entity_ids)} PRs")
            return entity_ids

        except Exception as e:
            logger.error(
                f"Failed to process PR batch from {pr_batch.org_or_owner}/{pr_batch.repo_name}: {e}"
            )
            raise

    def _create_pr_artifact(
        self,
        job_id: str,
        pr_data: dict[str, Any],
        organization: str,
        repository: str,
        repo_id: int,
        raw_files: list[dict[str, Any]],
    ) -> GitHubPullRequestArtifact | None:
        """Create a GitHubPullRequestArtifact from PR data.

        Args:
            job_id: The ingest job ID
            pr_data: PR data from GitHub API
            organization: Organization/owner name
            repository: Repository name
            repo_id: Repository ID
            raw_files: Raw file changes from GitHub API
        """
        try:
            pr_id = pr_data.get("id")
            pr_number = pr_data.get("number")
            if not pr_id or not pr_number:
                return None

            entity_id = get_github_pr_entity_id(repo_id=str(repo_id), pr_number=pr_number)

            # Extract and normalize comments before creating artifact
            raw_comments = pr_data.pop("comments", [])
            normalized_comments = normalize_comments(raw_comments)

            # Extract and normalize reviews before creating artifact
            raw_reviews = pr_data.pop("reviews", [])
            normalized_reviews = normalize_reviews(raw_reviews)

            # Normalize file changes (data already fetched)
            normalized_files = normalize_files(raw_files, pr_number)

            # Normalize the PR data
            normalized_pr = normalize_pr_data(pr_data)

            artifact = GitHubPullRequestArtifact(
                entity_id=entity_id,
                ingest_job_id=UUID(job_id),
                content=GitHubPullRequestArtifactContent(
                    pr_data=normalized_pr,
                    comments=normalized_comments,
                    reviews=normalized_reviews,
                    files=normalized_files,
                ),
                metadata=GitHubPullRequestArtifactMetadata(
                    pr_number=pr_number,
                    pr_title=normalized_pr.title,
                    repository=repository,
                    organization=organization,
                    repo_id=repo_id,
                    state=normalized_pr.state,
                    merged=normalized_pr.merged or False,
                    author=normalized_pr.user.login if normalized_pr.user else None,
                    assignees=[a.login for a in normalized_pr.assignees],
                    labels=normalized_pr.labels,
                ),
                # We just pulled this PR's data fresh from the API, so we can set source_updated_at to now()
                source_updated_at=datetime.now(tz=UTC),
            )

            return artifact

        except Exception as e:
            logger.error(
                f"Error creating PR artifact for PR {pr_data.get('number', 'unknown')}: {e}"
            )
            return None
