"""Pipedrive Deal document and chunk definitions.

Uses dataclass pattern matching the Attio connector for consistency.
"""

import contextlib
import re
from dataclasses import dataclass
from typing import Any, TypedDict

from connectors.base import BaseChunk, BaseDocument
from connectors.base.document_source import DocumentSource
from connectors.base.utils import convert_timestamp_to_iso
from connectors.pipedrive.pipedrive_artifacts import (
    PipedriveDealArtifact,
    _extract_entity_id,
)
from src.permissions.models import PermissionPolicy


class PipedriveDealChunkMetadata(TypedDict, total=False):
    """Metadata for Pipedrive deal chunks."""

    deal_id: int | None
    chunk_type: str | None
    content_preview: str | None
    source: str | None


class PipedriveDealDocumentMetadata(TypedDict, total=False):
    """Metadata for Pipedrive deal documents."""

    deal_id: int | None
    deal_title: str | None
    deal_value: float | None
    deal_currency: str | None
    deal_status: str | None
    stage_name: str | None
    pipeline_name: str | None
    owner_name: str | None
    owner_email: str | None
    person_name: str | None
    person_email: str | None
    org_name: str | None
    expected_close_date: str | None
    won_time: str | None
    lost_time: str | None
    lost_reason: str | None
    source_created_at: str | None
    source_updated_at: str | None
    source: str
    type: str


@dataclass
class PipedriveDealChunk(BaseChunk[PipedriveDealChunkMetadata]):
    """A searchable chunk from a Pipedrive deal document."""

    def get_content(self) -> str:
        """Get the chunk content."""
        # Header chunks store pre-formatted content directly
        if self.raw_data.get("chunk_type") == "header":
            return self.raw_data.get("content", "")

        # Check chunk_type for discriminator (note vs activity)
        chunk_type = self.raw_data.get("chunk_type", "").upper()
        content = self.raw_data.get("content", "") or self.raw_data.get("subject", "")

        if chunk_type == "NOTE":
            # Strip HTML if present
            clean_content = re.sub(r"<[^>]+>", "", content)
            return f"Note: {clean_content}"
        elif chunk_type == "ACTIVITY":
            subject = self.raw_data.get("subject", "Untitled Activity")
            # Use "type" field from Pipedrive API (e.g., "call", "meeting", "lunch")
            activity_type_name = self.raw_data.get("type", "")
            done = self.raw_data.get("done", False)
            status_icon = "[DONE]" if done else "[TODO]"
            return f"{status_icon} {activity_type_name}: {subject}"

        return content

    def get_metadata(self) -> PipedriveDealChunkMetadata:
        """Get chunk-specific metadata."""
        chunk_type = self.raw_data.get("chunk_type", "activity")
        content = self.get_content()
        content_preview = content[:200] if content else None

        return {
            "deal_id": self.raw_data.get("deal_id"),
            "chunk_type": chunk_type,
            "content_preview": content_preview,
            "source": "pipedrive_deal",
        }


@dataclass
class PipedriveDealDocument(BaseDocument[PipedriveDealChunk, PipedriveDealDocumentMetadata]):
    """Represents a Pipedrive deal for indexing and search."""

    raw_data: dict[str, Any]
    metadata: PipedriveDealDocumentMetadata | None = None
    chunk_class: type[PipedriveDealChunk] = PipedriveDealChunk

    @classmethod
    def from_artifact(
        cls,
        artifact: PipedriveDealArtifact,
        hydrated_metadata: dict[str, Any] | None = None,
        permission_policy: PermissionPolicy = "tenant",
        permission_allowed_tokens: list[str] | None = None,
    ) -> "PipedriveDealDocument":
        """Create document from artifact.

        Args:
            artifact: The Pipedrive deal artifact
            hydrated_metadata: Optional pre-hydrated metadata with enriched names
            permission_policy: Permission policy for the document
            permission_allowed_tokens: Allowed permission tokens

        Returns:
            PipedriveDealDocument instance
        """
        deal_data = artifact.content.deal_data.copy()
        deal_id = artifact.metadata.deal_id

        # Include notes and activities from artifact content
        deal_data["notes"] = artifact.content.notes
        deal_data["activities"] = artifact.content.activities

        # Merge hydrated metadata if provided
        if hydrated_metadata:
            deal_data["_hydrated"] = hydrated_metadata

        return cls(
            id=f"pipedrive_deal_{deal_id}",
            raw_data=deal_data,
            source_updated_at=artifact.source_updated_at,
            permission_policy=permission_policy,
            permission_allowed_tokens=permission_allowed_tokens,
        )

    def _get_deal_id(self) -> int:
        """Get the deal ID."""
        return self.raw_data.get("id", 0)

    def _get_title(self) -> str | None:
        """Get deal title."""
        return self.raw_data.get("title")

    def _get_hydrated_value(self, key: str) -> Any:
        """Get a hydrated value if available."""
        hydrated = self.raw_data.get("_hydrated", {})
        return hydrated.get(key)

    def get_header_content(self) -> str:
        """Get deal header for display."""
        deal_id = self._get_deal_id()
        deal_title = self._get_title() or f"Deal #{deal_id}"
        return f"Deal: <{deal_id}|{deal_title}>"

    def get_content(self) -> str:
        """Generate formatted deal content."""
        lines: list[str] = []
        deal_id = self._get_deal_id()

        # Title with ID for disambiguation
        title = self._get_title() or "Untitled Deal"
        lines.append(f"# {title} ({deal_id})")
        lines.append("")

        # Status and value
        status_parts: list[str] = []
        status = self.raw_data.get("status")
        if status:
            status_parts.append(f"Status: {status.upper()}")

        value = self.raw_data.get("value")
        currency = self.raw_data.get("currency") or "USD"
        if value:
            try:
                status_parts.append(f"Value: {float(value):,.2f} {currency}")
            except (ValueError, TypeError):
                status_parts.append(f"Value: {value} {currency}")
        if status_parts:
            lines.append(" | ".join(status_parts))
            lines.append("")

        # Pipeline and Stage
        pipeline_info: list[str] = []
        pipeline = self.raw_data.get("pipeline")
        stage = self.raw_data.get("stage")
        pipeline_name = (
            pipeline.get("name")
            if isinstance(pipeline, dict)
            else self._get_hydrated_value("pipeline_name")
        )
        stage_name = (
            stage.get("name") if isinstance(stage, dict) else self._get_hydrated_value("stage_name")
        )

        if pipeline_name:
            pipeline_info.append(f"Pipeline: {pipeline_name}")
        if stage_name:
            pipeline_info.append(f"Stage: {stage_name}")
        if pipeline_info:
            lines.append(" | ".join(pipeline_info))
            lines.append("")

        # Owner
        owner_name = self._get_hydrated_value("owner_name")
        owner_email = self._get_hydrated_value("owner_email")
        if owner_name:
            lines.append(f"Owner: {owner_name}")
            if owner_email:
                lines.append(f"Owner Email: {owner_email}")
            lines.append("")

        # Contact (Person)
        person_name = self._get_hydrated_value("person_name")
        person_email = self._get_hydrated_value("person_email")
        person_id = _extract_entity_id(self.raw_data.get("person_id"))
        if person_name:
            person_ref = f"{person_name} ({person_id})" if person_id else person_name
            lines.append(f"Contact: {person_ref}")
            if person_email:
                lines.append(f"Contact Email: {person_email}")
            lines.append("")

        # Organization
        org_name = self._get_hydrated_value("org_name")
        org_id = _extract_entity_id(self.raw_data.get("org_id"))
        if org_name:
            org_ref = f"{org_name} ({org_id})" if org_id else org_name
            lines.append(f"Organization: {org_ref}")
            lines.append("")

        # Dates
        expected_close = self.raw_data.get("expected_close_date")
        won_time = self.raw_data.get("won_time")
        lost_time = self.raw_data.get("lost_time")
        lost_reason = self.raw_data.get("lost_reason")

        if expected_close:
            lines.append(f"Expected Close: {expected_close}")
        if won_time:
            lines.append(f"Won Time: {won_time}")
        if lost_time:
            lines.append(f"Lost Time: {lost_time}")
            if lost_reason:
                lines.append(f"Lost Reason: {lost_reason}")

        # Notes
        notes = self.raw_data.get("notes", [])
        if notes and isinstance(notes, list):
            lines.append("")
            lines.append("## Notes")
            for note in notes[:5]:
                if isinstance(note, dict):
                    note_content = note.get("content", "")
                    if note_content:
                        clean_content = re.sub(r"<[^>]+>", "", note_content)
                        lines.append(f"- {clean_content[:500]}")

        # Activities
        activities = self.raw_data.get("activities", [])
        if activities and isinstance(activities, list):
            lines.append("")
            lines.append("## Activities")
            for activity in activities[:5]:
                if isinstance(activity, dict):
                    subject = activity.get("subject", "Untitled Activity")
                    activity_type = activity.get("type", "")
                    done = activity.get("done", False)
                    status_icon = "[DONE]" if done else "[TODO]"
                    lines.append(f"- {status_icon} {activity_type}: {subject}")

        return "\n".join(lines)

    def to_embedding_chunks(self) -> list[PipedriveDealChunk]:
        """Create chunks for deal header and activities."""
        chunks: list[PipedriveDealChunk] = []
        deal_id = self._get_deal_id()

        # Create header chunk with full content
        header_content = f"[{self.id}]\n{self.get_content()}"
        header_chunk = self.chunk_class(
            document=self,
            raw_data={
                "content": header_content,
                "deal_id": deal_id,
                "chunk_type": "header",
            },
        )
        self.populate_chunk_permissions(header_chunk)
        chunks.append(header_chunk)

        # Add notes as separate chunks if they exist
        notes = self.raw_data.get("notes", [])
        for note in notes:
            if isinstance(note, dict):
                note_data = {
                    **note,
                    "deal_id": deal_id,
                    "chunk_type": "note",
                }
                chunk = self.chunk_class(
                    document=self,
                    raw_data=note_data,
                )
                self.populate_chunk_permissions(chunk)
                chunks.append(chunk)

        # Add activities as separate chunks if they exist
        activities = self.raw_data.get("activities", [])
        for activity in activities:
            if isinstance(activity, dict):
                activity_data = {
                    **activity,
                    "deal_id": deal_id,
                    "chunk_type": "activity",
                }
                chunk = self.chunk_class(
                    document=self,
                    raw_data=activity_data,
                )
                self.populate_chunk_permissions(chunk)
                chunks.append(chunk)

        return chunks

    def get_source_enum(self) -> DocumentSource:
        return DocumentSource.PIPEDRIVE_DEAL

    def get_reference_id(self) -> str:
        """Get the reference ID for this document."""
        return "r_pipedrive_deal_" + str(self._get_deal_id())

    def get_metadata(self) -> PipedriveDealDocumentMetadata:
        """Get document metadata for search and filtering."""
        if self.metadata is not None:
            return self.metadata

        deal_id = self._get_deal_id()
        hydrated = self.raw_data.get("_hydrated", {})

        # Extract value
        value = self.raw_data.get("value")
        safe_value: float | None = None
        if value is not None:
            with contextlib.suppress(ValueError, TypeError):
                safe_value = float(value)

        # Extract stage and pipeline names
        pipeline = self.raw_data.get("pipeline")
        stage = self.raw_data.get("stage")
        pipeline_name = (
            pipeline.get("name") if isinstance(pipeline, dict) else hydrated.get("pipeline_name")
        )
        stage_name = stage.get("name") if isinstance(stage, dict) else hydrated.get("stage_name")

        metadata: PipedriveDealDocumentMetadata = {
            "deal_id": deal_id,
            "deal_title": self._get_title(),
            "deal_value": safe_value,
            "deal_currency": self.raw_data.get("currency"),
            "deal_status": self.raw_data.get("status"),
            "stage_name": stage_name,
            "pipeline_name": pipeline_name,
            "owner_name": hydrated.get("owner_name"),
            "owner_email": hydrated.get("owner_email"),
            "person_name": hydrated.get("person_name"),
            "person_email": hydrated.get("person_email"),
            "org_name": hydrated.get("org_name"),
            "expected_close_date": self.raw_data.get("expected_close_date"),
            "won_time": self.raw_data.get("won_time"),
            "lost_time": self.raw_data.get("lost_time"),
            "lost_reason": self.raw_data.get("lost_reason"),
            "source_created_at": convert_timestamp_to_iso(self.raw_data.get("add_time")),
            "source_updated_at": convert_timestamp_to_iso(self.raw_data.get("update_time")),
            "source": self.get_source(),
            "type": "pipedrive_deal",
        }

        return metadata
