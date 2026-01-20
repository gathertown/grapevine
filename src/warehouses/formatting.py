"""
Utility functions for formatting warehouse query results.
"""

from typing import Any


def format_table_to_markdown(
    data: list[dict[str, Any]], max_rows: int = 100, truncate_cell: int = 100
) -> str:
    """
    Format tabular data as a markdown table.

    Args:
        data: List of dictionaries representing rows
        max_rows: Maximum number of rows to include
        truncate_cell: Maximum characters per cell (longer cells are truncated)

    Returns:
        Markdown-formatted table string
    """
    if not data:
        return "_No results returned_"

    # Get column names from first row
    columns = list(data[0].keys())

    # Truncate data if needed
    truncated = len(data) > max_rows
    display_data = data[:max_rows]

    # Build header
    header = "| " + " | ".join(columns) + " |"
    separator = "| " + " | ".join(["---"] * len(columns)) + " |"

    # Build rows
    rows = []
    for row in display_data:
        cells = []
        for col in columns:
            value = row.get(col, "")

            # Convert to string and handle None
            cell_str = "_null_" if value is None else str(value)

            # Truncate long cells
            if len(cell_str) > truncate_cell:
                cell_str = cell_str[: truncate_cell - 3] + "..."

            # Escape pipe characters
            cell_str = cell_str.replace("|", "\\|")

            cells.append(cell_str)

        rows.append("| " + " | ".join(cells) + " |")

    # Combine all parts
    table_parts = [header, separator] + rows

    if truncated:
        table_parts.append("")
        table_parts.append(f"_Showing {max_rows} of {len(data)} rows. Additional rows truncated._")

    return "\n".join(table_parts)


def format_snowflake_results_to_objects(result: dict[str, Any]) -> list[dict[str, Any]]:
    """
    Transform Snowflake API columnar response into array of objects.

    Snowflake returns results as:
    {
        "resultSetMetaData": {"rowType": [{"name": "COL1", "type": "TEXT"}, ...]},
        "data": [[val1, val2, ...], [val1, val2, ...]]
    }

    This transforms it to:
    [
        {"COL1": val1, "COL2": val2, ...},
        {"COL1": val1, "COL2": val2, ...}
    ]

    Args:
        result: Snowflake SQL API response

    Returns:
        List of dictionaries (row objects)
    """
    data = result.get("data", [])
    if not data:
        return []

    metadata = result.get("resultSetMetaData", {})
    row_type = metadata.get("rowType", [])

    if not row_type:
        return []

    # Transform rows
    objects = []
    for row in data:
        obj = {}
        for idx, col_metadata in enumerate(row_type):
            col_name = col_metadata.get("name", f"column_{idx}")
            obj[col_name] = row[idx] if idx < len(row) else None
        objects.append(obj)

    return objects


def format_query_result_message(
    question: str,
    result_data: list[dict[str, Any]],
    generated_sql: str | None = None,
    explanation: str | None = None,
    execution_time_ms: int | None = None,
    row_count: int | None = None,
    success: bool = True,
    error_message: str | None = None,
) -> str:
    """
    Format a complete query result message for the agent.

    Args:
        question: Original question or SQL statement
        result_data: Query results as list of dictionaries
        generated_sql: SQL that was executed (for NL queries)
        explanation: Optional explanation of the query
        execution_time_ms: Query execution time
        row_count: Number of rows returned
        success: Whether query succeeded
        error_message: Error details if query failed

    Returns:
        Formatted markdown message
    """
    parts = []

    # Header
    parts.append("## Query Results")
    parts.append("")

    # Question
    parts.append(f"**Question:** {question}")
    parts.append("")

    # Error case
    if not success:
        parts.append("**Query failed**")
        parts.append("")
        if error_message:
            parts.append(f"**Error:** {error_message}")
        return "\n".join(parts)

    # Explanation (if provided by Cortex Analyst)
    if explanation:
        parts.append(f"**Explanation:** {explanation}")
        parts.append("")

    # Generated SQL (for natural language queries)
    if generated_sql:
        parts.append("**Generated SQL:**")
        parts.append("```sql")
        parts.append(generated_sql.strip())
        parts.append("```")
        parts.append("")

    # Metadata
    metadata_parts = []
    if row_count is not None:
        metadata_parts.append(f"**Rows returned:** {row_count}")
    if execution_time_ms is not None:
        metadata_parts.append(f"**Execution time:** {execution_time_ms}ms")

    if metadata_parts:
        parts.append(" | ".join(metadata_parts))
        parts.append("")

    # Results table
    if result_data:
        parts.append("**Results:**")
        parts.append("")
        parts.append(format_table_to_markdown(result_data))
    else:
        parts.append("_No results returned_")

    return "\n".join(parts)
