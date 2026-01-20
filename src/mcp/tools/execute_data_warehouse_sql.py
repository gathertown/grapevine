"""
MCP tool for executing raw SQL queries on data warehouses.

This tool provides direct SQL execution against data warehouse platforms
without natural language translation.
"""

from typing import Annotated

from fastmcp.server.context import Context
from pydantic import Field

from src.mcp.mcp_instance import get_mcp
from src.utils.logging import get_logger
from src.warehouses.formatting import format_query_result_message
from src.warehouses.models import WarehouseSource
from src.warehouses.strategy import WarehouseStrategyFactory

logger = get_logger(__name__)


@get_mcp().tool(
    description="""Execute a READ-ONLY SQL query on a structured data warehouse.

CRITICAL RESTRICTIONS - READ CAREFULLY:
- This tool is for READ-ONLY operations ONLY
- You MUST ONLY execute SELECT queries
- You MUST NEVER execute data modification operations
- FORBIDDEN operations: INSERT, UPDATE, DELETE, DROP, CREATE, ALTER, TRUNCATE, MERGE, REPLACE, GRANT, REVOKE
- If the user asks to modify data, politely explain you can only read data, not modify it
- All queries are logged and audited

Use this tool when:
- You have a specific SELECT query to run (not natural language)
- You want precise control over the query structure
- You need to run complex analytical SQL that's difficult to express in natural language
- You need to read/analyze data from the warehouse

Valid examples (READ-ONLY):
- Snowflake: "SELECT customer_id, SUM(revenue) AS total_revenue FROM orders GROUP BY customer_id ORDER BY total_revenue DESC LIMIT 10"
- PostHog (HogQL): "SELECT count() FROM events WHERE event = '$pageview'"
- PostHog (HogQL): "SELECT toDate(timestamp) as day, count(DISTINCT distinct_id) as users FROM events GROUP BY day ORDER BY day DESC"
- PostHog (HogQL): "SELECT event, count() FROM events GROUP BY event ORDER BY count() DESC LIMIT 10"

INVALID examples (DO NOT USE):
- "UPDATE customers SET email = ..."
- "DELETE FROM orders WHERE ..."
- "DROP TABLE users"
- "INSERT INTO logs VALUES ..."

Supported sources:
- "snowflake": Snowflake data warehouse
- "posthog": PostHog analytics (uses HogQL - PostHog's SQL-like query language)
- Future: "bigquery", "redshift", "databricks", etc.

PostHog HogQL Notes:
- HogQL is PostHog's SQL dialect for querying analytics data
- Main tables: events (all tracked events), persons (user profiles), sessions
- Common event properties: event (name), distinct_id (user), timestamp, properties.$current_url
- Use toDate(timestamp) for date grouping, count(DISTINCT distinct_id) for unique users

Returns:
- Formatted markdown string with query results as a table

Security:
- Uses user's OAuth token for authentication
- Respects native data warehouse permissions (RBAC, row-level security, etc.)
- Queries are logged for audit purposes
- READ-ONLY access only
"""
)
async def execute_data_warehouse_sql(
    sql: Annotated[str, Field(description="SQL query to execute")],
    source: Annotated[
        str,
        Field(
            description='Data warehouse source (e.g., "snowflake", "bigquery", "redshift")',
            default="snowflake",
        ),
    ] = "snowflake",
    warehouse: Annotated[
        str | None,
        Field(
            description="Optional: Warehouse/compute cluster to use for query execution",
            default=None,
        ),
    ] = None,
    database: Annotated[
        str | None,
        Field(
            description="Optional: Database to use (for Snowflake). If not provided, uses default from semantic model config.",
            default=None,
        ),
    ] = None,
    schema: Annotated[
        str | None,
        Field(
            description="Optional: Schema to use (for Snowflake). If not provided, uses default from semantic model config.",
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
    Execute a raw SQL query on a data warehouse.

    Args:
        sql: SQL query to execute
        source: Data warehouse source ("snowflake", "bigquery", "posthog", etc.)
        warehouse: Optional warehouse/cluster to use
        database: Optional database to use (Snowflake). Defaults to semantic model config.
        schema: Optional schema to use (Snowflake). Defaults to semantic model config.
        limit: Maximum rows to return
        ctx: FastMCP context (auto-injected)

    Returns:
        Dictionary with query results and formatted message
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
            "message": error_msg,
        }

    # Get strategy for the warehouse source
    try:
        strategy = WarehouseStrategyFactory.get_strategy(warehouse_source)
    except ValueError as e:
        error_msg = str(e)
        return {
            "success": False,
            "error": error_msg,
            "results": [],
            "row_count": 0,
            "message": error_msg,
        }

    # Execute SQL using strategy
    try:
        result = await strategy.execute_sql(
            tenant_id=tenant_id,
            sql=sql,
            warehouse=warehouse,
            database=database,
            schema=schema,
            limit=limit,
        )

        # Format result as markdown for display
        formatted_message = format_query_result_message(
            question=sql,
            result_data=result.data or [],
            generated_sql=None,  # No NL translation for direct SQL
            explanation=result.explanation,
            execution_time_ms=result.execution_time_ms,
            row_count=result.row_count,
            success=result.success,
            error_message=result.error_message,
        )

        return {
            "success": result.success,
            "results": result.data or [],
            "row_count": result.row_count or 0,
            "execution_time_ms": result.execution_time_ms,
            "error": result.error_message,
            "message": formatted_message,
        }
    finally:
        await strategy.close()
