"""Monday.com connector for Grapevine.

Indexes Monday.com boards, items (tasks), and updates (comments).
"""

# Client exports
from connectors.monday.client import (
    MondayBoard,
    MondayClient,
    MondayItem,
    get_monday_client_for_tenant,
)

# Extractor and artifact exports
from connectors.monday.extractors import (
    MondayBackfillRootExtractor,
    MondayBoardInfo,
    MondayBoardKind,
    MondayColumnValue,
    MondayFullBackfillExtractor,
    MondayGroup,
    MondayIncrementalBackfillConfig,
    MondayIncrementalBackfillExtractor,
    MondayItemArtifact,
    MondayItemArtifactContent,
    MondayItemArtifactMetadata,
    MondayItemBackfillExtractor,
    MondayItemBatchBackfiller,
    MondayItemState,
    MondayUpdate,
    MondayUser,
    MondayWorkspaceInfo,
)

# Other exports
from connectors.monday.monday_citation_resolver import (
    MondayCitationResolver,
    monday_citation_resolver,
)

# Job config exports
from connectors.monday.monday_job_models import (
    MondayBackfillRootConfig,
    MondayBoardBackfillConfig,
    MondayItemBackfillConfig,
)
from connectors.monday.monday_pruner import MondayPruner
from connectors.monday.monday_sync_service import MondaySyncService

# Transformer and document exports
from connectors.monday.transformers import (
    MondayItemChunk,
    MondayItemChunkMetadata,
    MondayItemDocument,
    MondayItemDocumentMetadata,
    MondayItemTransformer,
)

__all__ = [
    # Client
    "MondayClient",
    "MondayBoard",
    "MondayItem",
    "get_monday_client_for_tenant",
    # Artifact types
    "MondayItemArtifact",
    "MondayItemArtifactContent",
    "MondayItemArtifactMetadata",
    "MondayBoardInfo",
    "MondayWorkspaceInfo",
    "MondayGroup",
    "MondayColumnValue",
    "MondayUpdate",
    "MondayUser",
    "MondayItemState",
    "MondayBoardKind",
    # Config classes
    "MondayBackfillRootConfig",
    "MondayBoardBackfillConfig",
    "MondayItemBackfillConfig",
    "MondayIncrementalBackfillConfig",
    # Extractors
    "MondayBackfillRootExtractor",
    "MondayFullBackfillExtractor",
    "MondayIncrementalBackfillExtractor",
    "MondayItemBackfillExtractor",
    "MondayItemBatchBackfiller",
    # Transformers
    "MondayItemTransformer",
    # Document types
    "MondayItemDocument",
    "MondayItemChunk",
    "MondayItemDocumentMetadata",
    "MondayItemChunkMetadata",
    # Citation resolver
    "MondayCitationResolver",
    "monday_citation_resolver",
    # Pruner
    "MondayPruner",
    # Sync service
    "MondaySyncService",
]
