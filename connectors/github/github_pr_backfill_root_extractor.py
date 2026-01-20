import asyncio
import logging

import asyncpg

from connectors.base import BaseExtractor, TriggerIndexingCallback
from connectors.github.github_models import (
    GitHubPRBackfillRepoConfig,
    GitHubPRBackfillRootConfig,
)
from src.clients.github import GitHubClient
from src.clients.github_factory import get_github_client_for_tenant
from src.clients.sqs import SQSClient
from src.clients.ssm import SSMClient

logger = logging.getLogger(__name__)

# Maximum concurrent SQS operations
MAX_CONCURRENT_SQS_OPERATIONS = 100


class GitHubPRBackfillRootExtractor(BaseExtractor[GitHubPRBackfillRootConfig]):
    """
    Discovers GitHub repositories and sends repo jobs to enumerate PRs for each repository.
    """

    source_name = "github_pr_backfill_root"

    def __init__(self, ssm_client: SSMClient, sqs_client: SQSClient) -> None:
        super().__init__()
        self.ssm_client = ssm_client
        self.sqs_client = sqs_client
        # Semaphore to limit concurrent SQS operations
        self._sqs_semaphore = asyncio.Semaphore(MAX_CONCURRENT_SQS_OPERATIONS)

    async def process_job(
        self,
        job_id: str,
        config: GitHubPRBackfillRootConfig,
        db_pool: asyncpg.Pool,
        trigger_indexing: TriggerIndexingCallback,
    ) -> None:
        # Normally we would generate a backfill_id here, but we're intentionally not doing that
        # for this root job b/c we do it in github_file_backfill_root instead. This mirrors the behavior
        # use for backfill _start_ notifs as well - we always prefer to use github_file. Eventually we
        # should merge these two sources + jobs, probably
        logger.info(f"Processing GitHub PR backfill root job for tenant {config.tenant_id}")

        # Get GitHub client for this tenant
        github_client = await get_github_client_for_tenant(
            config.tenant_id, self.ssm_client, per_page=100
        )

        # Collect all repositories to process
        all_repos = list(config.repositories)  # Start with explicitly specified repos

        # Determine what organizations to process
        orgs_to_process = config.organizations

        # If both repositories and organizations are empty, auto-discover repositories
        if not config.repositories and not config.organizations:
            if github_client.is_app_authenticated():
                # GitHub App: get all repos the installation has access to
                installation_repos = github_client.get_installation_repositories()
                for repo in installation_repos:
                    repo_full_name = repo.get("full_name")
                    if repo_full_name and repo_full_name not in all_repos:
                        all_repos.append(repo_full_name)
                logger.info(
                    f"Found {len(installation_repos)} repositories accessible by installation"
                )
                # Skip organization processing since we got all repos directly
                orgs_to_process = []
            else:
                # PAT: use user-based organization discovery
                user_orgs = github_client.get_user_organizations()
                orgs_to_process = [org.login for org in user_orgs]
                logger.info(
                    f"Auto-discovered {len(orgs_to_process)} organizations: {orgs_to_process}"
                )

        # Add repositories from organizations
        for org_name in orgs_to_process:
            logger.info(f"Fetching repositories from organization: {org_name}")
            org_repos = github_client.get_organization_repos(org_name)
            for repo in org_repos:
                repo_full_name = repo.get("full_name")
                if repo_full_name and repo_full_name not in all_repos:
                    all_repos.append(repo_full_name)
            logger.info(f"Found {len(org_repos)} repositories in {org_name}")

        logger.info(f"Total repositories to process: {len(all_repos)}")

        # Get repository IDs for all repos
        repo_configs = await self._get_repo_configs(github_client, all_repos)

        logger.info(f"Root job {job_id} found {len(repo_configs)} repositories to process")

        # Send repo jobs for each repository
        if repo_configs:
            await self._send_repo_jobs(config, repo_configs)
            logger.info(f"Sent repo jobs for {len(repo_configs)} repositories")

        logger.info(f"Successfully completed root job {job_id}")

    async def _get_repo_configs(
        self, github_client: GitHubClient, all_repos: list[str]
    ) -> list[tuple[str, int]]:
        """Get repository full names and IDs for all repos."""
        repo_configs = []

        for repo_index, repo_spec in enumerate(all_repos):
            logger.info(
                f"Getting info for repository: {repo_spec} (repo {repo_index + 1} of {len(all_repos)})"
            )

            # Get repository info
            repo_info = github_client.get_individual_repo(repo_spec)
            if not repo_info:
                logger.error(f"Could not fetch repository information for {repo_spec}")
                continue

            repo_id = repo_info.get("id")
            if not repo_id:
                logger.error(f"No repository ID found for {repo_spec}")
                continue

            repo_configs.append((repo_spec, repo_id))

        return repo_configs

    async def _send_repo_jobs(
        self, config: GitHubPRBackfillRootConfig, repo_configs: list[tuple[str, int]]
    ) -> None:
        """Send repo jobs for each repository to enumerate PRs."""
        total_repos = len(repo_configs)
        logger.info(f"Preparing to send repo jobs for {total_repos} repositories")

        # Create all repo job tasks
        tasks = []
        for i, (repo_full_name, repo_id) in enumerate(repo_configs):
            repo_config = GitHubPRBackfillRepoConfig(
                tenant_id=config.tenant_id,
                repo_full_name=repo_full_name,
                repo_id=repo_id,
                backfill_id=config.backfill_id,
                suppress_notification=config.suppress_notification,
            )

            # Create task to send this repo job
            task = self._send_single_repo_job(repo_config, i)
            tasks.append(task)

        # Send all repo jobs in parallel
        logger.info(f"Sending {len(tasks)} repo jobs for {total_repos} repositories...")
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Check for failures
        jobs_sent = 0
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"Failed to send repo job {i}: {result}")
                raise result
            jobs_sent += 1

        logger.info(f"Sent {jobs_sent} repo jobs for {total_repos} repositories!")

    async def _send_single_repo_job(
        self,
        repo_config: GitHubPRBackfillRepoConfig,
        repo_index: int,
    ) -> None:
        """Send a single repo job message to SQS."""
        # Use semaphore to limit concurrent SQS operations
        async with self._sqs_semaphore:
            success = await self.sqs_client.send_backfill_ingest_message(
                backfill_config=repo_config,
            )

            if not success:
                raise RuntimeError(f"Failed to send repo job {repo_index} to SQS")

            log = logger.info if repo_index % 10 == 0 else logger.debug
            log(f"Sent repo job {repo_index} for repository {repo_config.repo_full_name}")
