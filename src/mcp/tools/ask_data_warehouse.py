"""
MCP tool for querying data warehouses using natural language.

This tool provides natural language to SQL translation and query execution
across multiple data warehouse platforms (Snowflake, BigQuery, Redshift, etc.).
"""

from typing import Annotated

from fastmcp.server.context import Context
from pydantic import Field

from src.mcp.mcp_instance import get_mcp
from src.utils.logging import get_logger
from src.warehouses.models import WarehouseSource
from src.warehouses.strategy import WarehouseStrategyFactory

logger = get_logger(__name__)


@get_mcp().tool(
    description="""Query structured data warehouses using natural language for READ-ONLY analytical queries.

IMPORTANT - READ-ONLY ACCESS:
- This tool is designed for READ-ONLY analytical queries
- It is intended for retrieving and analyzing data, NOT modifying it
- If a user asks to modify, update, delete, or change data, politely explain you can only read/analyze data
- This tool uses AI to translate natural language to SQL, so phrase questions as data retrieval requests

Use this tool when you need to:
- Get actual numbers, metrics, or quantitative data (revenue, counts, averages, etc.)
- Query tables, databases, or data warehouses
- Perform aggregations (top 10, sum, count, group by)
- Compare time periods (last quarter vs this quarter)
- Filter or slice business data by dimensions (by region, by product, by customer)
- Analyze trends, patterns, or insights from structured data

This tool differs from semantic/keyword search:
- ask_data_warehouse: Queries structured data tables for metrics and analytics (READ-ONLY)
- semantic_search/keyword_search: Searches unstructured documents (Slack, GitHub, Notion)

Examples of VALID questions (READ-ONLY analysis):
- "What were our top 10 customers by revenue last quarter?"
- "Show me sales by region for Q4"
- "How many support tickets did we close last month?"
- "What's the average deal size for enterprise customers?"
- "Which products have the highest return rate?"

Examples of INVALID questions (data modification):
- "Update customer emails to add a domain"
- "Delete old test records from the database"
- "Insert a new customer record"
- "Change the status of completed orders"

The tool will:
1. Translate your natural language question to SQL (via Snowflake Cortex Analyst, BigQuery, etc.)
2. Execute the query against the specified data warehouse
3. Return results as structured data with the generated SQL

Supported sources:
- "snowflake": Snowflake data warehouse (uses Cortex Analyst for NL→SQL)
- "posthog": PostHog analytics (Note: PostHog does not support NL queries; use execute_data_warehouse_sql with HogQL instead)
- Future: "bigquery", "redshift", "databricks", etc.

Returns:
- Dictionary with:
  - success: Boolean indicating if query succeeded
  - results: Array of result rows (each row is a dict of column name -> value)
  - generated_sql: The SQL query that was executed
  - explanation: Optional explanation from the data warehouse's AI
  - row_count: Number of rows returned
  - execution_time_ms: Query execution time in milliseconds
  - error: Optional error message if query failed
"""
)
async def ask_data_warehouse(
    question: Annotated[
        str, Field(description="Natural language question to query the data warehouse")
    ],
    source: Annotated[
        str,
        Field(
            description='Data warehouse source (e.g., "snowflake", "bigquery", "redshift")',
            default="snowflake",
        ),
    ] = "snowflake",
    semantic_model_id: Annotated[
        str | None,
        Field(
            description="Optional: Specific semantic model ID to use (if not provided, will use tenant's default or first available)",
            default=None,
        ),
    ] = None,
    limit: Annotated[
        int,
        Field(
            description="Maximum number of rows to return (default: 100)",
            ge=1,
            le=1000,
            default=100,
        ),
    ] = 100,
    ctx: Context | None = None,
) -> dict:
    """
    Query a data warehouse using natural language.

    The tool translates natural language to SQL and executes it against
    the specified data warehouse.

    Args:
        question: Natural language question
        source: Data warehouse source ("snowflake", "bigquery", etc.)
        semantic_model_id: Optional specific semantic model to use
        limit: Maximum rows to return
        ctx: FastMCP context (auto-injected)

    Returns:
        Dictionary with structured query results including:
        - results: Array of result rows
        - generated_sql: The SQL that was executed
        - explanation: Optional explanation
        - row_count: Number of rows returned
        - execution_time_ms: Execution time
        - success: Whether query succeeded
        - error: Optional error message
    """
    if not ctx:
        raise ValueError("Context is required")

    # Extract tenant from context
    tenant_id = ctx.get_state("tenant_id")

    if not tenant_id:
        raise ValueError("tenant_id not found in context")

    # Validate source
    try:
        warehouse_source = WarehouseSource(source.lower())
    except ValueError:
        error_msg = f"Unsupported data warehouse source: {source}. Supported sources: {', '.join([s.value for s in WarehouseSource])}"
        return {
            "success": False,
            "error": error_msg,
            "results": [],
            "row_count": 0,
        }

    # Get strategy for the warehouse source
    try:
        strategy = WarehouseStrategyFactory.get_strategy(warehouse_source)
    except ValueError as e:
        return {
            "success": False,
            "error": str(e),
            "results": [],
            "row_count": 0,
        }

    # Execute query using strategy
    try:
        result = await strategy.execute_natural_language_query(
            tenant_id=tenant_id,
            question=question,
            semantic_model_id=semantic_model_id,
            limit=limit,
        )

        # Convert QueryResult to dict for MCP tool response
        return {
            "success": result.success,
            "results": result.data or [],
            "generated_sql": result.generated_sql,
            "explanation": result.explanation,
            "row_count": result.row_count or 0,
            "execution_time_ms": result.execution_time_ms,
            "error": result.error_message,
        }
    finally:
        await strategy.close()
