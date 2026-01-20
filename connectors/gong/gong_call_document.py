"""Gong call document classes for structured call and transcript representation."""

from dataclasses import dataclass
from typing import Any, TypedDict

from connectors.base import BaseChunk, BaseDocument
from connectors.base.document_source import DocumentSource
from src.ingest.references.reference_ids import get_gong_call_reference_id


class GongCallChunkMetadata(TypedDict, total=False):
    """Metadata for Gong call chunks."""

    chunk_type: str
    call_id: str
    workspace_id: str | None
    segment_indices: list[int]
    start_ms: int | None
    end_ms: int | None
    speakers: list[dict[str, Any]]
    duration_ms: int | None
    owner_user_id: str | None
    owner_email: str | None
    title: str | None
    started: str | None
    library_folder_ids: list[str]
    meeting_url: str | None


class GongCallDocumentMetadata(TypedDict, total=False):
    """Metadata for Gong call documents."""

    call_id: str
    workspace_id: str | None
    title: str | None
    url: str | None
    meeting_url: str | None
    calendar_event_id: str | None
    is_private: bool
    owner_user_id: str | None
    owner_email: str | None
    library_folder_ids: list[str]
    explicit_access_user_ids: list[str]
    explicit_access_emails: list[str]
    source_created_at: str | None
    source_updated_at: str
    duration_ms: int | None
    language: str | None
    media: str | None
    direction: str | None
    system: str | None
    scope: str | None
    participant_emails_internal: list[str]
    participant_emails_external: list[str]
    transcript_segment_count: int
    transcript_chunk_count: int
    source: str
    type: str


class GongCallChunk(BaseChunk[GongCallChunkMetadata]):
    """Represents a chunk of Gong call content."""

    def get_content(self) -> str:
        return self.raw_data.get("content", "")

    def get_metadata(self) -> GongCallChunkMetadata:
        metadata: GongCallChunkMetadata = {
            "chunk_type": str(self.raw_data.get("chunk_type", "")),
            "call_id": str(self.raw_data.get("call_id", "")),
            "workspace_id": self.raw_data.get("workspace_id"),
            "segment_indices": self.raw_data.get("segment_indices", []),
            "start_ms": self.raw_data.get("start_ms"),
            "end_ms": self.raw_data.get("end_ms"),
            "speakers": self.raw_data.get("speakers", []),
            "duration_ms": self.raw_data.get("duration_ms"),
            "owner_user_id": self.raw_data.get("owner_user_id"),
            "owner_email": self.raw_data.get("owner_email"),
            "title": self.raw_data.get("title"),
            "started": self.raw_data.get("started"),
            "library_folder_ids": self.raw_data.get("library_folder_ids", []),
            "meeting_url": self.raw_data.get("meeting_url"),
        }
        return metadata


@dataclass
class GongCallDocument(BaseDocument[GongCallChunk, GongCallDocumentMetadata]):
    """Represents a Gong call document with header and transcript chunks."""

    raw_data: dict[str, Any]

    def get_header_content(self) -> str:
        raw_meta = self.raw_data
        lines = [
            f"Call: {raw_meta.get('title') or 'Untitled'}",
            f"Workspace: {raw_meta.get('workspace_id') or 'unknown'}",
            f"Owner: {raw_meta.get('owner_email') or raw_meta.get('owner_user_id') or 'unknown'}",
            f"Started: {raw_meta.get('started')}",
        ]

        duration = raw_meta.get("duration_ms")
        if duration is not None:
            lines.append(f"Duration: {duration} ms")

        folders = raw_meta.get("library_folder_ids") or []
        if folders:
            lines.append("Library Folders: " + ", ".join(sorted(set(folders))))

        participants = raw_meta.get("participants") or []
        if participants:
            lines.append("")
            lines.append("Participants:")
            for participant in participants:
                name = participant.get("name")
                email = participant.get("email")
                affiliation = participant.get("affiliation")
                label = name or email or "Unknown"
                if affiliation:
                    label = f"{label} ({affiliation})"
                lines.append(f"- {label}")

        return "\n".join(lines)

    def get_content(self) -> str:
        lines = [self.get_header_content()]
        transcript = self.raw_data.get("transcript_lines") or []
        if transcript:
            lines.extend(["", "Transcript:", "", *transcript])
        return "\n".join(lines)

    def to_embedding_chunks(self) -> list[GongCallChunk]:
        chunks: list[GongCallChunk] = []
        header_chunk = GongCallChunk(
            document=self,
            raw_data={
                "chunk_type": "header",
                "content": self.get_header_content(),
                "call_id": str(self.raw_data.get("call_id", "")),
                "workspace_id": self.raw_data.get("workspace_id"),
                "duration_ms": self.raw_data.get("duration_ms"),
                "owner_user_id": self.raw_data.get("owner_user_id"),
                "owner_email": self.raw_data.get("owner_email"),
                "title": self.raw_data.get("title"),
                "started": self.raw_data.get("started"),
                "library_folder_ids": self.raw_data.get("library_folder_ids", []),
                "meeting_url": self.raw_data.get("meeting_url"),
            },
        )
        chunks.append(header_chunk)

        for chunk_data in self.raw_data.get("transcript_chunks", []):
            chunk = GongCallChunk(
                document=self,
                raw_data={
                    **chunk_data,
                    "chunk_type": "transcript",
                },
            )
            chunks.append(chunk)

        for chunk in chunks:
            self.populate_chunk_permissions(chunk)

        return chunks

    def get_reference_id(self) -> str:
        return get_gong_call_reference_id(self.raw_data.get("call_id", ""))

    def get_source_enum(self) -> DocumentSource:
        return DocumentSource.GONG

    def get_metadata(self) -> GongCallDocumentMetadata:
        metadata: GongCallDocumentMetadata = {
            "call_id": str(self.raw_data.get("call_id", "")),
            "workspace_id": self.raw_data.get("workspace_id"),
            "title": self.raw_data.get("title"),
            "url": self.raw_data.get("url"),
            "meeting_url": self.raw_data.get("meeting_url"),
            "calendar_event_id": self.raw_data.get("calendar_event_id"),
            "is_private": bool(self.raw_data.get("is_private")),
            "owner_user_id": self.raw_data.get("owner_user_id"),
            "owner_email": self.raw_data.get("owner_email"),
            "library_folder_ids": self.raw_data.get("library_folder_ids", []),
            "explicit_access_user_ids": self.raw_data.get("explicit_access_user_ids", []),
            "explicit_access_emails": self.raw_data.get("explicit_access_emails", []),
            "source_created_at": self.raw_data.get("source_created_at"),
            "source_updated_at": self.source_updated_at.isoformat(),
            "duration_ms": self.raw_data.get("duration_ms"),
            "language": self.raw_data.get("language"),
            "media": self.raw_data.get("media"),
            "direction": self.raw_data.get("direction"),
            "system": self.raw_data.get("system"),
            "scope": self.raw_data.get("scope"),
            "participant_emails_internal": self.raw_data.get("participant_emails_internal", []),
            "participant_emails_external": self.raw_data.get("participant_emails_external", []),
            "transcript_segment_count": self.raw_data.get("transcript_segment_count", 0),
            "transcript_chunk_count": self.raw_data.get("transcript_chunk_count", 0),
            "source": self.get_source(),
            "type": "gong_call_document",
        }
        return metadata
