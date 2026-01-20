"""Salesforce citation resolver."""

from __future__ import annotations

from typing import TYPE_CHECKING

from connectors.base import BaseCitationResolver
from connectors.base.document_source import DocumentWithSourceAndMetadata
from connectors.salesforce.salesforce_base_document import BaseSalesforceDocumentMetadata
from src.utils.logging import get_logger

if TYPE_CHECKING:
    from src.mcp.api.citation_resolver import CitationResolver

logger = get_logger(__name__)


class SalesforceCitationResolver(BaseCitationResolver[BaseSalesforceDocumentMetadata]):
    """Resolver for Salesforce object citations."""

    async def resolve_citation(
        self,
        document: DocumentWithSourceAndMetadata[BaseSalesforceDocumentMetadata],
        excerpt: str,
        resolver: CitationResolver,
    ) -> str:
        # Extract record information from metadata
        record_id = document.metadata["record_id"]

        if not record_id:
            logger.error(f"Missing record_id for Salesforce document {document.id}")
            return ""

        # Get tenant-specific Salesforce instance URL
        instance_url = await self._get_salesforce_instance_domain(resolver)
        if not instance_url:
            logger.error(f"No Salesforce instance URL configured for tenant {resolver.tenant_id}")
            return ""

        return f"{instance_url}/{record_id}"

    async def _get_salesforce_instance_domain(self, resolver: CitationResolver) -> str | None:
        """
        Get the Salesforce instance domain for the tenant.
        Returns something like "https://orgfarm-0c36d862d2-dev-ed.develop.my.salesforce.com"
        """
        try:
            async with resolver.db_pool.acquire() as conn:
                instance_url = await conn.fetchval(
                    "SELECT value FROM config WHERE key = $1", "SALESFORCE_INSTANCE_URL"
                )

                if not instance_url:
                    return None
                return instance_url

        except Exception as e:
            logger.error(
                f"Error retrieving Salesforce instance URL for tenant {resolver.tenant_id}: {e}"
            )
            return None
