"""
HubSpot authentication service for managing OAuth tokens.
"""

import asyncio
import json
from datetime import UTC, datetime, timedelta

import asyncpg
from hubspot import HubSpot
from hubspot.oauth import ApiException as OAuthApiException

from src.clients.ssm import SSMClient
from src.utils.config import get_config_value
from src.utils.logging import get_logger

logger = get_logger(__name__)


class HubspotAuthService:
    """Service for managing HubSpot OAuth authentication and token lifecycle."""

    def __init__(self, ssm_client: SSMClient, db_pool: asyncpg.Pool):
        self.ssm_client = ssm_client
        self.db_pool = db_pool

    async def get_valid_access_token(self, tenant_id: str) -> str:
        # Get token expiry from database using helper
        async with self.db_pool.acquire() as conn:
            expires_at = await self._fetch_token_expiry(conn)

        # No expiry found or invalid - unexpected state, need to refresh
        if not expires_at:
            logger.warning(
                f"[tenant_id={tenant_id}] No valid HUBSPOT_TOKEN_EXPIRES_AT found - unexpected state, will refresh token anyway"
            )
            return await self.refresh_token(tenant_id)

        # Token expired or expiring soon - need to refresh
        if self._is_expiring_soon(expires_at):
            logger.info(
                f"[tenant_id={tenant_id}] HubSpot token expired or expiring soon; refreshing..."
            )
            return await self.refresh_token(tenant_id)

        # Token is valid, try to use existing one
        logger.info(f"[tenant_id={tenant_id}] Using existing HubSpot access token")
        access_token = await self.ssm_client.get_hubspot_access_token(tenant_id)

        if access_token:
            return access_token

        # Token should exist but not found - refresh as fallback
        logger.error(
            f"[tenant_id={tenant_id}] Token expiry exists but access token not found in SSM"
        )
        return await self.refresh_token(tenant_id)

    async def refresh_token(self, tenant_id: str) -> str:
        # Coordinate refresh across workers using a per-tenant advisory lock
        async with self.db_pool.acquire() as conn, conn.transaction():
            await self._acquire_tenant_refresh_lock(conn, tenant_id)
            logger.info(f"[tenant_id={tenant_id}] Acquired HubSpot token refresh lock")

            # Double-check expiry under the lock to avoid redundant refresh
            current_expires_at = await self._fetch_token_expiry(conn)
            if current_expires_at and not self._is_expiring_soon(current_expires_at):
                logger.info(
                    f"[tenant_id={tenant_id}] Token already refreshed by another worker; "
                    f"expiry now {current_expires_at.isoformat()} — reusing existing access token"
                )
                existing_token = await self.ssm_client.get_hubspot_access_token(tenant_id)
                if existing_token:
                    return existing_token
                logger.warning(
                    f"[tenant_id={tenant_id}] Expiry present but access token missing in SSM; proceeding to refresh"
                )

            # Get refresh token from SSM
            refresh_token = await self.ssm_client.get_hubspot_refresh_token(tenant_id)
            if not refresh_token:
                raise ValueError(f"No HubSpot refresh token configured for tenant {tenant_id}")

            # Get client credentials
            client_id, client_secret = self._get_client_credentials()

            # Refresh via HubSpot SDK
            logger.info(
                f"[tenant_id={tenant_id}] Refreshing HubSpot token (expired or expiring soon)"
            )
            access_token, new_refresh_token, expires_in = await self._perform_hubspot_token_refresh(
                refresh_token=refresh_token,
                client_id=client_id,
                client_secret=client_secret,
                tenant_id=tenant_id,
            )

            expires_at = datetime.now(tz=UTC) + timedelta(seconds=expires_in)

            # Persist tokens and expiry
            await self._persist_tokens_and_expiry(
                conn=conn,
                tenant_id=tenant_id,
                access_token=access_token,
                new_refresh_token=new_refresh_token,
                expires_at=expires_at,
            )

            logger.info(
                f"[tenant_id={tenant_id}] Successfully refreshed HubSpot token, expires at {expires_at}"
            )

            return access_token

    def _get_client_credentials(self) -> tuple[str, str]:
        """Fetch and validate HubSpot client credentials from environment."""
        client_id = get_config_value("HUBSPOT_CLIENT_ID")
        client_secret = get_config_value("HUBSPOT_CLIENT_SECRET")
        if not client_id or not client_secret:
            raise ValueError(
                "HUBSPOT_CLIENT_ID and HUBSPOT_CLIENT_SECRET environment variables are required"
            )
        return client_id, client_secret

    async def _perform_hubspot_token_refresh(
        self, *, refresh_token: str, client_id: str, client_secret: str, tenant_id: str
    ) -> tuple[str, str, int]:
        """Perform the HubSpot refresh-token exchange and return (access, refresh, expires_in)."""
        try:
            # Run the synchronous SDK call in a thread pool
            token_response = await asyncio.to_thread(
                self._do_token_refresh_sync,
                refresh_token=refresh_token,
                client_id=client_id,
                client_secret=client_secret,
            )
            return (
                token_response.access_token,
                token_response.refresh_token,
                token_response.expires_in,
            )
        except Exception as e:
            logger.error(f"[tenant_id={tenant_id}] Failed to refresh HubSpot token: {e}")
            raise Exception(f"Failed to refresh HubSpot token: {e}")

    def _parse_oauth_error(self, api_exception: OAuthApiException) -> str:
        """Extract detailed error message from OAuth API exception."""
        error_details = f"{api_exception.reason}"
        if api_exception.body:
            try:
                body_dict = json.loads(api_exception.body)
                message = body_dict.get("message", "")
                status = body_dict.get("status", "")
                error_details = f"{message} (Status: {status})"
            except (json.JSONDecodeError, AttributeError):
                pass
        return error_details

    def _do_token_refresh_sync(self, *, refresh_token: str, client_id: str, client_secret: str):
        """Synchronous token refresh call."""
        try:
            temp_client = HubSpot()
            return temp_client.oauth.tokens_api.create(
                grant_type="refresh_token",
                client_id=client_id,
                client_secret=client_secret,
                refresh_token=refresh_token,
            )
        except OAuthApiException as e:
            error_details = self._parse_oauth_error(e)
            raise Exception(f"{e.status} {error_details}")

    async def _persist_tokens_and_expiry(
        self,
        *,
        conn,
        tenant_id: str,
        access_token: str,
        new_refresh_token: str,
        expires_at: datetime,
    ) -> None:
        """Store new tokens in SSM and upsert expiry in the database."""
        await self.ssm_client.store_api_key(tenant_id, "HUBSPOT_ACCESS_TOKEN", access_token)
        await self.ssm_client.store_api_key(tenant_id, "HUBSPOT_REFRESH_TOKEN", new_refresh_token)

        await conn.execute(
            """
            INSERT INTO config (key, value)
            VALUES ('HUBSPOT_TOKEN_EXPIRES_AT', $1)
            ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
            """,
            expires_at.isoformat(),
        )

    async def _fetch_token_expiry(self, conn) -> datetime | None:
        """Read token expiry from config and parse as datetime, or None if missing/invalid."""
        row = await conn.fetchrow("SELECT value FROM config WHERE key = 'HUBSPOT_TOKEN_EXPIRES_AT'")
        if not row or not row.get("value"):
            return None
        try:
            return datetime.fromisoformat(str(row["value"]).replace("Z", "+00:00"))
        except Exception:
            return None

    def _is_expiring_soon(self, expires_at: datetime) -> bool:
        """Return True if the token expires within 5 minutes from now."""
        now = datetime.now(tz=UTC)
        diff = expires_at - now
        # log time difference
        logger.info(
            f"Checking if token expires in less than 5 minutes: {diff.total_seconds()} seconds"
        )
        return diff <= timedelta(minutes=5)

    async def _acquire_tenant_refresh_lock(self, conn, tenant_id: str) -> None:
        """Acquire a transaction-scoped advisory lock for this tenant's HubSpot token refresh."""
        lock_key = f"{tenant_id}:hubspot:token_refresh"
        await conn.execute("SELECT pg_advisory_xact_lock(hashtext($1))", lock_key)
