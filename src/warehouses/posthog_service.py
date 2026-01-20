"""
PostHog warehouse service for HogQL query execution.

This service handles:
- API key management from SSM
- HogQL query execution via PostHog Query API
- Query logging to warehouse_query_log table
"""

import uuid
from datetime import UTC, datetime
from typing import Any

from connectors.posthog.client import PostHogClient, get_posthog_client_for_tenant
from src.clients.tenant_db import tenant_db_manager
from src.utils.logging import get_logger
from src.warehouses.models import (
    QueryType,
    WarehouseQueryLog,
    WarehouseSource,
)

logger = get_logger(__name__)


class PostHogService:
    """Service for PostHog HogQL query execution."""

    def __init__(self):
        self._client: PostHogClient | None = None
        self._current_tenant_id: str | None = None

    async def _get_client(self, tenant_id: str) -> PostHogClient:
        """
        Get or create PostHog client for a tenant.

        The client is cached per tenant to reuse connections.
        """
        if self._client is None or self._current_tenant_id != tenant_id:
            # Close existing client if switching tenants
            if self._client is not None:
                await self._client.close()

            self._client = await get_posthog_client_for_tenant(tenant_id)
            self._current_tenant_id = tenant_id

        return self._client

    async def get_projects(self, tenant_id: str) -> list[dict[str, Any]]:
        """
        Get all accessible PostHog projects for a tenant.

        Projects serve as "semantic models" for PostHog - each project
        has its own analytics data that can be queried.

        Returns list of project records with id, name, etc.
        """
        client = await self._get_client(tenant_id)
        projects = await client.get_projects()

        return [
            {
                "id": project.id,
                "name": project.name,
                "uuid": project.uuid,
                "description": f"PostHog project: {project.name}",
            }
            for project in projects
        ]

    async def execute_hogql(
        self,
        tenant_id: str,
        query: str,
        project_id: int | None = None,
        limit: int = 100,
    ) -> dict[str, Any]:
        """
        Execute a HogQL query against PostHog.

        Args:
            tenant_id: Tenant identifier
            query: HogQL query to execute
            project_id: PostHog project ID (uses first available if not specified)
            limit: Maximum rows to return

        Returns:
            Query results with metadata

        Raises:
            ValueError: If query execution fails or no project available
        """
        client = await self._get_client(tenant_id)

        # Get project ID if not provided
        if project_id is None:
            projects = await client.get_projects()
            if not projects:
                raise ValueError("No PostHog projects found for this tenant")
            project_id = projects[0].id

        # Execute HogQL query
        result = await client.execute_hogql_query(
            project_id=project_id,
            query=query,
            limit=limit,
        )

        if result.get("error"):
            raise ValueError(f"HogQL query error: {result['error']}")

        return result

    async def log_query(
        self,
        tenant_id: str,
        user_id: str | None,
        source: WarehouseSource,
        query_type: QueryType,
        question: str,
        generated_sql: str | None = None,
        semantic_model_id: str | None = None,
        execution_time_ms: int | None = None,
        row_count: int | None = None,
        success: bool = True,
        error_message: str | None = None,
    ) -> None:
        """
        Log query execution to warehouse_query_log table in tenant database.

        Args:
            tenant_id: Tenant identifier
            user_id: User who executed the query (None for system queries)
            source: Data warehouse source (posthog)
            query_type: Type of query (natural_language or sql)
            question: Original question or HogQL statement
            generated_sql: SQL generated from NL (None for direct queries)
            semantic_model_id: Reference to project used
            execution_time_ms: Query execution time in milliseconds
            row_count: Number of rows returned
            success: Whether query succeeded
            error_message: Error details if query failed
        """
        query_log = WarehouseQueryLog(
            id=str(uuid.uuid4()),
            user_id=user_id,
            source=source,
            query_type=query_type,
            question=question,
            generated_sql=generated_sql,
            semantic_model_id=semantic_model_id,
            execution_time_ms=execution_time_ms,
            row_count=row_count,
            success=success,
            error_message=error_message,
            created_at=datetime.now(UTC),
        )

        async with tenant_db_manager.acquire_connection(tenant_id) as conn:
            insert_query = """
                INSERT INTO warehouse_query_log (
                    id, user_id, source, query_type, question, generated_sql,
                    semantic_model_id, execution_time_ms, row_count, success,
                    error_message, created_at
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
            """
            await conn.execute(
                insert_query,
                query_log.id,
                query_log.user_id,
                query_log.source.value,
                query_log.query_type.value,
                query_log.question,
                query_log.generated_sql,
                query_log.semantic_model_id,
                query_log.execution_time_ms,
                query_log.row_count,
                query_log.success,
                query_log.error_message,
                query_log.created_at,
            )

        logger.info(
            "Query logged to warehouse_query_log",
            extra={
                "tenant_id": tenant_id,
                "user_id": user_id or "system",
                "source": source.value,
                "query_type": query_type.value,
                "success": success,
                "execution_time_ms": execution_time_ms,
            },
        )

    async def close(self) -> None:
        """Close PostHog client."""
        if self._client is not None:
            await self._client.close()
            self._client = None
            self._current_tenant_id = None
