from __future__ import annotations

from datetime import UTC, datetime, timedelta

from connectors.asana.client.asana_client import AsanaClient
from connectors.asana.client.asana_oauth_token_models import AsanaOauthTokenPayload
from src.clients.ssm import SSMClient
from src.utils.logging import get_logger

logger = get_logger(__name__)


async def get_asana_client_for_tenant(
    tenant_id: str,
    ssm_client: SSMClient,
) -> AsanaClient:
    """
    Return a AsanaClient configured with the tenant's credentials.
    Requires tenant-specific configuration in the database.
    """

    access_token = await _get_token(tenant_id, ssm_client)

    redacted_token = (
        f"{access_token[:8]}...{access_token[-4:]}" if len(access_token) > 12 else "***"
    )

    logger.info(
        "Asana access_token loaded",
        tenant_id=tenant_id,
        token_preview=redacted_token,
    )

    return AsanaClient(access_token=access_token, tenant_id=tenant_id)


async def _get_token(tenant_id: str, ssm_client: SSMClient) -> str:
    """
    Prefer service account token over OAuth token if both are available. Refresh the oauth access
    token if it is expiring soon.
    """

    service_account_token = await ssm_client.get_asana_service_account_token(tenant_id)

    if service_account_token:
        logger.info(
            "Asana service account token found, using service account token",
            tenant_id=tenant_id,
        )
        return service_account_token
    else:
        logger.info(
            "Asana service account token not found, falling back to OAuth token",
            tenant_id=tenant_id,
        )

    token_payload_json = await ssm_client.get_asana_oauth_token_payload(tenant_id)

    if not token_payload_json:
        raise ValueError(f"Missing Asana oauth token for tenant {tenant_id}")

    token_payload = AsanaOauthTokenPayload.model_validate_json(token_payload_json)

    thirty_mins_from_now = datetime.now(UTC) + timedelta(minutes=30)
    access_token_expiring_soon = token_payload.access_token_expires_at and (
        token_payload.access_token_expires_at < thirty_mins_from_now
    )

    if access_token_expiring_soon:
        logger.info(
            "Asana oauth access token expiring soon, refreshing",
            tenant_id=tenant_id,
            access_token_expires_at=token_payload.access_token_expires_at,
        )

        async with AsanaClient(access_token=None, tenant_id=tenant_id) as refresh_client:
            token_response = await refresh_client.oauth_refresh(token_payload.refresh_token)
            token_payload = token_payload.refresh(token_response)

        await ssm_client.store_asana_oauth_token_payload(
            tenant_id=tenant_id,
            token_payload_json=token_payload.model_dump_json(),
        )

    return token_payload.access_token
