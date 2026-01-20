"""
PostHog warehouse strategy implementation.

Handles HogQL query execution for PostHog analytics data.
"""

import time

from src.clients.ssm import SSMClient
from src.utils.logging import get_logger
from src.warehouses.models import (
    QueryResult,
    QueryType,
    SemanticModel,
    WarehouseSource,
)
from src.warehouses.posthog_service import PostHogService
from src.warehouses.strategy import WarehouseStrategy

logger = get_logger(__name__)


class PostHogStrategy(WarehouseStrategy):
    """PostHog warehouse implementation using HogQL queries."""

    def __init__(self):
        self.service = PostHogService()

    @property
    def supports_natural_language(self) -> bool:
        """PostHog does not support NL queries - use HogQL directly."""
        return False

    async def execute_natural_language_query(
        self,
        tenant_id: str,
        question: str,
        semantic_model_id: str | None = None,
        limit: int = 100,
    ) -> QueryResult:
        """
        PostHog does not support natural language to SQL translation.

        Users should use execute_data_warehouse_sql with HogQL queries directly.
        """
        start_time = time.time()

        # Log the attempt
        await self.service.log_query(
            tenant_id=tenant_id,
            user_id=None,
            source=WarehouseSource.POSTHOG,
            query_type=QueryType.NATURAL_LANGUAGE,
            question=question,
            execution_time_ms=int((time.time() - start_time) * 1000),
            success=False,
            error_message="PostHog does not support natural language queries. Use execute_data_warehouse_sql with HogQL instead.",
        )

        return QueryResult(
            success=False,
            error_message=(
                "PostHog does not support natural language to SQL translation. "
                "Please use the execute_data_warehouse_sql tool with HogQL queries instead.\n\n"
                "HogQL is PostHog's SQL-like query language. Example queries:\n"
                "- Count pageviews: SELECT count() FROM events WHERE event = '$pageview'\n"
                "- Daily users: SELECT toDate(timestamp) as day, count(DISTINCT distinct_id) FROM events GROUP BY day\n"
                "- Top events: SELECT event, count() FROM events GROUP BY event ORDER BY count() DESC LIMIT 10"
            ),
            data=None,
            row_count=0,
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
        """
        Execute a HogQL query against PostHog.

        Note: The 'warehouse', 'database', 'schema' parameters are mapped to project_id
        for PostHog. Pass the project ID as 'database' if you want to query a specific project.
        """
        start_time = time.time()

        try:
            # Parse project_id from database parameter if provided
            # PostHog uses projects instead of databases/schemas
            project_id: int | None = None
            if database and database.isdigit():
                project_id = int(database)

            # Execute HogQL query
            result = await self.service.execute_hogql(
                tenant_id=tenant_id,
                query=sql,
                project_id=project_id,
                limit=limit,
            )

            execution_time_ms = int((time.time() - start_time) * 1000)

            # Transform results to list of dicts
            columns = result.get("columns", [])
            rows = result.get("results", [])
            result_data = [dict(zip(columns, row, strict=False)) for row in rows]

            row_count = len(result_data)

            # Log success
            await self.service.log_query(
                tenant_id=tenant_id,
                user_id=None,
                source=WarehouseSource.POSTHOG,
                query_type=QueryType.SQL,
                question=sql,
                generated_sql=result.get("hogql"),  # The actual HogQL executed
                semantic_model_id=str(project_id) if project_id else None,
                execution_time_ms=execution_time_ms,
                row_count=row_count,
                success=True,
            )

            return QueryResult(
                success=True,
                data=result_data,
                generated_sql=result.get("hogql"),
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
                source=WarehouseSource.POSTHOG,
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
        """Check if PostHog is configured for this tenant (has API key in SSM)."""
        try:
            ssm_client = SSMClient()
            api_key = await ssm_client.get_api_key(tenant_id, "POSTHOG_PERSONAL_API_KEY")
            return api_key is not None and len(api_key) > 0
        except Exception as e:
            logger.warning(
                "Error checking PostHog configuration",
                tenant_id=tenant_id,
                error=str(e),
                error_type=type(e).__name__,
            )
            return False

    async def get_semantic_models(self, tenant_id: str) -> list[SemanticModel]:
        """
        Get available PostHog projects as "semantic models".

        In PostHog, each project is a logical grouping of analytics data,
        similar to how semantic models work in Snowflake.
        """
        try:
            projects = await self.service.get_projects(tenant_id)
            return [
                SemanticModel(
                    id=str(project["id"]),
                    name=project["name"],
                    description=project.get("description"),
                    source=WarehouseSource.POSTHOG,
                )
                for project in projects
            ]
        except Exception as e:
            logger.warning(
                "Error fetching PostHog projects",
                tenant_id=tenant_id,
                error=str(e),
                error_type=type(e).__name__,
            )
            return []

    async def close(self) -> None:
        """Close PostHog service and clean up resources."""
        await self.service.close()
