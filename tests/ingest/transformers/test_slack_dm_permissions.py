"""Tests for Slack DM permission handling in transformer."""

from connectors.slack import SlackTransformer


class TestSlackDMPermissions:
    """Test DM permission handling in Slack transformer."""

    def test_get_user_email_from_profile(self):
        """Test getting user email from profile.email field."""
        transformer = SlackTransformer()
        transformer._users_metadata = {
            "U123456789": {"profile": {"email": "alice@company.com"}},
        }

        email = transformer._get_user_email("U123456789")
        assert email == "alice@company.com"

    def test_get_user_email_from_user_field(self):
        """Test getting user email from user.email field."""
        transformer = SlackTransformer()
        transformer._users_metadata = {
            "U123456789": {"email": "alice@company.com"},
        }

        email = transformer._get_user_email("U123456789")
        assert email == "alice@company.com"

    def test_get_user_email_not_found(self):
        """Test that None is returned when user is not found."""
        transformer = SlackTransformer()
        transformer._users_metadata = {}

        email = transformer._get_user_email("U123456789")
        assert email is None

    def test_get_user_email_no_email_field(self):
        """Test that None is returned when user has no email field."""
        transformer = SlackTransformer()
        transformer._users_metadata = {
            "U123456789": {"name": "alice", "profile": {"display_name": "Alice"}},
        }

        email = transformer._get_user_email("U123456789")
        assert email is None

    def test_get_dm_permission_tokens_from_memory_with_participants(self):
        """Test getting DM permission tokens from DM participants map."""
        transformer = SlackTransformer()
        dm_id = "D1234567890"

        # Mock user metadata with email addresses
        transformer._users_metadata = {
            "U123456789": {"profile": {"email": "alice@company.com"}},
            "U987654321": {"profile": {"email": "bob@company.com"}},
        }

        # Mock DM participants map with user IDs
        transformer._dm_participants_map = {dm_id: ["U123456789", "U987654321"]}

        # Test the method
        tokens = transformer._get_dm_permission_tokens(dm_id)

        # Verify results
        assert tokens is not None
        assert len(tokens) == 2
        assert "e:alice@company.com" in tokens
        assert "e:bob@company.com" in tokens

    def test_get_dm_permission_tokens_from_memory_no_participants(self):
        """Test that None is returned when no participants are found in DM map."""
        transformer = SlackTransformer()
        dm_id = "D1234567890"

        # Mock empty DM participants map
        transformer._dm_participants_map = {}

        # Test the method
        tokens = transformer._get_dm_permission_tokens(dm_id)

        # Verify results
        assert tokens is None

    def test_get_dm_permission_tokens_from_memory_no_emails(self):
        """Test that None is returned when participants have no emails."""
        transformer = SlackTransformer()
        dm_id = "D1234567890"

        # Mock user metadata without emails
        transformer._users_metadata = {
            "U123456789": {"profile": {}},
            "U987654321": {"name": "bob"},
        }

        # Mock DM participants map with user IDs that have no emails
        transformer._dm_participants_map = {dm_id: ["U123456789", "U987654321"]}

        # Test the method
        tokens = transformer._get_dm_permission_tokens(dm_id)

        # Verify results
        assert tokens is None

    def test_get_dm_permission_tokens_deduplication(self):
        """Test that duplicate participants are properly deduplicated."""
        transformer = SlackTransformer()
        dm_id = "D1234567890"

        # Mock user metadata with email addresses
        transformer._users_metadata = {
            "U123456789": {"profile": {"email": "rod@enok.co"}},
        }

        # Mock DM participants map with duplicate user IDs (self-DM scenario)
        transformer._dm_participants_map = {
            dm_id: ["U123456789", "U123456789"]  # Same user twice
        }

        # Test the method
        tokens = transformer._get_dm_permission_tokens(dm_id)

        # Verify results - should only have one token despite duplicate user IDs
        assert tokens is not None
        assert len(tokens) == 1
        assert "e:rod@enok.co" in tokens
