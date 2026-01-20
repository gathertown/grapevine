"""GitLab incremental backfill extractors.

These extractors handle incremental sync of MRs and files,
only processing items that have changed since the last sync.
"""

import asyncio
import logging
from uuid import uuid4

import asyncpg

from connectors.base import BaseExtractor, TriggerIndexingCallback
from connectors.gitlab.gitlab_client_factory import get_gitlab_client_for_tenant
from connectors.gitlab.gitlab_models import (
    GitLabFileIncrBackfillProjectConfig,
    GitLabIncrBackfillConfig,
    GitLabMRIncrBackfillProjectConfig,
)
from src.clients.sqs import SQSClient
from src.clients.ssm import SSMClient

logger = logging.getLogger(__name__)

# Maximum concurrent SQS operations
MAX_CONCURRENT_SQS_OPERATIONS = 100


class GitLabIncrBackfillRootExtractor(BaseExtractor[GitLabIncrBackfillConfig]):
    """
    Discovers GitLab projects and sends incremental project jobs for MRs and files.
    """

    source_name = "gitlab_incr_backfill"

    def __init__(self, ssm_client: SSMClient, sqs_client: SQSClient) -> None:
        super().__init__()
        self.ssm_client = ssm_client
        self.sqs_client = sqs_client
        self._sqs_semaphore = asyncio.Semaphore(MAX_CONCURRENT_SQS_OPERATIONS)

    async def process_job(
        self,
        job_id: str,
        config: GitLabIncrBackfillConfig,
        db_pool: asyncpg.Pool,
        trigger_indexing: TriggerIndexingCallback,
    ) -> None:
        backfill_id = config.backfill_id or str(uuid4())

        logger.info(
            f"Processing GitLab incremental backfill root job for tenant {config.tenant_id}, "
            f"backfill_id: {backfill_id}"
        )

        gitlab_client = await get_gitlab_client_for_tenant(
            config.tenant_id, self.ssm_client, per_page=100
        )

        try:
            # Collect projects (same logic as full backfill)
            all_projects: list[dict[str, int | str]] = []

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

            else:
                logger.info("No specific projects or groups specified, discovering all accessible")
                accessible_projects = await gitlab_client.get_accessible_projects(
                    membership=True,
                    archived=False,
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

            # Send incremental project jobs for MRs and files
            if all_projects:
                await self._send_incr_project_jobs(config, all_projects, backfill_id)

            logger.info(f"Successfully completed incremental root job {job_id}")

        finally:
            await gitlab_client.aclose()

    async def _send_incr_project_jobs(
        self,
        config: GitLabIncrBackfillConfig,
        projects: list[dict[str, int | str]],
        backfill_id: str,
    ) -> None:
        """Send incremental project jobs for both MRs and files."""
        tasks = []

        for i, project in enumerate(projects):
            # MR incremental job
            mr_config = GitLabMRIncrBackfillProjectConfig(
                tenant_id=config.tenant_id,
                project_id=int(project["id"]),
                project_path=str(project["path_with_namespace"]),
                backfill_id=backfill_id,
                suppress_notification=config.suppress_notification,
            )
            tasks.append(self._send_single_job(mr_config, i, "MR incr"))

            # File incremental job
            file_config = GitLabFileIncrBackfillProjectConfig(
                tenant_id=config.tenant_id,
                project_id=int(project["id"]),
                project_path=str(project["path_with_namespace"]),
                backfill_id=backfill_id,
                suppress_notification=config.suppress_notification,
            )
            tasks.append(self._send_single_job(file_config, i, "file incr"))

        logger.info(f"Sending {len(tasks)} incremental project jobs...")
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"Failed to send incremental job {i}: {result}")
                raise result

        logger.info(f"Sent {len(tasks)} incremental project jobs!")

    async def _send_single_job(
        self,
        project_config: GitLabMRIncrBackfillProjectConfig | GitLabFileIncrBackfillProjectConfig,
        project_index: int,
        job_type: str,
    ) -> None:
        """Send a single project job to SQS."""
        async with self._sqs_semaphore:
            success = await self.sqs_client.send_backfill_ingest_message(
                backfill_config=project_config,
            )

            if not success:
                raise RuntimeError(f"Failed to send {job_type} job {project_index} to SQS")

            if project_index % 10 == 0:
                logger.info(f"Sent {job_type} job {project_index}: {project_config.project_path}")
