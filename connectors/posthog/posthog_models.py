"""
PostHog connector models - artifacts and backfill configurations.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel

from connectors.base.base_ingest_artifact import (
    ArtifactEntity,
    BaseIngestArtifact,
    get_posthog_annotation_entity_id,
    get_posthog_dashboard_entity_id,
    get_posthog_experiment_entity_id,
    get_posthog_feature_flag_entity_id,
    get_posthog_insight_entity_id,
    get_posthog_survey_entity_id,
)
from connectors.base.models import BackfillIngestConfig

# =============================================================================
# Artifact Metadata Types (Pydantic for validation)
# =============================================================================


class PostHogDashboardArtifactMetadata(BaseModel):
    """Metadata for PostHog dashboard artifacts."""

    dashboard_id: int
    project_id: int
    name: str
    is_pinned: bool = False
    is_shared: bool = False
    tile_count: int = 0
    tags: list[str] = []


class PostHogInsightArtifactMetadata(BaseModel):
    """Metadata for PostHog insight artifacts."""

    insight_id: int
    project_id: int
    short_id: str
    name: str | None = None
    is_saved: bool = True
    dashboard_ids: list[int] = []
    tags: list[str] = []


class PostHogFeatureFlagArtifactMetadata(BaseModel):
    """Metadata for PostHog feature flag artifacts."""

    flag_id: int
    project_id: int
    key: str
    name: str | None = None
    is_active: bool = True
    rollout_percentage: int | None = None
    tags: list[str] = []


class PostHogAnnotationArtifactMetadata(BaseModel):
    """Metadata for PostHog annotation artifacts."""

    annotation_id: int
    project_id: int
    scope: str = "organization"
    dashboard_item_id: int | None = None


class PostHogExperimentArtifactMetadata(BaseModel):
    """Metadata for PostHog experiment artifacts."""

    experiment_id: int
    project_id: int
    name: str
    feature_flag_key: str | None = None
    is_archived: bool = False


class PostHogSurveyArtifactMetadata(BaseModel):
    """Metadata for PostHog survey artifacts."""

    survey_id: str
    project_id: int
    name: str
    survey_type: str = "popover"
    question_count: int = 0
    is_archived: bool = False


# =============================================================================
# Artifact Classes
# =============================================================================


class PostHogDashboardArtifact(BaseIngestArtifact):
    """Artifact representing a PostHog dashboard."""

    entity: ArtifactEntity = ArtifactEntity.POSTHOG_DASHBOARD
    content: dict[str, Any]
    metadata: PostHogDashboardArtifactMetadata

    @classmethod
    def from_api_response(
        cls,
        dashboard_data: dict[str, Any],
        project_id: int,
        ingest_job_id: UUID,
    ) -> PostHogDashboardArtifact:
        """
        Create a PostHogDashboardArtifact from API response data.

        Args:
            dashboard_data: Dashboard object from PostHog API
            project_id: The project ID this dashboard belongs to
            ingest_job_id: The job ID for this ingest operation
        """
        dashboard_id = dashboard_data.get("id", 0)

        # Parse updated_at timestamp
        updated_at_str = dashboard_data.get("updated_at") or dashboard_data.get("created_at", "")
        try:
            source_updated_at = datetime.fromisoformat(updated_at_str.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            source_updated_at = datetime.now(UTC)

        tiles = dashboard_data.get("tiles", [])
        tags = dashboard_data.get("tags", [])

        content: dict[str, Any] = {
            "dashboard_id": dashboard_id,
            "project_id": project_id,
            "name": dashboard_data.get("name", "Untitled Dashboard"),
            "description": dashboard_data.get("description"),
            "pinned": dashboard_data.get("pinned", False),
            "is_shared": dashboard_data.get("is_shared", False),
            "created_at": dashboard_data.get("created_at"),
            "updated_at": dashboard_data.get("updated_at"),
            "created_by": dashboard_data.get("created_by"),
            "tags": tags,
            "tiles": tiles,
            "tile_count": len(tiles),
        }

        metadata = PostHogDashboardArtifactMetadata(
            dashboard_id=dashboard_id,
            project_id=project_id,
            name=dashboard_data.get("name", "Untitled Dashboard"),
            is_pinned=dashboard_data.get("pinned", False),
            is_shared=dashboard_data.get("is_shared", False),
            tile_count=len(tiles),
            tags=tags,
        )

        return cls(
            entity_id=get_posthog_dashboard_entity_id(
                project_id=project_id, dashboard_id=dashboard_id
            ),
            content=content,
            metadata=metadata,
            source_updated_at=source_updated_at,
            ingest_job_id=ingest_job_id,
        )


class PostHogInsightArtifact(BaseIngestArtifact):
    """Artifact representing a PostHog insight (chart/query)."""

    entity: ArtifactEntity = ArtifactEntity.POSTHOG_INSIGHT
    content: dict[str, Any]
    metadata: PostHogInsightArtifactMetadata

    @classmethod
    def from_api_response(
        cls,
        insight_data: dict[str, Any],
        project_id: int,
        ingest_job_id: UUID,
    ) -> PostHogInsightArtifact:
        """
        Create a PostHogInsightArtifact from API response data.

        Args:
            insight_data: Insight object from PostHog API
            project_id: The project ID this insight belongs to
            ingest_job_id: The job ID for this ingest operation
        """
        insight_id = insight_data.get("id", 0)
        short_id = insight_data.get("short_id", "")

        # Parse last_modified_at or updated_at timestamp
        updated_at_str = (
            insight_data.get("last_modified_at")
            or insight_data.get("updated_at")
            or insight_data.get("created_at", "")
        )
        try:
            source_updated_at = datetime.fromisoformat(updated_at_str.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            source_updated_at = datetime.now(UTC)

        tags = insight_data.get("tags", [])
        dashboards = insight_data.get("dashboards", [])

        content: dict[str, Any] = {
            "insight_id": insight_id,
            "project_id": project_id,
            "short_id": short_id,
            "name": insight_data.get("name"),
            "description": insight_data.get("description"),
            "filters": insight_data.get("filters", {}),
            "query": insight_data.get("query"),
            "created_at": insight_data.get("created_at"),
            "updated_at": insight_data.get("updated_at"),
            "last_modified_at": insight_data.get("last_modified_at"),
            "created_by": insight_data.get("created_by"),
            "last_modified_by": insight_data.get("last_modified_by"),
            "saved": insight_data.get("saved", True),
            "tags": tags,
            "dashboards": dashboards,
        }

        metadata = PostHogInsightArtifactMetadata(
            insight_id=insight_id,
            project_id=project_id,
            short_id=short_id,
            name=insight_data.get("name"),
            is_saved=insight_data.get("saved", True),
            dashboard_ids=dashboards,
            tags=tags,
        )

        return cls(
            entity_id=get_posthog_insight_entity_id(project_id=project_id, insight_id=insight_id),
            content=content,
            metadata=metadata,
            source_updated_at=source_updated_at,
            ingest_job_id=ingest_job_id,
        )


class PostHogFeatureFlagArtifact(BaseIngestArtifact):
    """Artifact representing a PostHog feature flag."""

    entity: ArtifactEntity = ArtifactEntity.POSTHOG_FEATURE_FLAG
    content: dict[str, Any]
    metadata: PostHogFeatureFlagArtifactMetadata

    @classmethod
    def from_api_response(
        cls,
        flag_data: dict[str, Any],
        project_id: int,
        ingest_job_id: UUID,
    ) -> PostHogFeatureFlagArtifact:
        """
        Create a PostHogFeatureFlagArtifact from API response data.

        Args:
            flag_data: Feature flag object from PostHog API
            project_id: The project ID this flag belongs to
            ingest_job_id: The job ID for this ingest operation
        """
        flag_id = flag_data.get("id", 0)
        key = flag_data.get("key", "")

        # Parse created_at timestamp (feature flags don't have updated_at typically)
        created_at_str = flag_data.get("created_at", "")
        try:
            source_updated_at = datetime.fromisoformat(created_at_str.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            source_updated_at = datetime.now(UTC)

        tags = flag_data.get("tags", [])
        filters = flag_data.get("filters", {})

        # Extract rollout percentage from filters if available
        rollout_percentage = flag_data.get("rollout_percentage")
        if rollout_percentage is None and filters:
            groups = filters.get("groups", [])
            if groups and len(groups) > 0:
                rollout_percentage = groups[0].get("rollout_percentage")

        content: dict[str, Any] = {
            "flag_id": flag_id,
            "project_id": project_id,
            "key": key,
            "name": flag_data.get("name"),
            "filters": filters,
            "active": flag_data.get("active", True),
            "created_at": flag_data.get("created_at"),
            "created_by": flag_data.get("created_by"),
            "ensure_experience_continuity": flag_data.get("ensure_experience_continuity", False),
            "rollout_percentage": rollout_percentage,
            "tags": tags,
        }

        metadata = PostHogFeatureFlagArtifactMetadata(
            flag_id=flag_id,
            project_id=project_id,
            key=key,
            name=flag_data.get("name"),
            is_active=flag_data.get("active", True),
            rollout_percentage=rollout_percentage,
            tags=tags,
        )

        return cls(
            entity_id=get_posthog_feature_flag_entity_id(project_id=project_id, flag_id=flag_id),
            content=content,
            metadata=metadata,
            source_updated_at=source_updated_at,
            ingest_job_id=ingest_job_id,
        )


class PostHogAnnotationArtifact(BaseIngestArtifact):
    """Artifact representing a PostHog annotation."""

    entity: ArtifactEntity = ArtifactEntity.POSTHOG_ANNOTATION
    content: dict[str, Any]
    metadata: PostHogAnnotationArtifactMetadata

    @classmethod
    def from_api_response(
        cls,
        annotation_data: dict[str, Any],
        project_id: int,
        ingest_job_id: UUID,
    ) -> PostHogAnnotationArtifact:
        """
        Create a PostHogAnnotationArtifact from API response data.

        Args:
            annotation_data: Annotation object from PostHog API
            project_id: The project ID this annotation belongs to
            ingest_job_id: The job ID for this ingest operation
        """
        annotation_id = annotation_data.get("id", 0)

        # Parse updated_at timestamp
        updated_at_str = annotation_data.get("updated_at") or annotation_data.get("created_at", "")
        try:
            source_updated_at = datetime.fromisoformat(updated_at_str.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            source_updated_at = datetime.now(UTC)

        content: dict[str, Any] = {
            "annotation_id": annotation_id,
            "project_id": project_id,
            "content": annotation_data.get("content", ""),
            "date_marker": annotation_data.get("date_marker"),
            "created_at": annotation_data.get("created_at"),
            "updated_at": annotation_data.get("updated_at"),
            "created_by": annotation_data.get("created_by"),
            "scope": annotation_data.get("scope", "organization"),
            "dashboard_item": annotation_data.get("dashboard_item"),
        }

        metadata = PostHogAnnotationArtifactMetadata(
            annotation_id=annotation_id,
            project_id=project_id,
            scope=annotation_data.get("scope", "organization"),
            dashboard_item_id=annotation_data.get("dashboard_item"),
        )

        return cls(
            entity_id=get_posthog_annotation_entity_id(
                project_id=project_id, annotation_id=annotation_id
            ),
            content=content,
            metadata=metadata,
            source_updated_at=source_updated_at,
            ingest_job_id=ingest_job_id,
        )


class PostHogExperimentArtifact(BaseIngestArtifact):
    """Artifact representing a PostHog experiment (A/B test)."""

    entity: ArtifactEntity = ArtifactEntity.POSTHOG_EXPERIMENT
    content: dict[str, Any]
    metadata: PostHogExperimentArtifactMetadata

    @classmethod
    def from_api_response(
        cls,
        experiment_data: dict[str, Any],
        project_id: int,
        ingest_job_id: UUID,
    ) -> PostHogExperimentArtifact:
        """
        Create a PostHogExperimentArtifact from API response data.

        Args:
            experiment_data: Experiment object from PostHog API
            project_id: The project ID this experiment belongs to
            ingest_job_id: The job ID for this ingest operation
        """
        experiment_id = experiment_data.get("id", 0)

        # Parse updated_at timestamp
        updated_at_str = experiment_data.get("updated_at") or experiment_data.get("created_at", "")
        try:
            source_updated_at = datetime.fromisoformat(updated_at_str.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            source_updated_at = datetime.now(UTC)

        content: dict[str, Any] = {
            "experiment_id": experiment_id,
            "project_id": project_id,
            "name": experiment_data.get("name", ""),
            "description": experiment_data.get("description"),
            "start_date": experiment_data.get("start_date"),
            "end_date": experiment_data.get("end_date"),
            "created_at": experiment_data.get("created_at"),
            "updated_at": experiment_data.get("updated_at"),
            "created_by": experiment_data.get("created_by"),
            "feature_flag_key": experiment_data.get("feature_flag_key"),
            "feature_flag": experiment_data.get("feature_flag"),
            "parameters": experiment_data.get("parameters", {}),
            "filters": experiment_data.get("filters", {}),
            "archived": experiment_data.get("archived", False),
        }

        metadata = PostHogExperimentArtifactMetadata(
            experiment_id=experiment_id,
            project_id=project_id,
            name=experiment_data.get("name", ""),
            feature_flag_key=experiment_data.get("feature_flag_key"),
            is_archived=experiment_data.get("archived", False),
        )

        return cls(
            entity_id=get_posthog_experiment_entity_id(
                project_id=project_id, experiment_id=experiment_id
            ),
            content=content,
            metadata=metadata,
            source_updated_at=source_updated_at,
            ingest_job_id=ingest_job_id,
        )


class PostHogSurveyArtifact(BaseIngestArtifact):
    """Artifact representing a PostHog survey."""

    entity: ArtifactEntity = ArtifactEntity.POSTHOG_SURVEY
    content: dict[str, Any]
    metadata: PostHogSurveyArtifactMetadata

    @classmethod
    def from_api_response(
        cls,
        survey_data: dict[str, Any],
        project_id: int,
        ingest_job_id: UUID,
    ) -> PostHogSurveyArtifact:
        """
        Create a PostHogSurveyArtifact from API response data.

        Args:
            survey_data: Survey object from PostHog API
            project_id: The project ID this survey belongs to
            ingest_job_id: The job ID for this ingest operation
        """
        survey_id = survey_data.get("id", "")

        # Parse created_at timestamp
        created_at_str = survey_data.get("created_at", "")
        try:
            source_updated_at = datetime.fromisoformat(created_at_str.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            source_updated_at = datetime.now(UTC)

        questions = survey_data.get("questions", [])

        content: dict[str, Any] = {
            "survey_id": survey_id,
            "project_id": project_id,
            "name": survey_data.get("name", ""),
            "description": survey_data.get("description"),
            "type": survey_data.get("type", "popover"),
            "questions": questions,
            "appearance": survey_data.get("appearance"),
            "targeting_flag_filters": survey_data.get("targeting_flag_filters"),
            "start_date": survey_data.get("start_date"),
            "end_date": survey_data.get("end_date"),
            "created_at": survey_data.get("created_at"),
            "created_by": survey_data.get("created_by"),
            "archived": survey_data.get("archived", False),
        }

        metadata = PostHogSurveyArtifactMetadata(
            survey_id=survey_id,
            project_id=project_id,
            name=survey_data.get("name", ""),
            survey_type=survey_data.get("type", "popover"),
            question_count=len(questions),
            is_archived=survey_data.get("archived", False),
        )

        return cls(
            entity_id=get_posthog_survey_entity_id(project_id=project_id, survey_id=survey_id),
            content=content,
            metadata=metadata,
            source_updated_at=source_updated_at,
            ingest_job_id=ingest_job_id,
        )


# =============================================================================
# Backfill Configuration Models
# =============================================================================


class PostHogBackfillRootConfig(BackfillIngestConfig, frozen=True):
    """Configuration for starting a PostHog full backfill."""

    source: str = "posthog_backfill_root"
    # Optional: specific project IDs to sync. If not provided, syncs all accessible projects.
    project_ids_to_sync: list[int] | None = None


class PostHogProjectBackfillConfig(BackfillIngestConfig, frozen=True):
    """Configuration for backfilling a specific PostHog project."""

    source: str = "posthog_project_backfill"
    project_id: int


class PostHogIncrementalBackfillConfig(BackfillIngestConfig, frozen=True):
    """Configuration for incremental PostHog sync."""

    source: str = "posthog_incremental_backfill"
    lookback_hours: int = 24
