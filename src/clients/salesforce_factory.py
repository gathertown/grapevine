"""
Factory for creating Salesforce clients with proper authentication.
"""

import asyncpg

from src.clients.salesforce import SalesforceClient
from src.clients.ssm import SSMClient
from src.utils.config import get_config_value
from src.utils.logging import get_logger

logger = get_logger(__name__)


async def get_salesforce_client_for_tenant(
    tenant_id: str, ssm_client: SSMClient, db_pool: asyncpg.Pool
) -> SalesforceClient:
    """Get SalesforceClient for the specified tenant using stored credentials."""

    # Get stored credentials from SSM/environment
    refresh_token = await ssm_client.get_salesforce_refresh_token(tenant_id)
    if not refresh_token:
        raise ValueError(f"No Salesforce refresh token configured for tenant {tenant_id}")

    # Get instance URL and org ID from tenant config database
    async with db_pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT key, value FROM config WHERE key IN ($1, $2)",
            "SALESFORCE_INSTANCE_URL",
            "SALESFORCE_ORG_ID",
        )

    config = {row["key"]: row["value"] for row in rows}
    instance_url = config.get("SALESFORCE_INSTANCE_URL")
    org_id = config.get("SALESFORCE_ORG_ID")

    if not instance_url or not org_id:
        raise ValueError(
            f"No Salesforce instance URL or org ID configured for tenant {tenant_id}: {instance_url}, {org_id}"
        )

    # Get client credentials from environment
    client_id = get_config_value("SALESFORCE_CLIENT_ID")
    client_secret = get_config_value("SALESFORCE_CONSUMER_SECRET")
    if not client_id or not client_secret:
        raise ValueError(
            "SALESFORCE_CLIENT_ID and SALESFORCE_CONSUMER_SECRET environment variables are required"
        )

    try:
        client = await SalesforceClient.from_refresh_token(
            instance_url=instance_url,
            org_id=org_id,
            refresh_token=refresh_token,
            client_id=client_id,
            client_secret=client_secret,
        )
        logger.info(f"Successfully created Salesforce client for tenant {tenant_id}")
        return client
    except Exception as e:
        logger.error(f"Failed to create Salesforce client for tenant {tenant_id}: {e}")
        raise
