import asyncio
import logging

import asyncpg

from connectors.base import BaseExtractor, TriggerIndexingCallback
from connectors.github.github_models import (
    GitHubPRBackfillConfig,
    GitHubPRBackfillRepoConfig,
    GitHubPRBatch,
)
from src.clients.github import GitHubClient
from src.clients.github_factory import get_github_client_for_tenant
from src.clients.sqs import SQSClient
from src.clients.ssm import SSMClient

logger = logging.getLogger(__name__)

# Number of PRs per child job
CHILD_JOB_BATCH_SIZE = 50

# Maximum concurrent SQS operations
MAX_CONCURRENT_SQS_OPERATIONS = 100


class GitHubPRBackfillRepoExtractor(BaseExtractor[GitHubPRBackfillRepoConfig]):
    """
    Extracts GitHub PRs from a single repository and sends child jobs to process them.
    This is an intermediate job between root and leaf jobs.
    """

    source_name = "github_pr_backfill_repo"

    def __init__(self, ssm_client: SSMClient, sqs_client: SQSClient) -> None:
        super().__init__()
        self.ssm_client = ssm_client
        self.sqs_client = sqs_client
        # Semaphore to limit concurrent SQS operations
        self._sqs_semaphore = asyncio.Semaphore(MAX_CONCURRENT_SQS_OPERATIONS)

    async def process_job(
        self,
        job_id: str,
        config: GitHubPRBackfillRepoConfig,
        db_pool: asyncpg.Pool,
        trigger_indexing: TriggerIndexingCallback,
    ) -> None:
        logger.info(
            f"Processing GitHub PR repo backfill job for tenant {config.tenant_id}, "
            f"repo: {config.repo_full_name}"
        )

        # Get GitHub client for this tenant
        github_client = await get_github_client_for_tenant(
            config.tenant_id, self.ssm_client, per_page=100
        )

        # Parse repository spec
        parts = config.repo_full_name.split("/")
        if len(parts) != 2:
            logger.error(
                f"Invalid repository spec: {config.repo_full_name}. Expected format: owner/repo"
            )
            return

        org_or_owner, repo_name = parts

        # Enumerate all PRs for this repository
        pr_batches = await self._enumerate_prs_for_repo(
            github_client, config.repo_full_name, org_or_owner, repo_name, config.repo_id
        )

        logger.info(
            f"Repo job {job_id} found {len(pr_batches)} PR batches for {config.repo_full_name}"
        )

        # Send child jobs for PR processing
        if pr_batches:
            await self._send_child_jobs(config, pr_batches)
            logger.info(f"Sent child jobs for {len(pr_batches)} PR batches")

        logger.info(f"Successfully completed repo job {job_id} for {config.repo_full_name}")

    async def _enumerate_prs_for_repo(
        self,
        github_client: GitHubClient,
        repo_spec: str,
        org_or_owner: str,
        repo_name: str,
        repo_id: int,
    ) -> list[GitHubPRBatch]:
        """Enumerate all PRs for a single repository and create batches."""
        pr_batches = []

        logger.info(f"Enumerating PRs for repository: {repo_spec}")

        # Use GraphQL to efficiently fetch only PR numbers (not full PR objects)
        all_pr_numbers = github_client.get_all_pr_numbers_graphql(repo_spec)

        logger.info(f"Found {len(all_pr_numbers)} PRs in {repo_spec}")

        # Split PRs into batches
        for i in range(0, len(all_pr_numbers), CHILD_JOB_BATCH_SIZE):
            batch_pr_numbers = all_pr_numbers[i : i + CHILD_JOB_BATCH_SIZE]

            pr_batch = GitHubPRBatch(
                org_or_owner=org_or_owner,
                repo_name=repo_name,
                repo_id=repo_id,
                pr_numbers=batch_pr_numbers,
            )

            pr_batches.append(pr_batch)

        return pr_batches

    async def _send_child_jobs(
        self, config: GitHubPRBackfillRepoConfig, pr_batches: list[GitHubPRBatch]
    ) -> None:
        """Send child jobs to process PR batches."""
        total_batches = len(pr_batches)
        logger.info(f"Preparing to send child jobs for {total_batches} PR batches")

        # Create all child job tasks
        tasks = []
        for i, pr_batch in enumerate(pr_batches):
            child_config = GitHubPRBackfillConfig(
                tenant_id=config.tenant_id,
                pr_batches=[pr_batch],
                backfill_id=config.backfill_id,
                suppress_notification=config.suppress_notification,
            )

            # Create task to send this batch
            task = self._send_single_child_job(child_config, i)
            tasks.append(task)

        # Send all child jobs in parallel
        logger.info(f"Sending {len(tasks)} child jobs to process {total_batches} PR batches...")
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Check for failures
        jobs_sent = 0
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"Failed to send child job batch {i}: {result}")
                raise result
            jobs_sent += 1

        logger.info(f"Sent {jobs_sent} child jobs to process {total_batches} PR batches!")

    async def _send_single_child_job(
        self,
        child_config: GitHubPRBackfillConfig,
        batch_index: int,
    ) -> None:
        """Send a single child job message to SQS."""
        # Use semaphore to limit concurrent SQS operations
        async with self._sqs_semaphore:
            success = await self.sqs_client.send_backfill_ingest_message(
                backfill_config=child_config,
            )

            if not success:
                raise RuntimeError(f"Failed to send child job batch {batch_index} to SQS")

            log = logger.info if batch_index % 100 == 0 else logger.debug
            log(
                f"Sent child job batch {batch_index} with {len(child_config.pr_batches)} PR batches"
            )
