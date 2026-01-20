"""
Tests for Slack message reference finding functionality.
"""

import pytest

from src.ingest.references.find_references import find_references_in_doc


@pytest.mark.skip(reason="TODO: AIVP-384 figure out how to handle references to Slack docs")
class TestFindReferencesSlack:
    """Test suite for Slack message reference detection."""

    def test_slack_message_references(self):
        """Test detection of Slack message references."""
        content = """
        See this message: https://company.slack.com/archives/C1234567890/p1640995200123456
        Thread: https://team.slack.com/archives/C9876543210/p1640995300654321?thread_ts=1640995200.123456
        """
        result = find_references_in_doc(content, "test_doc")

        assert len(result) == 2
        assert result["r_slack_message_company_C1234567890_1640995200123456"] == 1
        assert result["r_slack_message_team_C9876543210_1640995300654321"] == 1

    def test_slack_url_with_params(self):
        """Test Slack URLs with query parameters."""
        content = """
        Slack with params: https://team.slack.com/archives/C123/p1640995200123456?thread_ts=123&cid=C123
        """
        result = find_references_in_doc(content, "test_doc")

        assert len(result) == 1
        assert result["r_slack_message_team_C123_1640995200123456"] == 1

    def test_slack_false_positives(self):
        """Test that Slack-like patterns that aren't actual Slack messages are ignored."""
        content = """
        False positives that should NOT be detected:
        - Non-Slack domains: https://discord.com/channels/123/456789012345678901
        - Incomplete URLs: slack.com/archives/C123 (no protocol)
        - Wrong URL format: https://team.slack.com/messages/C123/p1234 (wrong path)
        - Invalid channel IDs: https://team.slack.com/archives/channel123/p1640995200123456
        - Invalid timestamps: https://team.slack.com/archives/C123/p164099520012 (too short)
        - Invalid timestamps: too long example (17 digits)
        - Missing team: https://slack.com/archives/C123/p1640995200123456
        - Invalid characters: https://team.slack.com/archives/C12#/p1640995200123456
        - Non-numeric timestamp: https://team.slack.com/archives/C123/pabc0995200123456
        - Just regular text with no URLs at all
        """
        result = find_references_in_doc(content, "test_doc")

        assert result == {}
