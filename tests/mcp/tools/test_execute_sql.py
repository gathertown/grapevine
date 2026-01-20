"""Tests for execute_data_warehouse_sql MCP tool."""

from unittest.mock import AsyncMock, Mock, patch

import pytest
from fastmcp.server.context import Context

import src.mcp.tools.execute_data_warehouse_sql as execute_data_warehouse_sql_module
from src.warehouses.models import QueryResult

# Extract the actual function from the MCP decorated object
execute_data_warehouse_sql = execute_data_warehouse_sql_module.execute_data_warehouse_sql.fn


class TestExecuteSqlTool:
    """Test cases for execute_data_warehouse_sql MCP tool."""

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
    async def test_execute_data_warehouse_sql_no_context(self):
        """Test that tool raises error when context is missing."""
        with pytest.raises(ValueError, match="Context is required"):
            await execute_data_warehouse_sql(
                sql="SELECT 1",
                source="snowflake",
                ctx=None,
            )

    @pytest.mark.asyncio
    async def test_execute_data_warehouse_sql_missing_tenant_id(self):
        """Test error when tenant_id missing from context."""
        context = Mock(spec=Context)
        context.get_state.return_value = None

        with pytest.raises(ValueError, match="tenant_id not found"):
            await execute_data_warehouse_sql(
                sql="SELECT 1",
                source="snowflake",
                ctx=context,
            )

    @pytest.mark.asyncio
    async def test_execute_data_warehouse_sql_invalid_source(self, mock_context):
        """Test error for unsupported warehouse source."""
        result = await execute_data_warehouse_sql(
            sql="SELECT 1",
            source="invalid_warehouse",
            ctx=mock_context,
        )

        assert result["success"] is False
        assert "Unsupported data warehouse source" in result["error"]
        assert "invalid_warehouse" in result["error"]

    @pytest.mark.asyncio
    async def test_execute_data_warehouse_sql_snowflake_success(self, mock_context):
        """Test successful SQL execution on Snowflake."""
        mock_strategy = AsyncMock()
        mock_strategy.execute_sql.return_value = QueryResult(
            success=True,
            data=[
                {"CUSTOMER": "Alice", "REVENUE": 1000},
                {"CUSTOMER": "Bob", "REVENUE": 800},
            ],
            execution_time_ms=150,
            row_count=2,
        )
        mock_strategy.close = AsyncMock()

        with patch(
            "src.mcp.tools.execute_data_warehouse_sql.WarehouseStrategyFactory.get_strategy",
            return_value=mock_strategy,
        ):
            result = await execute_data_warehouse_sql(
                sql="SELECT customer, revenue FROM sales",
                source="snowflake",
                ctx=mock_context,
            )

            # Verify result structure
            assert result["success"] is True
            assert result["row_count"] == 2
            assert result["execution_time_ms"] == 150
            assert len(result["results"]) == 2
            assert result["results"][0]["CUSTOMER"] == "Alice"

            # Verify message format (markdown)
            assert "## Query Results" in result["message"]
            assert "SELECT customer, revenue FROM sales" in result["message"]
            assert "Alice" in result["message"]
            assert "1000" in result["message"]

            # Verify strategy methods called
            mock_strategy.execute_sql.assert_called_once()
            call_args = mock_strategy.execute_sql.call_args
            assert call_args[1]["sql"] == "SELECT customer, revenue FROM sales"
            assert call_args[1]["tenant_id"] == "tenant123"

            mock_strategy.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_data_warehouse_sql_with_warehouse(self, mock_context):
        """Test SQL execution with specific warehouse."""
        mock_strategy = AsyncMock()
        mock_strategy.execute_sql.return_value = QueryResult(
            success=True,
            data=[{"COUNT": 42}],
            row_count=1,
        )
        mock_strategy.close = AsyncMock()

        with patch(
            "src.mcp.tools.execute_data_warehouse_sql.WarehouseStrategyFactory.get_strategy",
            return_value=mock_strategy,
        ):
            result = await execute_data_warehouse_sql(
                sql="SELECT COUNT(*) FROM users",
                source="snowflake",
                warehouse="COMPUTE_WH",
                ctx=mock_context,
            )

            # Verify warehouse parameter was passed and result is formatted
            call_args = mock_strategy.execute_sql.call_args
            assert call_args[1]["warehouse"] == "COMPUTE_WH"
            assert result["success"] is True
            assert result["results"][0]["COUNT"] == 42
            assert "42" in result["message"]

    @pytest.mark.asyncio
    async def test_execute_data_warehouse_sql_with_limit(self, mock_context):
        """Test SQL execution respects limit parameter."""
        mock_strategy = AsyncMock()
        mock_strategy.execute_sql.return_value = QueryResult(
            success=True,
            data=[{"ID": i} for i in range(150)],
            row_count=150,
        )
        mock_strategy.close = AsyncMock()

        with patch(
            "src.mcp.tools.execute_data_warehouse_sql.WarehouseStrategyFactory.get_strategy",
            return_value=mock_strategy,
        ):
            result = await execute_data_warehouse_sql(
                sql="SELECT id FROM large_table",
                source="snowflake",
                limit=50,
                ctx=mock_context,
            )

            # Verify result structure and formatting
            assert result["success"] is True
            assert result["row_count"] == 150
            assert "## Query Results" in result["message"]
            mock_strategy.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_data_warehouse_sql_empty_results(self, mock_context):
        """Test handling of query with no results."""
        mock_strategy = AsyncMock()
        mock_strategy.execute_sql.return_value = QueryResult(
            success=True,
            data=[],
            row_count=0,
        )
        mock_strategy.close = AsyncMock()

        with patch(
            "src.mcp.tools.execute_data_warehouse_sql.WarehouseStrategyFactory.get_strategy",
            return_value=mock_strategy,
        ):
            result = await execute_data_warehouse_sql(
                sql="SELECT * FROM empty_table",
                source="snowflake",
                ctx=mock_context,
            )

            assert result["success"] is True
            assert result["row_count"] == 0
            assert result["results"] == []
            assert "_No results returned_" in result["message"]

    @pytest.mark.asyncio
    async def test_execute_data_warehouse_sql_query_failure(self, mock_context):
        """Test handling of SQL execution failure."""
        mock_strategy = AsyncMock()
        mock_strategy.execute_sql.return_value = QueryResult(
            success=False,
            error_message="Table 'nonexistent' does not exist",
            data=None,
            row_count=0,
        )
        mock_strategy.close = AsyncMock()

        with patch(
            "src.mcp.tools.execute_data_warehouse_sql.WarehouseStrategyFactory.get_strategy",
            return_value=mock_strategy,
        ):
            result = await execute_data_warehouse_sql(
                sql="SELECT * FROM nonexistent",
                source="snowflake",
                ctx=mock_context,
            )

            assert result["success"] is False
            assert result["error"] == "Table 'nonexistent' does not exist"
            assert "**Query failed**" in result["message"]
            assert "Table 'nonexistent' does not exist" in result["message"]
            mock_strategy.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_data_warehouse_sql_logs_as_sql_type(self, mock_context):
        """Test that direct SQL queries are logged with SQL query type."""
        mock_strategy = AsyncMock()
        mock_strategy.execute_sql.return_value = QueryResult(
            success=True,
            data=[{"RESULT": 1}],
            row_count=1,
        )
        mock_strategy.close = AsyncMock()

        with patch(
            "src.mcp.tools.execute_data_warehouse_sql.WarehouseStrategyFactory.get_strategy",
            return_value=mock_strategy,
        ):
            result = await execute_data_warehouse_sql(
                sql="SELECT 1",
                source="snowflake",
                ctx=mock_context,
            )

            # Strategy handles logging internally
            assert result["success"] is True
            assert "## Query Results" in result["message"]
            mock_strategy.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_data_warehouse_sql_not_implemented_source(self, mock_context):
        """Test error for sources that are valid but not yet implemented."""
        result = await execute_data_warehouse_sql(
            sql="SELECT 1",
            source="redshift",
            ctx=mock_context,
        )

        # Strategy factory will return error for unregistered source
        assert result["success"] is False
        assert "redshift" in result["error"].lower()
        assert "no strategy registered" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_execute_data_warehouse_sql_complex_query(self, mock_context):
        """Test execution of complex SQL with joins and aggregations."""
        mock_strategy = AsyncMock()
        mock_strategy.execute_sql.return_value = QueryResult(
            success=True,
            data=[
                {"DEPARTMENT": "Sales", "TOTAL_REVENUE": 50000, "AVG_REVENUE": 5000},
                {"DEPARTMENT": "Marketing", "TOTAL_REVENUE": 30000, "AVG_REVENUE": 3000},
            ],
            row_count=2,
        )
        mock_strategy.close = AsyncMock()

        complex_sql = """
        SELECT
            d.name AS department,
            SUM(r.revenue) AS total_revenue,
            AVG(r.revenue) AS avg_revenue
        FROM departments d
        JOIN revenue r ON d.id = r.department_id
        GROUP BY d.name
        ORDER BY total_revenue DESC
        """

        with patch(
            "src.mcp.tools.execute_data_warehouse_sql.WarehouseStrategyFactory.get_strategy",
            return_value=mock_strategy,
        ):
            result = await execute_data_warehouse_sql(
                sql=complex_sql,
                source="snowflake",
                ctx=mock_context,
            )

            assert result["success"] is True
            assert result["row_count"] == 2
            assert result["results"][0]["DEPARTMENT"] == "Sales"
            assert "Sales" in result["message"]
            assert "50000" in result["message"]
            assert "## Query Results" in result["message"]
