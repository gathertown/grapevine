# Artifacts
from connectors.zendesk.extractors.zendesk_artifacts import (
    ZendeskBrandArtifact,
    ZendeskBrandArtifactMetadata,
    ZendeskCustomTicketStatusArtifact,
    ZendeskCustomTicketStatusArtifactMetadata,
    ZendeskGroupArtifact,
    ZendeskGroupArtifactMetadata,
    ZendeskOrganizationArtifact,
    ZendeskOrganizationArtifactMetadata,
    ZendeskTicketArtifact,
    ZendeskTicketArtifactMetadata,
    ZendeskTicketAuditArtifact,
    ZendeskTicketAuditArtifactMetadata,
    ZendeskTicketFieldArtifact,
    ZendeskTicketFieldArtifactMetadata,
    ZendeskTicketMetricsArtifact,
    ZendeskTicketMetricsArtifactMetadata,
    ZendeskUserArtifact,
    ZendeskUserArtifactMetadata,
    zendesk_brand_entity_id,
    zendesk_custom_status_entity_id,
    zendesk_group_entity_id,
    zendesk_organization_entity_id,
    zendesk_ticket_audit_entity_id,
    zendesk_ticket_entity_id,
    zendesk_ticket_field_entity_id,
    zendesk_ticket_metrics_entity_id,
    zendesk_user_entity_id,
)
from connectors.zendesk.extractors.zendesk_full_backfill_extractor import (
    ZendeskFullBackfillConfig,
    ZendeskFullBackfillExtractor,
)
from connectors.zendesk.extractors.zendesk_incremental_backfill_extractor import (
    ZendeskIncrementalBackfillConfig,
    ZendeskIncrementalBackfillExtractor,
)
from connectors.zendesk.extractors.zendesk_window_backfill_extractor import (
    ZendeskWindowBackfillConfig,
    ZendeskWindowBackfillExtractor,
)
from connectors.zendesk.extractors.zendesk_window_with_next_backfill_extractor import (
    ZendeskWindowWithNextBackfillConfig,
    ZendeskWindowWithNextBackfillExtractor,
)
from connectors.zendesk.transformers.zendesk_article_transformer import ZendeskArticleTransformer
from connectors.zendesk.transformers.zendesk_ticket_document import (
    ZendeskTicketChunkMetadata,
    ZendeskTicketDocument,
    ZendeskTicketDocumentMetadata,
)
from connectors.zendesk.transformers.zendesk_ticket_transformer import ZendeskTicketTransformer

# Documents
# Citation Resolvers
from connectors.zendesk.zendesk_citation_resolver import ZendeskTicketCitationResolver

__all__ = [
    # Artifacts
    "ZendeskTicketArtifact",
    "ZendeskTicketArtifactMetadata",
    "ZendeskBrandArtifact",
    "ZendeskBrandArtifactMetadata",
    "ZendeskOrganizationArtifact",
    "ZendeskOrganizationArtifactMetadata",
    "ZendeskGroupArtifact",
    "ZendeskGroupArtifactMetadata",
    "ZendeskUserArtifact",
    "ZendeskUserArtifactMetadata",
    "ZendeskTicketFieldArtifact",
    "ZendeskTicketFieldArtifactMetadata",
    "ZendeskCustomTicketStatusArtifact",
    "ZendeskCustomTicketStatusArtifactMetadata",
    "ZendeskTicketAuditArtifact",
    "ZendeskTicketAuditArtifactMetadata",
    "ZendeskTicketMetricsArtifact",
    "ZendeskTicketMetricsArtifactMetadata",
    # Entity ID functions
    "zendesk_ticket_entity_id",
    "zendesk_brand_entity_id",
    "zendesk_organization_entity_id",
    "zendesk_group_entity_id",
    "zendesk_user_entity_id",
    "zendesk_ticket_field_entity_id",
    "zendesk_custom_status_entity_id",
    "zendesk_ticket_audit_entity_id",
    "zendesk_ticket_metrics_entity_id",
    # Citation Resolvers
    "ZendeskTicketCitationResolver",
    # Documents
    "ZendeskTicketDocument",
    "ZendeskTicketDocumentMetadata",
    "ZendeskTicketChunkMetadata",
    # Transformers
    "ZendeskTicketTransformer",
    "ZendeskArticleTransformer",
    # Extractors
    "ZendeskFullBackfillExtractor",
    "ZendeskIncrementalBackfillExtractor",
    "ZendeskWindowBackfillExtractor",
    "ZendeskWindowWithNextBackfillExtractor",
    "ZendeskFullBackfillConfig",
    "ZendeskIncrementalBackfillConfig",
    "ZendeskWindowBackfillConfig",
    "ZendeskWindowWithNextBackfillConfig",
]
