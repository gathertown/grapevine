from __future__ import annotations

from connectors.fireflies.client.fireflies_client import FirefliesClient
from src.clients.ssm import SSMClient
from src.utils.logging import get_logger

logger = get_logger(__name__)


async def get_fireflies_client_for_tenant(
    tenant_id: str,
    ssm_client: SSMClient,
) -> FirefliesClient:
    """
    Return a FirefliesClient configured with the tenant's credentials.
    Requires tenant-specific configuration in the database.
    """

    api_key = await ssm_client.get_fireflies_api_key(tenant_id)

    if not api_key:
        raise ValueError(f"Missing Fireflies API key for tenant {tenant_id}")

    redacted_api_key = f"{api_key[:4]}...{api_key[-4:]}" if len(api_key) > 12 else "***"

    logger.info(
        "Fireflies API key loaded",
        tenant_id=tenant_id,
        api_key_preview=redacted_api_key,
    )

    return FirefliesClient(access_token=api_key, tenant_id=tenant_id)
