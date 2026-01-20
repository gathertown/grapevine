"""Figma connector module."""

from connectors.figma.client import (
    FigmaAPIError,
    FigmaClient,
    FigmaComment,
    FigmaFile,
    FigmaFileMetadata,
    FigmaProject,
    FigmaRateLimitInfo,
    FigmaUser,
    FigmaVersion,
    get_figma_client_for_tenant,
)
from connectors.figma.extractors import (
    FigmaBackfillRootExtractor,
    FigmaFileBackfillExtractor,
    FigmaIncrementalBackfillExtractor,
)
from connectors.figma.figma_citation_resolver import (
    FigmaCommentCitationResolver,
    FigmaFileCitationResolver,
)
from connectors.figma.figma_documents import (
    FigmaCommentChunk,
    FigmaCommentChunkMetadata,
    FigmaCommentDocument,
    FigmaCommentDocumentMetadata,
    FigmaFileChunk,
    FigmaFileChunkMetadata,
    FigmaFileDocument,
    FigmaFileDocumentMetadata,
)
from connectors.figma.figma_models import (
    FigmaBackfillRootConfig,
    FigmaCommentArtifact,
    FigmaCommentArtifactMetadata,
    FigmaFileArtifact,
    FigmaFileArtifactMetadata,
    FigmaFileBackfillConfig,
    FigmaIncrementalBackfillConfig,
    FigmaTeamBackfillConfig,
    get_figma_entity_id,
)
from connectors.figma.figma_pruner import (
    FigmaPruner,
    figma_pruner,
)
from connectors.figma.figma_sync_service import FigmaSyncService
from connectors.figma.figma_transformers import (
    FigmaCommentTransformer,
    FigmaFileTransformer,
)
from connectors.figma.figma_webhook_extractor import (
    FigmaWebhookConfig,
    FigmaWebhookExtractor,
)
from connectors.figma.figma_webhook_handler import (
    FigmaWebhookVerifier,
    extract_figma_team_id,
    extract_figma_webhook_metadata,
    verify_figma_webhook,
)

__all__ = [
    # Client
    "FigmaAPIError",
    "FigmaClient",
    "FigmaComment",
    "FigmaFile",
    "FigmaFileMetadata",
    "FigmaProject",
    "FigmaRateLimitInfo",
    "FigmaUser",
    "FigmaVersion",
    "get_figma_client_for_tenant",
    # Extractors
    "FigmaBackfillRootExtractor",
    "FigmaFileBackfillExtractor",
    "FigmaIncrementalBackfillExtractor",
    # Citation resolvers
    "FigmaCommentCitationResolver",
    "FigmaFileCitationResolver",
    # Documents
    "FigmaCommentChunk",
    "FigmaCommentChunkMetadata",
    "FigmaCommentDocument",
    "FigmaCommentDocumentMetadata",
    "FigmaFileChunk",
    "FigmaFileChunkMetadata",
    "FigmaFileDocument",
    "FigmaFileDocumentMetadata",
    # Artifacts and models
    "FigmaBackfillRootConfig",
    "FigmaCommentArtifact",
    "FigmaCommentArtifactMetadata",
    "FigmaFileArtifact",
    "FigmaFileArtifactMetadata",
    "FigmaFileBackfillConfig",
    "FigmaIncrementalBackfillConfig",
    "FigmaTeamBackfillConfig",
    "get_figma_entity_id",
    # Sync service
    "FigmaSyncService",
    # Transformers
    "FigmaCommentTransformer",
    "FigmaFileTransformer",
    # Webhook handler
    "FigmaWebhookVerifier",
    "extract_figma_team_id",
    "extract_figma_webhook_metadata",
    "verify_figma_webhook",
    # Webhook extractor
    "FigmaWebhookConfig",
    "FigmaWebhookExtractor",
    # Pruner
    "FigmaPruner",
    "figma_pruner",
]
