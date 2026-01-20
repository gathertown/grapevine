"""Gong authentication service for managing tenant tokens."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from src.clients.ssm import SSMClient
from src.utils.config import require_config_value
from src.utils.logging import get_logger
from src.utils.tenant_config import get_tenant_config_value, set_tenant_config_value

logger = get_logger(__name__)


GONG_TOKEN_EXPIRES_AT_KEY = "GONG_TOKEN_EXPIRES_AT"
TOKEN_EXPIRY_REFRESH_THRESHOLD = timedelta(minutes=5)


class GongAuthService:
    """Service for managing Gong OAuth token lifecycle."""

    def __init__(self, ssm_client: SSMClient) -> None:
        self._ssm_client = ssm_client

    async def get_valid_access_token(self, tenant_id: str) -> str:
        """Return an access token, refreshing with the tenant refresh token when needed."""

        expires_at = await self._get_token_expires_at(tenant_id)

        if expires_at is None:
            logger.warning(
                "No Gong token expiry found; refreshing via refresh token",
                tenant_id=tenant_id,
            )
            return await self.refresh_token(tenant_id)

        # Calculate time until expiry for logging
        now = datetime.now(tz=UTC)
        time_until_expiry = expires_at - now

        if self._is_expiring_soon(expires_at):
            logger.info(
                "🔄 PREEMPTIVE REFRESH: Gong access token expiring soon - refreshing with refresh token",
                tenant_id=tenant_id,
                expires_at=expires_at.isoformat(),
                time_until_expiry_seconds=int(time_until_expiry.total_seconds()),
                threshold_seconds=int(TOKEN_EXPIRY_REFRESH_THRESHOLD.total_seconds()),
                is_preemptive=True,
            )
            return await self.refresh_token(tenant_id)

        access_token = await self._ssm_client.get_gong_access_token(tenant_id)
        if access_token:
            logger.debug(
                "✅ Using cached Gong access token (not expiring soon)",
                tenant_id=tenant_id,
                expires_at=expires_at.isoformat(),
                time_until_expiry_seconds=int(time_until_expiry.total_seconds()),
            )
            return access_token

        logger.warning(
            "Gong access token missing despite valid expiry; refreshing",
            tenant_id=tenant_id,
        )
        return await self.refresh_token(tenant_id)

    async def refresh_token(self, tenant_id: str) -> str:
        """Refresh the Gong access token using the stored refresh token."""

        refresh_token = await self._ssm_client.get_gong_refresh_token(tenant_id)
        if not refresh_token:
            raise ValueError(f"No Gong refresh token configured for tenant {tenant_id}")

        # OAuth endpoints are always on app.gong.io, not tenant-specific API URLs
        token_endpoint = "https://app.gong.io/oauth2/generate-customer-token"
        client_id = require_config_value("GONG_CLIENT_ID")
        client_secret = require_config_value("GONG_CLIENT_SECRET")

        # Mask the refresh token for logging (show first 8 chars only)
        refresh_token_masked = f"{refresh_token[:8]}..." if len(refresh_token) > 8 else "***"

        # Prepare the Basic auth header
        auth_header = _basic_auth_header(client_id, client_secret)

        payload = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        }
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Authorization": auth_header,
        }

        logger.info(
            "🔑 USING REFRESH TOKEN: Calling Gong token endpoint with refresh token",
            tenant_id=tenant_id,
            token_endpoint=token_endpoint,
            refresh_token_prefix=refresh_token_masked,
            grant_type="refresh_token",
            has_auth_header=bool(auth_header),
            auth_header_prefix=auth_header[:15] + "..." if len(auth_header) > 15 else auth_header,
            client_id_prefix=client_id[:8] + "..." if len(client_id) > 8 else client_id,
        )

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(token_endpoint, data=payload, headers=headers)

        if response.status_code != 200:
            logger.error(
                "❌ REFRESH TOKEN FAILED: Failed to refresh Gong token",
                tenant_id=tenant_id,
                status_code=response.status_code,
                body=response.text,
                request_headers_sent={
                    k: v[:20] + "..." if len(v) > 20 else v for k, v in headers.items()
                },
                request_url=token_endpoint,
                request_method="POST",
            )
            response.raise_for_status()

        data = response.json()
        access_token = data.get("access_token")
        new_refresh_token = data.get("refresh_token", refresh_token)
        expires_in = _parse_expires_in(data.get("expires_in"))

        if not access_token:
            raise ValueError("Gong token refresh response missing access_token")

        # Log successful refresh with details
        refresh_token_rotated = new_refresh_token != refresh_token
        logger.info(
            "✅ REFRESH TOKEN SUCCESS: Successfully refreshed Gong access token",
            tenant_id=tenant_id,
            new_access_token_prefix=f"{access_token[:8]}..." if len(access_token) > 8 else "***",
            expires_in_seconds=int(expires_in.total_seconds()),
            refresh_token_rotated=refresh_token_rotated,
        )

        await self._persist_tokens(
            tenant_id=tenant_id,
            access_token=access_token,
            refresh_token=new_refresh_token,
            expires_in=expires_in,
        )

        return access_token

    async def _persist_tokens(
        self,
        *,
        tenant_id: str,
        access_token: str,
        refresh_token: str,
        expires_in: timedelta,
    ) -> None:
        await self._ssm_client.store_api_key(tenant_id, "GONG_ACCESS_TOKEN", access_token)
        await self._ssm_client.store_api_key(tenant_id, "GONG_REFRESH_TOKEN", refresh_token)

        expires_at = datetime.now(tz=UTC) + expires_in
        await set_tenant_config_value(GONG_TOKEN_EXPIRES_AT_KEY, expires_at.isoformat(), tenant_id)

        logger.info(
            "💾 TOKENS STORED: Persisted refreshed Gong access and refresh tokens to SSM",
            tenant_id=tenant_id,
            expires_at=expires_at.isoformat(),
            expires_in_seconds=int(expires_in.total_seconds()),
            access_token_length=len(access_token),
            refresh_token_length=len(refresh_token),
        )

    async def _get_token_expires_at(self, tenant_id: str) -> datetime | None:
        stored_value = await get_tenant_config_value(GONG_TOKEN_EXPIRES_AT_KEY, tenant_id)
        if not stored_value:
            return None
        try:
            return datetime.fromisoformat(stored_value.replace("Z", "+00:00")).astimezone(UTC)
        except ValueError:
            logger.warning(
                "Unable to parse Gong token expiry; treating as missing",
                tenant_id=tenant_id,
                stored_value=stored_value,
            )
            return None

    def _is_expiring_soon(self, expires_at: datetime) -> bool:
        return expires_at <= datetime.now(tz=UTC) + TOKEN_EXPIRY_REFRESH_THRESHOLD


def _basic_auth_header(client_id: str, client_secret: str) -> str:
    import base64

    credential_bytes = f"{client_id}:{client_secret}".encode()
    encoded = base64.b64encode(credential_bytes).decode("utf-8")
    return f"Basic {encoded}"


def _parse_expires_in(expires_in: Any) -> timedelta:
    if isinstance(expires_in, (int, float)):
        seconds = int(expires_in)
    else:
        try:
            seconds = int(str(expires_in))
        except (TypeError, ValueError):
            logger.debug(
                "Gong expires_in missing or invalid; defaulting to 3600 seconds", value=expires_in
            )
            seconds = 3600
    return timedelta(seconds=max(60, seconds))
