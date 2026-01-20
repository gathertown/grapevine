"""HubSpot citation resolvers."""

from __future__ import annotations

from typing import TYPE_CHECKING

from connectors.base import BaseCitationResolver
from connectors.base.document_source import DocumentWithSourceAndMetadata
from connectors.zendesk.transformers.zendesk_ticket_document import ZendeskTicketDocumentMetadata
from src.utils.logging import get_logger

if TYPE_CHECKING:
    from src.mcp.api.citation_resolver import CitationResolver

logger = get_logger(__name__)


def get_zendesk_agent_ticket_url(subdomain: str, ticket_id: int) -> str:
    return f"https://{subdomain}.zendesk.com/agent/tickets/{ticket_id}"


class ZendeskTicketCitationResolver(BaseCitationResolver[ZendeskTicketDocumentMetadata]):
    async def resolve_citation(
        self,
        document: DocumentWithSourceAndMetadata[ZendeskTicketDocumentMetadata],
        excerpt: str,
        resolver: CitationResolver,
    ) -> str:
        ticket_id = document.metadata["ticket_id"]
        subdomain = document.metadata["ticket_subdomain"]

        return get_zendesk_agent_ticket_url(subdomain, ticket_id)
