"""Factory helpers for constructing Gong API clients."""

from __future__ import annotations

from src.clients.gong import GongClient
from src.clients.ssm import SSMClient
from src.ingest.services.gong_auth import GongAuthService
from src.utils.logging import get_logger
from src.utils.tenant_config import get_tenant_config_value

logger = get_logger(__name__)


async def get_gong_client_for_tenant(
    tenant_id: str,
    ssm_client: SSMClient,
    gong_auth_service: GongAuthService | None = None,
) -> GongClient:
    """Return a GongClient configured with the tenant's credentials.

    Requires tenant-specific configuration in the database.
    No fallbacks to environment variables to ensure proper per-tenant configuration.
    """

    # GONG_API_BASE_URL is stored in the database (non-sensitive), not SSM
    base_url = await get_tenant_config_value("GONG_API_BASE_URL", tenant_id)

    # Always create the auth service if not provided (enables refresh token support)
    if gong_auth_service is None:
        gong_auth_service = GongAuthService(ssm_client)

    logger.info(
        "🔐 BACKFILL AUTH: Authenticating Gong backfill job using GongAuthService (with refresh token support)",
        tenant_id=tenant_id,
    )
    access_token = await gong_auth_service.get_valid_access_token(tenant_id)
    token_source = "GongAuthService (refresh token enabled)"

    if not access_token:
        raise ValueError(f"Missing Gong access token for tenant {tenant_id}")
    if not base_url:
        raise ValueError(
            f"Missing Gong API base URL for tenant {tenant_id}. "
            f"Tenant needs to reconnect Gong through admin UI."
        )

    # Log credential source and values (with token redaction)
    redacted_token = (
        f"{access_token[:8]}...{access_token[-4:]}" if len(access_token) > 12 else "***"
    )

    logger.info(
        "Gong client credentials loaded",
        tenant_id=tenant_id,
        token_source=token_source,
        base_url_source="database",
        base_url=base_url,
        token_preview=redacted_token,
    )

    return GongClient(access_token=access_token, api_base_url=base_url)
