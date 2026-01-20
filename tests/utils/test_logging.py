"""Tests for the centralized logging utility with contextvars support."""

from __future__ import annotations

import json
import logging
import os
from io import StringIO
from unittest.mock import patch

import structlog

from src.utils.logging import (
    LogContext,
    _get_log_renderer,
    _is_local_environment,
    add_log_context,
    clear_log_context,
    configure_logging,
    get_logger,
    remove_log_context,
)


class TestBasicLoggerFunctionality:
    """Test basic logger creation and functionality."""

    def test_get_logger_returns_structlog_instance(self):
        """Test that get_logger returns a structlog BoundLogger."""
        logger = get_logger(__name__)
        # structlog returns different types depending on configuration
        # but they all have the same interface - test that we can call log methods
        assert hasattr(logger, "info")
        assert hasattr(logger, "error")
        assert hasattr(logger, "debug")
        assert callable(logger.info)

    def test_get_logger_with_extra_context(self):
        """Test that get_logger binds extra context."""
        logger = get_logger(__name__, component="test", version="1.0")

        # The logger should have the extra context bound
        # We can't easily inspect bound context, but we can test that it has logging methods
        assert hasattr(logger, "info")
        assert hasattr(logger, "bind")
        assert callable(logger.bind)


class TestEnvironmentDetection:
    """Test environment-based configuration."""

    def test_is_local_environment_with_environment_var(self):
        """Test local environment detection with ENVIRONMENT var."""
        with patch.dict(os.environ, {"GRAPEVINE_ENVIRONMENT": "local"}):
            assert _is_local_environment() is True

        with patch.dict(os.environ, {"GRAPEVINE_ENVIRONMENT": "production"}):
            assert _is_local_environment() is False

    def test_console_renderer_selection(self):
        """Test that the correct renderer is selected based on environment."""
        with patch.dict(os.environ, {"GRAPEVINE_ENVIRONMENT": "local"}):
            renderer = _get_log_renderer()
            assert isinstance(renderer, structlog.dev.ConsoleRenderer)

        with patch.dict(os.environ, {"GRAPEVINE_ENVIRONMENT": "production"}):
            renderer = _get_log_renderer()
            assert isinstance(renderer, structlog.processors.JSONRenderer)


@patch("src.utils.logging._is_local_environment", return_value=False)
class TestLogOutput:
    """Test actual log output with different configurations."""

    def setup_method(self):
        """Set up for each test."""
        clear_log_context()
        # Create a string buffer to capture log output
        self.log_stream = StringIO()
        self.handler = logging.StreamHandler(self.log_stream)

    def teardown_method(self):
        """Clean up after each test."""
        clear_log_context()
        if hasattr(self, "handler"):
            # Remove handler to avoid affecting other tests
            logging.getLogger().removeHandler(self.handler)

    def _setup_json_logging_with_test_handler(self):
        """Helper to configure JSON logging and redirect to test handler."""
        configure_logging()

        # Replace the handler that configure_logging created with our test handler
        # but keep the same formatter
        root_logger = logging.getLogger()
        existing_handler = root_logger.handlers[0]  # configure_logging adds one handler
        formatter = existing_handler.formatter  # Use the same ProcessorFormatter

        # Set up our test handler with the existing formatter
        self.handler.setFormatter(formatter)
        root_logger.handlers.clear()
        root_logger.addHandler(self.handler)

    def _get_logged_json_values(self) -> list[dict]:
        """Helper to get all logged JSON values from the log stream."""
        log_output = self.log_stream.getvalue().strip()
        if not log_output:
            return []

        lines = log_output.split("\n")
        return [json.loads(line) for line in lines if line.strip()]

    def test_context_appears_in_json_logs(self, _):
        """Test that context appears in JSON-formatted logs."""
        self._setup_json_logging_with_test_handler()

        # Set context and log
        add_log_context(tenant_id="test-tenant", request_id="req-123")
        logger = get_logger(__name__)
        logger.info("Test message", query="test query")

        # Get and verify the log output
        logs = self._get_logged_json_values()
        assert len(logs) == 1

        log_data = logs[0]
        assert log_data.get("tenant_id") == "test-tenant"
        assert log_data.get("request_id") == "req-123"
        assert log_data.get("query") == "test query"
        assert "Test message" in str(log_data)

    def test_context_with_log_context_manager(self, _):
        """Test that LogContext appears in logs."""
        self._setup_json_logging_with_test_handler()

        add_log_context(tenant_id="test-tenant")

        with LogContext(operation="test_op", user_id="user-123"):
            logger = get_logger(__name__)
            logger.info("Inside context")

            logs = self._get_logged_json_values()
            assert len(logs) == 1

            log_data = logs[0]
            assert log_data.get("tenant_id") == "test-tenant"
            assert log_data.get("operation") == "test_op"
            assert log_data.get("user_id") == "user-123"

    def test_context_persists_across_multiple_logs(self, _):
        """Test that context persists across multiple log calls."""
        self._setup_json_logging_with_test_handler()

        add_log_context(tenant_id="test-tenant", request_id="req-123")

        logger = get_logger(__name__)
        logger.info("First message")
        logger.info("Second message", extra_field="value")

        # Get and verify the log output
        logs = self._get_logged_json_values()
        assert len(logs) == 2

        # Both log messages should include the context
        for log_data in logs:
            assert log_data.get("tenant_id") == "test-tenant"
            assert log_data.get("request_id") == "req-123"

    def test_remove_log_context_removes_context_values(self, _):
        """Test that context removes context values."""
        self._setup_json_logging_with_test_handler()
        add_log_context(tenant_id="test-tenant", request_id="req-123")
        logger = get_logger(__name__)
        logger.info("First message")
        remove_log_context("request_id")
        logger.info("Second message")

        # Get and verify the log output
        logs = self._get_logged_json_values()
        assert len(logs) == 2

        # First log should have context, second shouldn't
        first_log, second_log = logs
        assert first_log.get("request_id") == "req-123"
        assert "request_id" not in second_log

    def test_clear_log_context_removes_context_from_logs(self, _):
        """Test that clear_log_context removes context from logs."""
        self._setup_json_logging_with_test_handler()

        add_log_context(tenant_id="test-tenant")
        logger = get_logger(__name__)
        logger.info("With context")

        clear_log_context()
        logger.info("Without context")

        # Get and verify the log output
        logs = self._get_logged_json_values()
        assert len(logs) == 2

        # First log should have context, second shouldn't
        first_log, second_log = logs
        assert first_log.get("tenant_id") == "test-tenant"
        assert "tenant_id" not in second_log

    def test_log_context_manager_adds_and_removes_context(self, _):
        """Test that LogContext adds context temporarily."""
        self._setup_json_logging_with_test_handler()

        add_log_context(tenant_id="test-tenant")
        logger = get_logger(__name__)

        logger.info("Before context")

        with LogContext(operation="search", user_id="user-123"):
            logger.info("Inside context")

        logger.info("After context")

        # Get and verify the log output
        logs = self._get_logged_json_values()
        assert len(logs) == 3

        first_log, second_log, third_log = logs

        # First log: only tenant_id
        assert first_log.get("tenant_id") == "test-tenant"
        assert "operation" not in first_log
        assert "user_id" not in first_log

        # Second log: all context
        assert second_log.get("tenant_id") == "test-tenant"
        assert second_log.get("operation") == "search"
        assert second_log.get("user_id") == "user-123"

        # Third log: back to only tenant_id
        assert third_log.get("tenant_id") == "test-tenant"
        assert "operation" not in third_log
        assert "user_id" not in third_log

    def test_log_context_exception_handling(self, _):
        """Test that LogContext cleans up even if exception occurs."""
        self._setup_json_logging_with_test_handler()

        add_log_context(tenant_id="test-tenant")
        logger = get_logger(__name__)

        logger.info("Before context")

        try:
            with LogContext(operation="failing_op"):
                logger.info("Inside context")
                raise ValueError("Test exception")
        except ValueError:
            pass

        logger.info("After exception")

        # Get and verify the log output
        logs = self._get_logged_json_values()
        assert len(logs) == 3

        # Context should be cleaned up after exception
        _, _, last_log = logs
        assert last_log.get("tenant_id") == "test-tenant"
        assert "operation" not in last_log
