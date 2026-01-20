"""Tests for New Relic logging integration."""

from unittest.mock import patch

from src.utils.newrelic_logging import newrelic_error_processor


class TestNewRelicErrorProcessor:
    """Test the New Relic error processor."""

    @patch("src.utils.newrelic_logging.newrelic.agent.notice_error")
    @patch("src.utils.newrelic_logging.NEWRELIC_AVAILABLE", True)
    def test_error_level_triggers_newrelic(self, mock_notice_error):
        """Test that error level logs trigger New Relic notice_error."""
        event_dict = {
            "message": "Test error message",
            "logger": "test.logger",
            "tenant_id": "test-tenant",
            "user_id": "test-user",
        }

        result = newrelic_error_processor(None, "error", event_dict)

        # Should call notice_error with custom error
        mock_notice_error.assert_called_once()

        # Should return original event dict unchanged
        assert result is event_dict

    @patch("src.utils.newrelic_logging.newrelic.agent.notice_error")
    @patch("src.utils.newrelic_logging.NEWRELIC_AVAILABLE", True)
    def test_critical_level_triggers_newrelic(self, mock_notice_error):
        """Test that critical level logs trigger New Relic notice_error."""
        event_dict = {"message": "Critical error"}

        newrelic_error_processor(None, "critical", event_dict)

        mock_notice_error.assert_called_once()

    @patch("src.utils.newrelic_logging.newrelic.agent.notice_error")
    @patch("src.utils.newrelic_logging.NEWRELIC_AVAILABLE", True)
    def test_warning_level_does_not_trigger_newrelic(self, mock_notice_error):
        """Test that warning level logs do NOT trigger New Relic."""
        event_dict = {"message": "Warning message"}

        newrelic_error_processor(None, "warning", event_dict)

        mock_notice_error.assert_not_called()

    @patch("src.utils.newrelic_logging.newrelic.agent.notice_error")
    @patch("src.utils.newrelic_logging.NEWRELIC_AVAILABLE", True)
    def test_info_level_does_not_trigger_newrelic(self, mock_notice_error):
        """Test that info level logs do NOT trigger New Relic."""
        event_dict = {"message": "Info message"}

        newrelic_error_processor(None, "info", event_dict)

        mock_notice_error.assert_not_called()

    @patch("src.utils.newrelic_logging.NEWRELIC_AVAILABLE", False)
    def test_newrelic_unavailable_does_nothing(self):
        """Test that when New Relic is unavailable, nothing happens."""
        event_dict = {"message": "Test error"}

        # Should not raise any exceptions
        result = newrelic_error_processor(None, "error", event_dict)

        # Should return original event dict unchanged
        assert result is event_dict
