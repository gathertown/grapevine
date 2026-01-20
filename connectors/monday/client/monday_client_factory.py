"""Factory functions for creating Monday.com API clients."""

from connectors.monday.client.monday_client import MondayClient
from src.clients.ssm import SSMClient
from src.utils.logging import get_logger

logger = get_logger(__name__)

# Minimum token length to show partial redaction (first 4 + "..." + last 4)
MIN_TOKEN_LENGTH_FOR_REDACTION = 12


async def get_monday_client_for_tenant(tenant_id: str, ssm_client: SSMClient) -> MondayClient:
    """Create a Monday.com client for a specific tenant.

    Retrieves the access token from SSM Parameter Store.

    Args:
        tenant_id: Tenant identifier
        ssm_client: SSM client for retrieving secrets

    Returns:
        Configured MondayClient instance

    Raises:
        ValueError: If access token is not found
    """
    param_name = f"/{tenant_id}/api-key/MONDAY_ACCESS_TOKEN"
    access_token = await ssm_client.get_parameter(param_name)

    if not access_token:
        raise ValueError(f"Monday.com access token not found for tenant {tenant_id}")

    redacted_token = (
        f"{access_token[:4]}...{access_token[-4:]}"
        if len(access_token) > MIN_TOKEN_LENGTH_FOR_REDACTION
        else "***"
    )

    logger.info(
        "Monday.com access token loaded",
        tenant_id=tenant_id,
        token_preview=redacted_token,
    )

    return MondayClient(access_token)
