"""Tests for warehouse data models."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from src.warehouses.models import (
    CortexAnalystRequest,
    CortexAnalystResponse,
    QueryResult,
    QueryType,
    WarehouseQueryLog,
    WarehouseSource,
)


class TestWarehouseSource:
    """Test cases for WarehouseSource enum."""

    def test_valid_sources(self):
        """Test valid warehouse sources."""
        assert WarehouseSource.SNOWFLAKE == "snowflake"
        assert WarehouseSource.BIGQUERY == "bigquery"  # type: ignore[unreachable]
        assert WarehouseSource.REDSHIFT == "redshift"
        assert WarehouseSource.DATABRICKS == "databricks"

    def test_value_assignment(self):
        """Test creating from string value."""
        source = WarehouseSource("snowflake")
        assert source == WarehouseSource.SNOWFLAKE


class TestQueryType:
    """Test cases for QueryType enum."""

    def test_valid_types(self):
        """Test valid query types."""
        assert QueryType.NATURAL_LANGUAGE == "natural_language"
        assert QueryType.SQL == "sql"  # type: ignore[unreachable]

    def test_value_assignment(self):
        """Test creating from string value."""
        query_type = QueryType("sql")
        assert query_type == QueryType.SQL


class TestWarehouseQueryLog:
    """Test cases for WarehouseQueryLog model."""

    def test_create_complete_log(self):
        """Test creating complete query log."""
        log = WarehouseQueryLog(
            id="query123",
            user_id="user456",
            source=WarehouseSource.SNOWFLAKE,
            query_type=QueryType.NATURAL_LANGUAGE,
            question="What are sales?",
            generated_sql="SELECT * FROM sales",
            semantic_model_id="model123",
            execution_time_ms=150,
            row_count=10,
            success=True,
            error_message=None,
            created_at=datetime.now(UTC),
        )

        assert log.id == "query123"
        assert log.user_id == "user456"
        assert log.source == WarehouseSource.SNOWFLAKE
        assert log.query_type == QueryType.NATURAL_LANGUAGE
        assert log.question == "What are sales?"
        assert log.generated_sql == "SELECT * FROM sales"
        assert log.success is True

    def test_create_minimal_log(self):
        """Test creating log with minimal required fields."""
        log = WarehouseQueryLog(
            id="query123",
            user_id="user456",
            source=WarehouseSource.SNOWFLAKE,
            query_type=QueryType.SQL,
            question="SELECT * FROM users",
            generated_sql=None,
            semantic_model_id=None,
            execution_time_ms=None,
            row_count=None,
            error_message=None,
            success=False,
        )

        assert log.id == "query123"
        assert log.generated_sql is None
        assert log.semantic_model_id is None
        assert log.execution_time_ms is None
        assert log.row_count is None
        assert log.error_message is None
        assert log.success is False

    def test_failed_query_log(self):
        """Test creating log for failed query."""
        log = WarehouseQueryLog(
            id="query123",
            user_id="user456",
            source=WarehouseSource.SNOWFLAKE,
            query_type=QueryType.SQL,
            question="SELECT * FROM nonexistent",
            generated_sql=None,
            semantic_model_id=None,
            success=False,
            error_message="Table 'nonexistent' does not exist",
            execution_time_ms=50,
            row_count=None,
        )

        assert log.success is False
        assert log.error_message == "Table 'nonexistent' does not exist"
        assert log.row_count is None

    def test_missing_required_fields(self):
        """Test validation error when required fields missing."""
        with pytest.raises(ValidationError):
            WarehouseQueryLog(  # type: ignore[call-arg]
                id="query123",
                user_id=None,
                generated_sql=None,
                semantic_model_id=None,
                execution_time_ms=None,
                row_count=None,
                error_message=None,
                # Missing required: source, query_type, question, success
            )


class TestQueryResult:
    """Test cases for QueryResult model."""

    def test_successful_result(self):
        """Test creating successful query result."""
        result = QueryResult(
            success=True,
            data=[{"name": "Alice", "age": 30}],
            generated_sql="SELECT name, age FROM users",
            execution_time_ms=100,
            row_count=1,
            explanation="Retrieved user data",
        )

        assert result.success is True
        assert result.data is not None
        assert len(result.data) == 1
        assert result.data[0]["name"] == "Alice"
        assert result.generated_sql == "SELECT name, age FROM users"
        assert result.execution_time_ms == 100

    def test_failed_result(self):
        """Test creating failed query result."""
        result = QueryResult(success=False, data=None, error_message="Connection timeout")

        assert result.success is False
        assert result.data is None
        assert result.error_message == "Connection timeout"
        assert result.generated_sql is None

    def test_minimal_result(self):
        """Test creating result with minimal fields."""
        result = QueryResult(success=True)

        assert result.success is True
        assert result.data is None
        assert result.generated_sql is None
        assert result.execution_time_ms is None


class TestCortexAnalystRequest:
    """Test cases for CortexAnalystRequest model."""

    def test_create_request(self):
        """Test creating Cortex Analyst request."""
        request = CortexAnalystRequest(
            messages=[{"role": "user", "content": "What are sales?"}],
            semantic_model_file="@stage/sales.yaml",
            warehouse="COMPUTE_WH",
        )

        assert len(request.messages) == 1
        assert request.messages[0]["role"] == "user"
        assert request.semantic_model_file == "@stage/sales.yaml"
        assert request.warehouse == "COMPUTE_WH"

    def test_request_without_warehouse(self):
        """Test creating request without optional warehouse."""
        request = CortexAnalystRequest(
            messages=[{"role": "user", "content": "Show data"}],
            semantic_model_file="@stage/model.yaml",
        )

        assert request.warehouse is None
        assert request.semantic_model_file == "@stage/model.yaml"

    def test_multiple_messages(self):
        """Test request with multiple messages (conversation)."""
        request = CortexAnalystRequest(
            messages=[
                {"role": "user", "content": "What are sales?"},
                {"role": "assistant", "content": "Here is the query..."},
                {"role": "user", "content": "Show top 10"},
            ],
            semantic_model_file="@stage/sales.yaml",
        )

        assert len(request.messages) == 3

    def test_model_dump_exclude_none(self):
        """Test that model_dump excludes None values."""
        request = CortexAnalystRequest(
            messages=[{"role": "user", "content": "Query"}],
            semantic_model_file="@stage/model.yaml",
            warehouse=None,
        )

        dumped = request.model_dump(exclude_none=True)
        assert "warehouse" not in dumped
        assert "messages" in dumped
        assert "semantic_model_file" in dumped


class TestCortexAnalystResponse:
    """Test cases for CortexAnalystResponse model."""

    def test_create_response(self):
        """Test creating Cortex Analyst response."""
        response = CortexAnalystResponse(
            message={"role": "assistant", "content": [{"type": "sql", "statement": "SELECT 1"}]},
            request_id="req123",
        )

        assert response.message["role"] == "assistant"
        assert response.request_id == "req123"

    def test_response_with_complex_content(self):
        """Test response with multiple content items."""
        response = CortexAnalystResponse(
            message={
                "role": "assistant",
                "content": [
                    {"type": "text", "text": "Here are the results"},
                    {"type": "sql", "statement": "SELECT * FROM sales"},
                    {"type": "results", "results": [{"revenue": 1000}]},
                ],
            },
            request_id="req123",
        )

        assert len(response.message["content"]) == 3
        assert response.message["content"][0]["type"] == "text"
        assert response.message["content"][1]["type"] == "sql"
        assert response.message["content"][2]["type"] == "results"
