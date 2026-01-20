import os
from urllib.parse import quote

import newrelic.agent
from opensearchpy import exceptions

from src.clients.opensearch import OPENSEARCH_SANITY_CHECK_DOCUMENT, OpenSearchClient
from src.steward.models import TenantCredentials
from src.utils.logging import get_logger

# Initialize logger
logger = get_logger(__name__)


def _get_opensearch_domain_host() -> str:
    """Get OpenSearch domain host from environment variable."""
    host = os.environ.get("OPENSEARCH_DOMAIN_HOST")
    if not host:
        raise RuntimeError(
            "No OpenSearch domain host found. Set OPENSEARCH_DOMAIN_HOST environment variable."
        )

    port = os.environ.get("OPENSEARCH_PORT")
    if not port:
        raise RuntimeError("No OpenSearch port found. Set OPENSEARCH_PORT environment variable.")

    return f"{host}:{port}"


def _get_admin_opensearch_url() -> str:
    """Get OpenSearch admin URL with basic auth credentials."""
    host = _get_opensearch_domain_host()
    use_ssl = os.environ.get("OPENSEARCH_USE_SSL") is not None
    protocol = "https" if use_ssl else "http"

    # Always use basic auth for admin operations
    user = os.environ.get("OPENSEARCH_ADMIN_USERNAME")
    password = os.environ.get("OPENSEARCH_ADMIN_PASSWORD")

    # URL-encode username and password to handle special characters
    encoded_user = quote(user, safe="") if user else ""
    encoded_password = quote(password, safe="") if password else ""

    return f"{protocol}://{encoded_user}:{encoded_password}@{host}"


async def _create_os_index(creds: TenantCredentials) -> None:
    """Create OpenSearch index and alias for tenant."""

    logger.info(f"Creating OpenSearch index for tenant {creds.tenant_id}")

    # Derive OpenSearch identifiers from tenant_id
    os_alias = f"tenant-{creds.tenant_id}"
    os_index = f"tenant-{creds.tenant_id}-v1"

    # Create OpenSearch client using admin/service credentials
    admin_url = _get_admin_opensearch_url()
    logger.info("Creating OpenSearch client using admin URL", admin_url=admin_url)
    os_client = OpenSearchClient(admin_url)

    # Create concrete index with alias
    await _create_index_with_alias(os_client, creds.tenant_id, os_alias, os_index)

    logger.info("Created OpenSearch index with alias", os_alias=os_alias, tenant_id=creds.tenant_id)

    logger.info(f"Successfully created OpenSearch index for tenant {creds.tenant_id}")


async def _create_index_with_alias(
    os_client: OpenSearchClient, tenant_id: str, os_alias: str, os_index: str
) -> None:
    """Create concrete index and set up alias."""
    logger.info(
        "Creating index with alias", os_index=os_index, os_alias=os_alias, tenant_id=tenant_id
    )

    # Create the concrete index (this will use the template if it exists)
    try:
        response = await os_client.create_index(index_name=os_index)
        if response.get("already_existed"):
            logger.info("Index already exists", os_index=os_index)
        else:
            logger.info("Created index", os_index=os_index)
        if not await os_client.exists_alias(name=os_alias):
            await os_client.put_alias(index=os_index, name=os_alias)
            logger.info("Created opensearch index alias", index=os_index, alias=os_alias)

    except Exception as e:
        # Record the error in New Relic
        newrelic.agent.record_exception()
        logger.error("Failed to create index", os_index=os_index, error=str(e))
        raise


async def _run_os_sanity_checks(creds: TenantCredentials) -> None:
    """Run OpenSearch sanity checks for tenant index access.

    Uses shared service credentials. Verifies the tenant's index exists and is accessible.
    """
    logger.info(f"Running sanity checks for tenant {creds.tenant_id}")

    # Derive OpenSearch alias from tenant_id
    os_alias = f"tenant-{creds.tenant_id}"

    # Create client with shared service credentials
    service_url = _get_admin_opensearch_url()
    service_client = OpenSearchClient(service_url)

    # Test 1: Verify index exists and can be searched
    try:
        response = await service_client.search(
            index=os_alias,
            body={"query": {"match_all": {}}, "size": 0},  # size=0 for count only
        )
        logger.info(
            "Service can search tenant index",
            os_alias=os_alias,
            doc_count=response["hits"]["total"]["value"],
        )
    except exceptions.NotFoundError:
        logger.info("Tenant index exists but is empty (expected for new tenant)", os_alias=os_alias)
    except Exception as e:
        newrelic.agent.record_exception()
        logger.error("Failed to search tenant index", os_alias=os_alias, error=str(e))
        raise

    # Test 2: Verify can write to tenant index
    try:
        await service_client.index(
            index=os_alias, body=OPENSEARCH_SANITY_CHECK_DOCUMENT, refresh=True
        )
        logger.info("Service can write to tenant index", os_alias=os_alias)

        # Clean up test document
        await service_client.delete_by_query(
            index=os_alias, body={"query": {"term": {"metadata.test": True}}}, refresh=True
        )
        logger.debug("Cleaned up test document")

    except Exception as e:
        newrelic.agent.record_exception()
        logger.error("Failed to write to tenant index", os_alias=os_alias, error=str(e))
        raise

    logger.info(f"Completed sanity checks for tenant {creds.tenant_id}")
