"""Unit tests for Linear issue chunk validation."""

from __future__ import annotations

from datetime import UTC, datetime

from connectors.linear import LinearIssueChunk, LinearIssueDocument


def _sample_document() -> LinearIssueDocument:
    """Create a sample Linear issue document for testing."""
    raw_data = {
        "issue_id": "test-issue-id",
        "issue_identifier": "TEST-1",
        "issue_title": "Test Issue",
        "issue_url": "https://linear.app/test/issue/TEST-1",
        "team_name": "Test Team",
        "team_id": "test-team-id",
        "status": "In Progress",
        "priority": "High",
        "assignee": "Test User",
        "labels": ["bug", "urgent"],
        "activities": [],
    }

    return LinearIssueDocument(
        id="test-doc-id",
        raw_data=raw_data,
        source_updated_at=datetime(2024, 1, 1, tzinfo=UTC),
        permission_policy="private",
        permission_allowed_tokens=None,
    )


class TestLinearIssueChunkValidation:
    """Test suite for Linear issue chunk content validation."""

    def test_empty_user_mentions_filtered(self) -> None:
        """Test that chunks with empty user mentions are filtered out."""
        document = _sample_document()
        chunk = LinearIssueChunk(
            document=document,
            linear_team_name="Test Team",
            raw_data={
                "activity_type": "issue_created",
                "formatted_time": "",
                "actor": "",
                "actor_id": "",
            },
        )

        assert not chunk.has_meaningful_content()
        assert chunk.get_content() == " <@|@> created issue"

    def test_partial_user_mentions_filtered(self) -> None:
        """Test that chunks with partial user mentions are filtered out."""
        document = _sample_document()
        chunk = LinearIssueChunk(
            document=document,
            linear_team_name="Test Team",
            raw_data={
                "activity_type": "issue_created",
                "formatted_time": "2024-01-01T12:00:00",
                "actor": "",
                "actor_id": "",
            },
        )

        assert not chunk.has_meaningful_content()
        assert "<@|@>" in chunk.get_content()

    def test_valid_comment_with_content_kept(self) -> None:
        """Test that valid comments with meaningful content are kept."""
        document = _sample_document()
        chunk = LinearIssueChunk(
            document=document,
            linear_team_name="Test Team",
            raw_data={
                "activity_type": "comment",
                "formatted_time": "2024-01-01T12:00:00",
                "actor": "John Doe",
                "actor_id": "user123",
                "comment_body": "This is a real comment with actual content",
            },
        )

        assert chunk.has_meaningful_content()
        content = chunk.get_content()
        assert "John Doe" in content
        assert "This is a real comment with actual content" in content

    def test_status_change_with_details_kept(self) -> None:
        """Test that status changes with details are kept."""
        document = _sample_document()
        chunk = LinearIssueChunk(
            document=document,
            linear_team_name="Test Team",
            raw_data={
                "activity_type": "status_changed",
                "formatted_time": "2024-01-01T12:00:00",
                "actor": "Jane Smith",
                "actor_id": "user456",
                "old_status": "In Progress",
                "new_status": "Done",
            },
        )

        assert chunk.has_meaningful_content()
        content = chunk.get_content()
        assert "Jane Smith" in content
        assert "In Progress" in content
        assert "Done" in content

    def test_empty_comment_filtered(self) -> None:
        """Test that empty comments are filtered out."""
        document = _sample_document()
        chunk = LinearIssueChunk(
            document=document,
            linear_team_name="Test Team",
            raw_data={
                "activity_type": "comment",
                "formatted_time": "2024-01-01T12:00:00",
                "actor": "John Doe",
                "actor_id": "user123",
                "comment_body": "",
            },
        )

        assert not chunk.has_meaningful_content()
        assert chunk.get_content().strip().endswith("commented:")

    def test_to_embedding_chunks_filters_empty_chunks(self) -> None:
        """Test that to_embedding_chunks filters out empty activity chunks."""
        raw_data = {
            "issue_id": "test-issue-id",
            "issue_identifier": "TEST-1",
            "issue_title": "Test Issue",
            "issue_url": "https://linear.app/test/issue/TEST-1",
            "team_name": "Test Team",
            "team_id": "test-team-id",
            "status": "In Progress",
            "activities": [
                # Empty activity (should be filtered)
                {
                    "activity_type": "issue_created",
                    "formatted_time": "",
                    "actor": "",
                    "actor_id": "",
                },
                # Valid comment (should be kept)
                {
                    "activity_type": "comment",
                    "formatted_time": "2024-01-01T12:00:00",
                    "actor": "John Doe",
                    "actor_id": "user123",
                    "comment_body": "This is a meaningful comment",
                },
                # Empty comment (should be filtered)
                {
                    "activity_type": "comment",
                    "formatted_time": "2024-01-01T13:00:00",
                    "actor": "Jane Smith",
                    "actor_id": "user456",
                    "comment_body": "",
                },
            ],
        }

        document = LinearIssueDocument(
            id="test-doc-id",
            raw_data=raw_data,
            source_updated_at=datetime(2024, 1, 1, tzinfo=UTC),
            permission_policy="private",
            permission_allowed_tokens=None,
        )

        chunks = document.to_embedding_chunks()

        # Should have header + 1 valid comment (2 empty activities filtered out)
        assert len(chunks) == 2

        # First chunk is header
        assert chunks[0].raw_data.get("chunk_type") == "header"

        # Second chunk is the valid comment
        assert chunks[1].raw_data.get("activity_type") == "comment"
        assert "meaningful comment" in chunks[1].get_content()

    def test_short_priority_values_kept(self) -> None:
        """Test that priority changes with short values like P0 are kept."""
        document = _sample_document()
        chunk = LinearIssueChunk(
            document=document,
            linear_team_name="Test Team",
            raw_data={
                "activity_type": "priority_changed",
                "formatted_time": "2024-01-01T12:00:00",
                "actor": "John Doe",
                "actor_id": "user123",
                "priority": "P0",
            },
        )

        assert chunk.has_meaningful_content()
        assert "P0" in chunk.get_content()

    def test_short_assignee_names_kept(self) -> None:
        """Test that assignees with short names are kept."""
        document = _sample_document()
        chunk = LinearIssueChunk(
            document=document,
            linear_team_name="Test Team",
            raw_data={
                "activity_type": "assignee_changed",
                "formatted_time": "2024-01-01T12:00:00",
                "actor": "John Doe",
                "actor_id": "user123",
                "assignee": "Bo",
            },
        )

        assert chunk.has_meaningful_content()
        assert "Bo" in chunk.get_content()

    def test_short_label_values_kept(self) -> None:
        """Test that labels with short values like P0 are kept."""
        document = _sample_document()
        chunk = LinearIssueChunk(
            document=document,
            linear_team_name="Test Team",
            raw_data={
                "activity_type": "label_removed",
                "formatted_time": "2024-01-01T12:00:00",
                "actor": "John Doe",
                "actor_id": "user123",
                "label": "P0",
            },
        )

        assert chunk.has_meaningful_content()
        assert "P0" in chunk.get_content()
