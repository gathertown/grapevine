"""Tests for warehouse query result formatting utilities."""

from src.warehouses.formatting import (
    format_query_result_message,
    format_snowflake_results_to_objects,
    format_table_to_markdown,
)


class TestFormatTableToMarkdown:
    """Test cases for format_table_to_markdown function."""

    def test_empty_data(self):
        """Test formatting empty data."""
        result = format_table_to_markdown([])
        assert result == "_No results returned_"

    def test_simple_table(self):
        """Test formatting simple table."""
        data = [
            {"name": "Alice", "age": 30, "city": "NYC"},
            {"name": "Bob", "age": 25, "city": "LA"},
        ]
        result = format_table_to_markdown(data)

        assert "| name | age | city |" in result
        assert "| --- | --- | --- |" in result
        assert "| Alice | 30 | NYC |" in result
        assert "| Bob | 25 | LA |" in result

    def test_null_values(self):
        """Test formatting null values."""
        data = [{"name": "Alice", "age": None, "city": "NYC"}]
        result = format_table_to_markdown(data)

        assert "| Alice | _null_ | NYC |" in result

    def test_pipe_escaping(self):
        """Test escaping pipe characters."""
        data = [{"text": "value with | pipe"}]
        result = format_table_to_markdown(data)

        assert "value with \\| pipe" in result

    def test_cell_truncation(self):
        """Test truncating long cell values."""
        long_text = "x" * 200
        data = [{"text": long_text}]
        result = format_table_to_markdown(data, truncate_cell=100)

        assert "x" * 97 in result
        assert "..." in result
        assert len([line for line in result.split("\n") if "x" * 97 in line][0]) < 120

    def test_row_truncation(self):
        """Test truncating rows when max_rows exceeded."""
        data = [{"id": i} for i in range(150)]
        result = format_table_to_markdown(data, max_rows=100)

        assert "Showing 100 of 150 rows" in result
        # Should only have 100 data rows (not counting header and separator)
        lines = result.split("\n")
        data_lines = [
            line
            for line in lines
            if line.startswith("| ") and "id" not in line and "---" not in line
        ]
        assert len(data_lines) == 100

    def test_no_truncation_message_when_under_limit(self):
        """Test no truncation message when data is under limit."""
        data = [{"id": i} for i in range(50)]
        result = format_table_to_markdown(data, max_rows=100)

        assert "Showing" not in result
        assert "truncated" not in result


class TestFormatSnowflakeResultsToObjects:
    """Test cases for format_snowflake_results_to_objects function."""

    def test_empty_results(self):
        """Test formatting empty results."""
        result = format_snowflake_results_to_objects({"data": []})
        assert result == []

    def test_missing_data_key(self):
        """Test handling missing data key."""
        result = format_snowflake_results_to_objects({})
        assert result == []

    def test_missing_metadata(self):
        """Test handling missing metadata."""
        result = format_snowflake_results_to_objects({"data": [[1, 2, 3]]})
        assert result == []

    def test_simple_transformation(self):
        """Test simple columnar to row transformation."""
        snowflake_response = {
            "resultSetMetaData": {
                "rowType": [
                    {"name": "ID", "type": "NUMBER"},
                    {"name": "NAME", "type": "TEXT"},
                ]
            },
            "data": [[1, "Alice"], [2, "Bob"]],
        }

        result = format_snowflake_results_to_objects(snowflake_response)

        assert len(result) == 2
        assert result[0] == {"ID": 1, "NAME": "Alice"}
        assert result[1] == {"ID": 2, "NAME": "Bob"}

    def test_null_values(self):
        """Test handling null values."""
        snowflake_response = {
            "resultSetMetaData": {"rowType": [{"name": "VALUE", "type": "TEXT"}]},
            "data": [[None], ["data"]],
        }

        result = format_snowflake_results_to_objects(snowflake_response)

        assert result[0] == {"VALUE": None}
        assert result[1] == {"VALUE": "data"}

    def test_mismatched_column_count(self):
        """Test handling rows with fewer values than columns."""
        snowflake_response = {
            "resultSetMetaData": {
                "rowType": [
                    {"name": "A", "type": "TEXT"},
                    {"name": "B", "type": "TEXT"},
                    {"name": "C", "type": "TEXT"},
                ]
            },
            "data": [["val1", "val2"]],  # Only 2 values instead of 3
        }

        result = format_snowflake_results_to_objects(snowflake_response)

        assert result[0] == {"A": "val1", "B": "val2", "C": None}


class TestFormatQueryResultMessage:
    """Test cases for format_query_result_message function."""

    def test_successful_query_with_all_fields(self):
        """Test formatting successful query with all optional fields."""
        result = format_query_result_message(
            question="What are the top customers?",
            result_data=[{"customer": "Alice", "revenue": 1000}],
            generated_sql="SELECT customer, revenue FROM sales",
            explanation="This query retrieves top customers by revenue",
            execution_time_ms=150,
            row_count=1,
            success=True,
        )

        assert "## Query Results" in result
        assert "What are the top customers?" in result
        assert "This query retrieves top customers by revenue" in result
        assert "SELECT customer, revenue FROM sales" in result
        assert "1ms" in result or "150ms" in result
        assert "| customer | revenue |" in result

    def test_successful_query_minimal(self):
        """Test formatting successful query with minimal fields."""
        result = format_query_result_message(
            question="SELECT * FROM table",
            result_data=[{"id": 1}],
            success=True,
        )

        assert "## Query Results" in result
        assert "SELECT * FROM table" in result
        assert "| id |" in result

    def test_failed_query(self):
        """Test formatting failed query."""
        result = format_query_result_message(
            question="SELECT * FROM nonexistent",
            result_data=[],
            success=False,
            error_message="Table 'nonexistent' does not exist",
        )

        assert "## Query Results" in result
        assert "**Query failed**" in result
        assert "Table 'nonexistent' does not exist" in result
        assert "SELECT * FROM nonexistent" in result

    def test_empty_results(self):
        """Test formatting query with no results."""
        result = format_query_result_message(
            question="SELECT * FROM empty_table",
            result_data=[],
            success=True,
        )

        assert "_No results returned_" in result

    def test_without_generated_sql(self):
        """Test direct SQL query (no generation)."""
        result = format_query_result_message(
            question="SELECT COUNT(*) FROM users",
            result_data=[{"count": 42}],
            generated_sql=None,
            success=True,
        )

        assert "SELECT COUNT(*) FROM users" in result
        assert "Generated SQL:" not in result
        assert "| count |" in result
