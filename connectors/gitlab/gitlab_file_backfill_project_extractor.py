"""GitLab file backfill project extractor.

This extractor enumerates all files in a project and sends batch jobs
to process them.
"""

import asyncio
import logging

import asyncpg

from connectors.base import BaseExtractor, TriggerIndexingCallback
from connectors.gitlab.gitlab_client_factory import get_gitlab_client_for_tenant
from connectors.gitlab.gitlab_models import (
    GitLabFileBackfillConfig,
    GitLabFileBackfillProjectConfig,
    GitLabFileBatch,
)
from connectors.gitlab.gitlab_sync_service import GitLabSyncService
from src.clients.sqs import SQSClient
from src.clients.ssm import SSMClient

logger = logging.getLogger(__name__)

# Number of files per child job
CHILD_JOB_BATCH_SIZE = 50

# Maximum concurrent SQS operations
MAX_CONCURRENT_SQS_OPERATIONS = 100

# File extensions to include in backfill
# Based on common code file extensions
SUPPORTED_EXTENSIONS = {
    # Programming languages
    ".py",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".mjs",
    ".cjs",
    ".java",
    ".kt",
    ".kts",
    ".scala",
    ".go",
    ".rs",
    ".rb",
    ".php",
    ".c",
    ".h",
    ".cpp",
    ".cc",
    ".cxx",
    ".hpp",
    ".cs",
    ".swift",
    ".m",
    ".mm",
    # Web/markup
    ".html",
    ".htm",
    ".css",
    ".scss",
    ".sass",
    ".less",
    ".vue",
    ".svelte",
    # Data/config
    ".json",
    ".yaml",
    ".yml",
    ".toml",
    ".xml",
    ".ini",
    ".cfg",
    ".conf",
    # Documentation
    ".md",
    ".mdx",
    ".rst",
    ".txt",
    # Shell/scripting
    ".sh",
    ".bash",
    ".zsh",
    ".ps1",
    ".bat",
    ".cmd",
    # Other
    ".sql",
    ".graphql",
    ".gql",
    ".proto",
    ".tf",
    ".hcl",
}


class GitLabFileBackfillProjectExtractor(BaseExtractor[GitLabFileBackfillProjectConfig]):
    """
    Extracts GitLab files from a single project and sends child jobs to process them.
    This is an intermediate job between root and leaf jobs.
    """

    source_name = "gitlab_file_backfill_project"

    def __init__(self, ssm_client: SSMClient, sqs_client: SQSClient) -> None:
        super().__init__()
        self.ssm_client = ssm_client
        self.sqs_client = sqs_client
        # Semaphore to limit concurrent SQS operations
        self._sqs_semaphore = asyncio.Semaphore(MAX_CONCURRENT_SQS_OPERATIONS)

    async def process_job(
        self,
        job_id: str,
        config: GitLabFileBackfillProjectConfig,
        db_pool: asyncpg.Pool,
        trigger_indexing: TriggerIndexingCallback,
    ) -> None:
        logger.info(
            f"Processing GitLab file project backfill job for tenant {config.tenant_id}, "
            f"project: {config.project_path}"
        )

        # Get GitLab client for this tenant
        gitlab_client = await get_gitlab_client_for_tenant(
            config.tenant_id, self.ssm_client, per_page=100
        )

        sync_service = GitLabSyncService(db_pool)

        try:
            # Get project info to determine default branch
            default_branch = await gitlab_client.get_default_branch(config.project_id)
            logger.info(f"Using default branch '{default_branch}' for {config.project_path}")

            # Get the latest commit SHA on the default branch for the sync cursor
            # Any commits after this will be picked up by incremental sync
            latest_commit_sha = None
            try:
                commits = await gitlab_client.get_repository_commits(
                    config.project_id, ref=default_branch
                )
                if commits:
                    latest_commit_sha = commits[0].get("id")
                    logger.info(f"Latest commit on {default_branch}: {latest_commit_sha}")
            except Exception as e:
                logger.warning(f"Could not get latest commit for sync cursor: {e}")

            # Enumerate all files for this project
            file_batches = await self._enumerate_files_for_project(
                gitlab_client, config.project_id, config.project_path, default_branch
            )

            logger.info(
                f"Project job {job_id} found {len(file_batches)} file batches "
                f"for {config.project_path}"
            )

            # Send child jobs for file processing
            if file_batches:
                await self._send_child_jobs(config, file_batches)
                logger.info(f"Sent child jobs for {len(file_batches)} file batches")

            # Set the file sync cursor so incremental sync knows where to start
            # This enables hourly incremental syncs to work after full backfill
            if latest_commit_sha:
                await sync_service.set_file_synced_commit(config.project_id, latest_commit_sha)
                logger.info(
                    f"Set file sync cursor for project {config.project_id} to {latest_commit_sha}"
                )

            logger.info(
                f"Successfully completed file project job {job_id} for {config.project_path}"
            )

        finally:
            await gitlab_client.aclose()

    async def _enumerate_files_for_project(
        self,
        gitlab_client,
        project_id: int,
        project_path: str,
        branch: str,
    ) -> list[GitLabFileBatch]:
        """Enumerate all files for a single project and create batches."""
        file_batches = []

        logger.info(f"Enumerating files for project: {project_path}")

        # Get repository tree recursively
        try:
            tree_items = await gitlab_client.get_repository_tree(
                project_id,
                path="",
                ref=branch,
                recursive=True,
            )
        except Exception as e:
            logger.warning(f"Failed to get repository tree for {project_path}: {e}")
            return []

        # Filter to only include supported file types
        file_paths = []
        for item in tree_items:
            if item.get("type") != "blob":
                continue

            file_path = item.get("path", "")
            ext = self._get_extension(file_path)
            if ext in SUPPORTED_EXTENSIONS:
                file_paths.append(file_path)

        logger.info(
            f"Found {len(file_paths)} supported files out of {len(tree_items)} "
            f"items in {project_path}"
        )

        # Split files into batches
        for i in range(0, len(file_paths), CHILD_JOB_BATCH_SIZE):
            batch_file_paths = file_paths[i : i + CHILD_JOB_BATCH_SIZE]

            file_batch = GitLabFileBatch(
                project_id=project_id,
                project_path=project_path,
                file_paths=batch_file_paths,
                branch=branch,
            )

            file_batches.append(file_batch)

        return file_batches

    def _get_extension(self, file_path: str) -> str:
        """Get file extension in lowercase."""
        if "." not in file_path:
            return ""
        return "." + file_path.rsplit(".", 1)[-1].lower()

    async def _send_child_jobs(
        self, config: GitLabFileBackfillProjectConfig, file_batches: list[GitLabFileBatch]
    ) -> None:
        """Send child jobs to process file batches."""
        total_batches = len(file_batches)
        logger.info(f"Preparing to send child jobs for {total_batches} file batches")

        # Create all child job tasks
        tasks = []
        for i, file_batch in enumerate(file_batches):
            child_config = GitLabFileBackfillConfig(
                tenant_id=config.tenant_id,
                file_batches=[file_batch],
                backfill_id=config.backfill_id,
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
        child_config: GitLabFileBackfillConfig,
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
                f"Sent child job batch {batch_index} with {len(child_config.file_batches)} "
                f"file batches"
            )
