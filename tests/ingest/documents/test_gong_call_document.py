"""Unit tests for Gong call document and chunk behaviour."""

from __future__ import annotations

from datetime import UTC, datetime

from connectors.gong import GongCallChunk, GongCallDocument
from src.ingest.references.reference_ids import get_gong_call_reference_id


def _sample_document() -> GongCallDocument:
    raw_data = {
        "call_id": "call-123",
        "workspace_id": "ws-1",
        "title": "Quarterly Update",
        "url": "https://app.gong.io/call/call-123",
        "meeting_url": "https://zoom.us/j/123",
        "calendar_event_id": "evt-1",
        "is_private": True,
        "owner_user_id": "user-1",
        "owner_email": "owner@example.com",
        "library_folder_ids": ["folder-a", "folder-b"],
        "explicit_access_user_ids": ["user-2"],
        "explicit_access_emails": ["user-2@example.com"],
        "source_created_at": "2024-01-01T10:00:00+00:00",
        "duration_ms": 3600000,
        "language": "en",
        "media": "zoom",
        "direction": "inbound",
        "system": "zoom",
        "scope": "company",
        "participants": [
            {
                "name": "Alice",
                "email": "alice@example.com",
                "affiliation": "Internal",
            },
            {
                "name": "Bob",
                "email": "bob@example.com",
                "affiliation": "External",
            },
        ],
        "participant_emails_internal": ["alice@example.com"],
        "participant_emails_external": ["bob@example.com"],
        "transcript_segment_count": 2,
        "transcript_chunk_count": 1,
        "transcript_lines": [
            "[00:00.00] Alice: Welcome everyone",
            "[00:30.00] Bob: Thanks Alice",
        ],
        "transcript_chunks": [
            {
                "call_id": "call-123",
                "workspace_id": "ws-1",
                "content": "[00:00.00] Alice: Welcome everyone\n[00:30.00] Bob: Thanks Alice",
                "segment_indices": [0, 1],
                "start_ms": 0,
                "end_ms": 30000,
                "speakers": [
                    {"speaker_id": "s-1", "name": "Alice"},
                    {"speaker_id": "s-2", "name": "Bob"},
                ],
            }
        ],
    }

    return GongCallDocument(
        id="doc-gong-call-123",
        raw_data=raw_data,
        source_updated_at=datetime(2024, 2, 1, tzinfo=UTC),
        permission_policy="private",
        permission_allowed_tokens=["e:owner@example.com"],
    )


class TestGongCallDocument:
    def test_get_header_content(self) -> None:
        document = _sample_document()
        header = document.get_header_content()

        assert "Call: Quarterly Update" in header
        assert "Workspace: ws-1" in header
        assert "Owner: owner@example.com" in header
        assert "Duration: 3600000 ms" in header
        assert "Participants:" in header
        assert "- Alice (Internal)" in header
        assert "- Bob (External)" in header

    def test_get_content_includes_transcript(self) -> None:
        document = _sample_document()
        content = document.get_content()

        assert "Transcript:" in content
        assert "[00:00.00] Alice: Welcome everyone" in content
        assert "[00:30.00] Bob: Thanks Alice" in content

    def test_to_embedding_chunks_populates_permissions(self) -> None:
        document = _sample_document()
        chunks = document.to_embedding_chunks()

        assert len(chunks) == 2
        header_chunk = chunks[0]
        assert isinstance(header_chunk, GongCallChunk)
        header_meta = header_chunk.get_metadata()
        assert header_meta["chunk_type"] == "header"
        assert header_meta["call_id"] == "call-123"
        assert header_meta["workspace_id"] == "ws-1"

        transcript_chunk = chunks[1]
        assert transcript_chunk.get_metadata()["segment_indices"] == [0, 1]
        # permissions copied from document
        assert transcript_chunk.permission_policy == "private"
        assert transcript_chunk.permission_allowed_tokens == ["e:owner@example.com"]

    def test_get_metadata_serializes_all_fields(self) -> None:
        document = _sample_document()
        metadata = document.get_metadata()

        assert metadata["call_id"] == "call-123"
        assert metadata["is_private"] is True
        assert metadata["participant_emails_internal"] == ["alice@example.com"]
        assert metadata["participant_emails_external"] == ["bob@example.com"]
        assert metadata["transcript_chunk_count"] == 1
        assert metadata["source"] == document.get_source()

    def test_reference_id_matches_helper(self) -> None:
        document = _sample_document()
        assert document.get_reference_id() == get_gong_call_reference_id("call-123")
