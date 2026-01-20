import asyncio
import logging
import os
import secrets
import shutil
import tempfile
from pathlib import Path

import asyncpg

from connectors.base import BaseExtractor, TriggerIndexingCallback
from connectors.github.github_models import (
    GitHubFileBackfillConfig,
    GitHubFileBackfillRootConfig,
    GitHubFileBatch,
)
from connectors.github.github_repo_utils import CloneResult, clone_repository, parse_repo_url
from src.clients.github import GitHubClient
from src.clients.github_factory import get_github_client_for_tenant
from src.clients.sqs import SQSClient
from src.clients.ssm import SSMClient
from src.utils.tenant_config import increment_backfill_total_ingest_jobs

logger = logging.getLogger(__name__)

# Number of files per child job
CHILD_JOB_BATCH_SIZE = 100

# Maximum concurrent SQS operations
MAX_CONCURRENT_SQS_OPERATIONS = 100


class GitHubFileBackfillRootExtractor(BaseExtractor[GitHubFileBackfillRootConfig]):
    """
    Extracts GitHub files from certain repositories and sends child jobs to process them.
    """

    source_name = "github_file_backfill_root"

    def __init__(self, ssm_client: SSMClient, sqs_client: SQSClient) -> None:
        super().__init__()
        self.ssm_client = ssm_client
        self.sqs_client = sqs_client
        self.temp_dir: str | None = None
        # Semaphore to limit concurrent SQS operations
        self._sqs_semaphore = asyncio.Semaphore(MAX_CONCURRENT_SQS_OPERATIONS)

    async def process_job(
        self,
        job_id: str,
        config: GitHubFileBackfillRootConfig,
        db_pool: asyncpg.Pool,
        trigger_indexing: TriggerIndexingCallback,
    ) -> None:
        # Generate a unique backfill ID for this root job
        backfill_id = secrets.token_hex(8)
        logger.info(
            f"Processing GitHub file backfill root job for tenant {config.tenant_id} with backfill_id {backfill_id}"
        )

        try:
            # Get GitHub client for this tenant

            github_client = await get_github_client_for_tenant(config.tenant_id, self.ssm_client)

            # Collect all repositories to process
            all_repo_urls = []

            for repo_spec in config.repositories:
                if not repo_spec.startswith("http"):
                    repo_url = f"https://github.com/{repo_spec}"
                else:
                    repo_url = repo_spec
                if repo_url not in all_repo_urls:
                    all_repo_urls.append(repo_url)

            # Determine what organizations to process
            orgs_to_process = config.organizations

            # If both repositories and organizations are empty, auto-discover repositories
            if not config.repositories and not config.organizations:
                if github_client.is_app_authenticated():
                    # GitHub App: get all repos the installation has access to
                    logger.info(
                        "No repositories or organizations specified - GitHub App authentication detected, "
                        "fetching installation repositories"
                    )
                    installation_repos = github_client.get_installation_repositories()
                    for repo in installation_repos:
                        repo_full_name = repo.get("full_name")
                        if repo_full_name:
                            # Convert full_name to URL format
                            repo_url = f"https://github.com/{repo_full_name}"
                            if repo_url not in all_repo_urls:
                                all_repo_urls.append(repo_url)
                    logger.info(
                        f"Found {len(installation_repos)} repositories accessible by installation"
                    )
                    # Skip organization processing since we got all repos directly
                    orgs_to_process = []
                else:
                    # PAT: use existing organization discovery
                    logger.info(
                        "No repositories or organizations specified - PAT authentication detected, "
                        "discovering all user organizations"
                    )
                    user_orgs = github_client.get_user_organizations()
                    orgs_to_process = [org.login for org in user_orgs]
                    logger.info(
                        f"Auto-discovered {len(orgs_to_process)} organizations: {orgs_to_process}"
                    )

            # Add repositories from organizations if we have any to process
            for org_name in orgs_to_process:
                logger.info(f"Fetching repositories from organization: {org_name}")
                org_repos = github_client.get_organization_repos(org_name)
                for repo in org_repos:
                    repo_full_name = repo.get("full_name")
                    if repo_full_name:
                        # Convert full_name to URL format
                        repo_url = f"https://github.com/{repo_full_name}"
                        if repo_url not in all_repo_urls:
                            all_repo_urls.append(repo_url)
                logger.info(f"Found {len(org_repos)} repositories in {org_name}")

            if not all_repo_urls:
                logger.warning(f"No repositories to process for job {job_id}")
                return

            logger.info(f"Total repositories to process: {len(all_repo_urls)}")

            # Create temporary directory for cloning
            temp_dir = tempfile.mkdtemp(prefix="github_repo_")
            self.temp_dir = temp_dir
            logger.info(f"Created temporary directory: {self.temp_dir}")

            # Analyze file counts and create batches
            file_batches = await self._analyze_and_create_file_batches(all_repo_urls, github_client)

            logger.info(
                f"Root job {job_id} found {len(file_batches)} file batches across "
                f"{len(all_repo_urls)} repositories with backfill_id {backfill_id}"
            )

            # Send child jobs for file processing
            if file_batches:
                # Track total number of ingest jobs (child batches) for this backfill
                await increment_backfill_total_ingest_jobs(
                    backfill_id, config.tenant_id, len(file_batches)
                )

                await self._send_child_jobs(config, file_batches, backfill_id)
                logger.info(f"Sent child jobs for {len(file_batches)} file batches")

            logger.info(f"Successfully completed root job {job_id}")

        finally:
            # Clean up temporary directory
            if self.temp_dir and os.path.exists(self.temp_dir):
                try:
                    shutil.rmtree(self.temp_dir)
                    logger.info(f"Cleaned up temporary directory: {self.temp_dir}")
                except Exception as e:
                    logger.error(f"Error cleaning up temporary directory: {e}")

    async def _analyze_and_create_file_batches(
        self, all_repo_urls: list[str], github_client: GitHubClient
    ) -> list[GitHubFileBatch]:
        """Analyze repositories to create file batches for child jobs."""
        file_batches = []

        for repo_index, repo_url in enumerate(all_repo_urls):
            logger.info(
                f"Analyzing repository: {repo_url} (repo {repo_index + 1} of {len(all_repo_urls)})"
            )

            # Parse repository info from URL
            repo_info = parse_repo_url(repo_url)
            repository = repo_info["name"]
            organization = repo_info["owner"]
            repo_spec = f"{organization}/{repository}"

            try:
                # Clone the repository (will detect default branch)
                if self.temp_dir is None:
                    raise ValueError("Temporary directory not initialized")
                clone_result: CloneResult = await clone_repository(
                    repo_url, github_client, self.temp_dir
                )
                repo_path = clone_result.repo_path
                logger.info(
                    f"Cloned repository to: {repo_path} (SHA: {clone_result.commit_sha}, branch: {clone_result.branch or 'unknown'})"
                )

                # List all files using git ls-tree (no checkout needed!)
                # Returns empty list for empty repos
                all_file_paths = await self._list_repository_files(repo_path)

                logger.info(f"Found {len(all_file_paths)} files in {repo_spec}")

                # Split files into batches
                for i in range(0, len(all_file_paths), CHILD_JOB_BATCH_SIZE):
                    batch_file_paths = all_file_paths[i : i + CHILD_JOB_BATCH_SIZE]

                    file_batch = GitHubFileBatch(
                        org_or_owner=organization,
                        repo_name=repository,
                        file_paths=batch_file_paths,
                        branch=clone_result.branch,
                        commit_sha=clone_result.commit_sha,
                    )

                    file_batches.append(file_batch)

                # Clean up this repository's clone
                if repo_path and repo_path.exists():
                    try:
                        shutil.rmtree(repo_path)
                    except Exception as e:
                        logger.error(f"Error cleaning up repo {repo_path}: {e}")

            except Exception as e:
                logger.error(f"Error analyzing repository {repo_url}: {e}")
                raise

        return file_batches

    def _walk_repository(self, repo_path: Path):
        """Walk through repository and yield all files, excluding common ignore patterns."""
        ignore_patterns = {
            ".git",
            ".github",
            "node_modules",
            "__pycache__",
            ".pytest_cache",
            ".venv",
            "venv",
            "env",
            ".env",
            "dist",
            "build",
            ".DS_Store",
            "*.pyc",
            "*.pyo",
            "*.egg-info",
            ".mypy_cache",
            ".tox",
            ".coverage",
            "htmlcov",
            ".idea",
            ".vscode",
        }

        for root, dirs, files in os.walk(repo_path):
            # Remove ignored directories from traversal
            dirs[:] = [d for d in dirs if d not in ignore_patterns]

            root_path = Path(root)
            for file in files:
                # Skip ignored file patterns
                if (
                    any(
                        file.endswith(pattern.replace("*", ""))
                        for pattern in ignore_patterns
                        if "*" in pattern
                    )
                    or file in ignore_patterns
                ):
                    logger.info(f"Skipping ignored file: {file}")
                    continue

                yield root_path / file

    async def _repo_has_any_commits(self, repo_path: Path) -> bool:
        check_cmd = ["git", "-C", str(repo_path), "rev-list", "-n", "1", "--all"]
        check_process = await asyncio.create_subprocess_exec(
            *check_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await check_process.communicate()

        if check_process.returncode != 0:
            logger.error(f"Could not check commit count: {stderr.decode()}")
            raise RuntimeError(f"Could not check commit count: {stderr.decode()}")

        # result is a commit hash if there is one. No output if not.
        has_commit = len(stdout.decode().strip()) != 0
        return has_commit

    async def _list_repository_files(self, repo_path: Path) -> list[str]:
        """
        List all files in repository using git ls-tree without checking them out.

        This is much faster than checking out + walking the filesystem, especially
        for large repositories with a blobless clone.

        Args:
            repo_path: Path to the cloned repository

        Returns:
            List of relative file paths as strings
        """
        from pathlib import PurePath

        has_commit = await self._repo_has_any_commits(repo_path)
        if not has_commit:
            logger.info(f"Repository {repo_path} has no commits (empty repository)")
            return []

        # Directories to exclude if they appear anywhere in the path
        ignore_directories = {
            ".git",
            ".github",
            "node_modules",
            "__pycache__",
            ".pytest_cache",
            ".venv",
            "venv",
            "env",
            "dist",
            "build",
            ".mypy_cache",
            ".tox",
            "htmlcov",
            ".idea",
            ".vscode",
        }

        # File patterns to exclude (pathlib.match() does suffix matching)
        ignore_file_patterns = [
            "*.pyc",
            "*.pyo",
            "*.egg-info",
            ".DS_Store",
            ".env",
            ".coverage",
        ]

        # Use git ls-tree to list all files in the repository tree without checking them out
        cmd = [
            "git",
            "-C",
            str(repo_path),
            "ls-tree",
            "-r",  # Recursive
            "--name-only",  # Only output filenames
            "HEAD",  # List files in HEAD commit
        ]

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        stdout, stderr = await process.communicate()

        if process.returncode != 0:
            error_msg = stderr.decode() if stderr else "Unknown error"
            raise RuntimeError(f"Failed to list repository files: {error_msg}")

        # Parse output and filter
        all_paths = stdout.decode().strip().split("\n")
        filtered_paths = []

        for file_path in all_paths:
            if not file_path:
                continue

            path = PurePath(file_path)
            should_ignore = False

            # Check if any directory component is in ignore list
            if any(part in ignore_directories for part in path.parts):
                should_ignore = True

            # Check if filename matches any ignore pattern
            if not should_ignore:
                for pattern in ignore_file_patterns:
                    if path.match(pattern):
                        should_ignore = True
                        break

            if not should_ignore:
                filtered_paths.append(file_path)

        logger.info(
            f"Listed {len(filtered_paths)} files from {len(all_paths)} total using git ls-tree "
            f"(excluded {len(all_paths) - len(filtered_paths)} files)"
        )

        return filtered_paths

    async def _send_child_jobs(
        self,
        config: GitHubFileBackfillRootConfig,
        file_batches: list[GitHubFileBatch],
        backfill_id: str,
    ) -> None:
        """Send child jobs to process file batches."""
        total_batches = len(file_batches)
        logger.info(f"Preparing to send child jobs for {total_batches} file batches")

        # Create all child job tasks
        tasks = []
        for i, file_batch in enumerate(file_batches):
            child_config = GitHubFileBackfillConfig(
                tenant_id=config.tenant_id,
                file_batches=[file_batch],
                backfill_id=backfill_id,
                suppress_notification=config.suppress_notification,
            )

            # Create task to send this batch
            task = self._send_single_child_job(child_config, i)
            tasks.append(task)

        # Send all child jobs in parallel
        logger.info(f"Sending {len(tasks)} child jobs to process {total_batches} file batches...")
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Check for failures
        jobs_sent = 0
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"Failed to send child job batch {i}: {result}")
                raise result
            jobs_sent += 1

        logger.info(f"Sent {jobs_sent} child jobs to process {total_batches} file batches!")

    async def _send_single_child_job(
        self,
        child_config: GitHubFileBackfillConfig,
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
                f"Sent child job batch {batch_index} with {len(child_config.file_batches)} file batches"
            )
