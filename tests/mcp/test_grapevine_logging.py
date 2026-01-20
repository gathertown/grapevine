"""Tests for GrapevineLoggingMiddleware."""

import json
import logging
from datetime import datetime
from io import StringIO
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastmcp.server.context import Context
from fastmcp.server.middleware import MiddlewareContext

from src.mcp.middleware.grapevine_logging import GrapevineLoggingMiddleware
from src.utils.logging import configure_logging, get_logger


@pytest.fixture
def middleware():
    """Create a GrapevineLoggingMiddleware instance."""
    return GrapevineLoggingMiddleware()


@pytest.fixture
def mock_context():
    """Create a mock FastMCP context."""
    context = MagicMock(spec=Context)
    context.get_state = MagicMock()
    return context


def create_middleware_context(
    fastmcp_context="auto",
    source="client",
    msg_type="request",
    method="tools/call",
    message=None,
    timestamp=None,
):
    """Helper to create a mock MiddlewareContext with customizable attributes.

    Args:
        fastmcp_context: The FastMCP context. Pass None for no context,
                        "auto" to create a MagicMock, or provide your own mock.
    """
    ctx = MagicMock(spec=MiddlewareContext)

    # Handle fastmcp_context specially to allow None
    if fastmcp_context == "auto":
        ctx.fastmcp_context = MagicMock(spec=Context)
        ctx.fastmcp_context.get_state = MagicMock()
    else:
        ctx.fastmcp_context = fastmcp_context

    ctx.source = source
    ctx.type = msg_type
    ctx.method = method
    ctx.timestamp = timestamp or datetime.now()

    # Create a message mock that doesn't auto-create attributes
    # Use spec to limit what attributes are available
    if message is None:
        # Create a simple object without 'name' attribute
        class MockMessage:
            pass

        ctx.message = MockMessage()
    else:
        ctx.message = message
    return ctx


@pytest.fixture
def middleware_context(mock_context):
    """Create a mock MiddlewareContext with required attributes."""
    return create_middleware_context(fastmcp_context=mock_context)


@pytest.fixture
def call_next():
    """Create a mock call_next function."""
    return AsyncMock(return_value="next_result")


class TestGrapevineLoggingMiddleware:
    """Test suite for GrapevineLoggingMiddleware."""

    def setup_method(self):
        """Set up for each test."""
        # Create a string buffer to capture log output
        self.log_stream = StringIO()
        self.handler = logging.StreamHandler(self.log_stream)

    def teardown_method(self):
        """Clean up after each test."""
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

    @patch("src.utils.logging._is_local_environment", return_value=False)
    @pytest.mark.asyncio
    async def test_middleware_with_tenant_id(self, _, middleware, middleware_context, call_next):
        """Test that middleware sets up logging context with tenant_id that appears in logs."""
        self._setup_json_logging_with_test_handler()

        # Setup
        middleware_context.fastmcp_context.get_state.return_value = "test-tenant-123"

        # Mock call_next to log something so we can verify the context
        async def mock_call_next(_):
            logger = get_logger(__name__)
            logger.info("Test log message")
            return "next_result"

        call_next.side_effect = mock_call_next

        # Execute
        await middleware(middleware_context, call_next)

        # Verify logs - should have 3 logs: Processing MCP, Test log, Completed MCP
        logs = self._get_logged_json_values()
        assert len(logs) == 3

        # First log: Processing MCP message
        assert logs[0].get("tenant_id") == "test-tenant-123"
        assert "Processing MCP message" in logs[0].get("message", "")

        # Second log: Test log message
        assert logs[1].get("tenant_id") == "test-tenant-123"
        assert "Test log message" in logs[1].get("message", "")

        # Third log: Completed MCP message
        assert logs[2].get("tenant_id") == "test-tenant-123"
        assert "Completed MCP message" in logs[2].get("message", "")
        assert "duration_ms" in logs[2]
        assert isinstance(logs[2]["duration_ms"], (int, float))
        assert logs[2]["duration_ms"] >= 0

    @patch("src.utils.logging._is_local_environment", return_value=False)
    @pytest.mark.asyncio
    async def test_middleware_without_tenant_id(self, _, middleware, middleware_context, call_next):
        """Test that middleware handles missing tenant_id gracefully."""
        self._setup_json_logging_with_test_handler()

        # Setup - tenant_id not found
        middleware_context.fastmcp_context.get_state.return_value = None

        # Mock call_next to log something so we can verify the context
        async def mock_call_next(_):
            logger = get_logger(__name__)
            logger.info("Test log message without tenant")
            return "next_result"

        call_next.side_effect = mock_call_next

        # Execute
        await middleware(middleware_context, call_next)

        # Verify logs - should have 3 logs: Processing MCP, Test log, Completed MCP
        logs = self._get_logged_json_values()
        assert len(logs) == 3

        # All logs should have tenant_id as None
        for log in logs:
            assert log.get("tenant_id") is None

        # Second log should be our test message
        assert "Test log message without tenant" in logs[1].get("message", "")

    @pytest.mark.asyncio
    async def test_middleware_with_none_context(self, middleware, call_next):
        """Test that middleware handles None fastmcp_context gracefully."""
        # Setup - no fastmcp_context
        middleware_context = create_middleware_context(fastmcp_context=None)

        # Execute
        with (
            patch("src.mcp.middleware.grapevine_logging.clear_log_context") as mock_clear,
            patch("src.mcp.middleware.grapevine_logging.LogContext") as mock_log_context,
        ):
            await middleware(middleware_context, call_next)

            # Verify logging context was cleared
            mock_clear.assert_called_once()

            # Verify LogContext was used with tenant_id=None and MCP attributes
            mock_log_context.assert_called_once_with(
                tenant_id=None, source="client", type="request", method="tools/call"
            )

            # Verify call_next was called
            call_next.assert_called_once_with(middleware_context)

    @pytest.mark.asyncio
    async def test_middleware_preserves_return_value(
        self, middleware, middleware_context, call_next
    ):
        """Test that middleware preserves the return value from call_next."""
        # Setup
        expected_result = {"result": "test_value"}
        call_next.return_value = expected_result
        middleware_context.fastmcp_context.get_state.return_value = "test-tenant"

        # Execute
        with (
            patch("src.mcp.middleware.grapevine_logging.clear_log_context"),
            patch("src.mcp.middleware.grapevine_logging.LogContext"),
        ):
            result = await middleware(middleware_context, call_next)

            # Verify the return value is preserved
            assert result == expected_result

    @pytest.mark.asyncio
    async def test_middleware_clears_context_on_each_request(
        self, middleware, middleware_context, call_next
    ):
        """Test that logging context is cleared at the start of each request."""
        # Execute multiple times to simulate multiple requests
        with (
            patch("src.mcp.middleware.grapevine_logging.clear_log_context") as mock_clear,
            patch("src.mcp.middleware.grapevine_logging.LogContext") as mock_log_context,
        ):
            # First request
            middleware_context.fastmcp_context.get_state.return_value = "tenant-1"
            await middleware(middleware_context, call_next)

            # Second request
            middleware_context.fastmcp_context.get_state.return_value = "tenant-2"
            await middleware(middleware_context, call_next)

            # Third request
            middleware_context.fastmcp_context.get_state.return_value = None
            await middleware(middleware_context, call_next)

            # Verify clear_log_context was called for each request
            assert mock_clear.call_count == 3

            # Verify LogContext was called with correct tenant_ids and MCP attributes
            assert mock_log_context.call_count == 3
            calls = mock_log_context.call_args_list
            assert calls[0][1] == {
                "tenant_id": "tenant-1",
                "source": "client",
                "type": "request",
                "method": "tools/call",
            }
            assert calls[1][1] == {
                "tenant_id": "tenant-2",
                "source": "client",
                "type": "request",
                "method": "tools/call",
            }
            assert calls[2][1] == {
                "tenant_id": None,
                "source": "client",
                "type": "request",
                "method": "tools/call",
            }

    @patch("src.utils.logging._is_local_environment", return_value=False)
    @pytest.mark.asyncio
    async def test_mcp_message_logging_with_payload(self, _, middleware_context, call_next):
        """Test that MCP messages are logged with payload when included."""
        middleware = GrapevineLoggingMiddleware(include_payloads=True, max_payload_length=100)
        self._setup_json_logging_with_test_handler()

        # Setup message with payload
        middleware_context.message.__dict__ = {"query": "test query", "context": "test context"}
        middleware_context.fastmcp_context.get_state.return_value = "test-tenant"

        # Execute
        await middleware(middleware_context, call_next)

        # Verify Processing MCP message includes payload
        logs = self._get_logged_json_values()
        processing_log = logs[0]
        assert "Processing MCP message" in processing_log.get("message", "")
        assert "payload" in processing_log
        assert "test query" in processing_log["payload"]
        # Verify Completed MCP message has duration
        completed_log = logs[1]
        assert "Completed MCP message" in completed_log.get("message", "")
        assert "duration_ms" in completed_log
        assert isinstance(completed_log["duration_ms"], (int, float))
        assert completed_log["duration_ms"] >= 0

    @patch("src.utils.logging._is_local_environment", return_value=False)
    @pytest.mark.asyncio
    async def test_mcp_message_logging_without_payload(self, _, middleware_context, call_next):
        """Test that MCP messages are logged without payload when disabled."""
        middleware = GrapevineLoggingMiddleware(include_payloads=False)
        self._setup_json_logging_with_test_handler()

        # Setup message with payload
        middleware_context.message.__dict__ = {"query": "test query", "context": "test context"}
        middleware_context.fastmcp_context.get_state.return_value = "test-tenant"

        # Execute
        await middleware(middleware_context, call_next)

        # Verify Processing MCP message does NOT include payload
        logs = self._get_logged_json_values()
        processing_log = logs[0]
        assert "Processing MCP message" in processing_log.get("message", "")
        assert "payload" not in processing_log
        # Verify Completed MCP message has duration
        completed_log = logs[1]
        assert "Completed MCP message" in completed_log.get("message", "")
        assert "duration_ms" in completed_log
        assert isinstance(completed_log["duration_ms"], (int, float))
        assert completed_log["duration_ms"] >= 0

    @patch("src.utils.logging._is_local_environment", return_value=False)
    @pytest.mark.asyncio
    async def test_payload_truncation(self, _, middleware_context, call_next):
        """Test that long payloads are truncated."""
        middleware = GrapevineLoggingMiddleware(include_payloads=True, max_payload_length=20)
        self._setup_json_logging_with_test_handler()

        # Setup message with long payload
        middleware_context.message.__dict__ = {"data": "x" * 100}
        middleware_context.fastmcp_context.get_state.return_value = "test-tenant"

        # Execute
        await middleware(middleware_context, call_next)

        # Verify payload is truncated
        logs = self._get_logged_json_values()
        processing_log = logs[0]
        assert "payload" in processing_log
        assert processing_log["payload"].endswith("...")
        assert len(processing_log["payload"]) == 23  # 20 chars + "..."
        # Verify Completed MCP message has duration
        completed_log = logs[1]
        assert "Completed MCP message" in completed_log.get("message", "")
        assert "duration_ms" in completed_log
        assert isinstance(completed_log["duration_ms"], (int, float))
        assert completed_log["duration_ms"] >= 0

    @patch("src.utils.logging._is_local_environment", return_value=False)
    @pytest.mark.asyncio
    async def test_non_serializable_payload(self, _, middleware_context, call_next):
        """Test handling of non-serializable payloads."""
        middleware = GrapevineLoggingMiddleware(include_payloads=True)
        self._setup_json_logging_with_test_handler()

        # Setup message with non-serializable payload
        class NonSerializable:
            def __str__(self):
                raise Exception("Cannot serialize")

        middleware_context.message.__dict__ = {"obj": NonSerializable()}
        middleware_context.fastmcp_context.get_state.return_value = "test-tenant"

        # Mock json.dumps to raise an exception
        with patch("json.dumps", side_effect=TypeError("Not serializable")):
            # Execute
            await middleware(middleware_context, call_next)

        # Verify non-serializable placeholder is used
        logs = self._get_logged_json_values()
        processing_log = logs[0]
        assert "payload" in processing_log
        assert processing_log["payload"] == "<non-serializable>"
        # Verify Completed MCP message has duration
        completed_log = logs[1]
        assert "Completed MCP message" in completed_log.get("message", "")
        assert "duration_ms" in completed_log
        assert isinstance(completed_log["duration_ms"], (int, float))
        assert completed_log["duration_ms"] >= 0

    @patch("src.utils.logging._is_local_environment", return_value=False)
    @pytest.mark.asyncio
    async def test_error_logging(self, _, middleware_context, call_next):
        """Test that errors are logged correctly."""
        middleware = GrapevineLoggingMiddleware()
        self._setup_json_logging_with_test_handler()

        # Setup call_next to raise an exception
        test_error = ValueError("Test error message")
        call_next.side_effect = test_error
        middleware_context.fastmcp_context.get_state.return_value = "test-tenant"

        # Execute and expect exception
        with pytest.raises(ValueError, match="Test error message"):
            await middleware(middleware_context, call_next)

        # Verify error is logged
        logs = self._get_logged_json_values()
        assert len(logs) == 2  # Processing and Failed

        error_log = logs[1]
        assert "Failed MCP message" in error_log.get("message", "")
        assert error_log.get("method") == "tools/call"
        assert error_log.get("error_type") == "ValueError"
        assert error_log.get("error_message") == "Test error message"
        assert "duration_ms" in error_log
        assert isinstance(error_log["duration_ms"], (int, float))
        assert error_log["duration_ms"] >= 0

    @patch("src.utils.logging._is_local_environment", return_value=False)
    @pytest.mark.asyncio
    async def test_mcp_attributes_in_context(self, _, call_next):
        """Test that MCP attributes are added to logging context."""
        middleware = GrapevineLoggingMiddleware()
        self._setup_json_logging_with_test_handler()

        # Setup different MCP attributes
        mock_context = MagicMock(spec=Context)
        mock_context.get_state = MagicMock(return_value="test-tenant")
        middleware_context = create_middleware_context(
            fastmcp_context=mock_context,
            source="server",
            msg_type="notification",
            method="custom/method",
        )

        # Mock call_next to log something
        async def mock_call_next(_):
            logger = get_logger(__name__)
            logger.info("Test with MCP attributes")
            return "result"

        call_next.side_effect = mock_call_next

        # Execute
        await middleware(middleware_context, call_next)

        # Verify MCP attributes appear in all logs
        logs = self._get_logged_json_values()
        for log in logs:
            assert log.get("source") == "server"
            assert log.get("type") == "notification"
            assert log.get("method") == "custom/method"

    @patch("src.utils.logging._is_local_environment", return_value=False)
    @pytest.mark.asyncio
    async def test_tool_name_extraction_from_tools_call(self, _, call_next):
        """Test that tool name is extracted from tools/call messages."""
        middleware = GrapevineLoggingMiddleware()
        self._setup_json_logging_with_test_handler()

        # Create mock message with tool name
        class MockMessage:
            def __init__(self):
                self.name = "semantic_search"
                self.__dict__ = {"name": "semantic_search", "arguments": {}}

        mock_message = MockMessage()

        mock_context = MagicMock(spec=Context)
        mock_context.get_state = MagicMock(return_value="test-tenant")

        # Use the helper function for consistency
        middleware_context = create_middleware_context(
            fastmcp_context=mock_context,
            method="tools/call",
            message=mock_message,
        )

        # Execute
        await middleware(middleware_context, call_next)

        # Verify tool name appears in all MCP logs
        logs = self._get_logged_json_values()
        assert len(logs) == 2  # Processing and Completed

        processing_log = logs[0]
        assert "Processing MCP message" in processing_log.get("message", "")
        assert processing_log.get("tool_name") == "semantic_search"

        completed_log = logs[1]
        assert "Completed MCP message" in completed_log.get("message", "")
        assert completed_log.get("tool_name") == "semantic_search"

    @patch("src.utils.logging._is_local_environment", return_value=False)
    @pytest.mark.asyncio
    async def test_tool_name_not_present_for_non_tools_call(self, _, call_next):
        """Test that tool_name is not added for non-tools/call methods."""
        middleware = GrapevineLoggingMiddleware()
        self._setup_json_logging_with_test_handler()

        mock_context = MagicMock(spec=Context)
        mock_context.get_state = MagicMock(return_value="test-tenant")
        middleware_context = create_middleware_context(
            fastmcp_context=mock_context,
            method="tools/list",
        )

        # Execute
        await middleware(middleware_context, call_next)

        # Verify tool_name is not present in logs
        logs = self._get_logged_json_values()
        for log in logs:
            assert "tool_name" not in log

    @patch("src.utils.logging._is_local_environment", return_value=False)
    @pytest.mark.asyncio
    async def test_tool_name_in_error_logs(self, _, call_next):
        """Test that tool name is included in error logs for tools/call."""
        middleware = GrapevineLoggingMiddleware()
        self._setup_json_logging_with_test_handler()

        # Create mock message with tool call params
        mock_message = MagicMock()
        mock_message.name = "failing_tool"

        # Setup call_next to raise an exception
        test_error = ValueError("Tool execution failed")
        call_next.side_effect = test_error

        mock_context = MagicMock(spec=Context)
        mock_context.get_state = MagicMock(return_value="test-tenant")
        middleware_context = create_middleware_context(
            fastmcp_context=mock_context,
            method="tools/call",
        )
        middleware_context.message = mock_message

        # Execute and expect exception
        with pytest.raises(ValueError, match="Tool execution failed"):
            await middleware(middleware_context, call_next)

        # Verify tool name appears in error log
        logs = self._get_logged_json_values()
        assert len(logs) == 2  # Processing and Failed

        error_log = logs[1]
        assert "Failed MCP message" in error_log.get("message", "")
        assert error_log.get("tool_name") == "failing_tool"
