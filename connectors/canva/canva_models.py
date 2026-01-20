"""
Canva connector models - artifacts and backfill configurations.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel

from connectors.base.base_ingest_artifact import (
    ArtifactEntity,
    BaseIngestArtifact,
    get_canva_design_entity_id,
)
from connectors.base.models import BackfillIngestConfig

# =============================================================================
# Artifact Metadata Types (Pydantic for validation)
# =============================================================================


class CanvaDesignArtifactMetadata(BaseModel):
    """Metadata for Canva design artifacts."""

    design_id: str
    owner_user_id: str | None = None
    owner_team_id: str | None = None
    page_count: int | None = None


# =============================================================================
# Artifact Classes
# =============================================================================


class CanvaDesignArtifact(BaseIngestArtifact):
    """Artifact representing a Canva design."""

    entity: ArtifactEntity = ArtifactEntity.CANVA_DESIGN
    content: dict[str, Any]
    metadata: CanvaDesignArtifactMetadata

    @classmethod
    def from_api_response(
        cls,
        design_data: dict[str, Any],
        ingest_job_id: UUID,
    ) -> CanvaDesignArtifact:
        """
        Create a CanvaDesignArtifact from API response data.

        Args:
            design_data: Response from GET /v1/designs or list endpoint
            ingest_job_id: The job ID for this ingest operation
        """
        design_id = design_data.get("id", "")

        # Parse timestamps (Unix timestamps in seconds)
        updated_at = design_data.get("updated_at")
        created_at = design_data.get("created_at")

        if updated_at is not None:
            try:
                source_updated_at = datetime.fromtimestamp(updated_at, tz=UTC)
            except (ValueError, TypeError, OSError):
                source_updated_at = datetime.now(UTC)
        elif created_at is not None:
            try:
                source_updated_at = datetime.fromtimestamp(created_at, tz=UTC)
            except (ValueError, TypeError, OSError):
                source_updated_at = datetime.now(UTC)
        else:
            source_updated_at = datetime.now(UTC)

        # Extract owner info
        owner = design_data.get("owner", {}) or {}
        owner_user_id = owner.get("user_id")
        owner_team_id = owner.get("team_id")

        # Extract URLs
        urls = design_data.get("urls", {}) or {}
        edit_url = urls.get("edit_url")
        view_url = urls.get("view_url")

        # Extract thumbnail
        thumbnail = design_data.get("thumbnail", {}) or {}

        content: dict[str, Any] = {
            "design_id": design_id,
            "title": design_data.get("title", "Untitled Design"),
            "edit_url": edit_url,
            "view_url": view_url,
            "thumbnail_url": thumbnail.get("url"),
            "thumbnail_width": thumbnail.get("width"),
            "thumbnail_height": thumbnail.get("height"),
            "page_count": design_data.get("page_count"),
            "owner_user_id": owner_user_id,
            "owner_team_id": owner_team_id,
            "created_at": created_at,
            "updated_at": updated_at,
        }

        metadata = CanvaDesignArtifactMetadata(
            design_id=design_id,
            owner_user_id=owner_user_id,
            owner_team_id=owner_team_id,
            page_count=design_data.get("page_count"),
        )

        return cls(
            entity_id=get_canva_design_entity_id(design_id=design_id),
            content=content,
            metadata=metadata,
            source_updated_at=source_updated_at,
            ingest_job_id=ingest_job_id,
        )


# =============================================================================
# Backfill Configuration Models
# =============================================================================


class CanvaBackfillRootConfig(BackfillIngestConfig, frozen=True):
    """Configuration for starting a Canva full backfill."""

    source: str = "canva_backfill_root"


class CanvaDesignBackfillConfig(BackfillIngestConfig, frozen=True):
    """Configuration for backfilling a batch of designs."""

    source: str = "canva_design_backfill"
    design_ids: list[str]


class CanvaIncrementalBackfillConfig(BackfillIngestConfig, frozen=True):
    """Configuration for incremental Canva sync."""

    source: str = "canva_incremental_backfill"
    # Number of designs to check per sync (sorted by modified_descending)
    # Since Canva doesn't support updated_after, we fetch recent designs and compare
    check_count: int = 200


# =============================================================================
# Sync State Keys
# =============================================================================

CANVA_ACCESS_TOKEN_KEY = "CANVA_ACCESS_TOKEN"
CANVA_REFRESH_TOKEN_KEY = "CANVA_REFRESH_TOKEN"
CANVA_USER_ID_KEY = "CANVA_USER_ID"
CANVA_USER_DISPLAY_NAME_KEY = "CANVA_USER_DISPLAY_NAME"
CANVA_TOKEN_EXPIRES_AT_KEY = "CANVA_TOKEN_EXPIRES_AT"
CANVA_FULL_BACKFILL_COMPLETE_KEY = "CANVA_FULL_BACKFILL_COMPLETE"
CANVA_DESIGNS_SYNCED_UNTIL_KEY = "CANVA_DESIGNS_SYNCED_UNTIL"

# All config keys for the connector
CANVA_CONFIG_KEYS = [
    CANVA_ACCESS_TOKEN_KEY,
    CANVA_REFRESH_TOKEN_KEY,
    CANVA_USER_ID_KEY,
    CANVA_USER_DISPLAY_NAME_KEY,
    CANVA_TOKEN_EXPIRES_AT_KEY,
    CANVA_FULL_BACKFILL_COMPLETE_KEY,
    CANVA_DESIGNS_SYNCED_UNTIL_KEY,
]

CANVA_SENSITIVE_KEYS = [
    CANVA_ACCESS_TOKEN_KEY,
    CANVA_REFRESH_TOKEN_KEY,
]

CANVA_NON_SENSITIVE_KEYS = [
    CANVA_USER_ID_KEY,
    CANVA_USER_DISPLAY_NAME_KEY,
    CANVA_TOKEN_EXPIRES_AT_KEY,
    CANVA_FULL_BACKFILL_COMPLETE_KEY,
    CANVA_DESIGNS_SYNCED_UNTIL_KEY,
]
