"""Tests for Linear comment threading / parent_id extraction."""

from connectors.linear.linear_helpers import create_comment_activity


class TestLinearCommentThreading:
    """Test suite for Linear comment parent_id extraction."""

    def test_extracts_parent_id_from_nested_parent_object(self) -> None:
        """Test that parent_id is extracted from nested parent object (API format)."""
        comment_data = {
            "id": "comment-123",
            "body": "This is a reply",
            "createdAt": "2025-08-14T01:07:33",
            "user": {
                "id": "user-1",
                "name": "Test User",
                "displayName": "Test User",
            },
            "parent": {  # Linear API returns parent as nested object
                "id": "parent-comment-456"
            },
        }

        activity = create_comment_activity(
            comment_data,
            issue_id="issue-1",
            issue_title="Test Issue",
            team_id="team-1",
            team_name="Test Team",
        )

        assert activity["parent_id"] == "parent-comment-456"
        assert activity["comment_id"] == "comment-123"
        assert activity["comment_body"] == "This is a reply"

    def test_extracts_parent_id_from_parent_id_field(self) -> None:
        """Test that parent_id is extracted from parentId field (webhook format)."""
        comment_data = {
            "id": "comment-123",
            "body": "This is a reply",
            "createdAt": "2025-08-14T01:07:33",
            "user": {
                "id": "user-1",
                "name": "Test User",
            },
            "parentId": "parent-comment-456",  # Webhook might use flat parentId
        }

        activity = create_comment_activity(
            comment_data,
            issue_id="issue-1",
            issue_title="Test Issue",
            team_id="team-1",
            team_name="Test Team",
        )

        assert activity["parent_id"] == "parent-comment-456"

    def test_handles_root_comment_with_no_parent(self) -> None:
        """Test that root comments (no parent) have empty parent_id."""
        comment_data = {
            "id": "comment-123",
            "body": "This is a root comment",
            "createdAt": "2025-08-14T01:07:33",
            "user": {
                "id": "user-1",
                "name": "Test User",
            },
            # No parent or parentId field
        }

        activity = create_comment_activity(
            comment_data,
            issue_id="issue-1",
            issue_title="Test Issue",
            team_id="team-1",
            team_name="Test Team",
        )

        assert activity["parent_id"] == ""
        assert activity["comment_id"] == "comment-123"

    def test_handles_null_parent_object(self) -> None:
        """Test that null parent object is handled gracefully."""
        comment_data = {
            "id": "comment-123",
            "body": "This is a root comment",
            "createdAt": "2025-08-14T01:07:33",
            "user": {
                "id": "user-1",
                "name": "Test User",
            },
            "parent": None,  # Explicitly null parent
        }

        activity = create_comment_activity(
            comment_data,
            issue_id="issue-1",
            issue_title="Test Issue",
            team_id="team-1",
            team_name="Test Team",
        )

        assert activity["parent_id"] == ""

    def test_prefers_nested_parent_over_flat_parent_id(self) -> None:
        """Test that nested parent takes precedence if both formats exist."""
        comment_data = {
            "id": "comment-123",
            "body": "This is a reply",
            "createdAt": "2025-08-14T01:07:33",
            "user": {
                "id": "user-1",
                "name": "Test User",
            },
            "parent": {"id": "parent-from-nested"},
            "parentId": "parent-from-flat",
        }

        activity = create_comment_activity(
            comment_data,
            issue_id="issue-1",
            issue_title="Test Issue",
            team_id="team-1",
            team_name="Test Team",
        )

        # Nested parent format should win (API format)
        assert activity["parent_id"] == "parent-from-nested"
