"""GitLab connector for MR and file ingestion."""

from connectors.gitlab.gitlab_artifacts import (
    GitLabApproval,
    GitLabDiff,
    GitLabMergeRequestData,
    GitLabMRApprovalEvent,
    GitLabMRArtifact,
    GitLabMRArtifactContent,
    GitLabMRArtifactMetadata,
    GitLabMRDocumentData,
    GitLabMREventBase,
    GitLabMRNoteEvent,
    GitLabNote,
    GitLabPipeline,
    GitLabUser,
)
from connectors.gitlab.gitlab_backfill_root_extractor import GitLabBackfillRootExtractor
from connectors.gitlab.gitlab_citation_resolver import (
    GitLabFileCitationResolver,
    GitLabMRCitationResolver,
)
from connectors.gitlab.gitlab_client import GitLabClient
from connectors.gitlab.gitlab_client_factory import get_gitlab_client_for_tenant
from connectors.gitlab.gitlab_file_artifacts import (
    GitLabFileArtifact,
    GitLabFileContent,
    GitLabFileContributor,
    GitLabFileMetadata,
)
from connectors.gitlab.gitlab_file_backfill_extractor import GitLabFileBackfillExtractor
from connectors.gitlab.gitlab_file_backfill_project_extractor import (
    GitLabFileBackfillProjectExtractor,
)
from connectors.gitlab.gitlab_file_document import (
    GitLabFileChunk,
    GitLabFileChunkMetadata,
    GitLabFileDocument,
    GitLabFileDocumentMetadata,
)
from connectors.gitlab.gitlab_file_incr_backfill_project_extractor import (
    GitLabFileIncrBackfillProjectExtractor,
)
from connectors.gitlab.gitlab_file_transformer import GitLabFileTransformer
from connectors.gitlab.gitlab_incr_backfill_extractor import GitLabIncrBackfillRootExtractor
from connectors.gitlab.gitlab_merge_request_document import (
    GitLabMRChunk,
    GitLabMRChunkMetadata,
    GitLabMRDiffChunk,
    GitLabMRDiffChunkMetadata,
    GitLabMRDocument,
    GitLabMRDocumentMetadata,
)
from connectors.gitlab.gitlab_models import (
    GitLabBackfillRootConfig,
    GitLabFileBackfillConfig,
    GitLabFileBackfillProjectConfig,
    GitLabFileBatch,
    GitLabFileIncrBackfillProjectConfig,
    GitLabIncrBackfillConfig,
    GitLabMRBackfillConfig,
    GitLabMRBackfillProjectConfig,
    GitLabMRBatch,
    GitLabMRIncrBackfillProjectConfig,
)
from connectors.gitlab.gitlab_mr_backfill_extractor import GitLabMRBackfillExtractor
from connectors.gitlab.gitlab_mr_backfill_project_extractor import (
    GitLabMRBackfillProjectExtractor,
)
from connectors.gitlab.gitlab_mr_incr_backfill_project_extractor import (
    GitLabMRIncrBackfillProjectExtractor,
)
from connectors.gitlab.gitlab_mr_transformer import GitLabMRTransformer
from connectors.gitlab.gitlab_sync_service import GitLabSyncService
from connectors.gitlab.gitlab_utils import (
    normalize_approvals,
    normalize_diffs,
    normalize_mr_data,
    normalize_notes,
    normalize_pipeline,
    normalize_user,
)

__all__ = [
    # MR Artifacts
    "GitLabApproval",
    "GitLabDiff",
    "GitLabMergeRequestData",
    "GitLabMRArtifact",
    "GitLabMRArtifactContent",
    "GitLabMRArtifactMetadata",
    "GitLabMRApprovalEvent",
    "GitLabMRDocumentData",
    "GitLabMREventBase",
    "GitLabMRNoteEvent",
    "GitLabNote",
    "GitLabPipeline",
    "GitLabUser",
    # File Artifacts
    "GitLabFileArtifact",
    "GitLabFileContent",
    "GitLabFileContributor",
    "GitLabFileMetadata",
    # Citation Resolvers
    "GitLabFileCitationResolver",
    "GitLabMRCitationResolver",
    # Client
    "GitLabClient",
    "get_gitlab_client_for_tenant",
    # MR Documents
    "GitLabMRChunk",
    "GitLabMRChunkMetadata",
    "GitLabMRDiffChunk",
    "GitLabMRDiffChunkMetadata",
    "GitLabMRDocument",
    "GitLabMRDocumentMetadata",
    # File Documents
    "GitLabFileChunk",
    "GitLabFileChunkMetadata",
    "GitLabFileDocument",
    "GitLabFileDocumentMetadata",
    # Models
    "GitLabBackfillRootConfig",
    "GitLabFileBatch",
    "GitLabFileBackfillConfig",
    "GitLabFileBackfillProjectConfig",
    "GitLabFileIncrBackfillProjectConfig",
    "GitLabIncrBackfillConfig",
    "GitLabMRBackfillConfig",
    "GitLabMRBackfillProjectConfig",
    "GitLabMRBatch",
    "GitLabMRIncrBackfillProjectConfig",
    # Extractors (Full Backfill)
    "GitLabBackfillRootExtractor",
    "GitLabFileBackfillExtractor",
    "GitLabFileBackfillProjectExtractor",
    "GitLabMRBackfillExtractor",
    "GitLabMRBackfillProjectExtractor",
    # Extractors (Incremental Backfill)
    "GitLabIncrBackfillRootExtractor",
    "GitLabFileIncrBackfillProjectExtractor",
    "GitLabMRIncrBackfillProjectExtractor",
    # Sync Service
    "GitLabSyncService",
    # Transformers
    "GitLabFileTransformer",
    "GitLabMRTransformer",
    # Utils
    "normalize_approvals",
    "normalize_diffs",
    "normalize_mr_data",
    "normalize_notes",
    "normalize_pipeline",
    "normalize_user",
]
