"""
PostHog document classes for structured representation.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any, TypedDict

from connectors.base import BaseChunk, BaseDocument
from connectors.base.document_source import DocumentSource
from connectors.posthog.posthog_models import (
    PostHogAnnotationArtifact,
    PostHogDashboardArtifact,
    PostHogExperimentArtifact,
    PostHogFeatureFlagArtifact,
    PostHogInsightArtifact,
    PostHogSurveyArtifact,
)
from src.permissions.models import PermissionPolicy

# =============================================================================
# PostHog Dashboard Document
# =============================================================================


class PostHogDashboardChunkMetadata(TypedDict, total=False):
    """Metadata for PostHog dashboard chunks."""

    dashboard_id: int | None
    project_id: int | None
    chunk_type: str | None
    source: str | None


class PostHogDashboardDocumentMetadata(TypedDict, total=False):
    """Metadata for PostHog dashboard documents."""

    dashboard_id: int | None
    project_id: int | None
    name: str | None
    is_pinned: bool | None
    is_shared: bool | None
    tile_count: int | None
    tags: list[str] | None
    created_at: str | None
    updated_at: str | None
    source_created_at: str | None
    source: str
    type: str


@dataclass
class PostHogDashboardChunk(BaseChunk[PostHogDashboardChunkMetadata]):
    """Chunk representing a PostHog dashboard."""

    def get_content(self) -> str:
        """Get the chunk content."""
        return self.raw_data.get("content", "")

    def get_metadata(self) -> PostHogDashboardChunkMetadata:
        """Get chunk-specific metadata."""
        return {
            "dashboard_id": self.raw_data.get("dashboard_id"),
            "project_id": self.raw_data.get("project_id"),
            "chunk_type": self.raw_data.get("chunk_type", "dashboard"),
            "source": "posthog_dashboard",
        }


@dataclass
class PostHogDashboardDocument(
    BaseDocument[PostHogDashboardChunk, PostHogDashboardDocumentMetadata]
):
    """Document representing a PostHog dashboard."""

    raw_data: dict[str, Any]
    metadata: PostHogDashboardDocumentMetadata | None = None
    chunk_class: type[PostHogDashboardChunk] = PostHogDashboardChunk

    @classmethod
    def from_artifact(
        cls,
        artifact: PostHogDashboardArtifact,
        permission_policy: PermissionPolicy = "tenant",
        permission_allowed_tokens: list[str] | None = None,
    ) -> "PostHogDashboardDocument":
        """Create document from artifact."""
        content = artifact.content
        metadata = artifact.metadata

        raw_data = {
            "dashboard_id": content["dashboard_id"],
            "project_id": content["project_id"],
            "name": content["name"],
            "description": content.get("description"),
            "pinned": content.get("pinned", False),
            "is_shared": content.get("is_shared", False),
            "created_at": content.get("created_at"),
            "updated_at": content.get("updated_at"),
            "created_by": content.get("created_by"),
            "tags": content.get("tags", []),
            "tiles": content.get("tiles", []),
            "tile_count": content.get("tile_count", 0),
        }

        return cls(
            id=f"posthog_dashboard_{metadata.project_id}_{metadata.dashboard_id}",
            raw_data=raw_data,
            source_updated_at=artifact.source_updated_at,
            permission_policy=permission_policy,
            permission_allowed_tokens=permission_allowed_tokens,
        )

    def get_content(self) -> str:
        """Generate formatted dashboard content."""
        lines: list[str] = []

        name = self.raw_data.get("name", "Untitled Dashboard")
        description = self.raw_data.get("description", "")

        # Header
        lines.append(f"PostHog Dashboard: {name}")
        lines.append("")

        if description:
            lines.append(f"Description: {description}")
            lines.append("")

        # Dashboard info
        tile_count = self.raw_data.get("tile_count", 0)
        is_pinned = self.raw_data.get("pinned", False)
        is_shared = self.raw_data.get("is_shared", False)

        lines.append(f"Tiles: {tile_count}")
        if is_pinned:
            lines.append("Status: Pinned")
        if is_shared:
            lines.append("Visibility: Shared")

        # Tags
        tags = self.raw_data.get("tags", [])
        if tags:
            lines.append("")
            lines.append(f"Tags: {', '.join(tags)}")

        # Tiles summary
        tiles = self.raw_data.get("tiles", [])
        if tiles:
            lines.append("")
            lines.append("Dashboard Tiles:")
            for tile in tiles[:20]:
                insight = tile.get("insight", {})
                if insight:
                    insight_name = insight.get("name") or insight.get("short_id", "Untitled")
                    lines.append(f"  - {insight_name}")
            if len(tiles) > 20:
                lines.append(f"  ... and {len(tiles) - 20} more tiles")

        return "\n".join(lines)

    def to_embedding_chunks(self) -> list[PostHogDashboardChunk]:
        """Create chunks for embedding."""
        chunks: list[PostHogDashboardChunk] = []

        dashboard_id = self.raw_data.get("dashboard_id")
        project_id = self.raw_data.get("project_id")

        content = f"[{self.id}]\n" + self.get_content()

        chunk = self.chunk_class(
            document=self,
            raw_data={
                "content": content,
                "dashboard_id": dashboard_id,
                "project_id": project_id,
                "chunk_type": "dashboard",
            },
        )
        self.populate_chunk_permissions(chunk)
        chunks.append(chunk)

        return chunks

    def get_source_enum(self) -> DocumentSource:
        return DocumentSource.POSTHOG_DASHBOARD

    def get_reference_id(self) -> str:
        """Get the reference ID for this document."""
        dashboard_id = self.raw_data.get("dashboard_id")
        project_id = self.raw_data.get("project_id")
        return f"r_posthog_dashboard_{project_id}_{dashboard_id}"

    def get_metadata(self) -> PostHogDashboardDocumentMetadata:
        """Get document metadata for search and filtering."""
        if self.metadata is not None:
            return self.metadata

        created_at = self.raw_data.get("created_at")

        return {
            "dashboard_id": self.raw_data.get("dashboard_id"),
            "project_id": self.raw_data.get("project_id"),
            "name": self.raw_data.get("name"),
            "is_pinned": self.raw_data.get("pinned"),
            "is_shared": self.raw_data.get("is_shared"),
            "tile_count": self.raw_data.get("tile_count"),
            "tags": self.raw_data.get("tags"),
            "created_at": created_at,
            "updated_at": self.raw_data.get("updated_at"),
            "source_created_at": created_at,
            "source": self.get_source(),
            "type": "posthog_dashboard",
        }


# =============================================================================
# PostHog Insight Document
# =============================================================================


class PostHogInsightChunkMetadata(TypedDict, total=False):
    """Metadata for PostHog insight chunks."""

    insight_id: int | None
    project_id: int | None
    short_id: str | None
    chunk_type: str | None
    source: str | None


class PostHogInsightDocumentMetadata(TypedDict, total=False):
    """Metadata for PostHog insight documents."""

    insight_id: int | None
    project_id: int | None
    short_id: str | None
    name: str | None
    is_saved: bool | None
    dashboard_ids: list[int] | None
    tags: list[str] | None
    created_at: str | None
    source_created_at: str | None
    source: str
    type: str


@dataclass
class PostHogInsightChunk(BaseChunk[PostHogInsightChunkMetadata]):
    """Chunk representing a PostHog insight."""

    def get_content(self) -> str:
        """Get the chunk content."""
        return self.raw_data.get("content", "")

    def get_metadata(self) -> PostHogInsightChunkMetadata:
        """Get chunk-specific metadata."""
        return {
            "insight_id": self.raw_data.get("insight_id"),
            "project_id": self.raw_data.get("project_id"),
            "short_id": self.raw_data.get("short_id"),
            "chunk_type": self.raw_data.get("chunk_type", "insight"),
            "source": "posthog_insight",
        }


@dataclass
class PostHogInsightDocument(BaseDocument[PostHogInsightChunk, PostHogInsightDocumentMetadata]):
    """Document representing a PostHog insight (chart/query)."""

    raw_data: dict[str, Any]
    metadata: PostHogInsightDocumentMetadata | None = None
    chunk_class: type[PostHogInsightChunk] = PostHogInsightChunk

    @classmethod
    def from_artifact(
        cls,
        artifact: PostHogInsightArtifact,
        permission_policy: PermissionPolicy = "tenant",
        permission_allowed_tokens: list[str] | None = None,
    ) -> "PostHogInsightDocument":
        """Create document from artifact."""
        content = artifact.content
        metadata = artifact.metadata

        raw_data = {
            "insight_id": content["insight_id"],
            "project_id": content["project_id"],
            "short_id": content["short_id"],
            "name": content.get("name"),
            "description": content.get("description"),
            "filters": content.get("filters", {}),
            "query": content.get("query"),
            "created_at": content.get("created_at"),
            "updated_at": content.get("updated_at"),
            "last_modified_at": content.get("last_modified_at"),
            "saved": content.get("saved", True),
            "tags": content.get("tags", []),
            "dashboards": content.get("dashboards", []),
        }

        return cls(
            id=f"posthog_insight_{metadata.project_id}_{metadata.insight_id}",
            raw_data=raw_data,
            source_updated_at=artifact.source_updated_at,
            permission_policy=permission_policy,
            permission_allowed_tokens=permission_allowed_tokens,
        )

    def get_content(self) -> str:
        """Generate formatted insight content."""
        lines: list[str] = []

        name = self.raw_data.get("name") or self.raw_data.get("short_id", "Untitled Insight")
        description = self.raw_data.get("description", "")

        # Header
        lines.append(f"PostHog Insight: {name}")
        lines.append("")

        if description:
            lines.append(f"Description: {description}")
            lines.append("")

        # Insight details from filters
        filters = self.raw_data.get("filters", {})
        if filters:
            insight_type = filters.get("insight", "TRENDS")
            lines.append(f"Type: {insight_type}")

            # Date range
            date_from = filters.get("date_from")
            date_to = filters.get("date_to")
            if date_from:
                date_range = self._format_date_range(date_from, date_to)
                lines.append(f"Date Range: {date_range}")

            # Interval (daily, weekly, monthly)
            interval = filters.get("interval")
            if interval:
                lines.append(f"Interval: {interval}")

            # Compare to previous period
            compare = filters.get("compare")
            if compare:
                lines.append("Comparing: to previous period")

            # Events being tracked
            events = filters.get("events", [])
            if events:
                lines.append("")
                lines.append("Events:")
                for event in events[:10]:
                    event_id = event.get("id", "Unknown")
                    event_name = event.get("name", event_id)
                    math = event.get("math", "total")
                    math_property = event.get("math_property")

                    # Format the aggregation
                    agg_str = self._format_aggregation(math, math_property)
                    lines.append(f"  - {event_name} ({agg_str})")

            # Actions being tracked
            actions = filters.get("actions", [])
            if actions:
                lines.append("")
                lines.append("Actions:")
                for action in actions[:10]:
                    action_name = action.get("name", "Unknown")
                    math = action.get("math", "total")
                    math_property = action.get("math_property")
                    agg_str = self._format_aggregation(math, math_property)
                    lines.append(f"  - {action_name} ({agg_str})")

            # Breakdown
            breakdown = filters.get("breakdown")
            breakdown_type = filters.get("breakdown_type", "event")
            if breakdown:
                lines.append("")
                if isinstance(breakdown, list):
                    breakdown_str = ", ".join(str(b) for b in breakdown)
                else:
                    breakdown_str = str(breakdown)
                lines.append(f"Breakdown: {breakdown_str} ({breakdown_type})")

            # Formula
            formula = filters.get("formula")
            if formula:
                lines.append("")
                lines.append(f"Formula: {formula}")

            # Filter groups (property filters)
            filter_groups = filters.get("filter_groups", [])
            if filter_groups:
                lines.append("")
                lines.append("Filters:")
                for group in filter_groups[:3]:
                    properties = group.get("values", [])
                    for prop in properties[:5]:
                        prop_key = prop.get("key", "unknown")
                        prop_value = prop.get("value", "")
                        prop_operator = prop.get("operator", "exact")
                        lines.append(f"  - {prop_key} {prop_operator} {prop_value}")

            # Legacy properties filter
            properties = filters.get("properties", [])
            if properties and not filter_groups:
                lines.append("")
                lines.append("Filters:")
                for prop in properties[:5]:
                    if isinstance(prop, dict):
                        prop_key = prop.get("key", "unknown")
                        prop_value = prop.get("value", "")
                        prop_operator = prop.get("operator", "exact")
                        lines.append(f"  - {prop_key} {prop_operator} {prop_value}")

        # HogQL query if present
        query = self.raw_data.get("query")
        if query and isinstance(query, dict):
            hogql = query.get("query") or query.get("source", {}).get("query")
            if hogql:
                lines.append("")
                lines.append("HogQL Query:")
                # Truncate long queries
                if len(hogql) > 500:
                    lines.append(f"  {hogql[:500]}...")
                else:
                    lines.append(f"  {hogql}")

        # Dashboards this insight belongs to
        dashboards = self.raw_data.get("dashboards", [])
        if dashboards:
            lines.append("")
            lines.append(f"Dashboards: {len(dashboards)} dashboard(s)")

        # Tags
        tags = self.raw_data.get("tags", [])
        if tags:
            lines.append("")
            lines.append(f"Tags: {', '.join(tags)}")

        return "\n".join(lines)

    def _format_date_range(self, date_from: str, date_to: str | None) -> str:
        """Format date range to human-readable string."""
        # Handle relative dates like -7d, -30d, -1m, etc.
        if date_from.startswith("-"):
            value = date_from[1:-1]
            unit = date_from[-1]
            unit_map = {"d": "days", "w": "weeks", "m": "months", "y": "years", "h": "hours"}
            unit_name = unit_map.get(unit, unit)
            return f"Last {value} {unit_name}"
        elif date_from == "dStart":
            return "Today"
        elif date_from == "mStart":
            return "This month"
        elif date_from == "yStart":
            return "This year"
        else:
            # Absolute date
            if date_to:
                return f"{date_from} to {date_to}"
            return f"From {date_from}"

    def _format_aggregation(self, math: str, math_property: str | None) -> str:
        """Format aggregation type to human-readable string."""
        math_labels = {
            "total": "count",
            "dau": "unique users per day",
            "weekly_active": "weekly active users",
            "monthly_active": "monthly active users",
            "unique_group": "unique groups",
            "hogql": "custom HogQL",
            "sum": f"sum of {math_property}" if math_property else "sum",
            "avg": f"average of {math_property}" if math_property else "average",
            "min": f"minimum of {math_property}" if math_property else "minimum",
            "max": f"maximum of {math_property}" if math_property else "maximum",
            "median": f"median of {math_property}" if math_property else "median",
            "p90": f"90th percentile of {math_property}" if math_property else "p90",
            "p95": f"95th percentile of {math_property}" if math_property else "p95",
            "p99": f"99th percentile of {math_property}" if math_property else "p99",
            "unique_session": "unique sessions",
            "first_time_for_user": "first time events",
        }
        return math_labels.get(math, math)

    def to_embedding_chunks(self) -> list[PostHogInsightChunk]:
        """Create chunks for embedding."""
        chunks: list[PostHogInsightChunk] = []

        insight_id = self.raw_data.get("insight_id")
        project_id = self.raw_data.get("project_id")
        short_id = self.raw_data.get("short_id")

        content = f"[{self.id}]\n" + self.get_content()

        chunk = self.chunk_class(
            document=self,
            raw_data={
                "content": content,
                "insight_id": insight_id,
                "project_id": project_id,
                "short_id": short_id,
                "chunk_type": "insight",
            },
        )
        self.populate_chunk_permissions(chunk)
        chunks.append(chunk)

        return chunks

    def get_source_enum(self) -> DocumentSource:
        return DocumentSource.POSTHOG_INSIGHT

    def get_reference_id(self) -> str:
        """Get the reference ID for this document."""
        insight_id = self.raw_data.get("insight_id")
        project_id = self.raw_data.get("project_id")
        return f"r_posthog_insight_{project_id}_{insight_id}"

    def get_metadata(self) -> PostHogInsightDocumentMetadata:
        """Get document metadata for search and filtering."""
        if self.metadata is not None:
            return self.metadata

        created_at = self.raw_data.get("created_at")

        return {
            "insight_id": self.raw_data.get("insight_id"),
            "project_id": self.raw_data.get("project_id"),
            "short_id": self.raw_data.get("short_id"),
            "name": self.raw_data.get("name"),
            "is_saved": self.raw_data.get("saved"),
            "dashboard_ids": self.raw_data.get("dashboards"),
            "tags": self.raw_data.get("tags"),
            "created_at": created_at,
            "source_created_at": created_at,
            "source": self.get_source(),
            "type": "posthog_insight",
        }


# =============================================================================
# PostHog Feature Flag Document
# =============================================================================


class PostHogFeatureFlagChunkMetadata(TypedDict, total=False):
    """Metadata for PostHog feature flag chunks."""

    flag_id: int | None
    project_id: int | None
    key: str | None
    chunk_type: str | None
    source: str | None


class PostHogFeatureFlagDocumentMetadata(TypedDict, total=False):
    """Metadata for PostHog feature flag documents."""

    flag_id: int | None
    project_id: int | None
    key: str | None
    name: str | None
    is_active: bool | None
    rollout_percentage: int | None
    tags: list[str] | None
    created_at: str | None
    source_created_at: str | None
    source: str
    type: str


@dataclass
class PostHogFeatureFlagChunk(BaseChunk[PostHogFeatureFlagChunkMetadata]):
    """Chunk representing a PostHog feature flag."""

    def get_content(self) -> str:
        """Get the chunk content."""
        return self.raw_data.get("content", "")

    def get_metadata(self) -> PostHogFeatureFlagChunkMetadata:
        """Get chunk-specific metadata."""
        return {
            "flag_id": self.raw_data.get("flag_id"),
            "project_id": self.raw_data.get("project_id"),
            "key": self.raw_data.get("key"),
            "chunk_type": self.raw_data.get("chunk_type", "feature_flag"),
            "source": "posthog_feature_flag",
        }


@dataclass
class PostHogFeatureFlagDocument(
    BaseDocument[PostHogFeatureFlagChunk, PostHogFeatureFlagDocumentMetadata]
):
    """Document representing a PostHog feature flag."""

    raw_data: dict[str, Any]
    metadata: PostHogFeatureFlagDocumentMetadata | None = None
    chunk_class: type[PostHogFeatureFlagChunk] = PostHogFeatureFlagChunk

    @classmethod
    def from_artifact(
        cls,
        artifact: PostHogFeatureFlagArtifact,
        permission_policy: PermissionPolicy = "tenant",
        permission_allowed_tokens: list[str] | None = None,
    ) -> "PostHogFeatureFlagDocument":
        """Create document from artifact."""
        content = artifact.content
        metadata = artifact.metadata

        raw_data = {
            "flag_id": content["flag_id"],
            "project_id": content["project_id"],
            "key": content["key"],
            "name": content.get("name"),
            "filters": content.get("filters", {}),
            "active": content.get("active", True),
            "created_at": content.get("created_at"),
            "ensure_experience_continuity": content.get("ensure_experience_continuity", False),
            "rollout_percentage": content.get("rollout_percentage"),
            "tags": content.get("tags", []),
        }

        return cls(
            id=f"posthog_feature_flag_{metadata.project_id}_{metadata.flag_id}",
            raw_data=raw_data,
            source_updated_at=artifact.source_updated_at,
            permission_policy=permission_policy,
            permission_allowed_tokens=permission_allowed_tokens,
        )

    def get_content(self) -> str:
        """Generate formatted feature flag content."""
        lines: list[str] = []

        key = self.raw_data.get("key", "")
        name = self.raw_data.get("name") or key

        # Header
        lines.append(f"PostHog Feature Flag: {name}")
        lines.append(f"Key: {key}")
        lines.append("")

        # Status
        is_active = self.raw_data.get("active", True)
        status = "Active" if is_active else "Inactive"
        lines.append(f"Status: {status}")

        # Rollout
        rollout = self.raw_data.get("rollout_percentage")
        if rollout is not None:
            lines.append(f"Rollout: {rollout}%")

        # Filters/conditions summary
        filters = self.raw_data.get("filters", {})
        groups = filters.get("groups", [])
        if groups:
            lines.append("")
            lines.append("Targeting Rules:")
            for i, group in enumerate(groups[:5], 1):
                properties = group.get("properties", [])
                rollout_pct = group.get("rollout_percentage", 100)
                if properties:
                    prop_summary = ", ".join(p.get("key", "unknown") for p in properties[:3])
                    lines.append(f"  Group {i}: {prop_summary} ({rollout_pct}%)")
                else:
                    lines.append(f"  Group {i}: All users ({rollout_pct}%)")

        # Tags
        tags = self.raw_data.get("tags", [])
        if tags:
            lines.append("")
            lines.append(f"Tags: {', '.join(tags)}")

        return "\n".join(lines)

    def to_embedding_chunks(self) -> list[PostHogFeatureFlagChunk]:
        """Create chunks for embedding."""
        chunks: list[PostHogFeatureFlagChunk] = []

        flag_id = self.raw_data.get("flag_id")
        project_id = self.raw_data.get("project_id")
        key = self.raw_data.get("key")

        content = f"[{self.id}]\n" + self.get_content()

        chunk = self.chunk_class(
            document=self,
            raw_data={
                "content": content,
                "flag_id": flag_id,
                "project_id": project_id,
                "key": key,
                "chunk_type": "feature_flag",
            },
        )
        self.populate_chunk_permissions(chunk)
        chunks.append(chunk)

        return chunks

    def get_source_enum(self) -> DocumentSource:
        return DocumentSource.POSTHOG_FEATURE_FLAG

    def get_reference_id(self) -> str:
        """Get the reference ID for this document."""
        flag_id = self.raw_data.get("flag_id")
        project_id = self.raw_data.get("project_id")
        return f"r_posthog_feature_flag_{project_id}_{flag_id}"

    def get_metadata(self) -> PostHogFeatureFlagDocumentMetadata:
        """Get document metadata for search and filtering."""
        if self.metadata is not None:
            return self.metadata

        created_at = self.raw_data.get("created_at")

        return {
            "flag_id": self.raw_data.get("flag_id"),
            "project_id": self.raw_data.get("project_id"),
            "key": self.raw_data.get("key"),
            "name": self.raw_data.get("name"),
            "is_active": self.raw_data.get("active"),
            "rollout_percentage": self.raw_data.get("rollout_percentage"),
            "tags": self.raw_data.get("tags"),
            "created_at": created_at,
            "source_created_at": created_at,
            "source": self.get_source(),
            "type": "posthog_feature_flag",
        }


# =============================================================================
# PostHog Annotation Document
# =============================================================================


class PostHogAnnotationChunkMetadata(TypedDict, total=False):
    """Metadata for PostHog annotation chunks."""

    annotation_id: int | None
    project_id: int | None
    chunk_type: str | None
    source: str | None


class PostHogAnnotationDocumentMetadata(TypedDict, total=False):
    """Metadata for PostHog annotation documents."""

    annotation_id: int | None
    project_id: int | None
    scope: str | None
    dashboard_item_id: int | None
    date_marker: str | None
    created_at: str | None
    source_created_at: str | None
    source: str
    type: str


@dataclass
class PostHogAnnotationChunk(BaseChunk[PostHogAnnotationChunkMetadata]):
    """Chunk representing a PostHog annotation."""

    def get_content(self) -> str:
        """Get the chunk content."""
        return self.raw_data.get("content", "")

    def get_metadata(self) -> PostHogAnnotationChunkMetadata:
        """Get chunk-specific metadata."""
        return {
            "annotation_id": self.raw_data.get("annotation_id"),
            "project_id": self.raw_data.get("project_id"),
            "chunk_type": self.raw_data.get("chunk_type", "annotation"),
            "source": "posthog_annotation",
        }


@dataclass
class PostHogAnnotationDocument(
    BaseDocument[PostHogAnnotationChunk, PostHogAnnotationDocumentMetadata]
):
    """Document representing a PostHog annotation."""

    raw_data: dict[str, Any]
    metadata: PostHogAnnotationDocumentMetadata | None = None
    chunk_class: type[PostHogAnnotationChunk] = PostHogAnnotationChunk

    @classmethod
    def from_artifact(
        cls,
        artifact: PostHogAnnotationArtifact,
        permission_policy: PermissionPolicy = "tenant",
        permission_allowed_tokens: list[str] | None = None,
    ) -> "PostHogAnnotationDocument":
        """Create document from artifact."""
        content = artifact.content
        metadata = artifact.metadata

        raw_data = {
            "annotation_id": content["annotation_id"],
            "project_id": content["project_id"],
            "content": content.get("content", ""),
            "date_marker": content.get("date_marker"),
            "created_at": content.get("created_at"),
            "updated_at": content.get("updated_at"),
            "created_by": content.get("created_by"),
            "scope": content.get("scope", "organization"),
            "dashboard_item": content.get("dashboard_item"),
        }

        return cls(
            id=f"posthog_annotation_{metadata.project_id}_{metadata.annotation_id}",
            raw_data=raw_data,
            source_updated_at=artifact.source_updated_at,
            permission_policy=permission_policy,
            permission_allowed_tokens=permission_allowed_tokens,
        )

    def get_content(self) -> str:
        """Generate formatted annotation content."""
        lines: list[str] = []

        annotation_content = self.raw_data.get("content", "")
        date_marker = self.raw_data.get("date_marker", "")

        # Header
        lines.append("PostHog Annotation")
        if date_marker:
            lines.append(f"Date: {self._format_date(date_marker)}")
        lines.append("")

        # Content
        lines.append(annotation_content)

        # Scope
        scope = self.raw_data.get("scope", "organization")
        lines.append("")
        lines.append(f"Scope: {scope}")

        return "\n".join(lines)

    def _format_date(self, date_str: str) -> str:
        """Format ISO date string to readable format."""
        try:
            dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            return dt.strftime("%Y-%m-%d %H:%M")
        except (ValueError, TypeError):
            return date_str

    def to_embedding_chunks(self) -> list[PostHogAnnotationChunk]:
        """Create chunks for embedding."""
        chunks: list[PostHogAnnotationChunk] = []

        annotation_id = self.raw_data.get("annotation_id")
        project_id = self.raw_data.get("project_id")

        content = f"[{self.id}]\n" + self.get_content()

        chunk = self.chunk_class(
            document=self,
            raw_data={
                "content": content,
                "annotation_id": annotation_id,
                "project_id": project_id,
                "chunk_type": "annotation",
            },
        )
        self.populate_chunk_permissions(chunk)
        chunks.append(chunk)

        return chunks

    def get_source_enum(self) -> DocumentSource:
        return DocumentSource.POSTHOG_ANNOTATION

    def get_reference_id(self) -> str:
        """Get the reference ID for this document."""
        annotation_id = self.raw_data.get("annotation_id")
        project_id = self.raw_data.get("project_id")
        return f"r_posthog_annotation_{project_id}_{annotation_id}"

    def get_metadata(self) -> PostHogAnnotationDocumentMetadata:
        """Get document metadata for search and filtering."""
        if self.metadata is not None:
            return self.metadata

        created_at = self.raw_data.get("created_at")

        return {
            "annotation_id": self.raw_data.get("annotation_id"),
            "project_id": self.raw_data.get("project_id"),
            "scope": self.raw_data.get("scope"),
            "dashboard_item_id": self.raw_data.get("dashboard_item"),
            "date_marker": self.raw_data.get("date_marker"),
            "created_at": created_at,
            "source_created_at": created_at,
            "source": self.get_source(),
            "type": "posthog_annotation",
        }


# =============================================================================
# PostHog Experiment Document
# =============================================================================


class PostHogExperimentChunkMetadata(TypedDict, total=False):
    """Metadata for PostHog experiment chunks."""

    experiment_id: int | None
    project_id: int | None
    chunk_type: str | None
    source: str | None


class PostHogExperimentDocumentMetadata(TypedDict, total=False):
    """Metadata for PostHog experiment documents."""

    experiment_id: int | None
    project_id: int | None
    name: str | None
    feature_flag_key: str | None
    is_archived: bool | None
    start_date: str | None
    end_date: str | None
    created_at: str | None
    source_created_at: str | None
    source: str
    type: str


@dataclass
class PostHogExperimentChunk(BaseChunk[PostHogExperimentChunkMetadata]):
    """Chunk representing a PostHog experiment."""

    def get_content(self) -> str:
        """Get the chunk content."""
        return self.raw_data.get("content", "")

    def get_metadata(self) -> PostHogExperimentChunkMetadata:
        """Get chunk-specific metadata."""
        return {
            "experiment_id": self.raw_data.get("experiment_id"),
            "project_id": self.raw_data.get("project_id"),
            "chunk_type": self.raw_data.get("chunk_type", "experiment"),
            "source": "posthog_experiment",
        }


@dataclass
class PostHogExperimentDocument(
    BaseDocument[PostHogExperimentChunk, PostHogExperimentDocumentMetadata]
):
    """Document representing a PostHog experiment (A/B test)."""

    raw_data: dict[str, Any]
    metadata: PostHogExperimentDocumentMetadata | None = None
    chunk_class: type[PostHogExperimentChunk] = PostHogExperimentChunk

    @classmethod
    def from_artifact(
        cls,
        artifact: PostHogExperimentArtifact,
        permission_policy: PermissionPolicy = "tenant",
        permission_allowed_tokens: list[str] | None = None,
    ) -> "PostHogExperimentDocument":
        """Create document from artifact."""
        content = artifact.content
        metadata = artifact.metadata

        raw_data = {
            "experiment_id": content["experiment_id"],
            "project_id": content["project_id"],
            "name": content.get("name", ""),
            "description": content.get("description"),
            "start_date": content.get("start_date"),
            "end_date": content.get("end_date"),
            "created_at": content.get("created_at"),
            "updated_at": content.get("updated_at"),
            "feature_flag_key": content.get("feature_flag_key"),
            "feature_flag": content.get("feature_flag"),
            "parameters": content.get("parameters", {}),
            "filters": content.get("filters", {}),
            "archived": content.get("archived", False),
        }

        return cls(
            id=f"posthog_experiment_{metadata.project_id}_{metadata.experiment_id}",
            raw_data=raw_data,
            source_updated_at=artifact.source_updated_at,
            permission_policy=permission_policy,
            permission_allowed_tokens=permission_allowed_tokens,
        )

    def get_content(self) -> str:
        """Generate formatted experiment content."""
        lines: list[str] = []

        name = self.raw_data.get("name", "Untitled Experiment")
        description = self.raw_data.get("description", "")

        # Header
        lines.append(f"PostHog Experiment: {name}")
        lines.append("")

        if description:
            lines.append(f"Description: {description}")
            lines.append("")

        # Status
        archived = self.raw_data.get("archived", False)
        start_date = self.raw_data.get("start_date")
        end_date = self.raw_data.get("end_date")

        if archived:
            lines.append("Status: Archived")
        elif end_date:
            lines.append("Status: Completed")
        elif start_date:
            lines.append("Status: Running")
        else:
            lines.append("Status: Draft")

        # Dates
        if start_date:
            lines.append(f"Start Date: {self._format_date(start_date)}")
        if end_date:
            lines.append(f"End Date: {self._format_date(end_date)}")

        # Feature flag
        feature_flag_key = self.raw_data.get("feature_flag_key")
        if feature_flag_key:
            lines.append("")
            lines.append(f"Feature Flag: {feature_flag_key}")

        # Parameters (variants)
        parameters = self.raw_data.get("parameters", {})
        variants = parameters.get("feature_flag_variants", [])
        if variants:
            lines.append("")
            lines.append("Variants:")
            for variant in variants:
                key = variant.get("key", "unknown")
                rollout = variant.get("rollout_percentage", 0)
                lines.append(f"  - {key}: {rollout}%")

        return "\n".join(lines)

    def _format_date(self, date_str: str) -> str:
        """Format ISO date string to readable format."""
        try:
            dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            return dt.strftime("%Y-%m-%d")
        except (ValueError, TypeError):
            return date_str

    def to_embedding_chunks(self) -> list[PostHogExperimentChunk]:
        """Create chunks for embedding."""
        chunks: list[PostHogExperimentChunk] = []

        experiment_id = self.raw_data.get("experiment_id")
        project_id = self.raw_data.get("project_id")

        content = f"[{self.id}]\n" + self.get_content()

        chunk = self.chunk_class(
            document=self,
            raw_data={
                "content": content,
                "experiment_id": experiment_id,
                "project_id": project_id,
                "chunk_type": "experiment",
            },
        )
        self.populate_chunk_permissions(chunk)
        chunks.append(chunk)

        return chunks

    def get_source_enum(self) -> DocumentSource:
        return DocumentSource.POSTHOG_EXPERIMENT

    def get_reference_id(self) -> str:
        """Get the reference ID for this document."""
        experiment_id = self.raw_data.get("experiment_id")
        project_id = self.raw_data.get("project_id")
        return f"r_posthog_experiment_{project_id}_{experiment_id}"

    def get_metadata(self) -> PostHogExperimentDocumentMetadata:
        """Get document metadata for search and filtering."""
        if self.metadata is not None:
            return self.metadata

        created_at = self.raw_data.get("created_at")

        return {
            "experiment_id": self.raw_data.get("experiment_id"),
            "project_id": self.raw_data.get("project_id"),
            "name": self.raw_data.get("name"),
            "feature_flag_key": self.raw_data.get("feature_flag_key"),
            "is_archived": self.raw_data.get("archived"),
            "start_date": self.raw_data.get("start_date"),
            "end_date": self.raw_data.get("end_date"),
            "created_at": created_at,
            "source_created_at": created_at,
            "source": self.get_source(),
            "type": "posthog_experiment",
        }


# =============================================================================
# PostHog Survey Document
# =============================================================================


class PostHogSurveyChunkMetadata(TypedDict, total=False):
    """Metadata for PostHog survey chunks."""

    survey_id: str | None
    project_id: int | None
    chunk_type: str | None
    source: str | None


class PostHogSurveyDocumentMetadata(TypedDict, total=False):
    """Metadata for PostHog survey documents."""

    survey_id: str | None
    project_id: int | None
    name: str | None
    survey_type: str | None
    question_count: int | None
    is_archived: bool | None
    start_date: str | None
    end_date: str | None
    created_at: str | None
    source_created_at: str | None
    source: str
    type: str


@dataclass
class PostHogSurveyChunk(BaseChunk[PostHogSurveyChunkMetadata]):
    """Chunk representing a PostHog survey."""

    def get_content(self) -> str:
        """Get the chunk content."""
        return self.raw_data.get("content", "")

    def get_metadata(self) -> PostHogSurveyChunkMetadata:
        """Get chunk-specific metadata."""
        return {
            "survey_id": self.raw_data.get("survey_id"),
            "project_id": self.raw_data.get("project_id"),
            "chunk_type": self.raw_data.get("chunk_type", "survey"),
            "source": "posthog_survey",
        }


@dataclass
class PostHogSurveyDocument(BaseDocument[PostHogSurveyChunk, PostHogSurveyDocumentMetadata]):
    """Document representing a PostHog survey."""

    raw_data: dict[str, Any]
    metadata: PostHogSurveyDocumentMetadata | None = None
    chunk_class: type[PostHogSurveyChunk] = PostHogSurveyChunk

    @classmethod
    def from_artifact(
        cls,
        artifact: PostHogSurveyArtifact,
        permission_policy: PermissionPolicy = "tenant",
        permission_allowed_tokens: list[str] | None = None,
    ) -> "PostHogSurveyDocument":
        """Create document from artifact."""
        content = artifact.content
        metadata = artifact.metadata

        raw_data = {
            "survey_id": content["survey_id"],
            "project_id": content["project_id"],
            "name": content.get("name", ""),
            "description": content.get("description"),
            "type": content.get("type", "popover"),
            "questions": content.get("questions", []),
            "appearance": content.get("appearance"),
            "targeting_flag_filters": content.get("targeting_flag_filters"),
            "start_date": content.get("start_date"),
            "end_date": content.get("end_date"),
            "created_at": content.get("created_at"),
            "archived": content.get("archived", False),
        }

        return cls(
            id=f"posthog_survey_{metadata.project_id}_{metadata.survey_id}",
            raw_data=raw_data,
            source_updated_at=artifact.source_updated_at,
            permission_policy=permission_policy,
            permission_allowed_tokens=permission_allowed_tokens,
        )

    def get_content(self) -> str:
        """Generate formatted survey content."""
        lines: list[str] = []

        name = self.raw_data.get("name", "Untitled Survey")
        description = self.raw_data.get("description", "")
        survey_type = self.raw_data.get("type", "popover")

        # Header
        lines.append(f"PostHog Survey: {name}")
        lines.append(f"Type: {survey_type}")
        lines.append("")

        if description:
            lines.append(f"Description: {description}")
            lines.append("")

        # Questions
        questions = self.raw_data.get("questions", [])
        if questions:
            lines.append("Questions:")
            for i, question in enumerate(questions, 1):
                q_type = question.get("type", "open")
                q_text = question.get("question", "")
                lines.append(f"  {i}. [{q_type}] {q_text}")

                # Show choices if available
                choices = question.get("choices", [])
                if choices:
                    for choice in choices[:5]:
                        lines.append(f"       - {choice}")
                    if len(choices) > 5:
                        lines.append(f"       ... and {len(choices) - 5} more")

        # Status
        archived = self.raw_data.get("archived", False)
        if archived:
            lines.append("")
            lines.append("Status: Archived")

        return "\n".join(lines)

    def to_embedding_chunks(self) -> list[PostHogSurveyChunk]:
        """Create chunks for embedding."""
        chunks: list[PostHogSurveyChunk] = []

        survey_id = self.raw_data.get("survey_id")
        project_id = self.raw_data.get("project_id")

        content = f"[{self.id}]\n" + self.get_content()

        chunk = self.chunk_class(
            document=self,
            raw_data={
                "content": content,
                "survey_id": survey_id,
                "project_id": project_id,
                "chunk_type": "survey",
            },
        )
        self.populate_chunk_permissions(chunk)
        chunks.append(chunk)

        return chunks

    def get_source_enum(self) -> DocumentSource:
        return DocumentSource.POSTHOG_SURVEY

    def get_reference_id(self) -> str:
        """Get the reference ID for this document."""
        survey_id = self.raw_data.get("survey_id")
        project_id = self.raw_data.get("project_id")
        return f"r_posthog_survey_{project_id}_{survey_id}"

    def get_metadata(self) -> PostHogSurveyDocumentMetadata:
        """Get document metadata for search and filtering."""
        if self.metadata is not None:
            return self.metadata

        created_at = self.raw_data.get("created_at")
        questions = self.raw_data.get("questions", [])

        return {
            "survey_id": self.raw_data.get("survey_id"),
            "project_id": self.raw_data.get("project_id"),
            "name": self.raw_data.get("name"),
            "survey_type": self.raw_data.get("type"),
            "question_count": len(questions),
            "is_archived": self.raw_data.get("archived"),
            "start_date": self.raw_data.get("start_date"),
            "end_date": self.raw_data.get("end_date"),
            "created_at": created_at,
            "source_created_at": created_at,
            "source": self.get_source(),
            "type": "posthog_survey",
        }
