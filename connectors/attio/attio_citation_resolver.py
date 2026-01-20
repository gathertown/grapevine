"""Attio citation resolvers."""

from __future__ import annotations

from typing import TYPE_CHECKING

from connectors.attio.attio_company_document import AttioCompanyDocumentMetadata
from connectors.attio.attio_deal_document import AttioDealDocumentMetadata
from connectors.attio.attio_person_document import AttioPersonDocumentMetadata
from connectors.base import BaseCitationResolver
from connectors.base.document_source import DocumentWithSourceAndMetadata
from src.utils.logging import get_logger
from src.utils.tenant_config import get_config_value_with_pool

if TYPE_CHECKING:
    from src.mcp.api.citation_resolver import CitationResolver

logger = get_logger(__name__)

# Attio app base URL
ATTIO_APP_BASE_URL = "https://app.attio.com"

# Config key for Attio workspace slug
ATTIO_WORKSPACE_SLUG_KEY = "ATTIO_WORKSPACE_SLUG"


async def _get_attio_workspace_slug(resolver: CitationResolver) -> str | None:
    """Get the Attio workspace slug for the tenant from config."""
    try:
        return await get_config_value_with_pool(ATTIO_WORKSPACE_SLUG_KEY, resolver.db_pool)
    except Exception as e:
        logger.error(f"Error retrieving Attio workspace slug for tenant {resolver.tenant_id}: {e}")
        return None


class AttioCompanyCitationResolver(BaseCitationResolver[AttioCompanyDocumentMetadata]):
    """Resolver for Attio company citations."""

    async def resolve_citation(
        self,
        document: DocumentWithSourceAndMetadata[AttioCompanyDocumentMetadata],
        excerpt: str,
        resolver: CitationResolver,
    ) -> str:
        """Generate Attio company URL.

        Attio company URLs follow the format:
        https://app.attio.com/<workspace_slug>/company/<record_id>/overview
        """
        company_id = document.metadata.get("company_id")
        if not company_id:
            return ""

        workspace_slug = await _get_attio_workspace_slug(resolver)
        if not workspace_slug:
            logger.warning(f"No Attio workspace slug configured for tenant {resolver.tenant_id}")
            return ""

        return f"{ATTIO_APP_BASE_URL}/{workspace_slug}/company/{company_id}/overview"


class AttioPersonCitationResolver(BaseCitationResolver[AttioPersonDocumentMetadata]):
    """Resolver for Attio person citations."""

    async def resolve_citation(
        self,
        document: DocumentWithSourceAndMetadata[AttioPersonDocumentMetadata],
        excerpt: str,
        resolver: CitationResolver,
    ) -> str:
        """Generate Attio person URL.

        Attio person URLs follow the format:
        https://app.attio.com/<workspace_slug>/person/<record_id>/overview
        """
        person_id = document.metadata.get("person_id")
        if not person_id:
            return ""

        workspace_slug = await _get_attio_workspace_slug(resolver)
        if not workspace_slug:
            logger.warning(f"No Attio workspace slug configured for tenant {resolver.tenant_id}")
            return ""

        return f"{ATTIO_APP_BASE_URL}/{workspace_slug}/person/{person_id}/overview"


class AttioDealCitationResolver(BaseCitationResolver[AttioDealDocumentMetadata]):
    """Resolver for Attio deal citations."""

    async def resolve_citation(
        self,
        document: DocumentWithSourceAndMetadata[AttioDealDocumentMetadata],
        excerpt: str,
        resolver: CitationResolver,
    ) -> str:
        """Generate Attio deal URL.

        Attio deal URLs follow the format:
        https://app.attio.com/<workspace_slug>/deal/<record_id>/overview
        """
        deal_id = document.metadata.get("deal_id")
        if not deal_id:
            return ""

        workspace_slug = await _get_attio_workspace_slug(resolver)
        if not workspace_slug:
            logger.warning(f"No Attio workspace slug configured for tenant {resolver.tenant_id}")
            return ""

        return f"{ATTIO_APP_BASE_URL}/{workspace_slug}/deal/{deal_id}/overview"
