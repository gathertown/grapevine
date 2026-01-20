"""Pipedrive artifact models for ingest pipeline.

Pipedrive returns dates in ISO format (YYYY-MM-DD) and timestamps in
ISO 8601 format (YYYY-MM-DDTHH:MM:SSZ).
"""

import contextlib
from datetime import UTC, datetime
from enum import Enum
from typing import Any
from uuid import UUID

from pydantic import BaseModel

from connectors.base.base_ingest_artifact import (
    ArtifactEntity,
    BaseIngestArtifact,
    get_pipedrive_activity_entity_id,
    get_pipedrive_deal_entity_id,
    get_pipedrive_note_entity_id,
    get_pipedrive_organization_entity_id,
    get_pipedrive_person_entity_id,
    get_pipedrive_product_entity_id,
    get_pipedrive_user_entity_id,
)
from connectors.base.utils import parse_iso_timestamp


def _extract_entity_id(value: Any) -> int | None:
    """Extract entity ID from a value that may be an int or a dict with 'id' field.

    Pipedrive API sometimes returns related entities as:
    - int: Just the ID (e.g., 123)
    - dict: Object with id field (e.g., {"id": 123, "name": "John"})
    """
    if value is None:
        return None
    if isinstance(value, dict):
        return value.get("id")
    if isinstance(value, int):
        return value
    return None


class PipedriveEntityType(str, Enum):
    """Pipedrive entity type identifiers."""

    DEAL = "deal"
    PERSON = "person"
    ORGANIZATION = "organization"
    ACTIVITY = "activity"
    NOTE = "note"
    USER = "user"
    PRODUCT = "product"


# Concrete list of main entity types for backfill iteration
PIPEDRIVE_MAIN_ENTITY_TYPES: list[PipedriveEntityType] = [
    PipedriveEntityType.DEAL,
    PipedriveEntityType.PERSON,
    PipedriveEntityType.ORGANIZATION,
    PipedriveEntityType.PRODUCT,
]


# =========================================================================
# Deal Artifact
# =========================================================================


class PipedriveDealArtifactContent(BaseModel):
    """Full deal record data from Pipedrive API."""

    deal_data: dict[str, Any]
    notes: list[dict[str, Any]] = []
    activities: list[dict[str, Any]] = []


class PipedriveDealArtifactMetadata(BaseModel):
    """Metadata for Pipedrive deal artifact."""

    deal_id: int
    title: str | None = None
    value: float | None = None
    currency: str | None = None
    status: str | None = None  # open, won, lost, deleted
    stage_id: int | None = None
    pipeline_id: int | None = None
    owner_id: int | None = None
    person_id: int | None = None
    org_id: int | None = None
    source_created_at: str | None = None
    source_updated_at: str | None = None


class PipedriveDealArtifact(BaseIngestArtifact):
    """Typed Pipedrive deal artifact with validated content and metadata."""

    entity: ArtifactEntity = ArtifactEntity.PIPEDRIVE_DEAL
    content: PipedriveDealArtifactContent
    metadata: PipedriveDealArtifactMetadata

    @classmethod
    def from_api_response(
        cls,
        deal_data: dict[str, Any],
        ingest_job_id: UUID,
        notes: list[dict[str, Any]] | None = None,
        activities: list[dict[str, Any]] | None = None,
    ) -> "PipedriveDealArtifact":
        """Create artifact from Pipedrive API deal response."""
        deal_id = deal_data.get("id", 0)
        add_time = deal_data.get("add_time", "")
        update_time = deal_data.get("update_time") or add_time

        # Parse update time for source_updated_at
        source_updated_at = datetime.now(UTC)
        if update_time:
            with contextlib.suppress(ValueError, TypeError):
                source_updated_at = parse_iso_timestamp(update_time)

        # Extract value - may be nested or direct
        value = deal_data.get("value")
        if isinstance(value, dict):
            value = value.get("value")

        return cls(
            entity_id=get_pipedrive_deal_entity_id(deal_id=deal_id),
            content=PipedriveDealArtifactContent(
                deal_data=deal_data,
                notes=notes or [],
                activities=activities or [],
            ),
            metadata=PipedriveDealArtifactMetadata(
                deal_id=deal_id,
                title=deal_data.get("title"),
                value=float(value) if value is not None else None,
                currency=deal_data.get("currency"),
                status=deal_data.get("status"),
                stage_id=deal_data.get("stage_id"),
                pipeline_id=deal_data.get("pipeline_id"),
                owner_id=_extract_entity_id(deal_data.get("owner_id"))
                or _extract_entity_id(deal_data.get("user_id")),
                person_id=_extract_entity_id(deal_data.get("person_id")),
                org_id=_extract_entity_id(deal_data.get("org_id")),
                source_created_at=add_time,
                source_updated_at=update_time,
            ),
            source_updated_at=source_updated_at,
            ingest_job_id=ingest_job_id,
        )


# =========================================================================
# Person Artifact
# =========================================================================


class PipedrivePersonArtifactContent(BaseModel):
    """Full person record data from Pipedrive API."""

    person_data: dict[str, Any]


class PipedrivePersonArtifactMetadata(BaseModel):
    """Metadata for Pipedrive person artifact."""

    person_id: int
    name: str | None = None
    email: str | None = None
    phone: str | None = None
    org_id: int | None = None
    owner_id: int | None = None
    source_created_at: str | None = None
    source_updated_at: str | None = None


class PipedrivePersonArtifact(BaseIngestArtifact):
    """Typed Pipedrive person artifact with validated content and metadata."""

    entity: ArtifactEntity = ArtifactEntity.PIPEDRIVE_PERSON
    content: PipedrivePersonArtifactContent
    metadata: PipedrivePersonArtifactMetadata

    @classmethod
    def from_api_response(
        cls,
        person_data: dict[str, Any],
        ingest_job_id: UUID,
    ) -> "PipedrivePersonArtifact":
        """Create artifact from Pipedrive API person response."""
        person_id = person_data.get("id", 0)
        add_time = person_data.get("add_time", "")
        update_time = person_data.get("update_time") or add_time

        # Parse update time for source_updated_at
        source_updated_at = datetime.now(UTC)
        if update_time:
            with contextlib.suppress(ValueError, TypeError):
                source_updated_at = parse_iso_timestamp(update_time)

        # Extract primary email from v2 API response (always "emails" plural)
        email = None
        emails = person_data.get("emails") or []
        if isinstance(emails, list) and emails:
            primary = next((e for e in emails if e.get("primary")), emails[0])
            email = primary.get("value") if isinstance(primary, dict) else primary

        # Extract primary phone from v2 API response (always "phones" plural)
        phone = None
        phones = person_data.get("phones") or []
        if isinstance(phones, list) and phones:
            primary = next((p for p in phones if p.get("primary")), phones[0])
            phone = primary.get("value") if isinstance(primary, dict) else primary

        return cls(
            entity_id=get_pipedrive_person_entity_id(person_id=person_id),
            content=PipedrivePersonArtifactContent(person_data=person_data),
            metadata=PipedrivePersonArtifactMetadata(
                person_id=person_id,
                name=person_data.get("name"),
                email=email,
                phone=phone,
                org_id=_extract_entity_id(person_data.get("org_id")),
                owner_id=_extract_entity_id(person_data.get("owner_id"))
                or _extract_entity_id(person_data.get("user_id")),
                source_created_at=add_time,
                source_updated_at=update_time,
            ),
            source_updated_at=source_updated_at,
            ingest_job_id=ingest_job_id,
        )


# =========================================================================
# Organization Artifact
# =========================================================================


class PipedriveOrganizationArtifactContent(BaseModel):
    """Full organization record data from Pipedrive API."""

    org_data: dict[str, Any]


class PipedriveOrganizationArtifactMetadata(BaseModel):
    """Metadata for Pipedrive organization artifact."""

    org_id: int
    name: str | None = None
    address: str | None = None
    owner_id: int | None = None
    people_count: int | None = None
    open_deals_count: int | None = None
    source_created_at: str | None = None
    source_updated_at: str | None = None


class PipedriveOrganizationArtifact(BaseIngestArtifact):
    """Typed Pipedrive organization artifact with validated content and metadata."""

    entity: ArtifactEntity = ArtifactEntity.PIPEDRIVE_ORGANIZATION
    content: PipedriveOrganizationArtifactContent
    metadata: PipedriveOrganizationArtifactMetadata

    @classmethod
    def from_api_response(
        cls,
        org_data: dict[str, Any],
        ingest_job_id: UUID,
    ) -> "PipedriveOrganizationArtifact":
        """Create artifact from Pipedrive API organization response."""
        org_id = org_data.get("id", 0)
        add_time = org_data.get("add_time", "")
        update_time = org_data.get("update_time") or add_time

        # Parse update time for source_updated_at
        source_updated_at = datetime.now(UTC)
        if update_time:
            with contextlib.suppress(ValueError, TypeError):
                source_updated_at = parse_iso_timestamp(update_time)

        return cls(
            entity_id=get_pipedrive_organization_entity_id(org_id=org_id),
            content=PipedriveOrganizationArtifactContent(org_data=org_data),
            metadata=PipedriveOrganizationArtifactMetadata(
                org_id=org_id,
                name=org_data.get("name"),
                address=org_data.get("address"),
                owner_id=_extract_entity_id(org_data.get("owner_id"))
                or _extract_entity_id(org_data.get("user_id")),
                people_count=org_data.get("people_count"),
                open_deals_count=org_data.get("open_deals_count"),
                source_created_at=add_time,
                source_updated_at=update_time,
            ),
            source_updated_at=source_updated_at,
            ingest_job_id=ingest_job_id,
        )


# =========================================================================
# Activity Artifact (embedded in deals, not indexed separately)
# =========================================================================


class PipedriveActivityArtifactContent(BaseModel):
    """Activity data from Pipedrive API."""

    activity_data: dict[str, Any]


class PipedriveActivityArtifactMetadata(BaseModel):
    """Metadata for Pipedrive activity artifact."""

    activity_id: int
    subject: str | None = None
    activity_type: str | None = None
    done: bool = False
    deal_id: int | None = None
    person_id: int | None = None
    org_id: int | None = None
    due_date: str | None = None
    source_created_at: str | None = None
    source_updated_at: str | None = None


class PipedriveActivityArtifact(BaseIngestArtifact):
    """Typed Pipedrive activity artifact (usually embedded in deal documents)."""

    entity: ArtifactEntity = ArtifactEntity.PIPEDRIVE_ACTIVITY
    content: PipedriveActivityArtifactContent
    metadata: PipedriveActivityArtifactMetadata

    @classmethod
    def from_api_response(
        cls,
        activity_data: dict[str, Any],
        ingest_job_id: UUID,
    ) -> "PipedriveActivityArtifact":
        """Create artifact from Pipedrive API activity response."""
        activity_id = activity_data.get("id", 0)
        add_time = activity_data.get("add_time", "")
        update_time = activity_data.get("update_time") or add_time

        source_updated_at = datetime.now(UTC)
        if update_time:
            with contextlib.suppress(ValueError, TypeError):
                source_updated_at = parse_iso_timestamp(update_time)

        return cls(
            entity_id=get_pipedrive_activity_entity_id(activity_id=activity_id),
            content=PipedriveActivityArtifactContent(activity_data=activity_data),
            metadata=PipedriveActivityArtifactMetadata(
                activity_id=activity_id,
                subject=activity_data.get("subject"),
                activity_type=activity_data.get("type"),
                done=activity_data.get("done", False),
                deal_id=activity_data.get("deal_id"),
                person_id=activity_data.get("person_id"),
                org_id=activity_data.get("org_id"),
                due_date=activity_data.get("due_date"),
                source_created_at=add_time,
                source_updated_at=update_time,
            ),
            source_updated_at=source_updated_at,
            ingest_job_id=ingest_job_id,
        )


# =========================================================================
# Note Artifact (embedded in deals, not indexed separately)
# =========================================================================


class PipedriveNoteArtifactContent(BaseModel):
    """Note data from Pipedrive API."""

    note_data: dict[str, Any]


class PipedriveNoteArtifactMetadata(BaseModel):
    """Metadata for Pipedrive note artifact."""

    note_id: int
    content_preview: str | None = None
    deal_id: int | None = None
    person_id: int | None = None
    org_id: int | None = None
    user_id: int | None = None
    pinned: bool = False
    source_created_at: str | None = None
    source_updated_at: str | None = None


class PipedriveNoteArtifact(BaseIngestArtifact):
    """Typed Pipedrive note artifact (usually embedded in deal documents)."""

    entity: ArtifactEntity = ArtifactEntity.PIPEDRIVE_NOTE
    content: PipedriveNoteArtifactContent
    metadata: PipedriveNoteArtifactMetadata

    @classmethod
    def from_api_response(
        cls,
        note_data: dict[str, Any],
        ingest_job_id: UUID,
    ) -> "PipedriveNoteArtifact":
        """Create artifact from Pipedrive API note response."""
        note_id = note_data.get("id", 0)
        add_time = note_data.get("add_time", "")
        update_time = note_data.get("update_time") or add_time

        source_updated_at = datetime.now(UTC)
        if update_time:
            with contextlib.suppress(ValueError, TypeError):
                source_updated_at = parse_iso_timestamp(update_time)

        # Extract content preview
        content = note_data.get("content", "")
        content_preview = content[:200] if content else None

        return cls(
            entity_id=get_pipedrive_note_entity_id(note_id=note_id),
            content=PipedriveNoteArtifactContent(note_data=note_data),
            metadata=PipedriveNoteArtifactMetadata(
                note_id=note_id,
                content_preview=content_preview,
                deal_id=note_data.get("deal_id"),
                person_id=note_data.get("person_id"),
                org_id=note_data.get("org_id"),
                user_id=note_data.get("user_id"),
                pinned=note_data.get("pinned_to_deal_flag", False)
                or note_data.get("pinned_to_person_flag", False)
                or note_data.get("pinned_to_organization_flag", False),
                source_created_at=add_time,
                source_updated_at=update_time,
            ),
            source_updated_at=source_updated_at,
            ingest_job_id=ingest_job_id,
        )


# =========================================================================
# User Artifact (reference data for name enrichment)
# =========================================================================


class PipedriveUserArtifactContent(BaseModel):
    """User data from Pipedrive API."""

    user_data: dict[str, Any]


class PipedriveUserArtifactMetadata(BaseModel):
    """Metadata for Pipedrive user artifact."""

    user_id: int
    name: str | None = None
    email: str | None = None
    active: bool = True


class PipedriveUserArtifact(BaseIngestArtifact):
    """Typed Pipedrive user artifact for reference data enrichment."""

    entity: ArtifactEntity = ArtifactEntity.PIPEDRIVE_USER
    content: PipedriveUserArtifactContent
    metadata: PipedriveUserArtifactMetadata

    @classmethod
    def from_api_response(
        cls,
        user_data: dict[str, Any],
        ingest_job_id: UUID,
    ) -> "PipedriveUserArtifact":
        """Create artifact from Pipedrive API user response."""
        user_id = user_data.get("id", 0)

        # Users don't have standard timestamps, use current time
        source_updated_at = datetime.now(UTC)

        return cls(
            entity_id=get_pipedrive_user_entity_id(user_id=user_id),
            content=PipedriveUserArtifactContent(user_data=user_data),
            metadata=PipedriveUserArtifactMetadata(
                user_id=user_id,
                name=user_data.get("name"),
                email=user_data.get("email"),
                active=user_data.get("active_flag", True),
            ),
            source_updated_at=source_updated_at,
            ingest_job_id=ingest_job_id,
        )


# =========================================================================
# Product Artifact
# =========================================================================


class PipedriveProductArtifactContent(BaseModel):
    """Full product record data from Pipedrive API."""

    product_data: dict[str, Any]


class PipedriveProductArtifactMetadata(BaseModel):
    """Metadata for Pipedrive product artifact."""

    product_id: int
    name: str | None = None
    code: str | None = None
    unit: str | None = None
    tax: float | None = None
    owner_id: int | None = None
    is_linkable: bool = True
    visible_to: int | None = None
    billing_frequency: str | None = None
    source_created_at: str | None = None
    source_updated_at: str | None = None


class PipedriveProductArtifact(BaseIngestArtifact):
    """Typed Pipedrive product artifact with validated content and metadata."""

    entity: ArtifactEntity = ArtifactEntity.PIPEDRIVE_PRODUCT
    content: PipedriveProductArtifactContent
    metadata: PipedriveProductArtifactMetadata

    @classmethod
    def from_api_response(
        cls,
        product_data: dict[str, Any],
        ingest_job_id: UUID,
    ) -> "PipedriveProductArtifact":
        """Create artifact from Pipedrive API product response."""
        product_id = product_data.get("id", 0)
        add_time = product_data.get("add_time", "")
        update_time = product_data.get("update_time") or add_time

        # Parse update time for source_updated_at
        source_updated_at = datetime.now(UTC)
        if update_time:
            with contextlib.suppress(ValueError, TypeError):
                source_updated_at = parse_iso_timestamp(update_time)

        return cls(
            entity_id=get_pipedrive_product_entity_id(product_id=product_id),
            content=PipedriveProductArtifactContent(product_data=product_data),
            metadata=PipedriveProductArtifactMetadata(
                product_id=product_id,
                name=product_data.get("name"),
                code=product_data.get("code"),
                unit=product_data.get("unit"),
                tax=product_data.get("tax"),
                owner_id=_extract_entity_id(product_data.get("owner_id"))
                or _extract_entity_id(product_data.get("user_id")),
                is_linkable=product_data.get("selectable", True),
                visible_to=product_data.get("visible_to"),
                billing_frequency=product_data.get("billing_frequency"),
                source_created_at=add_time,
                source_updated_at=update_time,
            ),
            source_updated_at=source_updated_at,
            ingest_job_id=ingest_job_id,
        )
