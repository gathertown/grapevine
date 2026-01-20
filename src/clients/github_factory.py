"""Factory for creating GitHub clients with appropriate authentication method."""

from src.clients.github import GitHubClient
from src.clients.github_app import get_github_app_client
from src.clients.ssm import SSMClient
from src.database.connector_installations import (
    ConnectorInstallationsRepository,
    ConnectorType,
)
from src.utils.logging import get_logger

logger = get_logger(__name__)


async def _get_github_app_installation_id(tenant_id: str) -> int | None:
    """Get GitHub App installation ID for tenant from database.

    Returns:
        Installation ID if found, None otherwise
    """
    repo = ConnectorInstallationsRepository()
    connector_installation = await repo.get_by_tenant_and_type(tenant_id, ConnectorType.GITHUB)

    if connector_installation and connector_installation.status != "disconnected":
        return int(connector_installation.external_id)
    return None


async def get_github_client_for_tenant(
    tenant_id: str, ssm_client: SSMClient, per_page: int | None = None
) -> GitHubClient:
    """Factory method to get GitHub client with appropriate authentication.

    Authentication Priority:
    1. GitHub App installation (if installation-id param exists)
    2. Personal Access Token (if GITHUB_TOKEN exists)

    Returns:
        GitHubClient configured with appropriate authentication, or None if no auth available

    Raises:
        ValueError: If tenant_id or installation_id is invalid or GitHub App credentials are malformed
        Exception: If client creation fails due to invalid credentials
    """
    if not tenant_id:
        raise ValueError("Tenant ID is required")

    try:
        # First, check for GitHub App installation
        installation_id = await _get_github_app_installation_id(tenant_id)

        if installation_id:
            logger.debug(f"Using GitHub App authentication for tenant {tenant_id}")
            # Use GitHub App authentication
            app_client = get_github_app_client()
            return GitHubClient(
                installation_id=installation_id, app_client=app_client, per_page=per_page
            )

        # Fall back to PAT token
        token = await ssm_client.get_github_token(tenant_id)
        if token:
            logger.debug(f"Using PAT authentication for tenant {tenant_id}")
            return GitHubClient(token=token, per_page=per_page)

        raise ValueError(f"No GitHub authentication configured for tenant {tenant_id}")

    except Exception as e:
        logger.error(f"Error creating GitHub client for tenant {tenant_id}: {e}")
        raise
