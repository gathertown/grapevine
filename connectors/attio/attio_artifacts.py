"""Attio artifact models for ingest pipeline.

Note: Unlike HubSpot, Attio's API returns all attributes by default,
so we don't need to specify which attributes to fetch. The document
classes handle extracting values from whatever attributes are present.
"""

from datetime import UTC, datetime
from enum import Enum
from typing import Any
from uuid import UUID

from pydantic import BaseModel


class AttioObjectType(str, Enum):
    """Attio CRM object type identifiers (API slugs)."""

    COMPANIES = "companies"
    PEOPLE = "people"
    DEALS = "deals"


class AttioWebhookEntityType(str, Enum):
    """Attio webhook entity types from event_type field."""

    RECORD = "record"
    NOTE = "note"
    TASK = "task"


class AttioWebhookAction(str, Enum):
    """Attio webhook actions from event_type field."""

    CREATED = "created"
    UPDATED = "updated"
    DELETED = "deleted"


# Concrete list of supported Attio object types for iteration
ATTIO_OBJECT_TYPES: list[AttioObjectType] = list(AttioObjectType)

from connectors.base.base_ingest_artifact import (
    ArtifactEntity,
    BaseIngestArtifact,
    get_attio_company_entity_id,
    get_attio_deal_entity_id,
    get_attio_person_entity_id,
)
from connectors.base.utils import parse_iso_timestamp


# Artifact Content Models
class AttioCompanyArtifactContent(BaseModel):
    """Full company record data from Attio API."""

    record_data: dict[str, Any]


class AttioCompanyArtifactMetadata(BaseModel):
    """Metadata for Attio company artifact."""

    record_id: str
    workspace_id: str | None = None
    created_at: str
    updated_at: str | None = None


class AttioCompanyArtifact(BaseIngestArtifact):
    """Typed Attio company artifact with validated content and metadata."""

    entity: ArtifactEntity = ArtifactEntity.ATTIO_COMPANY
    content: AttioCompanyArtifactContent
    metadata: AttioCompanyArtifactMetadata

    @classmethod
    def from_api_response(
        cls,
        record_data: dict[str, Any],
        ingest_job_id: UUID,
        workspace_id: str | None = None,
    ) -> "AttioCompanyArtifact":
        """Create artifact from Attio API record response."""
        record_id = record_data.get("id", {})
        if isinstance(record_id, dict):
            record_id = record_id.get("record_id", "")

        created_at = record_data.get("created_at", "")
        updated_at = record_data.get("updated_at")

        return cls(
            entity_id=get_attio_company_entity_id(company_id=record_id),
            content=AttioCompanyArtifactContent(record_data=record_data),
            metadata=AttioCompanyArtifactMetadata(
                record_id=record_id,
                workspace_id=workspace_id,
                created_at=created_at,
                updated_at=updated_at,
            ),
            source_updated_at=parse_iso_timestamp(updated_at or created_at)
            if (updated_at or created_at)
            else datetime.now(UTC),
            ingest_job_id=ingest_job_id,
        )


class AttioPersonArtifactContent(BaseModel):
    """Full person record data from Attio API."""

    record_data: dict[str, Any]


class AttioPersonArtifactMetadata(BaseModel):
    """Metadata for Attio person artifact."""

    record_id: str
    workspace_id: str | None = None
    created_at: str
    updated_at: str | None = None


class AttioPersonArtifact(BaseIngestArtifact):
    """Typed Attio person artifact with validated content and metadata."""

    entity: ArtifactEntity = ArtifactEntity.ATTIO_PERSON
    content: AttioPersonArtifactContent
    metadata: AttioPersonArtifactMetadata

    @classmethod
    def from_api_response(
        cls,
        record_data: dict[str, Any],
        ingest_job_id: UUID,
        workspace_id: str | None = None,
    ) -> "AttioPersonArtifact":
        """Create artifact from Attio API record response."""
        record_id = record_data.get("id", {})
        if isinstance(record_id, dict):
            record_id = record_id.get("record_id", "")

        created_at = record_data.get("created_at", "")
        updated_at = record_data.get("updated_at")

        return cls(
            entity_id=get_attio_person_entity_id(person_id=record_id),
            content=AttioPersonArtifactContent(record_data=record_data),
            metadata=AttioPersonArtifactMetadata(
                record_id=record_id,
                workspace_id=workspace_id,
                created_at=created_at,
                updated_at=updated_at,
            ),
            source_updated_at=parse_iso_timestamp(updated_at or created_at)
            if (updated_at or created_at)
            else datetime.now(UTC),
            ingest_job_id=ingest_job_id,
        )


class AttioDealArtifactContent(BaseModel):
    """Full deal record data from Attio API with embedded notes and tasks."""

    record_data: dict[str, Any]
    notes: list[dict[str, Any]] = []
    tasks: list[dict[str, Any]] = []


class AttioDealArtifactMetadata(BaseModel):
    """Metadata for Attio deal artifact."""

    record_id: str
    workspace_id: str | None = None
    pipeline_stage: str | None = None
    created_at: str
    updated_at: str | None = None


class AttioDealArtifact(BaseIngestArtifact):
    """Typed Attio deal artifact with validated content and metadata."""

    entity: ArtifactEntity = ArtifactEntity.ATTIO_DEAL
    content: AttioDealArtifactContent
    metadata: AttioDealArtifactMetadata

    @classmethod
    def from_api_response(
        cls,
        record_data: dict[str, Any],
        ingest_job_id: UUID,
        workspace_id: str | None = None,
        notes: list[dict[str, Any]] | None = None,
        tasks: list[dict[str, Any]] | None = None,
    ) -> "AttioDealArtifact":
        """Create artifact from Attio API record response with embedded notes/tasks."""
        record_id = record_data.get("id", {})
        if isinstance(record_id, dict):
            record_id = record_id.get("record_id", "")

        created_at = record_data.get("created_at", "")
        updated_at = record_data.get("updated_at")

        # Extract pipeline stage from values if available
        pipeline_stage = None
        values = record_data.get("values", {})
        stage_values = values.get("pipeline_stage", [])
        if stage_values and isinstance(stage_values, list):
            first_stage = stage_values[0]
            if isinstance(first_stage, dict):
                pipeline_stage = first_stage.get("value") or first_stage.get("title")

        return cls(
            entity_id=get_attio_deal_entity_id(deal_id=record_id),
            content=AttioDealArtifactContent(
                record_data=record_data,
                notes=notes or [],
                tasks=tasks or [],
            ),
            metadata=AttioDealArtifactMetadata(
                record_id=record_id,
                workspace_id=workspace_id,
                pipeline_stage=pipeline_stage,
                created_at=created_at,
                updated_at=updated_at,
            ),
            source_updated_at=parse_iso_timestamp(updated_at or created_at)
            if (updated_at or created_at)
            else datetime.now(UTC),
            ingest_job_id=ingest_job_id,
        )


class AttioNoteArtifactContent(BaseModel):
    """Note data from Attio API."""

    note_data: dict[str, Any]


class AttioNoteArtifactMetadata(BaseModel):
    """Metadata for Attio note artifact."""

    note_id: str
    parent_object: str | None = None
    parent_record_id: str | None = None
    created_at: str
    updated_at: str | None = None


class AttioNoteArtifact(BaseIngestArtifact):
    """Typed Attio note artifact (usually embedded in parent records)."""

    entity: ArtifactEntity = ArtifactEntity.ATTIO_NOTE
    content: AttioNoteArtifactContent
    metadata: AttioNoteArtifactMetadata


class AttioTaskArtifactContent(BaseModel):
    """Task data from Attio API."""

    task_data: dict[str, Any]


class AttioTaskArtifactMetadata(BaseModel):
    """Metadata for Attio task artifact."""

    task_id: str
    is_completed: bool = False
    deadline_at: str | None = None
    created_at: str
    updated_at: str | None = None


class AttioTaskArtifact(BaseIngestArtifact):
    """Typed Attio task artifact (usually embedded in parent records)."""

    entity: ArtifactEntity = ArtifactEntity.ATTIO_TASK
    content: AttioTaskArtifactContent
    metadata: AttioTaskArtifactMetadata
