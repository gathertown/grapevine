# ruff: isort: skip_file
# Import order is intentional to avoid circular imports

# Import constants from artifacts file
from connectors.hubspot.hubspot_artifacts import (
    HUBSPOT_ACTIVITY_ALL_PROPERTIES,
    HUBSPOT_ACTIVITY_PROPERTY_NAMES,
    HUBSPOT_COMPANY_PROPERTIES,
    HUBSPOT_CONTACT_PROPERTIES,
    HUBSPOT_DEAL_PROPERTIES,
    HUBSPOT_TICKET_PROPERTIES,
)

# Artifacts
from connectors.hubspot.hubspot_artifacts import (
    HubspotCompanyArtifact,
    HubspotContactArtifact,
    HubspotDealActivityArtifact,
    HubspotDealArtifact,
    HubspotTicketArtifact,
)

# Transformers
# Documents
from connectors.hubspot.hubspot_company_document import (
    HubspotCompanyChunk,
    HubspotCompanyChunkMetadata,
    HubspotCompanyDocument,
    HubspotCompanyDocumentMetadata,
)
from connectors.hubspot.hubspot_contact_document import (
    HubspotContactChunk,
    HubspotContactChunkMetadata,
    HubspotContactDocument,
    HubspotContactDocumentMetadata,
)
from connectors.hubspot.hubspot_deal_document import HubspotDealDocument
from connectors.hubspot.hubspot_deal_v2_document import (
    HubspotDealChunkMetadata,
    HubspotDealDocument as HubspotDealDocumentV2,
    HubspotDealDocumentMetadata,
)
from connectors.hubspot.hubspot_ticket_document import (
    HubspotTicketChunk,
    HubspotTicketChunkMetadata,
    HubspotTicketDocument,
    HubspotTicketDocumentMetadata,
)
from connectors.hubspot.hubspot_company_transformer import HubSpotCompanyTransformer
from connectors.hubspot.hubspot_contact_transformer import HubSpotContactTransformer
from connectors.hubspot.hubspot_deal_transformer import HubSpotDealTransformer
from connectors.hubspot.hubspot_ticket_transformer import HubSpotTicketTransformer

# Extractors - import base and simple extractors first
from connectors.hubspot.hubspot_backfill_root_extractor import HubSpotBackfillRootExtractor
from connectors.hubspot.hubspot_base import HubSpotExtractor
from connectors.hubspot.hubspot_company_backfill_extractor import HubSpotCompanyBackfillExtractor
from connectors.hubspot.hubspot_contact_backfill_extractor import HubSpotContactBackfillExtractor
from connectors.hubspot.hubspot_deal_backfill_extractor import HubSpotDealBackfillExtractor
from connectors.hubspot.hubspot_ticket_backfill_extractor import HubSpotTicketBackfillExtractor

# Import modules that depend on the package last to avoid circular imports
from connectors.hubspot.hubspot_object_sync_extractor import HubSpotObjectSyncExtractor
from connectors.hubspot.hubspot_webhook_extractor import HubSpotWebhookExtractor


# Pruners
from connectors.hubspot.hubspot_pruner import HubspotPruner, hubspot_pruner

# Citation Resolvers
from connectors.hubspot.hubspot_citation_resolver import (
    HubspotCompanyCitationResolver,
    HubspotContactCitationResolver,
    HubspotDealCitationResolver,
    HubspotTicketCitationResolver,
)

# Webhook Handlers
from connectors.hubspot.hubspot_webhook_handler import (
    HubSpotWebhookVerifier,
    deduplicate_hubspot_events,
    extract_hubspot_webhook_metadata,
    verify_hubspot_webhook,
)

__all__ = [
    # Constants
    "HUBSPOT_COMPANY_PROPERTIES",
    "HUBSPOT_CONTACT_PROPERTIES",
    "HUBSPOT_DEAL_PROPERTIES",
    "HUBSPOT_TICKET_PROPERTIES",
    "HUBSPOT_ACTIVITY_ALL_PROPERTIES",
    "HUBSPOT_ACTIVITY_PROPERTY_NAMES",
    # Artifacts
    "HubspotCompanyArtifact",
    "HubspotTicketArtifact",
    "HubspotDealArtifact",
    "HubspotDealActivityArtifact",
    "HubspotContactArtifact",
    # Citation Resolvers
    "HubspotCompanyCitationResolver",
    "HubspotContactCitationResolver",
    "HubspotDealCitationResolver",
    "HubspotTicketCitationResolver",
    # Documents
    "HubspotCompanyDocument",
    "HubspotCompanyDocumentMetadata",
    "HubspotCompanyChunk",
    "HubspotCompanyChunkMetadata",
    "HubspotContactDocument",
    "HubspotContactDocumentMetadata",
    "HubspotContactChunk",
    "HubspotContactChunkMetadata",
    "HubspotDealDocument",
    "HubspotDealDocumentV2",
    "HubspotDealDocumentMetadata",
    "HubspotDealChunkMetadata",
    "HubspotTicketDocument",
    "HubspotTicketDocumentMetadata",
    "HubspotTicketChunk",
    "HubspotTicketChunkMetadata",
    # Transformers
    "HubSpotCompanyTransformer",
    "HubSpotContactTransformer",
    "HubSpotDealTransformer",
    "HubSpotTicketTransformer",
    # Extractors
    "HubSpotExtractor",
    "HubSpotBackfillRootExtractor",
    "HubSpotCompanyBackfillExtractor",
    "HubSpotContactBackfillExtractor",
    "HubSpotDealBackfillExtractor",
    "HubSpotTicketBackfillExtractor",
    "HubSpotWebhookExtractor",
    "HubSpotObjectSyncExtractor",
    # Pruners
    "HubspotPruner",
    "hubspot_pruner",
    # Webhook Handlers
    "HubSpotWebhookVerifier",
    "verify_hubspot_webhook",
    "deduplicate_hubspot_events",
    "extract_hubspot_webhook_metadata",
]
