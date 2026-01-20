"""Pipedrive citation resolvers for generating deep links.

Citation URL patterns verified from the Pipedrive web application:
- Deals: https://{company}.pipedrive.com/deal/{deal_id}
- Persons: https://{company}.pipedrive.com/person/{person_id}
- Organizations: https://{company}.pipedrive.com/organization/{org_id}
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from connectors.base.base_citation_resolver import BaseCitationResolver
from connectors.base.document_source import DocumentWithSourceAndMetadata
from connectors.pipedrive.pipedrive_deal_document import PipedriveDealDocumentMetadata
from connectors.pipedrive.pipedrive_models import PIPEDRIVE_API_DOMAIN_KEY
from connectors.pipedrive.pipedrive_organization_document import (
    PipedriveOrganizationDocumentMetadata,
)
from connectors.pipedrive.pipedrive_person_document import PipedrivePersonDocumentMetadata
from connectors.pipedrive.pipedrive_product_document import PipedriveProductDocumentMetadata
from src.utils.logging import get_logger
from src.utils.tenant_config import get_config_value_with_pool

if TYPE_CHECKING:
    from src.mcp.api.citation_resolver import CitationResolver

logger = get_logger(__name__)


async def _get_pipedrive_api_domain(resolver: CitationResolver) -> str | None:
    """Get the Pipedrive API domain for the tenant from config."""
    try:
        return await get_config_value_with_pool(PIPEDRIVE_API_DOMAIN_KEY, resolver.db_pool)
    except Exception as e:
        logger.error(f"Error retrieving Pipedrive API domain for tenant {resolver.tenant_id}: {e}")
        return None


class PipedriveDealCitationResolver(BaseCitationResolver[PipedriveDealDocumentMetadata]):
    """Resolves citations for Pipedrive deal documents."""

    async def resolve_citation(
        self,
        document: DocumentWithSourceAndMetadata[PipedriveDealDocumentMetadata],
        excerpt: str,
        resolver: CitationResolver,
    ) -> str:
        """Generate a deep link to a Pipedrive deal.

        Pipedrive deal URLs follow the format:
        https://{company}.pipedrive.com/deal/{deal_id}
        """
        deal_id = document.metadata.get("deal_id")
        if not deal_id:
            return ""

        api_domain = await _get_pipedrive_api_domain(resolver)
        if not api_domain:
            logger.warning(f"No Pipedrive API domain configured for tenant {resolver.tenant_id}")
            return ""

        return f"{api_domain}/deal/{deal_id}"


class PipedrivePersonCitationResolver(BaseCitationResolver[PipedrivePersonDocumentMetadata]):
    """Resolves citations for Pipedrive person documents."""

    async def resolve_citation(
        self,
        document: DocumentWithSourceAndMetadata[PipedrivePersonDocumentMetadata],
        excerpt: str,
        resolver: CitationResolver,
    ) -> str:
        """Generate a deep link to a Pipedrive person.

        Pipedrive person URLs follow the format:
        https://{company}.pipedrive.com/person/{person_id}
        """
        person_id = document.metadata.get("person_id")
        if not person_id:
            return ""

        api_domain = await _get_pipedrive_api_domain(resolver)
        if not api_domain:
            logger.warning(f"No Pipedrive API domain configured for tenant {resolver.tenant_id}")
            return ""

        return f"{api_domain}/person/{person_id}"


class PipedriveOrganizationCitationResolver(
    BaseCitationResolver[PipedriveOrganizationDocumentMetadata]
):
    """Resolves citations for Pipedrive organization documents."""

    async def resolve_citation(
        self,
        document: DocumentWithSourceAndMetadata[PipedriveOrganizationDocumentMetadata],
        excerpt: str,
        resolver: CitationResolver,
    ) -> str:
        """Generate a deep link to a Pipedrive organization.

        Pipedrive organization URLs follow the format:
        https://{company}.pipedrive.com/organization/{org_id}
        """
        org_id = document.metadata.get("org_id")
        if not org_id:
            return ""

        api_domain = await _get_pipedrive_api_domain(resolver)
        if not api_domain:
            logger.warning(f"No Pipedrive API domain configured for tenant {resolver.tenant_id}")
            return ""

        return f"{api_domain}/organization/{org_id}"


class PipedriveProductCitationResolver(BaseCitationResolver[PipedriveProductDocumentMetadata]):
    """Resolves citations for Pipedrive product documents."""

    async def resolve_citation(
        self,
        document: DocumentWithSourceAndMetadata[PipedriveProductDocumentMetadata],
        excerpt: str,
        resolver: CitationResolver,
    ) -> str:
        """Generate a deep link to a Pipedrive product.

        Pipedrive product URLs follow the format:
        https://{company}.pipedrive.com/product/{product_id}
        """
        product_id = document.metadata.get("product_id")
        if not product_id:
            return ""

        api_domain = await _get_pipedrive_api_domain(resolver)
        if not api_domain:
            logger.warning(f"No Pipedrive API domain configured for tenant {resolver.tenant_id}")
            return ""

        return f"{api_domain}/product/{product_id}"
