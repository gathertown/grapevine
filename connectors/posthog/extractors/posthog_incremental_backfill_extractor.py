"""Incremental backfill extractor for PostHog.

Uses timestamp-based filtering to sync only recently modified records.
Scheduled via cron every 30 minutes.
"""

from datetime import UTC, datetime, timedelta
from uuid import UUID

import asyncpg

from connectors.base import BaseExtractor, TriggerIndexingCallback
from connectors.base.document_source import DocumentSource
from connectors.posthog.client import get_posthog_client_for_tenant
from connectors.posthog.posthog_models import (
    PostHogAnnotationArtifact,
    PostHogDashboardArtifact,
    PostHogExperimentArtifact,
    PostHogFeatureFlagArtifact,
    PostHogIncrementalBackfillConfig,
    PostHogInsightArtifact,
    PostHogSurveyArtifact,
)
from connectors.posthog.posthog_sync_service import PostHogSyncService
from src.clients.ssm import SSMClient
from src.ingest.utils import DEFAULT_INDEX_BATCH_SIZE
from src.utils.logging import get_logger

logger = get_logger(__name__)

# Default lookback window (24 hours)
DEFAULT_LOOKBACK_HOURS = 24


class PostHogIncrementalBackfillExtractor(BaseExtractor[PostHogIncrementalBackfillConfig]):
    """Extracts recently modified PostHog entities.

    Syncs dashboards, insights, feature flags, annotations, experiments, and surveys
    that have been updated since the last sync.
    """

    source_name = "posthog_incremental_backfill"

    def __init__(self, ssm_client: SSMClient):
        super().__init__()
        self.ssm_client = ssm_client

    async def process_job(
        self,
        job_id: str,
        config: PostHogIncrementalBackfillConfig,
        db_pool: asyncpg.Pool,
        trigger_indexing: TriggerIndexingCallback,
    ) -> None:
        """Execute the incremental backfill job."""
        tenant_id = config.tenant_id
        lookback_hours = config.lookback_hours or DEFAULT_LOOKBACK_HOURS

        logger.info(
            "Starting PostHog incremental backfill",
            tenant_id=tenant_id,
            lookback_hours=lookback_hours,
        )

        # Initialize services
        client = await get_posthog_client_for_tenant(tenant_id)
        sync_service = PostHogSyncService(db_pool, tenant_id)

        try:
            # Calculate the lookback timestamp for first run
            default_lookback = datetime.now(UTC) - timedelta(hours=lookback_hours)

            # Get sync cursor - use stored cursor if available, otherwise use default
            last_synced = await sync_service.get_last_synced_at() or default_lookback

            # Track sync time BEFORE fetching (to handle changes during sync)
            sync_time = datetime.now(UTC)

            # Get selected project IDs
            project_ids = await sync_service.get_selected_project_ids()
            if not project_ids:
                # If no projects selected, get all accessible projects
                projects = await client.get_projects()
                project_ids = [p.id for p in projects]

            if not project_ids:
                logger.warning("No PostHog projects found for incremental backfill")
                return

            # Sync all entity types for each project
            total_synced = 0
            all_entity_ids: dict[DocumentSource, list[str]] = {
                DocumentSource.POSTHOG_DASHBOARD: [],
                DocumentSource.POSTHOG_INSIGHT: [],
                DocumentSource.POSTHOG_FEATURE_FLAG: [],
                DocumentSource.POSTHOG_ANNOTATION: [],
                DocumentSource.POSTHOG_EXPERIMENT: [],
                DocumentSource.POSTHOG_SURVEY: [],
            }

            for project_id in project_ids:
                # Sync dashboards
                count, entity_ids = await self._sync_dashboards(
                    client, db_pool, UUID(job_id), project_id, last_synced
                )
                total_synced += count
                all_entity_ids[DocumentSource.POSTHOG_DASHBOARD].extend(entity_ids)

                # Sync insights
                count, entity_ids = await self._sync_insights(
                    client, db_pool, UUID(job_id), project_id, last_synced
                )
                total_synced += count
                all_entity_ids[DocumentSource.POSTHOG_INSIGHT].extend(entity_ids)

                # Sync feature flags
                count, entity_ids = await self._sync_feature_flags(
                    client, db_pool, UUID(job_id), project_id, last_synced
                )
                total_synced += count
                all_entity_ids[DocumentSource.POSTHOG_FEATURE_FLAG].extend(entity_ids)

                # Sync annotations
                count, entity_ids = await self._sync_annotations(
                    client, db_pool, UUID(job_id), project_id, last_synced
                )
                total_synced += count
                all_entity_ids[DocumentSource.POSTHOG_ANNOTATION].extend(entity_ids)

                # Sync experiments
                count, entity_ids = await self._sync_experiments(
                    client, db_pool, UUID(job_id), project_id, last_synced
                )
                total_synced += count
                all_entity_ids[DocumentSource.POSTHOG_EXPERIMENT].extend(entity_ids)

                # Sync surveys
                count, entity_ids = await self._sync_surveys(
                    client, db_pool, UUID(job_id), project_id, last_synced
                )
                total_synced += count
                all_entity_ids[DocumentSource.POSTHOG_SURVEY].extend(entity_ids)

            # Trigger indexing for all synced entities
            for source, entity_ids in all_entity_ids.items():
                if entity_ids:
                    for i in range(0, len(entity_ids), DEFAULT_INDEX_BATCH_SIZE):
                        batch = entity_ids[i : i + DEFAULT_INDEX_BATCH_SIZE]
                        await trigger_indexing(
                            batch,
                            source,
                            tenant_id,
                            config.backfill_id,
                            config.suppress_notification,
                        )

            # Update sync cursor with overlap (subtract 1 second to handle boundary)
            cursor_time = sync_time - timedelta(seconds=1)
            await sync_service.set_last_synced_at(cursor_time)

            logger.info(
                "Completed PostHog incremental backfill",
                tenant_id=tenant_id,
                total_synced=total_synced,
                next_sync_cursor=cursor_time.isoformat(),
            )

        finally:
            await client.close()

    async def _sync_dashboards(
        self,
        client,
        db_pool: asyncpg.Pool,
        job_id: UUID,
        project_id: int,
        since: datetime,
    ) -> tuple[int, list[str]]:
        """Sync dashboards updated since the given timestamp."""
        artifacts: list[PostHogDashboardArtifact] = []
        entity_ids: list[str] = []

        try:
            dashboards = await client.get_dashboards(project_id)
            for dashboard in dashboards:
                # Check if updated since last sync
                updated_at_str = dashboard.updated_at or dashboard.created_at
                if updated_at_str:
                    try:
                        updated_at = datetime.fromisoformat(updated_at_str.replace("Z", "+00:00"))
                        if updated_at < since:
                            continue
                    except (ValueError, TypeError):
                        pass

                artifact = PostHogDashboardArtifact.from_api_response(
                    dashboard_data=dashboard.model_dump(),
                    project_id=project_id,
                    ingest_job_id=job_id,
                )
                artifacts.append(artifact)
                entity_ids.append(artifact.entity_id)

        except Exception as e:
            logger.warning(f"Failed to sync dashboards for project {project_id}: {e}")

        if artifacts:
            await self.store_artifacts_batch(db_pool, artifacts)

        return len(artifacts), entity_ids

    async def _sync_insights(
        self,
        client,
        db_pool: asyncpg.Pool,
        job_id: UUID,
        project_id: int,
        since: datetime,
    ) -> tuple[int, list[str]]:
        """Sync insights updated since the given timestamp."""
        artifacts: list[PostHogInsightArtifact] = []
        entity_ids: list[str] = []

        try:
            insights = await client.get_insights(project_id)
            for insight in insights:
                # Check if updated since last sync
                updated_at_str = (
                    insight.last_modified_at or insight.updated_at or insight.created_at
                )
                if updated_at_str:
                    try:
                        updated_at = datetime.fromisoformat(updated_at_str.replace("Z", "+00:00"))
                        if updated_at < since:
                            continue
                    except (ValueError, TypeError):
                        pass

                artifact = PostHogInsightArtifact.from_api_response(
                    insight_data=insight.model_dump(),
                    project_id=project_id,
                    ingest_job_id=job_id,
                )
                artifacts.append(artifact)
                entity_ids.append(artifact.entity_id)

        except Exception as e:
            logger.warning(f"Failed to sync insights for project {project_id}: {e}")

        if artifacts:
            await self.store_artifacts_batch(db_pool, artifacts)

        return len(artifacts), entity_ids

    async def _sync_feature_flags(
        self,
        client,
        db_pool: asyncpg.Pool,
        job_id: UUID,
        project_id: int,
        since: datetime,
    ) -> tuple[int, list[str]]:
        """Sync feature flags updated since the given timestamp."""
        artifacts: list[PostHogFeatureFlagArtifact] = []
        entity_ids: list[str] = []

        try:
            flags = await client.get_feature_flags(project_id)
            for flag in flags:
                # Check if updated since last sync
                updated_at_str = flag.updated_at or flag.created_at
                if updated_at_str:
                    try:
                        updated_at = datetime.fromisoformat(updated_at_str.replace("Z", "+00:00"))
                        if updated_at < since:
                            continue
                    except (ValueError, TypeError):
                        pass

                artifact = PostHogFeatureFlagArtifact.from_api_response(
                    flag_data=flag.model_dump(),
                    project_id=project_id,
                    ingest_job_id=job_id,
                )
                artifacts.append(artifact)
                entity_ids.append(artifact.entity_id)

        except Exception as e:
            logger.warning(f"Failed to sync feature flags for project {project_id}: {e}")

        if artifacts:
            await self.store_artifacts_batch(db_pool, artifacts)

        return len(artifacts), entity_ids

    async def _sync_annotations(
        self,
        client,
        db_pool: asyncpg.Pool,
        job_id: UUID,
        project_id: int,
        since: datetime,
    ) -> tuple[int, list[str]]:
        """Sync annotations updated since the given timestamp."""
        artifacts: list[PostHogAnnotationArtifact] = []
        entity_ids: list[str] = []

        try:
            annotations = await client.get_annotations(project_id)
            for annotation in annotations:
                # Check if updated since last sync
                updated_at_str = annotation.updated_at or annotation.created_at
                if updated_at_str:
                    try:
                        updated_at = datetime.fromisoformat(updated_at_str.replace("Z", "+00:00"))
                        if updated_at < since:
                            continue
                    except (ValueError, TypeError):
                        pass

                artifact = PostHogAnnotationArtifact.from_api_response(
                    annotation_data=annotation.model_dump(),
                    project_id=project_id,
                    ingest_job_id=job_id,
                )
                artifacts.append(artifact)
                entity_ids.append(artifact.entity_id)

        except Exception as e:
            logger.warning(f"Failed to sync annotations for project {project_id}: {e}")

        if artifacts:
            await self.store_artifacts_batch(db_pool, artifacts)

        return len(artifacts), entity_ids

    async def _sync_experiments(
        self,
        client,
        db_pool: asyncpg.Pool,
        job_id: UUID,
        project_id: int,
        since: datetime,
    ) -> tuple[int, list[str]]:
        """Sync experiments updated since the given timestamp."""
        artifacts: list[PostHogExperimentArtifact] = []
        entity_ids: list[str] = []

        try:
            experiments = await client.get_experiments(project_id)
            for experiment in experiments:
                # Check if updated since last sync
                updated_at_str = experiment.updated_at or experiment.created_at
                if updated_at_str:
                    try:
                        updated_at = datetime.fromisoformat(updated_at_str.replace("Z", "+00:00"))
                        if updated_at < since:
                            continue
                    except (ValueError, TypeError):
                        pass

                artifact = PostHogExperimentArtifact.from_api_response(
                    experiment_data=experiment.model_dump(),
                    project_id=project_id,
                    ingest_job_id=job_id,
                )
                artifacts.append(artifact)
                entity_ids.append(artifact.entity_id)

        except Exception as e:
            logger.warning(f"Failed to sync experiments for project {project_id}: {e}")

        if artifacts:
            await self.store_artifacts_batch(db_pool, artifacts)

        return len(artifacts), entity_ids

    async def _sync_surveys(
        self,
        client,
        db_pool: asyncpg.Pool,
        job_id: UUID,
        project_id: int,
        since: datetime,
    ) -> tuple[int, list[str]]:
        """Sync surveys updated since the given timestamp."""
        artifacts: list[PostHogSurveyArtifact] = []
        entity_ids: list[str] = []

        try:
            surveys = await client.get_surveys(project_id)
            for survey in surveys:
                # Check if updated since last sync
                updated_at_str = survey.updated_at or survey.created_at
                if updated_at_str:
                    try:
                        updated_at = datetime.fromisoformat(updated_at_str.replace("Z", "+00:00"))
                        if updated_at < since:
                            continue
                    except (ValueError, TypeError):
                        pass

                artifact = PostHogSurveyArtifact.from_api_response(
                    survey_data=survey.model_dump(),
                    project_id=project_id,
                    ingest_job_id=job_id,
                )
                artifacts.append(artifact)
                entity_ids.append(artifact.entity_id)

        except Exception as e:
            logger.warning(f"Failed to sync surveys for project {project_id}: {e}")

        if artifacts:
            await self.store_artifacts_batch(db_pool, artifacts)

        return len(artifacts), entity_ids
