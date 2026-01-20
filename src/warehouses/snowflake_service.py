"""
Snowflake service for Cortex Analyst integration and SQL execution.

This service handles:
- OAuth token management (get, refresh, validate)
- Semantic model retrieval from tenant DB
- Cortex Analyst API calls for natural language to SQL translation
- Direct SQL execution with user OAuth tokens
- Query logging to warehouse_query_log table
"""

import json
import uuid
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from src.clients.ssm import SSMClient
from src.clients.tenant_db import tenant_db_manager
from src.utils.logging import get_logger
from src.warehouses.models import (
    CortexAnalystRequest,
    QueryType,
    WarehouseQueryLog,
    WarehouseSource,
)

logger = get_logger(__name__)

# Constants for token validity calculations
SECONDS_PER_DAY = 86400
SNOWFLAKE_REFRESH_TOKEN_VALIDITY_DAYS = 90  # Default refresh token validity
SNOWFLAKE_REFRESH_TOKEN_VALIDITY_SECONDS = (
    SNOWFLAKE_REFRESH_TOKEN_VALIDITY_DAYS * SECONDS_PER_DAY
)  # 7776000
PROACTIVE_REFRESH_THRESHOLD_DAYS = 7  # Refresh tokens within 7 days of expiry


class SnowflakeOAuthToken:
    """Snowflake OAuth token with expiry information."""

    def __init__(
        self,
        access_token: str,
        refresh_token: str,
        access_token_expires_at: str,
        refresh_token_expires_at: str | None = None,
        refresh_token_validity_seconds: int | None = None,
        username: str | None = None,
    ):
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.access_token_expires_at = access_token_expires_at
        self.refresh_token_expires_at = refresh_token_expires_at
        self.refresh_token_validity_seconds = refresh_token_validity_seconds
        self.username = username

    def is_access_token_expired(self) -> bool:
        """Check if access token is expired."""
        expires_at = datetime.fromisoformat(self.access_token_expires_at.replace("Z", "+00:00"))
        return datetime.now(UTC) >= expires_at

    def is_expired(self) -> bool:
        """Check if access token is expired (for backward compatibility)."""
        return self.is_access_token_expired()

    def is_refresh_token_expiring_soon(
        self, days_threshold: int = PROACTIVE_REFRESH_THRESHOLD_DAYS
    ) -> bool:
        """Check if refresh token will expire within the specified number of days."""
        if not self.refresh_token_expires_at:
            return False
        expires_at = datetime.fromisoformat(self.refresh_token_expires_at.replace("Z", "+00:00"))
        threshold_date = datetime.now(UTC) + timedelta(days=days_threshold)
        return expires_at <= threshold_date

    def is_refresh_token_expired(self) -> bool:
        """Check if refresh token is expired."""
        if not self.refresh_token_expires_at:
            return False
        expires_at = datetime.fromisoformat(self.refresh_token_expires_at.replace("Z", "+00:00"))
        return datetime.now(UTC) >= expires_at

    def to_dict(self) -> dict[str, str | int | None]:
        """Convert to dictionary for SSM storage."""
        result: dict[str, str | int | None] = {
            "access_token": self.access_token,
            "refresh_token": self.refresh_token,
            "access_token_expires_at": self.access_token_expires_at,
        }
        if self.refresh_token_expires_at:
            result["refresh_token_expires_at"] = self.refresh_token_expires_at
        if self.refresh_token_validity_seconds is not None:
            result["refresh_token_validity_seconds"] = self.refresh_token_validity_seconds
        if self.username:
            result["username"] = self.username
        return result

    @classmethod
    def from_dict(cls, data: Mapping[str, str | int]) -> "SnowflakeOAuthToken":
        """Create from dictionary loaded from SSM."""
        validity_seconds_raw = data.get("refresh_token_validity_seconds")
        validity_seconds: int | None = None
        if validity_seconds_raw is not None:
            try:
                if isinstance(validity_seconds_raw, str):
                    validity_seconds = int(validity_seconds_raw)
                elif isinstance(validity_seconds_raw, int):
                    validity_seconds = validity_seconds_raw
            except ValueError:
                pass

        refresh_token_expires_at_raw = data.get("refresh_token_expires_at")
        refresh_token_expires_at: str | None = None
        if refresh_token_expires_at_raw is not None and isinstance(
            refresh_token_expires_at_raw, str
        ):
            try:
                datetime.fromisoformat(refresh_token_expires_at_raw.replace("Z", "+00:00"))
                refresh_token_expires_at = refresh_token_expires_at_raw
            except ValueError:
                pass

        username_raw = data.get("username")
        username: str | None = str(username_raw) if username_raw is not None else None

        return cls(
            access_token=str(data["access_token"]),
            refresh_token=str(data["refresh_token"]),
            access_token_expires_at=str(data["access_token_expires_at"]),
            refresh_token_expires_at=refresh_token_expires_at,
            refresh_token_validity_seconds=validity_seconds,
            username=username,
        )


class SnowflakeService:
    """Service for Snowflake Cortex Analyst and SQL execution."""

    def __init__(self):
        self.ssm_client = SSMClient()
        self.http_client = httpx.AsyncClient(timeout=120.0)

    async def _get_oauth_token_from_ssm(self, tenant_id: str) -> SnowflakeOAuthToken | None:
        """
        Get OAuth token from SSM.

        Token is stored at: /{tenant_id}/api-key/SNOWFLAKE_OAUTH_TOKEN_PAYLOAD
        This is a tenant-wide token shared by all users.
        """
        ssm_key = f"/{tenant_id}/api-key/SNOWFLAKE_OAUTH_TOKEN_PAYLOAD"
        token_json = await self.ssm_client.get_parameter(ssm_key)

        if not token_json:
            return None

        token_data = json.loads(token_json)
        return SnowflakeOAuthToken.from_dict(token_data)

    async def _save_oauth_token_to_ssm(self, tenant_id: str, token: SnowflakeOAuthToken) -> None:
        """Save OAuth token to SSM."""
        ssm_key = f"/{tenant_id}/api-key/SNOWFLAKE_OAUTH_TOKEN_PAYLOAD"
        token_json = json.dumps(token.to_dict())
        await self.ssm_client.put_parameter(ssm_key, token_json)

    async def _get_snowflake_config(self, tenant_id: str) -> dict[str, str | None]:
        """
        Get Snowflake configuration from tenant database and SSM.

        Returns account_identifier, client_id, client_secret, token_endpoint.
        Note: client_secret is fetched from SSM for security.
        """
        async with tenant_db_manager.acquire_connection(tenant_id) as conn:
            # Get non-sensitive config from tenant's config table
            config_query = """
                SELECT key, value
                FROM config
                WHERE key IN (
                    'SNOWFLAKE_ACCOUNT_IDENTIFIER',
                    'SNOWFLAKE_CLIENT_ID',
                    'SNOWFLAKE_OAUTH_TOKEN_ENDPOINT'
                )
            """
            rows = await conn.fetch(config_query)

            config = {}
            for row in rows:
                config[row["key"]] = row["value"]

            # Get client_secret from SSM (more secure)
            ssm_key = f"/{tenant_id}/api-key/SNOWFLAKE_CLIENT_SECRET"
            client_secret = await self.ssm_client.get_parameter(ssm_key)

            return {
                "account_identifier": config.get("SNOWFLAKE_ACCOUNT_IDENTIFIER"),
                "client_id": config.get("SNOWFLAKE_CLIENT_ID"),
                "client_secret": client_secret,
                "token_endpoint": config.get("SNOWFLAKE_OAUTH_TOKEN_ENDPOINT"),
            }

    async def _refresh_access_token(
        self,
        refresh_token: str,
        account_identifier: str,
        client_id: str,
        client_secret: str,
        token_endpoint: str | None = None,
    ) -> dict[str, Any]:
        """
        Refresh an expired access token using the refresh token.

        Returns new token response from Snowflake OAuth server.
        """
        # Build token URL
        if token_endpoint:
            token_url = token_endpoint
        else:
            token_url = f"https://{account_identifier}.snowflakecomputing.com/oauth/token-request"

        # Prepare credentials for Basic Auth
        credentials = f"{client_id}:{client_secret}"
        import base64

        credentials_b64 = base64.b64encode(credentials.encode()).decode()

        # Prepare request
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Authorization": f"Basic {credentials_b64}",
            "Accept": "application/json",
        }

        data = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        }

        response = await self.http_client.post(token_url, headers=headers, data=data)

        if not response.is_success:
            error_text = response.text
            try:
                error_json = response.json()
                if error_json.get("error") == "invalid_grant":
                    raise ValueError(
                        "Snowflake refresh token is invalid or expired. "
                        "Please disconnect and reconnect your Snowflake account."
                    )
            except json.JSONDecodeError:
                pass

            raise ValueError(f"Snowflake token refresh failed: {response.status_code} {error_text}")

        return response.json()

    async def get_valid_oauth_token(self, tenant_id: str) -> tuple[SnowflakeOAuthToken, str]:
        """
        Get a valid OAuth token for the tenant, refreshing if necessary.

        Returns tuple of (token, account_identifier).

        Raises:
            ValueError: If token not found or refresh fails
        """
        # Get token from SSM
        token = await self._get_oauth_token_from_ssm(tenant_id)
        if not token:
            raise ValueError(
                "No Snowflake OAuth token found. Please connect your Snowflake account first."
            )

        # Get config
        config = await self._get_snowflake_config(tenant_id)
        account_identifier = config["account_identifier"]
        if not account_identifier:
            raise ValueError("No Snowflake account identifier found in configuration.")

        # Check if token is expired
        if token.is_expired():
            logger.info(
                "Access token expired, refreshing...",
                tenant_id=tenant_id,
                expired_at=token.access_token_expires_at,
            )

            client_id = config["client_id"]
            client_secret = config["client_secret"]
            token_endpoint = config["token_endpoint"]

            if not client_id or not client_secret:
                raise ValueError("Missing OAuth credentials for token refresh")

            # Refresh token
            token_response = await self._refresh_access_token(
                token.refresh_token,
                account_identifier,
                client_id,
                client_secret,
                token_endpoint,
            )

            # Calculate new expiry
            expires_in_seconds = token_response["expires_in"]
            new_access_token_expires_at = datetime.now(UTC) + timedelta(seconds=expires_in_seconds)

            # Calculate refresh token expiry
            # Use the stored validity seconds if available, otherwise default to 90 days
            # This handles both new tokens and legacy tokens without the validity field
            if (
                token.refresh_token_validity_seconds is not None
                and token.refresh_token_validity_seconds > 0
            ):
                validity_seconds = token.refresh_token_validity_seconds
            else:
                # Fallback to default validity
                validity_seconds = SNOWFLAKE_REFRESH_TOKEN_VALIDITY_SECONDS
                logger.info(
                    "No refresh_token_validity_seconds found, using default",
                    tenant_id=tenant_id,
                    validity_days=SNOWFLAKE_REFRESH_TOKEN_VALIDITY_DAYS,
                )

            # If Snowflake returned a new refresh token, it has a fresh expiry
            # If no new refresh token, keep the old expiry
            new_refresh_token = token_response.get("refresh_token")
            refresh_token_expires_at_str: str | None
            if new_refresh_token:
                # New refresh token received - calculate fresh expiry using stored validity
                new_refresh_token_expires_at = datetime.now(UTC) + timedelta(
                    seconds=validity_seconds
                )
                refresh_token_expires_at_str = new_refresh_token_expires_at.isoformat()
            else:
                # No new refresh token - keep existing expiry
                new_refresh_token = token.refresh_token
                refresh_token_expires_at_str = token.refresh_token_expires_at

            # Create new token object, preserving the validity seconds
            token = SnowflakeOAuthToken(
                access_token=token_response["access_token"],
                refresh_token=new_refresh_token,
                access_token_expires_at=new_access_token_expires_at.isoformat(),
                refresh_token_expires_at=refresh_token_expires_at_str,
                refresh_token_validity_seconds=token.refresh_token_validity_seconds,
                username=token_response.get("username"),
            )

            # Save refreshed token
            await self._save_oauth_token_to_ssm(tenant_id, token)

            logger.info(
                "Access token refreshed successfully",
                extra={
                    "tenant_id": tenant_id,
                    "new_expiry": token.access_token_expires_at,
                    "username": token.username,
                },
            )

        return token, account_identifier

    async def force_refresh_oauth_token(self, tenant_id: str) -> SnowflakeOAuthToken:
        """
        Force refresh the OAuth token regardless of access token expiry.

        This is used by the proactive token refresh job to get a new refresh token
        with a fresh expiry, even when the access token is still valid.

        Returns the refreshed token.

        Raises:
            ValueError: If token not found or refresh fails
        """
        # Get current token from SSM
        token = await self._get_oauth_token_from_ssm(tenant_id)
        if not token:
            raise ValueError(
                "No Snowflake OAuth token found. Please connect your Snowflake account first."
            )

        # Get config
        config = await self._get_snowflake_config(tenant_id)
        account_identifier = config["account_identifier"]
        if not account_identifier:
            raise ValueError("No Snowflake account identifier found in configuration.")

        client_id = config["client_id"]
        client_secret = config["client_secret"]
        token_endpoint = config["token_endpoint"]

        if not client_id or not client_secret:
            raise ValueError("Missing OAuth credentials for token refresh")

        logger.info(
            "Force refreshing token to extend refresh token validity",
            tenant_id=tenant_id,
        )

        # Refresh token
        token_response = await self._refresh_access_token(
            token.refresh_token,
            account_identifier,
            client_id,
            client_secret,
            token_endpoint,
        )

        # Calculate new expiry
        expires_in_seconds = token_response["expires_in"]
        new_access_token_expires_at = datetime.now(UTC) + timedelta(seconds=expires_in_seconds)

        # Calculate refresh token expiry
        if (
            token.refresh_token_validity_seconds is not None
            and token.refresh_token_validity_seconds > 0
        ):
            validity_seconds = token.refresh_token_validity_seconds
        else:
            validity_seconds = SNOWFLAKE_REFRESH_TOKEN_VALIDITY_SECONDS
            logger.info(
                "No refresh_token_validity_seconds found, using default",
                tenant_id=tenant_id,
                validity_days=SNOWFLAKE_REFRESH_TOKEN_VALIDITY_DAYS,
            )

        # If Snowflake returned a new refresh token, it has a fresh expiry
        new_refresh_token = token_response.get("refresh_token")
        refresh_token_expires_at_str: str | None
        if new_refresh_token:
            new_refresh_token_expires_at = datetime.now(UTC) + timedelta(seconds=validity_seconds)
            refresh_token_expires_at_str = new_refresh_token_expires_at.isoformat()
        else:
            # No new refresh token - keep existing
            new_refresh_token = token.refresh_token
            refresh_token_expires_at_str = token.refresh_token_expires_at

        # Create new token object
        new_token = SnowflakeOAuthToken(
            access_token=token_response["access_token"],
            refresh_token=new_refresh_token,
            access_token_expires_at=new_access_token_expires_at.isoformat(),
            refresh_token_expires_at=refresh_token_expires_at_str,
            refresh_token_validity_seconds=token.refresh_token_validity_seconds,
            username=token_response.get("username"),
        )

        # Save refreshed token
        await self._save_oauth_token_to_ssm(tenant_id, new_token)

        logger.info(
            "Token force refreshed successfully",
            extra={
                "tenant_id": tenant_id,
                "new_access_token_expiry": new_token.access_token_expires_at,
                "new_refresh_token_expiry": new_token.refresh_token_expires_at,
                "username": new_token.username,
            },
        )

        return new_token

    async def get_semantic_models(self, tenant_id: str) -> list[dict[str, Any]]:
        """
        Get all enabled semantic models for a tenant from tenant DB.

        Returns list of semantic model records with id, name, stage_path, etc.
        """
        async with tenant_db_manager.acquire_connection(tenant_id) as conn:
            query = """
                SELECT id, name, type, stage_path, database_name, schema_name,
                       description, warehouse, state, created_at, updated_at
                FROM snowflake_semantic_models
                WHERE state = $1
                ORDER BY created_at DESC
            """
            rows = await conn.fetch(query, "enabled")

            models = []
            for row in rows:
                models.append(
                    {
                        "id": row["id"],
                        "name": row["name"],
                        "type": row["type"],
                        "stage_path": row.get("stage_path"),
                        "database_name": row.get("database_name"),
                        "schema_name": row.get("schema_name"),
                        "description": row.get("description"),
                        "warehouse": row.get("warehouse"),
                        "state": row["state"],
                        "created_at": row["created_at"],
                        "updated_at": row["updated_at"],
                    }
                )

            return models

    async def call_cortex_analyst(
        self,
        tenant_id: str,
        question: str,
        semantic_model_file: str | None = None,
        semantic_view: str | None = None,
        warehouse: str | None = None,
    ) -> dict[str, Any]:
        """
        Call Snowflake Cortex Analyst API to translate natural language to SQL.

        Args:
            tenant_id: Tenant identifier
            question: Natural language question
            semantic_model_file: Path to semantic model file in stage (e.g., @stage/model.yaml)
            semantic_view: Path to semantic view object (e.g., DB.SCHEMA.VIEW_NAME)
            warehouse: Optional warehouse to use. If not provided, uses user's default warehouse.

        Returns:
            Cortex Analyst response with generated SQL and results

        Raises:
            ValueError: If API call fails or both/neither parameters provided
        """
        if not semantic_model_file and not semantic_view:
            raise ValueError("Either semantic_model_file or semantic_view must be provided")
        if semantic_model_file and semantic_view:
            raise ValueError("Only one of semantic_model_file or semantic_view should be provided")

        # Get valid token
        token, account_identifier = await self.get_valid_oauth_token(tenant_id)

        # Build Cortex Analyst API URL
        # Format: https://{account}.snowflakecomputing.com/api/v2/cortex/analyst/message
        api_url = (
            f"https://{account_identifier}.snowflakecomputing.com/api/v2/cortex/analyst/message"
        )

        # Build request with proper message format
        # Official API expects content as array of objects with type and text
        request = CortexAnalystRequest(
            messages=[
                {
                    "role": "user",
                    "content": [{"type": "text", "text": question}],
                }
            ],
            semantic_model_file=semantic_model_file,
            semantic_view=semantic_view,
            warehouse=warehouse,
        )

        headers = {
            "Authorization": f"Bearer {token.access_token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "X-Snowflake-Authorization-Token-Type": "OAUTH",
        }

        response = await self.http_client.post(
            api_url, headers=headers, json=request.model_dump(exclude_none=True)
        )

        if not response.is_success:
            error_text = response.text
            raise ValueError(f"Cortex Analyst API error: {response.status_code} {error_text}")

        return response.json()

    async def execute_sql(
        self,
        tenant_id: str,
        sql: str,
        warehouse: str | None = None,
        database: str | None = None,
        schema: str | None = None,
        timeout: int = 60,
    ) -> dict[str, Any]:
        """
        Execute a SQL query directly on Snowflake.

        Args:
            tenant_id: Tenant identifier
            sql: SQL query to execute
            warehouse: Optional warehouse to use. If not provided, uses user's default warehouse.
            database: Optional database to use
            schema: Optional schema to use
            timeout: Query timeout in seconds

        Returns:
            Query results with metadata

        Raises:
            ValueError: If query execution fails
        """
        # Get valid token
        token, account_identifier = await self.get_valid_oauth_token(tenant_id)

        # Build SQL API URL
        api_url = f"https://{account_identifier}.snowflakecomputing.com/api/v2/statements"

        # Build request body
        request_body: dict[str, Any] = {
            "statement": sql,
            "timeout": timeout,
        }

        if warehouse:
            request_body["warehouse"] = warehouse
        if database:
            request_body["database"] = database
        if schema:
            request_body["schema"] = schema

        headers = {
            "Authorization": f"Bearer {token.access_token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "Grapevine/1.0",
            "X-Snowflake-Authorization-Token-Type": "OAUTH",
        }

        response = await self.http_client.post(api_url, headers=headers, json=request_body)

        if not response.is_success:
            error_text = response.text
            raise ValueError(f"Snowflake SQL API error: {response.status_code} {error_text}")

        return response.json()

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
            user_id: User who executed the query (None for system/tenant-wide queries)
            source: Data warehouse source (snowflake, bigquery, etc.)
            query_type: Type of query (natural_language or sql)
            question: Original question or SQL statement
            generated_sql: SQL generated from NL (None for direct SQL queries)
            semantic_model_id: Reference to semantic model used
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
        """Close HTTP client."""
        await self.http_client.aclose()
