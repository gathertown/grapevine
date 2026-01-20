from __future__ import annotations

from connectors.clickup.client.clickup_client import ClickupClient
from src.clients.ssm import SSMClient
from src.utils.logging import get_logger

logger = get_logger(__name__)


async def get_clickup_client_for_tenant(
    tenant_id: str,
    ssm_client: SSMClient,
) -> ClickupClient:
    """
    Return a ClickupClient configured with the tenant's credentials.
    Requires tenant-specific configuration in the database.
    """

    oauth_token = await ssm_client.get_clickup_oauth_token(tenant_id)
    if not oauth_token:
        raise ValueError(f"Missing Clickup OAuth token for tenant {tenant_id}")

    redacted_oauth_token = (
        f"{oauth_token[:4]}...{oauth_token[-4:]}" if len(oauth_token) > 12 else "***"
    )
    logger.info(
        "Clickup OAuth token loaded",
        tenant_id=tenant_id,
        oauth_token_preview=redacted_oauth_token,
    )

    client = ClickupClient(access_token=oauth_token, tenant_id=tenant_id)
    await client.setup_rate_limit()

    return client
