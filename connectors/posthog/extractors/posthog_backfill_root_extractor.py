"""Root extractor for PostHog full backfill.

Orchestrates the full backfill by:
1. Setting incremental sync cursors to "now"
2. Collecting all accessible projects
3. Enqueuing project-specific backfill jobs
"""

import secrets
from datetime import UTC, datetime
from uuid import UUID

import asyncpg

from connectors.base import BaseExtractor, TriggerIndexingCallback
from connectors.base.document_source import DocumentSource
from connectors.posthog.client import get_posthog_client_for_tenant
from connectors.posthog.posthog_models import (
    PostHogAnnotationArtifact,
    PostHogBackfillRootConfig,
    PostHogDashboardArtifact,
    PostHogExperimentArtifact,
    PostHogFeatureFlagArtifact,
    PostHogInsightArtifact,
    PostHogProjectBackfillConfig,
    PostHogSurveyArtifact,
)
from connectors.posthog.posthog_sync_service import PostHogSyncService
from src.clients.sqs import SQSClient
from src.utils.logging import get_logger
from src.utils.tenant_config import increment_backfill_total_ingest_jobs

logger = get_logger(__name__)


class PostHogBackfillRootExtractor(BaseExtractor[PostHogBackfillRootConfig]):
    """Root extractor that discovers all projects and splits into project jobs.

    This extractor:
    1. Sets incremental sync cursors to "now" (so incremental picks up changes during backfill)
    2. Discovers all accessible projects
    3. Enqueues child jobs for each project
    """

    source_name = "posthog_backfill_root"

    def __init__(self, sqs_client: SQSClient):
        super().__init__()
        self.sqs_client = sqs_client

    async def process_job(
        self,
        job_id: str,
        config: PostHogBackfillRootConfig,
        db_pool: asyncpg.Pool,
        trigger_indexing: TriggerIndexingCallback,
    ) -> None:
        backfill_id = config.backfill_id or secrets.token_hex(8)
        tenant_id = config.tenant_id

        logger.info(
            "Starting PostHog backfill root job",
            backfill_id=backfill_id,
            tenant_id=tenant_id,
            project_ids_to_sync=config.project_ids_to_sync,
        )

        # Initialize services
        sync_service = PostHogSyncService(db_pool, tenant_id)

        # Step 1: Set incremental sync cursor to "now"
        sync_start_time = datetime.now(UTC)
        await sync_service.set_last_synced_at(sync_start_time)

        logger.info(
            "Set incremental sync cursor",
            tenant_id=tenant_id,
            sync_start_time=sync_start_time.isoformat(),
        )

        # Step 2: Determine which project IDs to sync
        if config.project_ids_to_sync:
            project_ids = config.project_ids_to_sync
            logger.info(
                "Syncing specific projects from config",
                tenant_id=tenant_id,
                project_ids=project_ids,
            )
        else:
            # Get selected projects from connector metadata, or discover all
            selected_ids = await sync_service.get_selected_project_ids()
            if selected_ids:
                project_ids = selected_ids
                logger.info(
                    "Syncing selected projects",
                    tenant_id=tenant_id,
                    project_ids=project_ids,
                )
            else:
                # Discover all accessible projects
                try:
                    async with await get_posthog_client_for_tenant(tenant_id) as client:
                        projects = await client.get_projects()
                        project_ids = [p.id for p in projects]
                        logger.info(
                            "Discovered all accessible projects",
                            tenant_id=tenant_id,
                            project_count=len(project_ids),
                        )
                except Exception as e:
                    logger.error(f"Failed to get PostHog client: {e}")
                    raise

        if not project_ids:
            logger.warning(
                "No project IDs found for PostHog backfill",
                tenant_id=tenant_id,
            )
            return

        # Track total jobs for backfill progress tracking
        total_jobs = len(project_ids)
        await increment_backfill_total_ingest_jobs(backfill_id, tenant_id, total_jobs)

        # Step 3: Schedule project jobs
        for project_id in project_ids:
            project_config = PostHogProjectBackfillConfig(
                tenant_id=tenant_id,
                project_id=project_id,
                backfill_id=backfill_id,
            )

            await self.sqs_client.send_backfill_ingest_message(project_config)

        logger.info(
            "PostHog root backfill complete - project jobs enqueued",
            tenant_id=tenant_id,
            backfill_id=backfill_id,
            total_projects=total_jobs,
        )


class PostHogProjectBackfillExtractor(BaseExtractor[PostHogProjectBackfillConfig]):
    """Extractor that backfills all data from a single PostHog project."""

    source_name = "posthog_project_backfill"

    async def process_job(
        self,
        job_id: str,
        config: PostHogProjectBackfillConfig,
        db_pool: asyncpg.Pool,
        trigger_indexing: TriggerIndexingCallback,
    ) -> None:
        tenant_id = config.tenant_id
        project_id = config.project_id
        backfill_id = config.backfill_id
        ingest_job_id = UUID(job_id)

        logger.info(
            "Starting PostHog project backfill",
            tenant_id=tenant_id,
            project_id=project_id,
            backfill_id=backfill_id,
        )

        sync_service = PostHogSyncService(db_pool, tenant_id)

        try:
            async with await get_posthog_client_for_tenant(tenant_id) as client:
                # Fetch and store dashboards
                dashboard_entity_ids = await self._process_dashboards(
                    client, project_id, ingest_job_id, db_pool
                )

                # Fetch and store insights
                insight_entity_ids = await self._process_insights(
                    client, project_id, ingest_job_id, db_pool
                )

                # Fetch and store feature flags
                feature_flag_entity_ids = await self._process_feature_flags(
                    client, project_id, ingest_job_id, db_pool
                )

                # Fetch and store annotations
                annotation_entity_ids = await self._process_annotations(
                    client, project_id, ingest_job_id, db_pool
                )

                # Fetch and store experiments
                experiment_entity_ids = await self._process_experiments(
                    client, project_id, ingest_job_id, db_pool
                )

                # Fetch and store surveys
                survey_entity_ids = await self._process_surveys(
                    client, project_id, ingest_job_id, db_pool
                )

        except Exception as e:
            logger.error(
                f"Failed to backfill PostHog project {project_id}: {e}",
                tenant_id=tenant_id,
            )
            raise

        # Trigger indexing for all entity types
        if dashboard_entity_ids:
            await trigger_indexing(
                dashboard_entity_ids,
                DocumentSource.POSTHOG_DASHBOARD,
                tenant_id,
                backfill_id,
            )

        if insight_entity_ids:
            await trigger_indexing(
                insight_entity_ids,
                DocumentSource.POSTHOG_INSIGHT,
                tenant_id,
                backfill_id,
            )

        if feature_flag_entity_ids:
            await trigger_indexing(
                feature_flag_entity_ids,
                DocumentSource.POSTHOG_FEATURE_FLAG,
                tenant_id,
                backfill_id,
            )

        if annotation_entity_ids:
            await trigger_indexing(
                annotation_entity_ids,
                DocumentSource.POSTHOG_ANNOTATION,
                tenant_id,
                backfill_id,
            )

        if experiment_entity_ids:
            await trigger_indexing(
                experiment_entity_ids,
                DocumentSource.POSTHOG_EXPERIMENT,
                tenant_id,
                backfill_id,
            )

        if survey_entity_ids:
            await trigger_indexing(
                survey_entity_ids,
                DocumentSource.POSTHOG_SURVEY,
                tenant_id,
                backfill_id,
            )

        # Mark project as synced
        await sync_service.add_synced_project_ids([project_id])

        logger.info(
            "PostHog project backfill complete",
            tenant_id=tenant_id,
            project_id=project_id,
            dashboards=len(dashboard_entity_ids),
            insights=len(insight_entity_ids),
            feature_flags=len(feature_flag_entity_ids),
            annotations=len(annotation_entity_ids),
            experiments=len(experiment_entity_ids),
            surveys=len(survey_entity_ids),
        )

    async def _process_dashboards(
        self,
        client,
        project_id: int,
        ingest_job_id: UUID,
        db_pool: asyncpg.Pool,
    ) -> list[str]:
        """Fetch and store all dashboards for a project."""
        try:
            dashboards = await client.get_dashboards(project_id)
            logger.info(f"Fetched {len(dashboards)} dashboards from project {project_id}")

            artifacts = []
            for dashboard in dashboards:
                artifact = PostHogDashboardArtifact.from_api_response(
                    dashboard.model_dump(),
                    project_id=project_id,
                    ingest_job_id=ingest_job_id,
                )
                artifacts.append(artifact)

            if artifacts:
                await self.store_artifacts_batch(db_pool, artifacts)

            return [a.entity_id for a in artifacts]

        except Exception as e:
            logger.error(f"Failed to process dashboards for project {project_id}: {e}")
            return []

    async def _process_insights(
        self,
        client,
        project_id: int,
        ingest_job_id: UUID,
        db_pool: asyncpg.Pool,
    ) -> list[str]:
        """Fetch and store all insights for a project."""
        try:
            insights = await client.get_insights(project_id, saved_only=True)
            logger.info(f"Fetched {len(insights)} insights from project {project_id}")

            artifacts = []
            for insight in insights:
                artifact = PostHogInsightArtifact.from_api_response(
                    insight.model_dump(),
                    project_id=project_id,
                    ingest_job_id=ingest_job_id,
                )
                artifacts.append(artifact)

            if artifacts:
                await self.store_artifacts_batch(db_pool, artifacts)

            return [a.entity_id for a in artifacts]

        except Exception as e:
            logger.error(f"Failed to process insights for project {project_id}: {e}")
            return []

    async def _process_feature_flags(
        self,
        client,
        project_id: int,
        ingest_job_id: UUID,
        db_pool: asyncpg.Pool,
    ) -> list[str]:
        """Fetch and store all feature flags for a project."""
        try:
            flags = await client.get_feature_flags(project_id)
            logger.info(f"Fetched {len(flags)} feature flags from project {project_id}")

            artifacts = []
            for flag in flags:
                artifact = PostHogFeatureFlagArtifact.from_api_response(
                    flag.model_dump(),
                    project_id=project_id,
                    ingest_job_id=ingest_job_id,
                )
                artifacts.append(artifact)

            if artifacts:
                await self.store_artifacts_batch(db_pool, artifacts)

            return [a.entity_id for a in artifacts]

        except Exception as e:
            logger.error(f"Failed to process feature flags for project {project_id}: {e}")
            return []

    async def _process_annotations(
        self,
        client,
        project_id: int,
        ingest_job_id: UUID,
        db_pool: asyncpg.Pool,
    ) -> list[str]:
        """Fetch and store all annotations for a project."""
        try:
            annotations = await client.get_annotations(project_id)
            logger.info(f"Fetched {len(annotations)} annotations from project {project_id}")

            artifacts = []
            for annotation in annotations:
                artifact = PostHogAnnotationArtifact.from_api_response(
                    annotation.model_dump(),
                    project_id=project_id,
                    ingest_job_id=ingest_job_id,
                )
                artifacts.append(artifact)

            if artifacts:
                await self.store_artifacts_batch(db_pool, artifacts)

            return [a.entity_id for a in artifacts]

        except Exception as e:
            logger.error(f"Failed to process annotations for project {project_id}: {e}")
            return []

    async def _process_experiments(
        self,
        client,
        project_id: int,
        ingest_job_id: UUID,
        db_pool: asyncpg.Pool,
    ) -> list[str]:
        """Fetch and store all experiments for a project."""
        try:
            experiments = await client.get_experiments(project_id)
            logger.info(f"Fetched {len(experiments)} experiments from project {project_id}")

            artifacts = []
            for experiment in experiments:
                artifact = PostHogExperimentArtifact.from_api_response(
                    experiment.model_dump(),
                    project_id=project_id,
                    ingest_job_id=ingest_job_id,
                )
                artifacts.append(artifact)

            if artifacts:
                await self.store_artifacts_batch(db_pool, artifacts)

            return [a.entity_id for a in artifacts]

        except Exception as e:
            logger.error(f"Failed to process experiments for project {project_id}: {e}")
            return []

    async def _process_surveys(
        self,
        client,
        project_id: int,
        ingest_job_id: UUID,
        db_pool: asyncpg.Pool,
    ) -> list[str]:
        """Fetch and store all surveys for a project."""
        try:
            surveys = await client.get_surveys(project_id)
            logger.info(f"Fetched {len(surveys)} surveys from project {project_id}")

            artifacts = []
            for survey in surveys:
                artifact = PostHogSurveyArtifact.from_api_response(
                    survey.model_dump(),
                    project_id=project_id,
                    ingest_job_id=ingest_job_id,
                )
                artifacts.append(artifact)

            if artifacts:
                await self.store_artifacts_batch(db_pool, artifacts)

            return [a.entity_id for a in artifacts]

        except Exception as e:
            logger.error(f"Failed to process surveys for project {project_id}: {e}")
            return []
