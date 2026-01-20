import logging

import asyncpg

from connectors.base import TriggerIndexingCallback
from connectors.base.document_source import DocumentSource
from connectors.jira.jira_base import JiraExtractor
from connectors.jira.jira_models import JiraApiBackfillConfig
from src.utils.tenant_config import (
    increment_backfill_attempted_ingest_jobs,
    increment_backfill_done_ingest_jobs,
)

logger = logging.getLogger(__name__)

# Store and trigger indexing in batches of 10 to avoid memory issues
ARTIFACT_BATCH_SIZE = 10


class JiraApiBackfillExtractor(JiraExtractor[JiraApiBackfillConfig]):
    source_name = "jira_api_backfill"

    async def process_job(
        self,
        job_id: str,
        config: JiraApiBackfillConfig,
        db_pool: asyncpg.Pool,
        trigger_indexing: TriggerIndexingCallback,
    ) -> None:
        """Process Jira API backfill job for specified projects."""
        logger.info(
            f"Processing Jira API backfill job {job_id} for tenant {config.tenant_id} "
            f"with {len(config.project_batches)} project batches"
        )

        try:
            jira_client = await self.get_jira_client(config.tenant_id)

            artifact_batch = []
            issue_ids_batch: list[str] = []

            for project_batch in config.project_batches:
                logger.info(
                    f"Processing Jira project: {project_batch.project_name} ({project_batch.project_key})"
                )

                try:
                    cursor = None

                    while True:
                        response = jira_client.get_project_issues(
                            project_key=project_batch.project_key,
                            cursor=cursor,
                        )

                        issues = response.get("issues", [])
                        if not issues:
                            break

                        logger.info(
                            f"Processing {len(issues)} issues from project {project_batch.project_key}"
                        )

                        for issue_data in issues:
                            issue_key = issue_data.get("key", "")
                            try:
                                artifacts = await self._process_issue(
                                    job_id, issue_data, config.tenant_id
                                )

                                artifact_batch.extend(artifacts)
                                issue_id = issue_data.get("id", "")
                                if issue_id:
                                    issue_ids_batch.append(issue_id)

                                if len(artifact_batch) >= ARTIFACT_BATCH_SIZE:
                                    logger.info(
                                        f"Storing batch of {len(artifact_batch)} Jira artifacts"
                                    )
                                    await self.store_artifacts_batch(db_pool, artifact_batch)

                                    if issue_ids_batch:
                                        await trigger_indexing(
                                            issue_ids_batch,
                                            DocumentSource.JIRA,
                                            config.tenant_id,
                                            config.backfill_id,
                                            config.suppress_notification,
                                        )
                                        logger.info(
                                            f"Triggered indexing for batch of {len(issue_ids_batch)} issues"
                                        )

                                    artifact_batch = []
                                    issue_ids_batch = []

                            except Exception as e:
                                logger.error(f"Failed to process issue {issue_key}: {e}")
                                continue

                        cursor = response.get("nextPageToken")
                        if not cursor:
                            break

                except Exception as e:
                    logger.error(f"Failed to process project {project_batch.project_key}: {e}")
                    continue

            if artifact_batch:
                logger.info(f"Storing final batch of {len(artifact_batch)} Jira artifacts")
                await self.store_artifacts_batch(db_pool, artifact_batch)

                if issue_ids_batch:
                    await trigger_indexing(
                        issue_ids_batch,
                        DocumentSource.JIRA,
                        config.tenant_id,
                        config.backfill_id,
                        config.suppress_notification,
                    )
                    logger.info(
                        f"Triggered indexing for final batch of {len(issue_ids_batch)} issues"
                    )

            if config.backfill_id:
                await increment_backfill_done_ingest_jobs(config.backfill_id, config.tenant_id, 1)

        except Exception as e:
            logger.error(f"Jira API backfill job {job_id} failed: {e}")
            raise
        finally:
            if config.backfill_id:
                await increment_backfill_attempted_ingest_jobs(
                    config.backfill_id, config.tenant_id, 1
                )
