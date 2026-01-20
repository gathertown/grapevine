"""
Tests for incremental Turbopuffer indexing optimization.

These tests verify that when a document is updated with new content,
only new/changed chunks are embedded and indexed, rather than re-indexing
all chunks from scratch.
"""

import uuid
from unittest.mock import MagicMock

from connectors.slack.slack_channel_document import (
    SlackChannelChunk,
    SlackChannelDocument,
)
from src.ingest.utils import compute_chunk_diff


class TestDeterministicChunkIds:
    """Test that chunk IDs are deterministic based on content identifiers."""

    def test_slack_chunk_deterministic_id_from_message_ts(self):
        """Test that Slack chunks generate deterministic IDs from message_ts."""
        doc = MagicMock()
        doc.id = "C12345678_2025-01-15"

        chunk = SlackChannelChunk(
            document=doc,
            slack_channel_id="C12345678",
            slack_channel_name="general",
            raw_data={
                "message_ts": "1705339200.000100",
                "user_id": "U12345678",
                "username": "john",
                "text": "Hello world",
                "formatted_time": "2025-01-15 12:00:00",
            },
        )

        # Should have a unique key based on message_ts
        unique_key = chunk.get_unique_key()
        assert unique_key == "msg:1705339200.000100"

        # Should generate deterministic ID
        id1 = chunk.get_deterministic_id()
        id2 = chunk.get_deterministic_id()
        assert id1 == id2

        # Same message_ts on same document should always produce same ID
        chunk2 = SlackChannelChunk(
            document=doc,
            slack_channel_id="C12345678",
            slack_channel_name="general",
            raw_data={
                "message_ts": "1705339200.000100",
                "user_id": "U12345678",
                "username": "john",
                "text": "Different text, same message",  # Text changed but same message_ts
                "formatted_time": "2025-01-15 12:00:00",
            },
        )
        assert chunk2.get_deterministic_id() == id1

    def test_slack_header_chunk_deterministic_id(self):
        """Test that Slack header chunks have a deterministic ID."""
        doc = MagicMock()
        doc.id = "C12345678_2025-01-15"

        header_chunk = SlackChannelChunk(
            document=doc,
            slack_channel_id="C12345678",
            slack_channel_name="general",
            raw_data={
                "chunk_type": "header",
                "content": "Channel: #general\nDate: 2025-01-15",
                "channel_id": "C12345678",
                "channel_name": "general",
                "date": "2025-01-15",
            },
        )

        assert header_chunk.get_unique_key() == "header"
        id1 = header_chunk.get_deterministic_id()
        id2 = header_chunk.get_deterministic_id()
        assert id1 == id2

    def test_different_messages_different_ids(self):
        """Test that different messages get different deterministic IDs."""
        doc = MagicMock()
        doc.id = "C12345678_2025-01-15"

        chunk1 = SlackChannelChunk(
            document=doc,
            slack_channel_id="C12345678",
            slack_channel_name="general",
            raw_data={
                "message_ts": "1705339200.000100",
                "user_id": "U12345678",
                "username": "john",
                "text": "First message",
                "formatted_time": "2025-01-15 12:00:00",
            },
        )

        chunk2 = SlackChannelChunk(
            document=doc,
            slack_channel_id="C12345678",
            slack_channel_name="general",
            raw_data={
                "message_ts": "1705339260.000200",  # Different message_ts
                "user_id": "U87654321",
                "username": "jane",
                "text": "Second message",
                "formatted_time": "2025-01-15 12:01:00",
            },
        )

        assert chunk1.get_deterministic_id() != chunk2.get_deterministic_id()


class TestContentHashing:
    """Test content hash computation for chunk deduplication."""

    def test_same_content_same_hash(self):
        """Test that identical content produces identical hash."""
        doc = MagicMock()
        doc.id = "C12345678_2025-01-15"

        chunk1 = SlackChannelChunk(
            document=doc,
            slack_channel_id="C12345678",
            slack_channel_name="general",
            raw_data={
                "message_ts": "1705339200.000100",
                "user_id": "U12345678",
                "username": "john",
                "text": "Hello world",
                "formatted_time": "2025-01-15 12:00:00",
            },
        )

        chunk2 = SlackChannelChunk(
            document=doc,
            slack_channel_id="C12345678",
            slack_channel_name="general",
            raw_data={
                "message_ts": "1705339200.000100",
                "user_id": "U12345678",
                "username": "john",
                "text": "Hello world",
                "formatted_time": "2025-01-15 12:00:00",
            },
        )

        assert chunk1.get_content_hash() == chunk2.get_content_hash()

    def test_different_content_different_hash(self):
        """Test that different content produces different hash."""
        doc = MagicMock()
        doc.id = "C12345678_2025-01-15"

        chunk1 = SlackChannelChunk(
            document=doc,
            slack_channel_id="C12345678",
            slack_channel_name="general",
            raw_data={
                "message_ts": "1705339200.000100",
                "user_id": "U12345678",
                "username": "john",
                "text": "Hello world",
                "formatted_time": "2025-01-15 12:00:00",
            },
        )

        chunk2 = SlackChannelChunk(
            document=doc,
            slack_channel_id="C12345678",
            slack_channel_name="general",
            raw_data={
                "message_ts": "1705339200.000100",
                "user_id": "U12345678",
                "username": "john",
                "text": "Hello world EDITED",  # Changed text
                "formatted_time": "2025-01-15 12:00:00",
            },
        )

        assert chunk1.get_content_hash() != chunk2.get_content_hash()


class TestChunkDiffComputation:
    """Test the chunk diff algorithm."""

    def test_new_chunks_detected(self):
        """Test that new chunks are correctly identified."""
        doc = MagicMock()
        doc.id = "C12345678_2025-01-15"

        # Existing chunks in Turbopuffer
        existing_chunk_hashes: dict[str, str] = {}  # Empty - no existing chunks

        # New chunks to index
        new_chunk = SlackChannelChunk(
            document=doc,
            slack_channel_id="C12345678",
            slack_channel_name="general",
            raw_data={
                "message_ts": "1705339200.000100",
                "user_id": "U12345678",
                "username": "john",
                "text": "Hello world",
                "formatted_time": "2025-01-15 12:00:00",
            },
        )

        diff = compute_chunk_diff([new_chunk], existing_chunk_hashes)

        assert len(diff.new_chunks) == 1
        assert len(diff.changed_chunks) == 0
        assert len(diff.unchanged_chunk_ids) == 0
        assert len(diff.deleted_chunk_ids) == 0

    def test_unchanged_chunks_skipped(self):
        """Test that unchanged chunks are correctly identified and skipped."""
        doc = MagicMock()
        doc.id = "C12345678_2025-01-15"

        chunk = SlackChannelChunk(
            document=doc,
            slack_channel_id="C12345678",
            slack_channel_name="general",
            raw_data={
                "message_ts": "1705339200.000100",
                "user_id": "U12345678",
                "username": "john",
                "text": "Hello world",
                "formatted_time": "2025-01-15 12:00:00",
            },
        )

        chunk_id = str(chunk.get_deterministic_id())
        chunk_hash = chunk.get_content_hash()

        # Existing chunks in Turbopuffer - same ID and hash
        existing_chunk_hashes = {chunk_id: chunk_hash}

        diff = compute_chunk_diff([chunk], existing_chunk_hashes)

        assert len(diff.new_chunks) == 0
        assert len(diff.changed_chunks) == 0
        assert len(diff.unchanged_chunk_ids) == 1
        assert chunk_id in diff.unchanged_chunk_ids
        assert len(diff.deleted_chunk_ids) == 0

    def test_changed_chunks_detected(self):
        """Test that changed chunks (same ID, different hash) are detected."""
        doc = MagicMock()
        doc.id = "C12345678_2025-01-15"

        chunk = SlackChannelChunk(
            document=doc,
            slack_channel_id="C12345678",
            slack_channel_name="general",
            raw_data={
                "message_ts": "1705339200.000100",
                "user_id": "U12345678",
                "username": "john",
                "text": "Hello world EDITED",  # Changed content
                "formatted_time": "2025-01-15 12:00:00",
            },
        )

        chunk_id = str(chunk.get_deterministic_id())
        old_hash = "old_hash_that_doesnt_match"

        # Existing chunks in Turbopuffer - same ID but different hash
        existing_chunk_hashes = {chunk_id: old_hash}

        diff = compute_chunk_diff([chunk], existing_chunk_hashes)

        assert len(diff.new_chunks) == 0
        assert len(diff.changed_chunks) == 1
        assert len(diff.unchanged_chunk_ids) == 0
        assert len(diff.deleted_chunk_ids) == 0

    def test_deleted_chunks_detected(self):
        """Test that deleted chunks are correctly identified."""
        doc = MagicMock()
        doc.id = "C12345678_2025-01-15"

        # Current chunks (only one message remains)
        current_chunk = SlackChannelChunk(
            document=doc,
            slack_channel_id="C12345678",
            slack_channel_name="general",
            raw_data={
                "message_ts": "1705339200.000100",
                "user_id": "U12345678",
                "username": "john",
                "text": "Hello world",
                "formatted_time": "2025-01-15 12:00:00",
            },
        )

        current_id = str(current_chunk.get_deterministic_id())
        current_hash = current_chunk.get_content_hash()

        # Existing chunks in Turbopuffer - has an extra chunk that was deleted
        deleted_chunk_id = str(uuid.uuid4())
        existing_chunk_hashes = {
            current_id: current_hash,  # Still exists
            deleted_chunk_id: "some_hash",  # Was deleted from source
        }

        diff = compute_chunk_diff([current_chunk], existing_chunk_hashes)

        assert len(diff.new_chunks) == 0
        assert len(diff.changed_chunks) == 0
        assert len(diff.unchanged_chunk_ids) == 1
        assert len(diff.deleted_chunk_ids) == 1
        assert deleted_chunk_id in diff.deleted_chunk_ids

    def test_incremental_update_scenario(self):
        """
        Test the main use case: adding a new message to an existing channel-day.

        This is the scenario that triggered the bug:
        - Channel has 1197 existing messages
        - New message arrives
        - Should only embed 1 new chunk, not all 1198
        """
        doc = MagicMock()
        doc.id = "C12345678_2025-01-15"

        # Create "existing" chunks (simulating 3 messages already indexed)
        existing_messages = [
            {"message_ts": "1705339200.000100", "text": "First message"},
            {"message_ts": "1705339260.000200", "text": "Second message"},
            {"message_ts": "1705339320.000300", "text": "Third message"},
        ]

        existing_chunk_hashes = {}
        for msg in existing_messages:
            chunk = SlackChannelChunk(
                document=doc,
                slack_channel_id="C12345678",
                slack_channel_name="general",
                raw_data={
                    "message_ts": msg["message_ts"],
                    "user_id": "U12345678",
                    "username": "john",
                    "text": msg["text"],
                    "formatted_time": "2025-01-15 12:00:00",
                },
            )
            chunk_id = str(chunk.get_deterministic_id())
            chunk_hash = chunk.get_content_hash()
            existing_chunk_hashes[chunk_id] = chunk_hash

        # Now create current chunks (same 3 + 1 new message)
        all_messages = existing_messages + [
            {"message_ts": "1705339380.000400", "text": "Fourth message (NEW)"},
        ]

        current_chunks = []
        for msg in all_messages:
            chunk = SlackChannelChunk(
                document=doc,
                slack_channel_id="C12345678",
                slack_channel_name="general",
                raw_data={
                    "message_ts": msg["message_ts"],
                    "user_id": "U12345678",
                    "username": "john",
                    "text": msg["text"],
                    "formatted_time": "2025-01-15 12:00:00",
                },
            )
            current_chunks.append(chunk)

        # Compute diff
        diff = compute_chunk_diff(current_chunks, existing_chunk_hashes)

        # Should detect exactly 1 new chunk
        assert len(diff.new_chunks) == 1, (
            f"Expected 1 new chunk, got {len(diff.new_chunks)}. "
            "The incremental indexing optimization should detect only the new message."
        )

        # Should detect 3 unchanged chunks
        assert len(diff.unchanged_chunk_ids) == 3, (
            f"Expected 3 unchanged chunks, got {len(diff.unchanged_chunk_ids)}. "
            "Existing messages should be detected as unchanged and skipped."
        )

        # No changed or deleted chunks
        assert len(diff.changed_chunks) == 0
        assert len(diff.deleted_chunk_ids) == 0

        # Verify the new chunk is the fourth message
        new_chunk = diff.new_chunks[0]
        assert "Fourth message" in new_chunk.get_content()


class TestSlackDocumentChunkGeneration:
    """Test that SlackChannelDocument generates chunks with proper unique keys."""

    def test_to_embedding_chunks_has_unique_keys(self):
        """Test that all chunks from a Slack document have unique keys for deterministic IDs."""
        from datetime import UTC, datetime

        doc = SlackChannelDocument(
            id="C12345678_2025-01-15",
            raw_data={
                "channel_id": "C12345678",
                "channel_name": "general",
                "date": "2025-01-15",
                "messages": [
                    {
                        "message_ts": "1705339200.000100",
                        "user_id": "U12345678",
                        "username": "john",
                        "text": "First message",
                        "formatted_time": "2025-01-15 12:00:00",
                    },
                    {
                        "message_ts": "1705339260.000200",
                        "user_id": "U87654321",
                        "username": "jane",
                        "text": "Second message",
                        "formatted_time": "2025-01-15 12:01:00",
                    },
                ],
            },
            source_updated_at=datetime.now(UTC),
            permission_policy="tenant",
            permission_allowed_tokens=None,
        )

        chunks = doc.to_embedding_chunks()

        # Should have header + 2 messages = 3 chunks
        assert len(chunks) == 3

        # All chunks should have unique keys
        unique_keys = [chunk.get_unique_key() for chunk in chunks]
        assert all(key is not None for key in unique_keys), (
            "All Slack chunks should have unique keys"
        )

        # Keys should be unique
        assert len(set(unique_keys)) == len(unique_keys), "All unique keys should be different"

        # Header chunk should have "header" key
        assert unique_keys[0] == "header"

        # Message chunks should have "msg:" prefix
        assert unique_keys[1] is not None and unique_keys[1].startswith("msg:")
        assert unique_keys[2] is not None and unique_keys[2].startswith("msg:")

        # Deterministic IDs should be unique
        deterministic_ids = [str(chunk.get_deterministic_id()) for chunk in chunks]
        assert len(set(deterministic_ids)) == len(deterministic_ids), (
            "All deterministic IDs should be unique"
        )
