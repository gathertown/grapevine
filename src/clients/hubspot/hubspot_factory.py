"""
Factory for creating HubSpot clients with proper authentication.
"""

import asyncpg

from src.clients.hubspot.hubspot_client import HubSpotClient
from src.clients.ssm import SSMClient
from src.ingest.services.hubspot_auth import HubspotAuthService


async def get_hubspot_client_for_tenant(
    tenant_id: str, ssm_client: SSMClient, db_pool: asyncpg.Pool
) -> HubSpotClient:
    # Create auth service
    auth_service = HubspotAuthService(ssm_client, db_pool)

    # Get valid access token from auth service
    access_token = await auth_service.get_valid_access_token(tenant_id)

    # Create and return client with auth service injected
    return HubSpotClient(
        tenant_id=tenant_id,
        access_token=access_token,
        auth_service=auth_service,
    )
