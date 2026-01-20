"""Tests for MCP tool call tracking."""

import asyncio
from unittest.mock import patch

import pytest

from src.mcp.tracking import track_invalid_tool, track_tool_call


class TestTrackInvalidTool:
    """Test the track_invalid_tool function."""

    @patch("src.mcp.tracking.tool_tracker.logger")
    @patch("src.mcp.tracking.tool_tracker.newrelic.agent.record_custom_metric")
    def test_track_invalid_tool(self, mock_newrelic, mock_logger):
        """Test tracking an invalid tool call."""
        track_invalid_tool("nonexistent_tool")

        # Check NewRelic metric
        mock_newrelic.assert_called_once_with("Custom/MCPTool/InvalidTool/Count", 1)

        # Check logging
        mock_logger.warning.assert_called_once()
        log_message = mock_logger.warning.call_args[0][0]
        assert "Invalid MCP tool requested" in log_message
        log_data = mock_logger.warning.call_args[1]
        assert log_data["tool_name"] == "nonexistent_tool"
        assert log_data["status"] == "invalid"


class TestTrackToolCall:
    """Test the track_tool_call wrapper function."""

    @pytest.mark.asyncio
    @patch("src.mcp.tracking.tool_tracker.logger")
    @patch("src.mcp.tracking.tool_tracker.newrelic.agent.record_custom_metrics")
    async def test_async_function_success(self, mock_newrelic, mock_logger):
        """Test tracking an async function that succeeds."""
        expected_result = {"results": [1, 2, 3]}

        async def async_tool():
            await asyncio.sleep(0.01)
            return expected_result

        result = await track_tool_call(
            tool_name="async_tool",
            tool_func=async_tool,
            parameters={"param1": "value1"},
            tenant_id="tenant123",
        )

        assert result == expected_result

        # Check that metrics were recorded
        mock_newrelic.assert_called_once()
        metrics_list = mock_newrelic.call_args[0][0]
        metrics_dict = dict(metrics_list)
        assert "Custom/MCPTool/All/Count" in metrics_dict
        assert metrics_dict["Custom/MCPTool/All/Count"] == 1
        assert "Custom/MCPTool/async_tool/Success" in metrics_dict

        # Check that success was logged
        mock_logger.info.assert_called_once()
        log_data = mock_logger.info.call_args[1]
        assert log_data["tool_name"] == "async_tool"
        assert log_data["status"] == "success"
        assert log_data["tenant_id"] == "tenant123"
        assert log_data["result_count"] == 3

    @pytest.mark.asyncio
    @patch("src.mcp.tracking.tool_tracker.logger")
    @patch("src.mcp.tracking.tool_tracker.newrelic.agent.notice_error")
    @patch("src.mcp.tracking.tool_tracker.newrelic.agent.record_custom_metrics")
    async def test_async_function_error(
        self, mock_newrelic_metrics, mock_newrelic_exception, mock_logger
    ):
        """Test tracking an async function that raises an exception."""

        async def failing_tool():
            await asyncio.sleep(0.01)
            raise ValueError("Tool failed")

        with pytest.raises(ValueError, match="Tool failed"):
            await track_tool_call(
                tool_name="failing_tool",
                tool_func=failing_tool,
                parameters={"param2": "value2"},
            )

        # Check that metrics were recorded
        mock_newrelic_metrics.assert_called_once()
        metrics_list = mock_newrelic_metrics.call_args[0][0]
        metrics_dict = dict(metrics_list)
        assert "Custom/MCPTool/All/Error" in metrics_dict
        assert "Custom/MCPTool/failing_tool/Error" in metrics_dict

        # Check that exception was recorded
        mock_newrelic_exception.assert_called_once()

        # Check that error was logged
        mock_logger.error.assert_called_once()
        log_data = mock_logger.error.call_args[1]
        assert log_data["tool_name"] == "failing_tool"
        assert log_data["status"] == "error"
        assert log_data["error_type"] == "ValueError"
        assert log_data["error_message"] == "Tool failed"

    @pytest.mark.asyncio
    @patch("src.mcp.tracking.tool_tracker.logger")
    @patch("src.mcp.tracking.tool_tracker.newrelic.agent.record_custom_metrics")
    async def test_sync_function_wrapped_as_async(self, mock_newrelic, mock_logger):
        """Test tracking a sync function (lambda) that returns an awaitable."""
        expected_result = {"results": ["a", "b", "c"]}

        async def actual_work():
            await asyncio.sleep(0.01)
            return expected_result

        # Use a lambda that returns an awaitable (common pattern in our code)
        result = await track_tool_call(
            tool_name="lambda_tool",
            tool_func=lambda: actual_work(),
            parameters={"key": "value"},
        )

        assert result == expected_result

        # Check that success was logged
        mock_logger.info.assert_called_once()
        log_data = mock_logger.info.call_args[1]
        assert log_data["tool_name"] == "lambda_tool"
        assert log_data["status"] == "success"
        assert log_data["result_count"] == 3

    @pytest.mark.asyncio
    @patch("src.mcp.tracking.tool_tracker.logger")
    @patch("src.mcp.tracking.tool_tracker.newrelic.agent.record_custom_metrics")
    async def test_immediate_value_function(self, mock_newrelic, mock_logger):
        """Test tracking a function that returns a value immediately (not async)."""
        expected_result = {"results": [42]}

        def sync_tool():
            return expected_result

        result = await track_tool_call(
            tool_name="sync_tool",
            tool_func=sync_tool,
        )

        assert result == expected_result

        # Check that success was logged
        mock_logger.info.assert_called_once()
        log_data = mock_logger.info.call_args[1]
        assert log_data["tool_name"] == "sync_tool"
        assert log_data["status"] == "success"
        assert log_data["result_count"] == 1

    @pytest.mark.asyncio
    @patch("src.mcp.tracking.tool_tracker.logger")
    @patch("src.mcp.tracking.tool_tracker.newrelic.agent.record_custom_metrics")
    async def test_result_extraction_edge_cases(self, mock_newrelic, mock_logger):
        """Test edge cases for result extraction."""
        # Test with no results key
        await track_tool_call(
            tool_name="test_tool",
            tool_func=lambda: {"other_key": "value"},
        )
        log_data = mock_logger.info.call_args[1]
        assert "result_count" not in log_data

        mock_logger.reset_mock()
        mock_newrelic.reset_mock()

        # Test with results not being a list
        await track_tool_call(
            tool_name="test_tool",
            tool_func=lambda: {"results": "not a list"},
        )
        log_data = mock_logger.info.call_args[1]
        assert "result_count" not in log_data

        mock_logger.reset_mock()
        mock_newrelic.reset_mock()

        # Test with None result
        await track_tool_call(
            tool_name="test_tool",
            tool_func=lambda: None,
        )
        log_data = mock_logger.info.call_args[1]
        assert "result_count" not in log_data


class TestIntegrationScenarios:
    """Test real-world integration scenarios."""

    @pytest.mark.asyncio
    @patch("src.mcp.tracking.tool_tracker.logger")
    @patch("src.mcp.tracking.tool_tracker.newrelic.agent.record_custom_metrics")
    async def test_multiple_concurrent_track_tool_call(self, mock_newrelic, mock_logger):
        """Test multiple track_tool_call functions running concurrently."""

        async def tool_execution(tool_name: str, delay: float, should_fail: bool = False):
            async def tool_func():
                await asyncio.sleep(delay)
                if should_fail:
                    raise ValueError(f"Error in {tool_name}")
                return {"results": [tool_name]}

            return await track_tool_call(tool_name=tool_name, tool_func=tool_func)

        # Run multiple tools concurrently
        tasks = [
            tool_execution("tool1", 0.01),
            tool_execution("tool2", 0.02),
            tool_execution("tool3", 0.01, should_fail=True),
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Check that we got the expected exception
        assert any(isinstance(r, ValueError) for r in results)

        # Check that metrics were recorded for all tools
        assert mock_newrelic.call_count == 3

        # Check that we have both success and error logs
        assert mock_logger.info.call_count == 2  # Two successful
        assert mock_logger.error.call_count == 1  # One failed
