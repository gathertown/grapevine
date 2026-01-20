"""
Linear authentication service for managing OAuth tokens.
"""

import os
from datetime import UTC, datetime, timedelta

import asyncpg
import httpx

from src.clients.ssm import SSMClient
from src.utils.logging import get_logger

logger = get_logger(__name__)

LINEAR_TOKEN_URL = "https://api.linear.app/oauth/token"
LINEAR_GRANT_TYPE_REFRESH = "refresh_token"
LINEAR_HTTP_TIMEOUT_SECONDS = 30.0

LINEAR_TOKEN_EXPIRES_AT_KEY = "LINEAR_TOKEN_EXPIRES_AT"
LINEAR_TOKEN_REFRESH_BUFFER_HOURS = 1  # Refresh token 1 hour before expiry

LINEAR_LOCK_KEY_SUFFIX = "linear:token_refresh"

ENV_LINEAR_CLIENT_ID = "LINEAR_CLIENT_ID"
ENV_LINEAR_CLIENT_SECRET = "LINEAR_CLIENT_SECRET"


class LinearAuthService:
    """Service for managing Linear OAuth authentication and token lifecycle."""

    def __init__(self, ssm_client: SSMClient, db_pool: asyncpg.Pool):
        self.ssm_client = ssm_client
        self.db_pool = db_pool

    async def get_valid_access_token(self, tenant_id: str) -> str:
        """Get a valid Linear access token, refreshing if necessary.

        Args:
            tenant_id: Tenant ID

        Returns:
            Valid access token
        """
        async with self.db_pool.acquire() as conn:
            expires_at = await self._fetch_token_expiry(conn)

        if not expires_at:
            logger.info(
                f"[tenant_id={tenant_id}] No LINEAR_TOKEN_EXPIRES_AT found - checking for OAuth token"
            )
            access_token = await self.ssm_client.get_linear_access_token(tenant_id)
            if access_token:
                logger.info(
                    f"[tenant_id={tenant_id}] Found OAuth token without expiry, refreshing to update metadata"
                )
                return await self.refresh_token(tenant_id)

            raise ValueError(f"No Linear OAuth configuration found for tenant {tenant_id}")

        if self._is_expiring_soon(expires_at):
            logger.info(
                f"[tenant_id={tenant_id}] Linear token expired or expiring soon; refreshing..."
            )
            return await self.refresh_token(tenant_id)

        logger.info(f"[tenant_id={tenant_id}] Using existing Linear access token")
        access_token = await self.ssm_client.get_linear_access_token(tenant_id)

        if access_token:
            return access_token

        logger.error(
            f"[tenant_id={tenant_id}] Token expiry exists but access token not found in SSM"
        )
        return await self.refresh_token(tenant_id)

    async def refresh_token(self, tenant_id: str) -> str:
        """Refresh the Linear OAuth access token using the refresh token.

        Coordinates refresh across workers using PostgreSQL advisory locks.

        Args:
            tenant_id: Tenant ID

        Returns:
            The new access token
        """
        async with self.db_pool.acquire() as conn, conn.transaction():
            await self._acquire_tenant_refresh_lock(conn, tenant_id)
            logger.info(f"[tenant_id={tenant_id}] Acquired Linear token refresh lock")

            current_expires_at = await self._fetch_token_expiry(conn)
            if current_expires_at and not self._is_expiring_soon(current_expires_at):
                logger.info(
                    f"[tenant_id={tenant_id}] Token already refreshed by another worker; "
                    f"expiry now {current_expires_at.isoformat()} — reusing existing access token"
                )
                existing_token = await self.ssm_client.get_linear_access_token(tenant_id)
                if existing_token:
                    return existing_token
                logger.warning(
                    f"[tenant_id={tenant_id}] Expiry present but access token missing in SSM; proceeding to refresh"
                )

            refresh_token = await self.ssm_client.get_linear_refresh_token(tenant_id)
            if not refresh_token:
                raise ValueError(f"No Linear refresh token found for tenant {tenant_id}")

            client_id, client_secret = self._get_client_credentials()

            logger.info(f"[tenant_id={tenant_id}] Refreshing Linear access token")
            access_token, new_refresh_token, expires_in = await self._perform_token_refresh(
                refresh_token=refresh_token,
                client_id=client_id,
                client_secret=client_secret,
            )

            expires_at = datetime.now(tz=UTC) + timedelta(seconds=expires_in)

            await self._persist_tokens_and_expiry(
                conn=conn,
                tenant_id=tenant_id,
                access_token=access_token,
                new_refresh_token=new_refresh_token,
                expires_at=expires_at,
            )

            logger.info(
                f"[tenant_id={tenant_id}] Successfully refreshed Linear token, expires at {expires_at.isoformat()}"
            )

            return access_token

    def _get_client_credentials(self) -> tuple[str, str]:
        """Fetch and validate Linear client credentials from environment."""
        client_id = os.environ.get(ENV_LINEAR_CLIENT_ID)
        client_secret = os.environ.get(ENV_LINEAR_CLIENT_SECRET)
        if not client_id or not client_secret:
            raise ValueError(
                "LINEAR_CLIENT_ID and LINEAR_CLIENT_SECRET environment variables are required"
            )
        return client_id, client_secret

    async def _perform_token_refresh(
        self, *, refresh_token: str, client_id: str, client_secret: str
    ) -> tuple[str, str, int]:
        """Perform the HTTP token refresh request.

        Args:
            refresh_token: The refresh token to exchange
            client_id: Linear OAuth client ID
            client_secret: Linear OAuth client secret

        Returns:
            Tuple of (access_token, refresh_token, expires_in)
        """
        async with httpx.AsyncClient(timeout=LINEAR_HTTP_TIMEOUT_SECONDS) as client:
            response = await client.post(
                LINEAR_TOKEN_URL,
                data={
                    "grant_type": LINEAR_GRANT_TYPE_REFRESH,
                    "refresh_token": refresh_token,
                    "client_id": client_id,
                    "client_secret": client_secret,
                },
            )

        if response.status_code != 200:
            error_data = response.json() if response.text else {}
            logger.error(f"Failed to refresh Linear token: {error_data}")
            raise RuntimeError(f"Failed to refresh Linear token: {response.status_code}")

        tokens = response.json()
        access_token = tokens["access_token"]
        new_refresh_token = tokens.get("refresh_token", refresh_token)
        expires_in = tokens["expires_in"]

        return access_token, new_refresh_token, expires_in

    async def _persist_tokens_and_expiry(
        self,
        *,
        conn: asyncpg.Connection,
        tenant_id: str,
        access_token: str,
        new_refresh_token: str,
        expires_at: datetime,
    ) -> None:
        """Store new tokens in SSM and upsert expiry in the control database."""
        await self.ssm_client.store_linear_access_token(tenant_id, access_token)
        await self.ssm_client.store_linear_refresh_token(tenant_id, new_refresh_token)

        await conn.execute(
            """
            INSERT INTO config (key, value)
            VALUES ($1, $2)
            ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
            """,
            LINEAR_TOKEN_EXPIRES_AT_KEY,
            expires_at.isoformat(),
        )

    async def _fetch_token_expiry(self, conn: asyncpg.Connection) -> datetime | None:
        """Read token expiry from config and parse as datetime, or None if missing/invalid."""
        row = await conn.fetchrow(
            "SELECT value FROM config WHERE key = $1", LINEAR_TOKEN_EXPIRES_AT_KEY
        )
        if not row or not row.get("value"):
            return None
        try:
            return datetime.fromisoformat(str(row["value"]).replace("Z", "+00:00")).astimezone(UTC)
        except ValueError:
            logger.warning(f"Invalid LINEAR_TOKEN_EXPIRES_AT format: {row['value']}")
            return None

    def _is_expiring_soon(self, expires_at: datetime) -> bool:
        """Return True if the token expires within the configured buffer time."""
        buffer_time_from_now = datetime.now(tz=UTC) + timedelta(
            hours=LINEAR_TOKEN_REFRESH_BUFFER_HOURS
        )
        return expires_at <= buffer_time_from_now

    async def _acquire_tenant_refresh_lock(self, conn: asyncpg.Connection, tenant_id: str) -> None:
        """Acquire a transaction-scoped advisory lock for this tenant's Linear token refresh."""
        lock_key = f"{tenant_id}:{LINEAR_LOCK_KEY_SUFFIX}"
        await conn.execute("SELECT pg_advisory_xact_lock(hashtext($1))", lock_key)
