import asyncio
import contextlib
import os
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

from src.clients.opensearch import OpenSearchClient, OpenSearchDocument
from src.utils.config import get_opensearch_admin_password, get_opensearch_admin_username
from src.utils.logging import get_logger

logger = get_logger(__name__)


class TenantScopedOpenSearchClient:
    """Wrapper around OpenSearchClient that enforces tenant isolation.

    This client only allows operations on the specific tenant's index, preventing
    accidental or malicious cross-tenant data access.
    """

    def __init__(self, underlying_client: OpenSearchClient, tenant_index: str, tenant_id: str):
        """Initialize tenant-scoped client.

        Args:
            underlying_client: The underlying OpenSearchClient with full admin access
            tenant_index: The tenant's index name (e.g., "tenant-abc123")
            tenant_id: The tenant ID for logging
        """
        self._client = underlying_client
        self._tenant_index = tenant_index
        self._tenant_id = tenant_id

    def _validate_index(self, index_name: str) -> None:
        """Validate that the index name matches this tenant's index.

        Args:
            index_name: The index name to validate

        Raises:
            ValueError: If index_name doesn't match the tenant's index
        """
        if index_name != self._tenant_index:
            error_msg = (
                f"Security violation: Attempted to access index '{index_name}' "
                f"but only '{self._tenant_index}' is allowed for tenant {self._tenant_id}"
            )
            logger.error(error_msg)
            raise ValueError(error_msg)

    @property
    def client(self):
        """Access to underlying OpenSearch client for direct operations.

        WARNING: This bypasses tenant scoping. Only use when you need direct access
        and are certain about tenant isolation (e.g., cluster health checks).
        """
        return self._client.client

    async def create_index(self, index_name: str) -> dict[str, Any]:
        """Create index (tenant-scoped)."""
        self._validate_index(index_name)
        return await self._client.create_index(index_name)

    async def index_document(self, index_name: str, document: OpenSearchDocument) -> dict[str, Any]:
        """Index a document (tenant-scoped)."""
        self._validate_index(index_name)
        return await self._client.index_document(index_name, document)

    async def bulk_index_documents(
        self, index_name: str, documents: list[OpenSearchDocument]
    ) -> dict[str, Any]:
        """Bulk index documents (tenant-scoped)."""
        self._validate_index(index_name)
        return await self._client.bulk_index_documents(index_name, documents)

    async def search_similar(
        self,
        index_name: str,
        query_embedding: list[float],
        limit: int = 10,
        filters: dict | None = None,
    ) -> list[dict[str, Any]]:
        """Search for similar documents (tenant-scoped)."""
        self._validate_index(index_name)
        return await self._client.search_similar(index_name, query_embedding, limit, filters)

    async def delete_index(self, index_name: str) -> dict[str, Any]:
        """Delete index (tenant-scoped)."""
        self._validate_index(index_name)
        return await self._client.delete_index(index_name)

    async def delete_document(self, index_name: str, document_id: str) -> dict[str, Any]:
        """Delete a document (tenant-scoped)."""
        self._validate_index(index_name)
        return await self._client.delete_document(index_name, document_id)

    async def index_exists(self, index_name: str) -> bool:
        """Check if index exists (tenant-scoped)."""
        self._validate_index(index_name)
        return await self._client.index_exists(index_name)

    async def keyword_search(
        self,
        index_name: str,
        query: str,
        fields: list[str],
        query_weight: float = 1.0,
        recency_weight: float = 0.0,
        references_weight: float = 0.0,
        limit: int = 10,
        filters: dict | None = None,
        advanced: bool = False,
    ) -> list[dict[str, Any]]:
        """Keyword search (tenant-scoped)."""
        self._validate_index(index_name)
        return await self._client.keyword_search(
            index_name,
            query,
            fields,
            query_weight,
            recency_weight,
            references_weight,
            limit,
            filters,
            advanced,
        )

    async def bulk(
        self, index: str, body: list[dict[str, Any]], refresh: bool | str = False
    ) -> dict[str, Any]:
        """Bulk operations (tenant-scoped).

        Args:
            index: Index name (must match tenant index)
            body: List of operations to perform
            refresh: Whether to refresh the index after the operation

        Returns:
            Response from OpenSearch bulk API
        """
        self._validate_index(index)
        return await self._client.bulk(index=index, body=body, refresh=refresh)

    async def delete_by_query(
        self, index: str, body: dict[str, Any], refresh: bool | str = False
    ) -> dict[str, Any]:
        """Delete documents by query (tenant-scoped).

        Args:
            index: Index name (must match tenant index)
            body: Query to match documents to delete
            refresh: Whether to refresh the index after the operation

        Returns:
            Response from OpenSearch delete_by_query API
        """
        self._validate_index(index)
        return await self._client.delete_by_query(index=index, body=body, refresh=refresh)

    async def search(
        self, index: str, body: dict[str, Any], size: int | None = None
    ) -> dict[str, Any]:
        """Search documents (tenant-scoped).

        Args:
            index: Index name (must match tenant index)
            body: Query to search for documents
            size: Maximum number of results to return

        Returns:
            Response from OpenSearch search API
        """
        self._validate_index(index)
        return await self._client.search(index=index, body=body, size=size)

    async def index_raw(
        self, index: str, body: dict[str, Any], refresh: bool | str = False
    ) -> dict[str, Any]:
        """Index a raw document (tenant-scoped).

        This is different from index_document() which takes an OpenSearchDocument.
        This method takes a raw dictionary and indexes it directly.

        Args:
            index: Index name (must match tenant index)
            body: Raw document to index
            refresh: Whether to refresh the index after the operation

        Returns:
            Response from OpenSearch index API
        """
        self._validate_index(index)
        return await self._client.index(index=index, body=body, refresh=refresh)

    async def exists_alias(self, name: str) -> bool:
        """Check if alias exists (tenant-scoped).

        Args:
            name: Alias name (must match tenant index)

        Returns:
            True if alias exists, False otherwise
        """
        self._validate_index(name)
        return await self._client.exists_alias(name=name)

    async def put_alias(self, index: str, name: str) -> dict[str, Any]:
        """Create alias for index (tenant-scoped).

        Args:
            index: Index name (must match tenant index pattern)
            name: Alias name (must match tenant index)

        Returns:
            Response from OpenSearch put_alias API
        """
        # Validate the alias name matches tenant index
        self._validate_index(name)
        # For index name, we need to allow tenant-{id}-v{N} pattern
        # The alias is tenant-{id}, so we validate that the index starts with the alias
        if not index.startswith(self._tenant_index):
            error_msg = (
                f"Security violation: Attempted to create alias for index '{index}' "
                f"but only indices starting with '{self._tenant_index}' are allowed for tenant {self._tenant_id}"
            )
            logger.error(error_msg)
            raise ValueError(error_msg)
        return await self._client.put_alias(index=index, name=name)

    async def aclose(self):
        """Close the underlying client."""
        await self._client.aclose()


@dataclass
class OpenSearchPoolInfo:
    """Information about an OpenSearch client including reference count."""

    client: TenantScopedOpenSearchClient
    index_alias: str
    ref_count: int = 0
    tenant_id: str = ""


class TenantOpenSearchManager:
    """Manage OpenSearch clients per tenant (organization).

    All tenants share the same service credentials. Tenant isolation is enforced
    by application-layer index name filtering.

    Provides context managers for acquiring tenant-specific OpenSearch clients.
    Includes reference counting to automatically close unused clients.
    """

    def __init__(self) -> None:
        self._client_info: dict[str, OpenSearchPoolInfo] = {}
        self._lock = asyncio.Lock()

    def _build_opensearch_url(self) -> str:
        """Construct an OpenSearch URL using shared admin credentials.

        All tenants use the same admin credentials. Tenant isolation is enforced
        by application-layer index name filtering.

        Returns:
            Complete OpenSearch URL with embedded admin credentials

        Raises:
            RuntimeError: If required environment variables are missing
        """
        os_user = get_opensearch_admin_username()
        os_pass = get_opensearch_admin_password()

        if not os_user or not os_pass:
            raise RuntimeError(
                "OPENSEARCH_ADMIN_USERNAME and OPENSEARCH_ADMIN_PASSWORD env vars are required"
            )

        host = os.environ.get("OPENSEARCH_DOMAIN_HOST")
        if not host:
            raise RuntimeError(
                "OPENSEARCH_DOMAIN_HOST env var is required for OpenSearch connections"
            )
        port = os.environ.get("OPENSEARCH_PORT", "443")
        use_ssl = os.environ.get("OPENSEARCH_USE_SSL") is not None
        protocol = "https" if use_ssl else "http"

        return f"{protocol}://{quote(os_user)}:{quote(os_pass)}@{host}:{port}"

    async def _get_or_create_client(self, tenant_id: str) -> OpenSearchPoolInfo:
        """Internal method to get or create an OpenSearch client for a tenant.

        Returns OpenSearchPoolInfo object containing the client and reference count.
        """
        if not tenant_id:
            raise ValueError("tenant_id is required to get tenant OpenSearch client")

        # Fast path without lock if client exists
        client_info = self._client_info.get(tenant_id)
        if client_info is not None:
            return client_info

        async with self._lock:
            # Re-check under lock
            client_info = self._client_info.get(tenant_id)
            if client_info is not None:
                return client_info

            opensearch_url = self._build_opensearch_url()
            logger.info(f"Creating new OpenSearch client for tenant {tenant_id}")

            # Create underlying client with admin credentials
            underlying_client = OpenSearchClient(opensearch_url)
            index_alias = f"tenant-{tenant_id}"  # Standard alias format from tenant provisioning

            # Wrap in tenant-scoped client to enforce isolation
            scoped_client = TenantScopedOpenSearchClient(
                underlying_client=underlying_client, tenant_index=index_alias, tenant_id=tenant_id
            )

            client_info = OpenSearchPoolInfo(
                client=scoped_client, index_alias=index_alias, ref_count=0, tenant_id=tenant_id
            )
            self._client_info[tenant_id] = client_info
            return client_info

    async def _increment_ref_count(self, tenant_id: str) -> OpenSearchPoolInfo:
        """Increment reference count for an OpenSearch client."""
        client_info = await self._get_or_create_client(tenant_id)

        async with self._lock:
            client_info.ref_count += 1
            logger.debug(
                f"OpenSearch client for tenant {tenant_id} ref_count incremented to {client_info.ref_count}"
            )
            return client_info

    async def _decrement_ref_count(self, tenant_id: str) -> None:
        """Decrement reference count for an OpenSearch client and remove if zero."""
        async with self._lock:
            client_info = self._client_info.get(tenant_id)
            if client_info is None:
                logger.warning(
                    f"Attempted to decrement ref_count for non-existent OpenSearch client: {tenant_id}"
                )
                return

            client_info.ref_count -= 1
            logger.debug(
                f"OpenSearch client for tenant {tenant_id} ref_count decremented to {client_info.ref_count}"
            )

            # Remove client if no longer referenced
            if client_info.ref_count <= 0:
                logger.info(f"Removing unused OpenSearch client for tenant {tenant_id}")
                try:
                    await client_info.client.aclose()
                    del self._client_info[tenant_id]
                except Exception as e:
                    logger.error(f"Error removing OpenSearch client for tenant {tenant_id}: {e}")

    @contextlib.asynccontextmanager
    async def acquire_client(
        self, tenant_id: str
    ) -> AsyncIterator[tuple[TenantScopedOpenSearchClient, str]]:
        """Context manager to acquire a tenant-scoped OpenSearch client and index alias.

        The returned client enforces tenant isolation - it will only allow operations
        on the tenant's index and will raise ValueError if code attempts to access
        a different index.

        Usage:
            async with tenant_opensearch_manager.acquire_client(tenant_id) as (client, index):
                # client is tenant-scoped and only allows operations on 'index'
                await client.search(index=index, ...)  # OK
                await client.search(index="other-tenant", ...)  # Raises ValueError

        Returns:
            Tuple of (TenantScopedOpenSearchClient, index_alias)

        The client will be automatically removed when reference count reaches zero.
        """
        client_info = await self._increment_ref_count(tenant_id)
        try:
            yield client_info.client, client_info.index_alias
        finally:
            await self._decrement_ref_count(tenant_id)

    async def cleanup(self) -> None:
        """Remove all OpenSearch clients."""
        for client_info in list(self._client_info.values()):
            logger.info(
                f"Removing OpenSearch client for tenant {client_info.tenant_id} "
                f"(ref_count={client_info.ref_count})"
            )
            try:
                await client_info.client.aclose()
            except Exception as e:
                logger.error(
                    f"Error closing OpenSearch client for tenant {client_info.tenant_id}: {e}"
                )
        self._client_info.clear()


# Singleton manager
_tenant_opensearch_manager = TenantOpenSearchManager()

# Export the singleton for external use
tenant_opensearch_manager = _tenant_opensearch_manager
