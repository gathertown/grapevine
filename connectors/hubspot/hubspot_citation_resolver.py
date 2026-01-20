"""HubSpot citation resolvers."""

from __future__ import annotations

from typing import TYPE_CHECKING

from connectors.base import BaseCitationResolver
from connectors.base.document_source import DocumentWithSourceAndMetadata
from connectors.hubspot.hubspot_company_document import HubspotCompanyDocumentMetadata
from connectors.hubspot.hubspot_contact_document import HubspotContactDocumentMetadata
from connectors.hubspot.hubspot_deal_document import HubspotDealDocumentMetadata
from connectors.hubspot.hubspot_ticket_document import HubspotTicketDocumentMetadata
from src.clients.tenant_db import tenant_db_manager
from src.ingest.services.hubspot import hubspot_installation_service
from src.utils.logging import get_logger

if TYPE_CHECKING:
    from src.mcp.api.citation_resolver import CitationResolver

logger = get_logger(__name__)


async def get_hubspot_portal_id(tenant_id: str) -> int | None:
    """Get the HubSpot portal ID for a given tenant."""
    control_pool = await tenant_db_manager.get_control_db()
    async with control_pool.acquire() as conn:
        installation = await hubspot_installation_service.get_installation(tenant_id, conn)
    if installation:
        return installation.portal_id
    return None


class HubspotDealCitationResolver(BaseCitationResolver[HubspotDealDocumentMetadata]):
    """Resolver for HubSpot deal citations."""

    async def resolve_citation(
        self,
        document: DocumentWithSourceAndMetadata[HubspotDealDocumentMetadata],
        excerpt: str,
        resolver: CitationResolver,
    ) -> str:
        deal_id = document.metadata["deal_id"]
        if deal_id:
            portal_id = await get_hubspot_portal_id(resolver.tenant_id)
            if not portal_id:
                logger.error(f"No portal ID found for tenant {resolver.tenant_id}")
                return ""
            return f"https://app.hubspot.com/contacts/{portal_id}/record/0-3/{deal_id}"
        return ""


class HubspotCompanyCitationResolver(BaseCitationResolver[HubspotCompanyDocumentMetadata]):
    """Resolver for HubSpot company citations."""

    async def resolve_citation(
        self,
        document: DocumentWithSourceAndMetadata[HubspotCompanyDocumentMetadata],
        excerpt: str,
        resolver: CitationResolver,
    ) -> str:
        # Generate HubSpot company URL from company_id
        company_id = document.metadata["company_id"]
        if company_id:
            portal_id = await get_hubspot_portal_id(resolver.tenant_id)
            if not portal_id:
                logger.error(f"No portal ID found for tenant {resolver.tenant_id}")
                return ""
            return f"https://app.hubspot.com/contacts/{portal_id}/record/0-2/{company_id}"

        return ""


class HubspotContactCitationResolver(BaseCitationResolver[HubspotContactDocumentMetadata]):
    """Resolver for HubSpot contact citations."""

    async def resolve_citation(
        self,
        document: DocumentWithSourceAndMetadata[HubspotContactDocumentMetadata],
        excerpt: str,
        resolver: CitationResolver,
    ) -> str:
        contact_id = document.metadata["contact_id"]
        if contact_id:
            portal_id = await get_hubspot_portal_id(resolver.tenant_id)
            if not portal_id:
                logger.error(f"No portal ID found for tenant {resolver.tenant_id}")
                return ""
            return f"https://app.hubspot.com/contacts/{portal_id}/record/0-1/{contact_id}"
        return ""


class HubspotTicketCitationResolver(BaseCitationResolver[HubspotTicketDocumentMetadata]):
    """Resolver for HubSpot ticket citations."""

    async def resolve_citation(
        self,
        document: DocumentWithSourceAndMetadata[HubspotTicketDocumentMetadata],
        excerpt: str,
        resolver: CitationResolver,
    ) -> str:
        ticket_id = document.metadata["ticket_id"]
        if ticket_id:
            portal_id = await get_hubspot_portal_id(resolver.tenant_id)
            if not portal_id:
                logger.error(f"No portal ID found for tenant {resolver.tenant_id}")
                return ""
            return f"https://app.hubspot.com/contacts/{portal_id}/record/0-5/{ticket_id}"

        return ""
