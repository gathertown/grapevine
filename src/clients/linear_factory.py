"""Factory for creating Linear clients with proper authentication."""

import asyncpg

from src.clients.linear import LinearClient
from src.clients.ssm import SSMClient
from src.ingest.services.linear_auth import LinearAuthService


async def get_linear_client_for_tenant(
    tenant_id: str, ssm_client: SSMClient, db_pool: asyncpg.Pool
) -> LinearClient:
    """Factory method to get Linear client with proper OAuth authentication.

    This factory handles token refresh automatically if the token is expired
    or expiring soon.

    Args:
        tenant_id: Tenant ID
        ssm_client: SSM client for retrieving secrets
        db_pool: Database pool for token expiry management

    Returns:
        LinearClient configured with valid access token
    """
    auth_service = LinearAuthService(ssm_client, db_pool)

    access_token = await auth_service.get_valid_access_token(tenant_id)

    return LinearClient(token=access_token)
