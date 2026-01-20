"""PostHog connector for ingesting analytics data."""

from connectors.posthog.posthog_citation_resolver import (
    PostHogAnnotationCitationResolver,
    PostHogDashboardCitationResolver,
    PostHogExperimentCitationResolver,
    PostHogFeatureFlagCitationResolver,
    PostHogInsightCitationResolver,
    PostHogSurveyCitationResolver,
)
from connectors.posthog.posthog_documents import (
    PostHogAnnotationDocument,
    PostHogAnnotationDocumentMetadata,
    PostHogDashboardDocument,
    PostHogDashboardDocumentMetadata,
    PostHogExperimentDocument,
    PostHogExperimentDocumentMetadata,
    PostHogFeatureFlagDocument,
    PostHogFeatureFlagDocumentMetadata,
    PostHogInsightDocument,
    PostHogInsightDocumentMetadata,
    PostHogSurveyDocument,
    PostHogSurveyDocumentMetadata,
)
from connectors.posthog.posthog_models import (
    PostHogAnnotationArtifact,
    PostHogBackfillRootConfig,
    PostHogDashboardArtifact,
    PostHogExperimentArtifact,
    PostHogFeatureFlagArtifact,
    PostHogIncrementalBackfillConfig,
    PostHogInsightArtifact,
    PostHogProjectBackfillConfig,
    PostHogSurveyArtifact,
)
from connectors.posthog.posthog_pruner import PostHogPruner
from connectors.posthog.posthog_transformers import (
    PostHogAnnotationTransformer,
    PostHogDashboardTransformer,
    PostHogExperimentTransformer,
    PostHogFeatureFlagTransformer,
    PostHogInsightTransformer,
    PostHogSurveyTransformer,
)

__all__ = [
    # Citation resolvers
    "PostHogAnnotationCitationResolver",
    "PostHogDashboardCitationResolver",
    "PostHogExperimentCitationResolver",
    "PostHogFeatureFlagCitationResolver",
    "PostHogInsightCitationResolver",
    "PostHogSurveyCitationResolver",
    # Documents and metadata
    "PostHogAnnotationDocument",
    "PostHogAnnotationDocumentMetadata",
    "PostHogDashboardDocument",
    "PostHogDashboardDocumentMetadata",
    "PostHogExperimentDocument",
    "PostHogExperimentDocumentMetadata",
    "PostHogFeatureFlagDocument",
    "PostHogFeatureFlagDocumentMetadata",
    "PostHogInsightDocument",
    "PostHogInsightDocumentMetadata",
    "PostHogSurveyDocument",
    "PostHogSurveyDocumentMetadata",
    # Artifacts
    "PostHogAnnotationArtifact",
    "PostHogDashboardArtifact",
    "PostHogExperimentArtifact",
    "PostHogFeatureFlagArtifact",
    "PostHogInsightArtifact",
    "PostHogSurveyArtifact",
    # Backfill configs
    "PostHogBackfillRootConfig",
    "PostHogIncrementalBackfillConfig",
    "PostHogProjectBackfillConfig",
    # Pruner
    "PostHogPruner",
    # Transformers
    "PostHogAnnotationTransformer",
    "PostHogDashboardTransformer",
    "PostHogExperimentTransformer",
    "PostHogFeatureFlagTransformer",
    "PostHogInsightTransformer",
    "PostHogSurveyTransformer",
]
