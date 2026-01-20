"""Tests for Linear helper functions."""

from connectors.linear.linear_helpers import normalize_user_names_in_activities


class TestNormalizeUserNamesInActivities:
    """Test suite for user name normalization in Linear activities."""

    def test_normalizes_inconsistent_names_to_longest(self) -> None:
        """Test that inconsistent names for same user are normalized to longest (full name)."""
        activities = [
            {
                "activity_type": "issue_created",
                "actor": "Chandler Roth",
                "actor_id": "001d6dfc-1729-4d2b-9fd6-bd1e5c5d7b4c",
                "timestamp": "2025-08-14T01:07:01",
            },
            {
                "activity_type": "comment",
                "actor": "croth",  # Same user, different name
                "actor_id": "001d6dfc-1729-4d2b-9fd6-bd1e5c5d7b4c",
                "timestamp": "2025-08-14T01:07:33",
            },
            {
                "activity_type": "comment",
                "actor": "croth",  # Same user, different name
                "actor_id": "001d6dfc-1729-4d2b-9fd6-bd1e5c5d7b4c",
                "timestamp": "2025-08-14T01:13:24",
            },
        ]

        normalized = normalize_user_names_in_activities(activities)

        # All activities should now use the longest name (full name)
        assert len(normalized) == 3
        assert normalized[0]["actor"] == "Chandler Roth"
        assert normalized[1]["actor"] == "Chandler Roth"
        assert normalized[2]["actor"] == "Chandler Roth"

        # actor_id should remain unchanged
        assert all(act["actor_id"] == "001d6dfc-1729-4d2b-9fd6-bd1e5c5d7b4c" for act in normalized)

    def test_handles_multiple_users(self) -> None:
        """Test normalization with multiple different users."""
        activities = [
            {
                "activity_type": "issue_created",
                "actor": "Alice Smith",
                "actor_id": "user-1",
                "timestamp": "2025-08-14T01:00:00",
            },
            {
                "activity_type": "comment",
                "actor": "asmith",  # Same as Alice
                "actor_id": "user-1",
                "timestamp": "2025-08-14T01:01:00",
            },
            {
                "activity_type": "comment",
                "actor": "Bob Jones",
                "actor_id": "user-2",
                "timestamp": "2025-08-14T01:02:00",
            },
            {
                "activity_type": "comment",
                "actor": "bjones",  # Same as Bob
                "actor_id": "user-2",
                "timestamp": "2025-08-14T01:03:00",
            },
        ]

        normalized = normalize_user_names_in_activities(activities)

        assert len(normalized) == 4
        # Alice's activities use full name
        assert normalized[0]["actor"] == "Alice Smith"
        assert normalized[1]["actor"] == "Alice Smith"
        # Bob's activities use full name
        assert normalized[2]["actor"] == "Bob Jones"
        assert normalized[3]["actor"] == "Bob Jones"

    def test_handles_empty_activities_list(self) -> None:
        """Test that empty activities list is handled."""
        assert normalize_user_names_in_activities([]) == []

    def test_handles_activities_without_actor(self) -> None:
        """Test that activities missing actor fields are handled gracefully."""
        activities = [
            {
                "activity_type": "issue_created",
                "actor": "Alice",
                "actor_id": "user-1",
                "timestamp": "2025-08-14T01:00:00",
            },
            {
                "activity_type": "comment",
                # Missing actor and actor_id
                "timestamp": "2025-08-14T01:01:00",
            },
            {
                "activity_type": "comment",
                "actor": "Alice",
                "actor_id": "user-1",
                "timestamp": "2025-08-14T01:02:00",
            },
        ]

        normalized = normalize_user_names_in_activities(activities)

        assert len(normalized) == 3
        # First and third should be normalized
        assert normalized[0]["actor"] == "Alice"
        assert normalized[2]["actor"] == "Alice"
        # Second should remain unchanged (no actor fields)
        assert "actor" not in normalized[1]

    def test_prefers_full_name_when_encountered_first(self) -> None:
        """Test that full name is kept even if username appears first."""
        activities = [
            {
                "activity_type": "comment",
                "actor": "croth",  # Short name first
                "actor_id": "user-1",
                "timestamp": "2025-08-14T01:00:00",
            },
            {
                "activity_type": "issue_created",
                "actor": "Chandler Roth",  # Full name after
                "actor_id": "user-1",
                "timestamp": "2025-08-14T01:01:00",
            },
        ]

        normalized = normalize_user_names_in_activities(activities)

        # Both should use the longer (full) name
        assert normalized[0]["actor"] == "Chandler Roth"
        assert normalized[1]["actor"] == "Chandler Roth"

    def test_does_not_modify_other_fields(self) -> None:
        """Test that normalization only changes actor field, not other data."""
        activities = [
            {
                "activity_type": "comment",
                "actor": "Alice",
                "actor_id": "user-1",
                "timestamp": "2025-08-14T01:00:00",
                "comment_body": "Test comment",
                "issue_id": "issue-123",
            },
            {
                "activity_type": "comment",
                "actor": "Alice Smith",
                "actor_id": "user-1",
                "timestamp": "2025-08-14T01:01:00",
                "comment_body": "Another comment",
                "issue_id": "issue-123",
            },
        ]

        normalized = normalize_user_names_in_activities(activities)

        # Other fields should remain unchanged
        assert normalized[0]["comment_body"] == "Test comment"
        assert normalized[0]["issue_id"] == "issue-123"
        assert normalized[1]["comment_body"] == "Another comment"
        assert normalized[1]["issue_id"] == "issue-123"
