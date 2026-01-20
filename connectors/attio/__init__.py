"""Attio CRM connector for ingesting companies, people, and deals.

Note: Unlike HubSpot, Attio's API returns all attributes by default,
so we don't need attribute lists for API calls.
"""

from connectors.attio.attio_artifacts import (
    ATTIO_OBJECT_TYPES,
    AttioCompanyArtifact,
    AttioCompanyArtifactContent,
    AttioCompanyArtifactMetadata,
    AttioDealArtifact,
    AttioDealArtifactContent,
    AttioDealArtifactMetadata,
    AttioNoteArtifact,
    AttioNoteArtifactContent,
    AttioNoteArtifactMetadata,
    AttioObjectType,
    AttioPersonArtifact,
    AttioPersonArtifactContent,
    AttioPersonArtifactMetadata,
    AttioTaskArtifact,
    AttioTaskArtifactContent,
    AttioTaskArtifactMetadata,
    AttioWebhookAction,
    AttioWebhookEntityType,
)
from connectors.attio.attio_backfill_root_extractor import AttioBackfillRootExtractor
from connectors.attio.attio_citation_resolver import (
    AttioCompanyCitationResolver,
    AttioDealCitationResolver,
    AttioPersonCitationResolver,
)
from connectors.attio.attio_company_backfill_extractor import AttioCompanyBackfillExtractor
from connectors.attio.attio_company_document import (
    AttioCompanyChunk,
    AttioCompanyChunkMetadata,
    AttioCompanyDocument,
    AttioCompanyDocumentMetadata,
)
from connectors.attio.attio_company_transformer import AttioCompanyTransformer
from connectors.attio.attio_deal_backfill_extractor import AttioDealBackfillExtractor
from connectors.attio.attio_deal_document import (
    AttioDealActivityChunk,
    AttioDealChunkMetadata,
    AttioDealDocument,
    AttioDealDocumentMetadata,
)
from connectors.attio.attio_deal_transformer import AttioDealTransformer
from connectors.attio.attio_models import (
    AttioBackfillRootConfig,
    AttioCompanyBackfillConfig,
    AttioDealBackfillConfig,
    AttioPersonBackfillConfig,
)
from connectors.attio.attio_person_backfill_extractor import AttioPersonBackfillExtractor
from connectors.attio.attio_person_document import (
    AttioPersonChunk,
    AttioPersonChunkMetadata,
    AttioPersonDocument,
    AttioPersonDocumentMetadata,
)
from connectors.attio.attio_person_transformer import AttioPersonTransformer
from connectors.attio.attio_pruner import AttioPruner, attio_pruner
from connectors.attio.attio_webhook_extractor import AttioWebhookExtractor
from connectors.attio.attio_webhook_handler import (
    AttioWebhookVerifier,
    extract_attio_webhook_metadata,
    extract_attio_workspace_id,
    verify_attio_webhook,
)
from connectors.base.base_ingest_artifact import (
    get_attio_company_entity_id,
    get_attio_deal_entity_id,
    get_attio_note_entity_id,
    get_attio_person_entity_id,
    get_attio_task_entity_id,
)

__all__ = [
    # Object type constants
    "AttioObjectType",
    "ATTIO_OBJECT_TYPES",
    # Webhook enums
    "AttioWebhookEntityType",
    "AttioWebhookAction",
    # Artifact entity ID helpers (from base_ingest_artifact)
    "get_attio_company_entity_id",
    "get_attio_person_entity_id",
    "get_attio_deal_entity_id",
    "get_attio_note_entity_id",
    "get_attio_task_entity_id",
    # Config classes
    "AttioBackfillRootConfig",
    "AttioCompanyBackfillConfig",
    "AttioPersonBackfillConfig",
    "AttioDealBackfillConfig",
    # Extractors
    "AttioBackfillRootExtractor",
    "AttioCompanyBackfillExtractor",
    "AttioPersonBackfillExtractor",
    "AttioDealBackfillExtractor",
    "AttioWebhookExtractor",
    # Transformers
    "AttioCompanyTransformer",
    "AttioPersonTransformer",
    "AttioDealTransformer",
    # Company artifact
    "AttioCompanyArtifact",
    "AttioCompanyArtifactContent",
    "AttioCompanyArtifactMetadata",
    # Person artifact
    "AttioPersonArtifact",
    "AttioPersonArtifactContent",
    "AttioPersonArtifactMetadata",
    # Deal artifact
    "AttioDealArtifact",
    "AttioDealArtifactContent",
    "AttioDealArtifactMetadata",
    # Note artifact
    "AttioNoteArtifact",
    "AttioNoteArtifactContent",
    "AttioNoteArtifactMetadata",
    # Task artifact
    "AttioTaskArtifact",
    "AttioTaskArtifactContent",
    "AttioTaskArtifactMetadata",
    # Company document
    "AttioCompanyDocument",
    "AttioCompanyChunk",
    "AttioCompanyDocumentMetadata",
    "AttioCompanyChunkMetadata",
    # Person document
    "AttioPersonDocument",
    "AttioPersonChunk",
    "AttioPersonDocumentMetadata",
    "AttioPersonChunkMetadata",
    # Deal document
    "AttioDealDocument",
    "AttioDealActivityChunk",
    "AttioDealDocumentMetadata",
    "AttioDealChunkMetadata",
    # Citation resolvers
    "AttioCompanyCitationResolver",
    "AttioPersonCitationResolver",
    "AttioDealCitationResolver",
    # Pruner
    "AttioPruner",
    "attio_pruner",
    # Webhook Handlers
    "AttioWebhookVerifier",
    "verify_attio_webhook",
    "extract_attio_workspace_id",
    "extract_attio_webhook_metadata",
]
