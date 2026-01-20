"""PostHog pruner for cleaning up deleted entities."""

import asyncpg

from connectors.base import BasePruner
from connectors.base.base_ingest_artifact import (
    get_posthog_annotation_entity_id,
    get_posthog_dashboard_entity_id,
    get_posthog_experiment_entity_id,
    get_posthog_feature_flag_entity_id,
    get_posthog_insight_entity_id,
    get_posthog_survey_entity_id,
)
from connectors.base.document_source import DocumentSource
from connectors.posthog.client import PostHogClient, get_posthog_client_for_tenant
from connectors.posthog.posthog_sync_service import PostHogSyncService
from src.utils.logging import get_logger

logger = get_logger(__name__)

# Safety threshold: abort if more than this percentage would be deleted
# Protects against API returning empty/partial results due to errors
MAX_DELETION_RATIO = 0.7  # 70%

# Document ID prefixes match the entity_id format from artifacts
POSTHOG_DASHBOARD_DOC_ID_PREFIX = "posthog_dashboard_"
POSTHOG_INSIGHT_DOC_ID_PREFIX = "posthog_insight_"
POSTHOG_FEATURE_FLAG_DOC_ID_PREFIX = "posthog_feature_flag_"
POSTHOG_ANNOTATION_DOC_ID_PREFIX = "posthog_annotation_"
POSTHOG_EXPERIMENT_DOC_ID_PREFIX = "posthog_experiment_"
POSTHOG_SURVEY_DOC_ID_PREFIX = "posthog_survey_"


def _extract_project_id_from_entity_id(entity_id: str, prefix: str) -> int | None:
    """Extract project_id from a PostHog entity ID.

    Entity IDs have format: {prefix}{project_id}_{entity_specific_id}
    E.g., posthog_dashboard_123_456 -> project_id=123
    """
    try:
        # Remove prefix and get the rest
        remainder = entity_id[len(prefix) :]
        # Split by underscore - first part is project_id
        parts = remainder.split("_", 1)
        if parts:
            return int(parts[0])
    except (ValueError, IndexError):
        pass
    return None


class PostHogPruner(BasePruner):
    """Prunes PostHog entities that have been deleted.

    This pruner:
    1. Gets all indexed PostHog entity IDs from the database
    2. Checks each entity's current state in PostHog
    3. Marks deleted entities for removal from the index
    """

    async def find_stale_documents(
        self,
        tenant_id: str,
        db_pool: asyncpg.Pool,
    ) -> list[str]:
        """Find PostHog documents that should be removed.

        Args:
            tenant_id: Tenant identifier
            db_pool: Database connection pool

        Returns:
            List of document IDs to delete
        """
        try:
            client = await get_posthog_client_for_tenant(tenant_id)
        except Exception as e:
            logger.error(f"Failed to get PostHog client for pruning: {e}")
            return []

        try:
            sync_service = PostHogSyncService(db_pool, tenant_id)
            project_ids = await sync_service.get_selected_project_ids()

            if not project_ids:
                # Get all accessible projects if none selected
                projects = await client.get_projects()
                project_ids = [p.id for p in projects]

            # Safety guard: if no projects found, abort to prevent mass deletion
            if not project_ids:
                logger.warning(
                    "PostHog API returned no projects. "
                    "Aborting staleness check to prevent mass deletion."
                )
                return []

            stale_doc_ids: list[str] = []

            # Check each entity type
            stale_doc_ids.extend(await self._find_stale_dashboards(client, db_pool, project_ids))
            stale_doc_ids.extend(await self._find_stale_insights(client, db_pool, project_ids))
            stale_doc_ids.extend(await self._find_stale_feature_flags(client, db_pool, project_ids))
            stale_doc_ids.extend(await self._find_stale_annotations(client, db_pool, project_ids))
            stale_doc_ids.extend(await self._find_stale_experiments(client, db_pool, project_ids))
            stale_doc_ids.extend(await self._find_stale_surveys(client, db_pool, project_ids))

            logger.info(f"Found {len(stale_doc_ids)} stale PostHog documents")
            return stale_doc_ids

        finally:
            await client.close()

    async def _find_stale_dashboards(
        self,
        client: PostHogClient,
        db_pool: asyncpg.Pool,
        project_ids: list[int],
    ) -> list[str]:
        """Find stale dashboard documents."""
        stale_doc_ids: list[str] = []

        async with db_pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT id FROM documents WHERE source = $1",
                DocumentSource.POSTHOG_DASHBOARD.value,
            )

        if not rows:
            return []

        # Get all current dashboards from PostHog
        active_entity_ids: set[str] = set()
        failed_project_ids: set[int] = set()
        for project_id in project_ids:
            try:
                dashboards = await client.get_dashboards(project_id)
                for d in dashboards:
                    entity_id = get_posthog_dashboard_entity_id(
                        project_id=project_id, dashboard_id=d.id
                    )
                    active_entity_ids.add(entity_id)
            except Exception as e:
                logger.warning(f"Failed to get dashboards for project {project_id}: {e}")
                # Track failed projects to avoid incorrectly marking their docs as stale
                failed_project_ids.add(project_id)

        # Safety guard: if all projects failed, abort
        if len(failed_project_ids) == len(project_ids):
            logger.warning(
                "All PostHog project API calls failed for dashboards. "
                "Aborting staleness check to prevent mass deletion."
            )
            return []

        # Check indexed documents against active ones
        # Skip documents from projects where API failed to prevent accidental deletion
        eligible_count = 0
        for row in rows:
            doc_id = row["id"]
            # Check if this document belongs to a failed project
            doc_project_id = _extract_project_id_from_entity_id(
                doc_id, POSTHOG_DASHBOARD_DOC_ID_PREFIX
            )
            if doc_project_id in failed_project_ids:
                continue
            eligible_count += 1
            # Document IDs match entity_ids for PostHog
            if doc_id not in active_entity_ids:
                stale_doc_ids.append(doc_id)

        # Safety guard: abort if deletion ratio is too high (likely API issue)
        if eligible_count > 0 and len(stale_doc_ids) / eligible_count >= MAX_DELETION_RATIO:
            logger.warning(
                f"PostHog dashboards staleness check would delete {len(stale_doc_ids)}/{eligible_count} "
                f"documents ({len(stale_doc_ids) / eligible_count:.1%}). "
                "Aborting to prevent mass deletion due to potential API issue."
            )
            return []

        return stale_doc_ids

    async def _find_stale_insights(
        self,
        client: PostHogClient,
        db_pool: asyncpg.Pool,
        project_ids: list[int],
    ) -> list[str]:
        """Find stale insight documents."""
        stale_doc_ids: list[str] = []

        async with db_pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT id FROM documents WHERE source = $1",
                DocumentSource.POSTHOG_INSIGHT.value,
            )

        if not rows:
            return []

        active_entity_ids: set[str] = set()
        failed_project_ids: set[int] = set()
        for project_id in project_ids:
            try:
                insights = await client.get_insights(project_id)
                for i in insights:
                    entity_id = get_posthog_insight_entity_id(
                        project_id=project_id, insight_id=i.id
                    )
                    active_entity_ids.add(entity_id)
            except Exception as e:
                logger.warning(f"Failed to get insights for project {project_id}: {e}")
                failed_project_ids.add(project_id)

        # Safety guard: if all projects failed, abort
        if len(failed_project_ids) == len(project_ids):
            logger.warning(
                "All PostHog project API calls failed for insights. "
                "Aborting staleness check to prevent mass deletion."
            )
            return []

        eligible_count = 0
        for row in rows:
            doc_id = row["id"]
            doc_project_id = _extract_project_id_from_entity_id(
                doc_id, POSTHOG_INSIGHT_DOC_ID_PREFIX
            )
            if doc_project_id in failed_project_ids:
                continue
            eligible_count += 1
            if doc_id not in active_entity_ids:
                stale_doc_ids.append(doc_id)

        # Safety guard: abort if deletion ratio is too high (likely API issue)
        if eligible_count > 0 and len(stale_doc_ids) / eligible_count >= MAX_DELETION_RATIO:
            logger.warning(
                f"PostHog insights staleness check would delete {len(stale_doc_ids)}/{eligible_count} "
                f"documents ({len(stale_doc_ids) / eligible_count:.1%}). "
                "Aborting to prevent mass deletion due to potential API issue."
            )
            return []

        return stale_doc_ids

    async def _find_stale_feature_flags(
        self,
        client: PostHogClient,
        db_pool: asyncpg.Pool,
        project_ids: list[int],
    ) -> list[str]:
        """Find stale feature flag documents."""
        stale_doc_ids: list[str] = []

        async with db_pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT id FROM documents WHERE source = $1",
                DocumentSource.POSTHOG_FEATURE_FLAG.value,
            )

        if not rows:
            return []

        active_entity_ids: set[str] = set()
        failed_project_ids: set[int] = set()
        for project_id in project_ids:
            try:
                flags = await client.get_feature_flags(project_id)
                for f in flags:
                    entity_id = get_posthog_feature_flag_entity_id(
                        project_id=project_id, flag_id=f.id
                    )
                    active_entity_ids.add(entity_id)
            except Exception as e:
                logger.warning(f"Failed to get feature flags for project {project_id}: {e}")
                failed_project_ids.add(project_id)

        # Safety guard: if all projects failed, abort
        if len(failed_project_ids) == len(project_ids):
            logger.warning(
                "All PostHog project API calls failed for feature flags. "
                "Aborting staleness check to prevent mass deletion."
            )
            return []

        eligible_count = 0
        for row in rows:
            doc_id = row["id"]
            doc_project_id = _extract_project_id_from_entity_id(
                doc_id, POSTHOG_FEATURE_FLAG_DOC_ID_PREFIX
            )
            if doc_project_id in failed_project_ids:
                continue
            eligible_count += 1
            if doc_id not in active_entity_ids:
                stale_doc_ids.append(doc_id)

        # Safety guard: abort if deletion ratio is too high (likely API issue)
        if eligible_count > 0 and len(stale_doc_ids) / eligible_count >= MAX_DELETION_RATIO:
            logger.warning(
                f"PostHog feature flags staleness check would delete {len(stale_doc_ids)}/{eligible_count} "
                f"documents ({len(stale_doc_ids) / eligible_count:.1%}). "
                "Aborting to prevent mass deletion due to potential API issue."
            )
            return []

        return stale_doc_ids

    async def _find_stale_annotations(
        self,
        client: PostHogClient,
        db_pool: asyncpg.Pool,
        project_ids: list[int],
    ) -> list[str]:
        """Find stale annotation documents."""
        stale_doc_ids: list[str] = []

        async with db_pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT id FROM documents WHERE source = $1",
                DocumentSource.POSTHOG_ANNOTATION.value,
            )

        if not rows:
            return []

        active_entity_ids: set[str] = set()
        failed_project_ids: set[int] = set()
        for project_id in project_ids:
            try:
                annotations = await client.get_annotations(project_id)
                for a in annotations:
                    entity_id = get_posthog_annotation_entity_id(
                        project_id=project_id, annotation_id=a.id
                    )
                    active_entity_ids.add(entity_id)
            except Exception as e:
                logger.warning(f"Failed to get annotations for project {project_id}: {e}")
                failed_project_ids.add(project_id)

        # Safety guard: if all projects failed, abort
        if len(failed_project_ids) == len(project_ids):
            logger.warning(
                "All PostHog project API calls failed for annotations. "
                "Aborting staleness check to prevent mass deletion."
            )
            return []

        eligible_count = 0
        for row in rows:
            doc_id = row["id"]
            doc_project_id = _extract_project_id_from_entity_id(
                doc_id, POSTHOG_ANNOTATION_DOC_ID_PREFIX
            )
            if doc_project_id in failed_project_ids:
                continue
            eligible_count += 1
            if doc_id not in active_entity_ids:
                stale_doc_ids.append(doc_id)

        # Safety guard: abort if deletion ratio is too high (likely API issue)
        if eligible_count > 0 and len(stale_doc_ids) / eligible_count >= MAX_DELETION_RATIO:
            logger.warning(
                f"PostHog annotations staleness check would delete {len(stale_doc_ids)}/{eligible_count} "
                f"documents ({len(stale_doc_ids) / eligible_count:.1%}). "
                "Aborting to prevent mass deletion due to potential API issue."
            )
            return []

        return stale_doc_ids

    async def _find_stale_experiments(
        self,
        client: PostHogClient,
        db_pool: asyncpg.Pool,
        project_ids: list[int],
    ) -> list[str]:
        """Find stale experiment documents."""
        stale_doc_ids: list[str] = []

        async with db_pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT id FROM documents WHERE source = $1",
                DocumentSource.POSTHOG_EXPERIMENT.value,
            )

        if not rows:
            return []

        active_entity_ids: set[str] = set()
        failed_project_ids: set[int] = set()
        for project_id in project_ids:
            try:
                experiments = await client.get_experiments(project_id)
                for exp in experiments:
                    entity_id = get_posthog_experiment_entity_id(
                        project_id=project_id, experiment_id=exp.id
                    )
                    active_entity_ids.add(entity_id)
            except Exception as e:
                logger.warning(f"Failed to get experiments for project {project_id}: {e}")
                failed_project_ids.add(project_id)

        # Safety guard: if all projects failed, abort
        if len(failed_project_ids) == len(project_ids):
            logger.warning(
                "All PostHog project API calls failed for experiments. "
                "Aborting staleness check to prevent mass deletion."
            )
            return []

        eligible_count = 0
        for row in rows:
            doc_id = row["id"]
            doc_project_id = _extract_project_id_from_entity_id(
                doc_id, POSTHOG_EXPERIMENT_DOC_ID_PREFIX
            )
            if doc_project_id in failed_project_ids:
                continue
            eligible_count += 1
            if doc_id not in active_entity_ids:
                stale_doc_ids.append(doc_id)

        # Safety guard: abort if deletion ratio is too high (likely API issue)
        if eligible_count > 0 and len(stale_doc_ids) / eligible_count >= MAX_DELETION_RATIO:
            logger.warning(
                f"PostHog experiments staleness check would delete {len(stale_doc_ids)}/{eligible_count} "
                f"documents ({len(stale_doc_ids) / eligible_count:.1%}). "
                "Aborting to prevent mass deletion due to potential API issue."
            )
            return []

        return stale_doc_ids

    async def _find_stale_surveys(
        self,
        client: PostHogClient,
        db_pool: asyncpg.Pool,
        project_ids: list[int],
    ) -> list[str]:
        """Find stale survey documents."""
        stale_doc_ids: list[str] = []

        async with db_pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT id FROM documents WHERE source = $1",
                DocumentSource.POSTHOG_SURVEY.value,
            )

        if not rows:
            return []

        active_entity_ids: set[str] = set()
        failed_project_ids: set[int] = set()
        for project_id in project_ids:
            try:
                surveys = await client.get_surveys(project_id)
                for s in surveys:
                    entity_id = get_posthog_survey_entity_id(project_id=project_id, survey_id=s.id)
                    active_entity_ids.add(entity_id)
            except Exception as e:
                logger.warning(f"Failed to get surveys for project {project_id}: {e}")
                failed_project_ids.add(project_id)

        # Safety guard: if all projects failed, abort
        if len(failed_project_ids) == len(project_ids):
            logger.warning(
                "All PostHog project API calls failed for surveys. "
                "Aborting staleness check to prevent mass deletion."
            )
            return []

        eligible_count = 0
        for row in rows:
            doc_id = row["id"]
            doc_project_id = _extract_project_id_from_entity_id(
                doc_id, POSTHOG_SURVEY_DOC_ID_PREFIX
            )
            if doc_project_id in failed_project_ids:
                continue
            eligible_count += 1
            if doc_id not in active_entity_ids:
                stale_doc_ids.append(doc_id)

        # Safety guard: abort if deletion ratio is too high (likely API issue)
        if eligible_count > 0 and len(stale_doc_ids) / eligible_count >= MAX_DELETION_RATIO:
            logger.warning(
                f"PostHog surveys staleness check would delete {len(stale_doc_ids)}/{eligible_count} "
                f"documents ({len(stale_doc_ids) / eligible_count:.1%}). "
                "Aborting to prevent mass deletion due to potential API issue."
            )
            return []

        return stale_doc_ids
