"""Tests for ask_data_warehouse MCP tool."""

from unittest.mock import AsyncMock, Mock, patch

import pytest
from fastmcp.server.context import Context

import src.mcp.tools.ask_data_warehouse as ask_data_warehouse_module
from src.warehouses.models import QueryResult

# Extract the actual function from the MCP decorated object
ask_data_warehouse = ask_data_warehouse_module.ask_data_warehouse.fn


class TestAskWarehouseTool:
    """Test cases for ask_data_warehouse MCP tool."""

    @pytest.fixture
    def mock_context(self):
        """Create mock FastMCP context."""
        context = Mock(spec=Context)
        context.get_state.side_effect = lambda key: {
            "tenant_id": "tenant123",
            "user_id": "user456",
        }.get(key)
        return context

    @pytest.mark.asyncio
    async def test_ask_data_warehouse_no_context(self):
        """Test that tool raises error when context is missing."""
        with pytest.raises(ValueError, match="Context is required"):
            await ask_data_warehouse(
                question="What are sales?",
                source="snowflake",
                ctx=None,
            )

    @pytest.mark.asyncio
    async def test_ask_data_warehouse_missing_tenant_id(self):
        """Test error when tenant_id missing from context."""
        context = Mock(spec=Context)
        context.get_state.return_value = None

        with pytest.raises(ValueError, match="tenant_id not found"):
            await ask_data_warehouse(
                question="What are sales?",
                source="snowflake",
                ctx=context,
            )

    @pytest.mark.asyncio
    async def test_ask_data_warehouse_invalid_source(self, mock_context):
        """Test error for unsupported warehouse source."""
        result = await ask_data_warehouse(
            question="What are sales?",
            source="invalid_warehouse",
            ctx=mock_context,
        )

        assert result["success"] is False
        assert "Unsupported data warehouse source" in result["error"]
        assert "invalid_warehouse" in result["error"]

    @pytest.mark.asyncio
    async def test_ask_data_warehouse_snowflake_success(self, mock_context):
        """Test successful Snowflake natural language query."""
        # Mock strategy to return successful result
        mock_strategy = AsyncMock()
        mock_strategy.execute_natural_language_query.return_value = QueryResult(
            success=True,
            data=[
                {"customer": "Alice", "revenue": 1000},
                {"customer": "Bob", "revenue": 800},
            ],
            generated_sql="SELECT customer, revenue FROM sales",
            explanation="Here are the top customers",
            execution_time_ms=150,
            row_count=2,
        )
        mock_strategy.close = AsyncMock()

        with patch(
            "src.mcp.tools.ask_data_warehouse.WarehouseStrategyFactory.get_strategy",
            return_value=mock_strategy,
        ):
            result = await ask_data_warehouse(
                question="What are the top customers?",
                source="snowflake",
                ctx=mock_context,
            )

            # Verify result format (dict)
            assert result["success"] is True
            assert result["row_count"] == 2
            assert result["generated_sql"] == "SELECT customer, revenue FROM sales"
            assert len(result["results"]) == 2
            assert result["results"][0]["customer"] == "Alice"

            # Verify strategy methods called
            mock_strategy.execute_natural_language_query.assert_called_once()
            mock_strategy.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_ask_data_warehouse_no_semantic_models(self, mock_context):
        """Test error when no semantic models configured."""
        mock_strategy = AsyncMock()
        mock_strategy.execute_natural_language_query.return_value = QueryResult(
            success=False,
            error_message="No semantic models configured for Snowflake. Please add semantic models in the admin dashboard first.",
            data=None,
            row_count=0,
        )
        mock_strategy.close = AsyncMock()

        with patch(
            "src.mcp.tools.ask_data_warehouse.WarehouseStrategyFactory.get_strategy",
            return_value=mock_strategy,
        ):
            result = await ask_data_warehouse(
                question="What are sales?",
                source="snowflake",
                ctx=mock_context,
            )

            assert result["success"] is False
            assert "No semantic models configured" in result["error"]
            mock_strategy.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_ask_data_warehouse_with_specific_model_id(self, mock_context):
        """Test query with specific semantic model ID."""
        mock_strategy = AsyncMock()
        mock_strategy.execute_natural_language_query.return_value = QueryResult(
            success=True,
            data=[],
            row_count=0,
        )
        mock_strategy.close = AsyncMock()

        with patch(
            "src.mcp.tools.ask_data_warehouse.WarehouseStrategyFactory.get_strategy",
            return_value=mock_strategy,
        ):
            result = await ask_data_warehouse(
                question="What are sales?",
                source="snowflake",
                semantic_model_id="model2",
                ctx=mock_context,
            )

            # Verify strategy was called with the semantic model ID
            call_args = mock_strategy.execute_natural_language_query.call_args
            assert call_args[1]["semantic_model_id"] == "model2"
            assert result["success"] is True

    @pytest.mark.asyncio
    async def test_ask_data_warehouse_invalid_model_id(self, mock_context):
        """Test error when specified model ID not found."""
        mock_strategy = AsyncMock()
        mock_strategy.execute_natural_language_query.return_value = QueryResult(
            success=False,
            error_message="Semantic model 'nonexistent' not found or not enabled.",
            data=None,
            row_count=0,
        )
        mock_strategy.close = AsyncMock()

        with patch(
            "src.mcp.tools.ask_data_warehouse.WarehouseStrategyFactory.get_strategy",
            return_value=mock_strategy,
        ):
            result = await ask_data_warehouse(
                question="What are sales?",
                source="snowflake",
                semantic_model_id="nonexistent",
                ctx=mock_context,
            )

            assert result["success"] is False
            assert "not found" in result["error"] or "not enabled" in result["error"]
            mock_strategy.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_ask_data_warehouse_with_semantic_view(self, mock_context):
        """Test query using semantic view instead of model."""
        mock_strategy = AsyncMock()
        mock_strategy.execute_natural_language_query.return_value = QueryResult(
            success=True,
            data=[],
            row_count=0,
        )
        mock_strategy.close = AsyncMock()

        with patch(
            "src.mcp.tools.ask_data_warehouse.WarehouseStrategyFactory.get_strategy",
            return_value=mock_strategy,
        ):
            result = await ask_data_warehouse(
                question="What are sales?",
                source="snowflake",
                ctx=mock_context,
            )

            # Strategy handles view vs model logic internally
            assert result["success"] is True
            mock_strategy.execute_natural_language_query.assert_called_once()

    @pytest.mark.asyncio
    async def test_ask_data_warehouse_query_failure(self, mock_context):
        """Test handling of query execution failure."""
        mock_strategy = AsyncMock()
        mock_strategy.execute_natural_language_query.return_value = QueryResult(
            success=False,
            error_message="Connection timeout",
            data=None,
            row_count=0,
            execution_time_ms=100,
        )
        mock_strategy.close = AsyncMock()

        with patch(
            "src.mcp.tools.ask_data_warehouse.WarehouseStrategyFactory.get_strategy",
            return_value=mock_strategy,
        ):
            result = await ask_data_warehouse(
                question="What are sales?",
                source="snowflake",
                ctx=mock_context,
            )

            assert result["success"] is False
            assert "Connection timeout" in result["error"]
            mock_strategy.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_ask_data_warehouse_not_implemented_source(self, mock_context):
        """Test error for sources that are valid but not yet implemented."""
        # Mock factory to raise ValueError for unregistered source
        with patch(
            "src.mcp.tools.ask_data_warehouse.WarehouseStrategyFactory.get_strategy",
            side_effect=ValueError("No strategy registered for bigquery"),
        ):
            result = await ask_data_warehouse(
                question="What are sales?",
                source="bigquery",
                ctx=mock_context,
            )

            assert result["success"] is False
            assert "bigquery" in result["error"]
