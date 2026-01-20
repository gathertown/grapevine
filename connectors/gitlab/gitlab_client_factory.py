"""Factory for creating GitLab clients with tenant-specific credentials.

Note: This factory only supports gitlab.com. Self-hosted GitLab instances
are not supported in this version.
"""

import logging

from connectors.gitlab.gitlab_client import GitLabClient
from src.clients.ssm import SSMClient

logger = logging.getLogger(__name__)

# SSM config key for GitLab access token
GITLAB_CONFIG_KEY_ACCESS_TOKEN = "GITLAB_ACCESS_TOKEN"


async def get_gitlab_client_for_tenant(
    tenant_id: str,
    ssm_client: SSMClient,
    per_page: int = 100,
) -> GitLabClient:
    """Create a GitLab client with tenant-specific credentials.

    Note: Only gitlab.com is supported. Self-hosted instances are not supported.

    Args:
        tenant_id: The tenant ID to get credentials for
        ssm_client: SSM client for retrieving credentials
        per_page: Number of items per page for paginated requests

    Returns:
        Configured GitLabClient instance for gitlab.com

    Raises:
        ValueError: If required credentials are not found
    """
    # Get access token from SSM
    access_token = await ssm_client.get_api_key(tenant_id, GITLAB_CONFIG_KEY_ACCESS_TOKEN)
    if not access_token:
        raise ValueError(f"GitLab access token not found for tenant {tenant_id}")

    logger.info(f"Creating GitLab client for tenant {tenant_id} (gitlab.com)")

    return GitLabClient(
        access_token=access_token,
        tenant_id=tenant_id,
        per_page=per_page,
    )
