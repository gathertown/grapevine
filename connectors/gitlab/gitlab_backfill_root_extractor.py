"""GitLab backfill root extractor.

This extractor discovers all accessible GitLab projects and sends
project-level jobs to enumerate MRs and code files.
"""

import asyncio
import logging
from uuid import uuid4

import asyncpg

from connectors.base import BaseExtractor, TriggerIndexingCallback
from connectors.gitlab.gitlab_client_factory import get_gitlab_client_for_tenant
from connectors.gitlab.gitlab_models import (
    GitLabBackfillRootConfig,
    GitLabFileBackfillProjectConfig,
    GitLabMRBackfillProjectConfig,
)
from src.clients.sqs import SQSClient
from src.clients.ssm import SSMClient

logger = logging.getLogger(__name__)

# Maximum concurrent SQS operations
MAX_CONCURRENT_SQS_OPERATIONS = 100


class GitLabBackfillRootExtractor(BaseExtractor[GitLabBackfillRootConfig]):
    """
    Discovers GitLab projects and sends project jobs to enumerate MRs and files for each project.
    """

    source_name = "gitlab_backfill_root"

    def __init__(self, ssm_client: SSMClient, sqs_client: SQSClient) -> None:
        super().__init__()
        self.ssm_client = ssm_client
        self.sqs_client = sqs_client
        # Semaphore to limit concurrent SQS operations
        self._sqs_semaphore = asyncio.Semaphore(MAX_CONCURRENT_SQS_OPERATIONS)

    async def process_job(
        self,
        job_id: str,
        config: GitLabBackfillRootConfig,
        db_pool: asyncpg.Pool,
        trigger_indexing: TriggerIndexingCallback,
    ) -> None:
        # Generate backfill_id for tracking if not provided
        backfill_id = config.backfill_id or str(uuid4())

        logger.info(
            f"Processing GitLab backfill root job for tenant {config.tenant_id}, "
            f"backfill_id: {backfill_id}"
        )

        # Get GitLab client for this tenant
        gitlab_client = await get_gitlab_client_for_tenant(
            config.tenant_id, self.ssm_client, per_page=100
        )

        try:
            # Collect all projects to process
            all_projects: list[dict[str, int | str]] = []

            # If specific projects are specified, use those
            if config.projects:
                for project_path in config.projects:
                    try:
                        project = await gitlab_client.get_project(project_path)
                        all_projects.append(
                            {
                                "id": project["id"],
                                "path_with_namespace": project["path_with_namespace"],
                            }
                        )
                        logger.info(f"Added specified project: {project['path_with_namespace']}")
                    except Exception as e:
                        logger.error(f"Failed to get project {project_path}: {e}")

            # If specific groups are specified, get their projects
            elif config.groups:
                for group_path in config.groups:
                    try:
                        group_projects = await gitlab_client.get_group_projects(group_path)
                        for project in group_projects:
                            if project["id"] not in [p["id"] for p in all_projects]:
                                all_projects.append(
                                    {
                                        "id": project["id"],
                                        "path_with_namespace": project["path_with_namespace"],
                                    }
                                )
                        logger.info(f"Found {len(group_projects)} projects in group {group_path}")
                    except Exception as e:
                        logger.error(f"Failed to get projects for group {group_path}: {e}")

            # Otherwise, discover all accessible projects
            else:
                logger.info(
                    "No specific projects or groups specified, discovering all accessible projects"
                )
                accessible_projects = await gitlab_client.get_accessible_projects(
                    membership=True,
                    archived=False,
                    # Only get projects where user has at least Reporter access (can see MRs)
                    min_access_level=20,
                )
                for project in accessible_projects:
                    all_projects.append(
                        {
                            "id": project["id"],
                            "path_with_namespace": project["path_with_namespace"],
                        }
                    )
                logger.info(f"Discovered {len(accessible_projects)} accessible projects")

            logger.info(f"Total projects to process: {len(all_projects)}")

            # Send project jobs for each project (both MR and file jobs)
            if all_projects:
                await self._send_mr_project_jobs(config, all_projects, backfill_id)
                logger.info(f"Sent MR project jobs for {len(all_projects)} projects")

                await self._send_file_project_jobs(config, all_projects, backfill_id)
                logger.info(f"Sent file project jobs for {len(all_projects)} projects")

            logger.info(f"Successfully completed root job {job_id}")

        finally:
            await gitlab_client.aclose()

    async def _send_mr_project_jobs(
        self,
        config: GitLabBackfillRootConfig,
        projects: list[dict[str, int | str]],
        backfill_id: str,
    ) -> None:
        """Send MR project jobs for each project to enumerate MRs."""
        total_projects = len(projects)
        logger.info(f"Preparing to send MR project jobs for {total_projects} projects")

        # Create all project job tasks
        tasks = []
        for i, project in enumerate(projects):
            project_config = GitLabMRBackfillProjectConfig(
                tenant_id=config.tenant_id,
                project_id=int(project["id"]),
                project_path=str(project["path_with_namespace"]),
                backfill_id=backfill_id,
                suppress_notification=config.suppress_notification,
            )

            # Create task to send this project job
            task = self._send_single_backfill_job(project_config, i, "MR")
            tasks.append(task)

        # Send all project jobs in parallel
        logger.info(f"Sending {len(tasks)} MR project jobs for {total_projects} projects...")
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Check for failures
        jobs_sent = 0
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"Failed to send MR project job {i}: {result}")
                raise result
            jobs_sent += 1

        logger.info(f"Sent {jobs_sent} MR project jobs for {total_projects} projects!")

    async def _send_file_project_jobs(
        self,
        config: GitLabBackfillRootConfig,
        projects: list[dict[str, int | str]],
        backfill_id: str,
    ) -> None:
        """Send file project jobs for each project to enumerate files."""
        total_projects = len(projects)
        logger.info(f"Preparing to send file project jobs for {total_projects} projects")

        # Create all project job tasks
        tasks = []
        for i, project in enumerate(projects):
            project_config = GitLabFileBackfillProjectConfig(
                tenant_id=config.tenant_id,
                project_id=int(project["id"]),
                project_path=str(project["path_with_namespace"]),
                backfill_id=backfill_id,
                suppress_notification=config.suppress_notification,
            )

            # Create task to send this project job
            task = self._send_single_backfill_job(project_config, i, "file")
            tasks.append(task)

        # Send all project jobs in parallel
        logger.info(f"Sending {len(tasks)} file project jobs for {total_projects} projects...")
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Check for failures
        jobs_sent = 0
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"Failed to send file project job {i}: {result}")
                raise result
            jobs_sent += 1

        logger.info(f"Sent {jobs_sent} file project jobs for {total_projects} projects!")

    async def _send_single_backfill_job(
        self,
        project_config: GitLabMRBackfillProjectConfig | GitLabFileBackfillProjectConfig,
        project_index: int,
        job_type: str,
    ) -> None:
        """Send a single project backfill job message to SQS."""
        # Use semaphore to limit concurrent SQS operations
        async with self._sqs_semaphore:
            success = await self.sqs_client.send_backfill_ingest_message(
                backfill_config=project_config,
            )

            if not success:
                raise RuntimeError(f"Failed to send {job_type} project job {project_index} to SQS")

            log = logger.info if project_index % 10 == 0 else logger.debug
            log(
                f"Sent {job_type} project job {project_index} for project {project_config.project_path}"
            )
