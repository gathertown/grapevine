"""Factory helpers for constructing Zendesk API clients."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from connectors.zendesk.client.zendesk_client import (
    ZendeskClient,
    ZendeskOauthClient,
)
from connectors.zendesk.client.zendesk_models import ZendeskTokenPayload
from src.clients.ssm import SSMClient
from src.utils.logging import get_logger
from src.utils.tenant_config import get_tenant_config_value

logger = get_logger(__name__)


async def get_zendesk_client_for_tenant(
    tenant_id: str,
    ssm_client: SSMClient,
) -> ZendeskClient:
    """Return a ZendeskClient configured with the tenant's credentials.

    Requires tenant-specific configuration in the database.
    No fallbacks to environment variables to ensure proper per-tenant configuration.
    """

    subdomain = await get_tenant_config_value("ZENDESK_SUBDOMAIN", tenant_id)
    token_payload_json = await ssm_client.get_zendesk_token_payload(tenant_id)

    if not token_payload_json:
        raise ValueError(f"Missing Zendesk token for tenant {tenant_id}")
    if not subdomain:
        raise ValueError(
            f"Missing Zendesk subdomain for tenant {tenant_id}. "
            f"Tenant needs to reconnect Zendesk through admin UI."
        )

    token_payload = ZendeskTokenPayload.model_validate_json(token_payload_json)

    thirty_mins_from_now = datetime.now(UTC) + timedelta(minutes=30)
    access_token_expiring_soon = token_payload.access_token_expires_at and (
        token_payload.access_token_expires_at < thirty_mins_from_now
    )

    three_days_from_now = datetime.now(UTC) + timedelta(days=3)
    refresh_token_expiring_soon = token_payload.refresh_token_expires_at < three_days_from_now

    if access_token_expiring_soon or refresh_token_expiring_soon:
        logger.info(
            "Zendesk token expiring soon, refreshing",
            tenant_id=tenant_id,
            subdomain=subdomain,
            access_token_expires_at=token_payload.access_token_expires_at,
            refresh_token_expires_at=token_payload.refresh_token_expires_at,
        )

        async with ZendeskOauthClient(subdomain=subdomain) as refresh_client:
            token_response = await refresh_client.oauth_refresh(token_payload.refresh_token)
            token_payload = ZendeskTokenPayload.from_token_response(token_response)

        await ssm_client.store_zendesk_token_payload(
            tenant_id=tenant_id,
            token_payload_json=token_payload.model_dump_json(),
        )

    redacted_token = (
        f"{token_payload.access_token[:8]}...{token_payload.access_token[-4:]}"
        if len(token_payload.access_token) > 12
        else "***"
    )

    logger.info(
        "Zendesk access_token loaded",
        tenant_id=tenant_id,
        subdomain=subdomain,
        token_preview=redacted_token,
    )

    return ZendeskClient(subdomain=subdomain, access_token=token_payload.access_token)
