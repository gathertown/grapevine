"""
Snowflake warehouse strategy implementation.

Handles natural language queries via Cortex Analyst and direct SQL execution.
"""

import time

from src.clients.tenant_db import tenant_db_manager
from src.utils.logging import get_logger
from src.warehouses.formatting import format_snowflake_results_to_objects
from src.warehouses.models import (
    DEFAULT_SQL_TIMEOUT_SECONDS,
    QueryResult,
    QueryType,
    SemanticModel,
    WarehouseSource,
)
from src.warehouses.snowflake_service import SnowflakeService
from src.warehouses.strategy import WarehouseStrategy

logger = get_logger(__name__)

# Semantic model type constants (matches TypeScript SemanticModelType enum)
SEMANTIC_MODEL_TYPE_MODEL = "model"
SEMANTIC_MODEL_TYPE_VIEW = "view"


class SnowflakeStrategy(WarehouseStrategy):
    """Snowflake warehouse implementation using Cortex Analyst and SQL API."""

    def __init__(self):
        self.service = SnowflakeService()

    @property
    def supports_natural_language(self) -> bool:
        """Snowflake supports NL queries via Cortex Analyst."""
        return True

    async def execute_natural_language_query(
        self,
        tenant_id: str,
        question: str,
        semantic_model_id: str | None = None,
        limit: int = 100,
    ) -> QueryResult:
        """Execute natural language query using Snowflake Cortex Analyst."""
        start_time = time.time()

        try:
            # Get semantic models
            semantic_models = await self.service.get_semantic_models(tenant_id)

            if not semantic_models:
                error_msg = "No semantic models configured for Snowflake. Please add semantic models in the admin dashboard first."
                return QueryResult(
                    success=False,
                    error_message=error_msg,
                    data=None,
                    row_count=0,
                )

            # Select semantic model
            if semantic_model_id:
                selected_model = next(
                    (m for m in semantic_models if str(m["id"]) == semantic_model_id),
                    None,
                )
                if not selected_model:
                    error_msg = f"Semantic model '{semantic_model_id}' not found or not enabled."
                    return QueryResult(
                        success=False,
                        error_message=error_msg,
                        data=None,
                        row_count=0,
                    )
            else:
                # Use first available model
                selected_model = semantic_models[0]

            logger.info(
                "Using Snowflake semantic model for natural language query",
                extra={
                    "tenant_id": tenant_id,
                    "model_id": selected_model["id"],
                    "model_name": selected_model["name"],
                    "model_type": selected_model["type"],
                },
            )

            # Get semantic model path based on type
            # Use semantic_model_file for stage files, semantic_view for database objects
            if selected_model["type"] == SEMANTIC_MODEL_TYPE_MODEL:
                semantic_model_file = selected_model["stage_path"]
                semantic_view = None
            else:
                # For views, construct the full database object path
                db = selected_model["database_name"]
                schema = selected_model["schema_name"]
                name = selected_model["name"]
                semantic_model_file = None
                semantic_view = f"{db}.{schema}.{name}"

            # Get warehouse (optional, falls back to user default if not specified)
            warehouse = selected_model.get("warehouse")

            # Call Cortex Analyst
            cortex_response = await self.service.call_cortex_analyst(
                tenant_id=tenant_id,
                question=question,
                semantic_model_file=semantic_model_file,
                semantic_view=semantic_view,
                warehouse=warehouse,
            )

            # Parse response
            message = cortex_response.get("message", {})
            content_items = message.get("content", [])

            # Extract SQL and explanation
            generated_sql = None
            explanation = None
            for item in content_items:
                if item.get("type") == "sql":
                    generated_sql = item.get("statement")
                elif item.get("type") == "text":
                    explanation = item.get("text")

            if not generated_sql:
                return QueryResult(
                    success=False,
                    error_message="Cortex Analyst did not generate SQL",
                    data=None,
                    row_count=0,
                )

            # Get database/schema from view if using semantic view
            database = None
            schema = None
            if semantic_view:
                parts = semantic_view.split(".")
                if len(parts) >= 2:
                    database = parts[0]
                    schema = parts[1]

            # Execute the generated SQL
            sql_response = await self.service.execute_sql(
                tenant_id=tenant_id,
                sql=generated_sql,
                warehouse=warehouse,
                database=database,
                schema=schema,
                timeout=DEFAULT_SQL_TIMEOUT_SECONDS,
            )

            # Transform results
            result_data = format_snowflake_results_to_objects(sql_response)
            execution_time_ms = int((time.time() - start_time) * 1000)

            # Apply limit to data
            limited_data = result_data[:limit]
            row_count = len(limited_data)

            # Log query with actual returned row count
            await self.service.log_query(
                tenant_id=tenant_id,
                user_id=None,
                source=WarehouseSource.SNOWFLAKE,
                query_type=QueryType.NATURAL_LANGUAGE,
                question=question,
                generated_sql=generated_sql,
                semantic_model_id=str(selected_model["id"]),
                execution_time_ms=execution_time_ms,
                row_count=row_count,
                success=True,
            )

            return QueryResult(
                success=True,
                data=limited_data,
                generated_sql=generated_sql,
                execution_time_ms=execution_time_ms,
                row_count=row_count,
                explanation=explanation,
            )

        except Exception as e:
            execution_time_ms = int((time.time() - start_time) * 1000)
            error_msg = str(e)

            # Log failure
            await self.service.log_query(
                tenant_id=tenant_id,
                user_id=None,
                source=WarehouseSource.SNOWFLAKE,
                query_type=QueryType.NATURAL_LANGUAGE,
                question=question,
                execution_time_ms=execution_time_ms,
                success=False,
                error_message=error_msg,
            )

            return QueryResult(
                success=False,
                error_message=error_msg,
                data=None,
                row_count=0,
                execution_time_ms=execution_time_ms,
            )

    async def execute_sql(
        self,
        tenant_id: str,
        sql: str,
        warehouse: str | None = None,
        database: str | None = None,
        schema: str | None = None,
        limit: int = 100,
    ) -> QueryResult:
        """Execute direct SQL query against Snowflake."""
        start_time = time.time()

        try:
            # If warehouse/database/schema not specified, try to get defaults from semantic models
            if not warehouse or not database or not schema:
                semantic_models = await self.service.get_semantic_models(tenant_id)
                if semantic_models:
                    first_model = semantic_models[0]
                    if not warehouse:
                        warehouse = first_model.get("warehouse")
                    if not database:
                        database = first_model.get("database_name")
                    if not schema:
                        schema = first_model.get("schema_name")

            # Execute SQL
            sql_response = await self.service.execute_sql(
                tenant_id=tenant_id,
                sql=sql,
                warehouse=warehouse,
                database=database,
                schema=schema,
                timeout=DEFAULT_SQL_TIMEOUT_SECONDS,
            )

            # Transform results
            result_data = format_snowflake_results_to_objects(sql_response)
            execution_time_ms = int((time.time() - start_time) * 1000)

            # Apply limit to data
            sliced_data = result_data[:limit]
            row_count = len(sliced_data)

            # Log query with actual returned row count
            await self.service.log_query(
                tenant_id=tenant_id,
                user_id=None,
                source=WarehouseSource.SNOWFLAKE,
                query_type=QueryType.SQL,
                question=sql,
                generated_sql=None,
                execution_time_ms=execution_time_ms,
                row_count=row_count,
                success=True,
            )

            return QueryResult(
                success=True,
                data=sliced_data,
                generated_sql=None,
                execution_time_ms=execution_time_ms,
                row_count=row_count,
            )

        except Exception as e:
            execution_time_ms = int((time.time() - start_time) * 1000)
            error_msg = str(e)

            # Log failure
            await self.service.log_query(
                tenant_id=tenant_id,
                user_id=None,
                source=WarehouseSource.SNOWFLAKE,
                query_type=QueryType.SQL,
                question=sql,
                execution_time_ms=execution_time_ms,
                success=False,
                error_message=error_msg,
            )

            return QueryResult(
                success=False,
                error_message=error_msg,
                data=None,
                row_count=0,
                execution_time_ms=execution_time_ms,
            )

    async def has_configuration(self, tenant_id: str) -> bool:
        """Check if Snowflake is configured with semantic models for this tenant."""
        try:
            async with tenant_db_manager.acquire_connection(tenant_id) as conn:
                result = await conn.fetch(
                    """
                    SELECT COUNT(*) as count
                    FROM snowflake_semantic_models
                    WHERE state = $1
                    """,
                    "enabled",
                )
                return result and result[0]["count"] > 0
        except Exception as e:
            # Table might not exist yet
            logger.warning(
                "Error checking Snowflake configuration",
                tenant_id=tenant_id,
                error=str(e),
                error_type=type(e).__name__,
            )
            return False

    async def get_semantic_models(self, tenant_id: str) -> list[SemanticModel]:
        """Get available Snowflake semantic models for the tenant."""
        try:
            models = await self.service.get_semantic_models(tenant_id)
            return [
                SemanticModel(
                    id=str(model["id"]),
                    name=model["name"],
                    description=model.get("description"),
                    source=WarehouseSource.SNOWFLAKE,
                )
                for model in models
            ]
        except Exception as e:
            logger.warning(
                "Error fetching Snowflake semantic models",
                tenant_id=tenant_id,
                error=str(e),
                error_type=type(e).__name__,
            )
            return []

    async def close(self) -> None:
        """Close HTTP client and clean up resources."""
        await self.service.close()
