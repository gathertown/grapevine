"""PostHog citation resolvers for generating deep links to PostHog entities."""

from __future__ import annotations

from typing import TYPE_CHECKING

from connectors.base.base_citation_resolver import BaseCitationResolver
from connectors.base.document_source import DocumentWithSourceAndMetadata
from connectors.posthog.posthog_documents import (
    PostHogAnnotationDocumentMetadata,
    PostHogDashboardDocumentMetadata,
    PostHogExperimentDocumentMetadata,
    PostHogFeatureFlagDocumentMetadata,
    PostHogInsightDocumentMetadata,
    PostHogSurveyDocumentMetadata,
)
from src.utils.logging import get_logger
from src.utils.tenant_config import get_config_value_with_pool

if TYPE_CHECKING:
    from src.mcp.api.citation_resolver import CitationResolver

logger = get_logger(__name__)

# Config key for PostHog host URL
POSTHOG_HOST_CONFIG_KEY = "POSTHOG_HOST"
DEFAULT_POSTHOG_HOST = "https://us.posthog.com"


async def _get_posthog_host(resolver: CitationResolver) -> str:
    """Get the PostHog host URL from tenant config."""
    host = await get_config_value_with_pool(POSTHOG_HOST_CONFIG_KEY, resolver.db_pool)
    return (host or DEFAULT_POSTHOG_HOST).rstrip("/")


class PostHogDashboardCitationResolver(BaseCitationResolver[PostHogDashboardDocumentMetadata]):
    """Resolver for PostHog dashboard citations."""

    async def resolve_citation(
        self,
        document: DocumentWithSourceAndMetadata[PostHogDashboardDocumentMetadata],
        _excerpt: str,
        resolver: CitationResolver,
    ) -> str:
        """Generate PostHog dashboard URL.

        PostHog dashboard URLs follow the format:
        https://us.posthog.com/project/{project_id}/dashboard/{dashboard_id}
        """
        dashboard_id = document.metadata.get("dashboard_id")
        project_id = document.metadata.get("project_id")

        if not dashboard_id or not project_id:
            return ""

        host = await _get_posthog_host(resolver)
        return f"{host}/project/{project_id}/dashboard/{dashboard_id}"


class PostHogInsightCitationResolver(BaseCitationResolver[PostHogInsightDocumentMetadata]):
    """Resolver for PostHog insight citations."""

    async def resolve_citation(
        self,
        document: DocumentWithSourceAndMetadata[PostHogInsightDocumentMetadata],
        _excerpt: str,
        resolver: CitationResolver,
    ) -> str:
        """Generate PostHog insight URL.

        PostHog insight URLs follow the format:
        https://us.posthog.com/project/{project_id}/insights/{short_id}
        """
        short_id = document.metadata.get("short_id")
        project_id = document.metadata.get("project_id")

        if not short_id or not project_id:
            return ""

        host = await _get_posthog_host(resolver)
        return f"{host}/project/{project_id}/insights/{short_id}"


class PostHogFeatureFlagCitationResolver(BaseCitationResolver[PostHogFeatureFlagDocumentMetadata]):
    """Resolver for PostHog feature flag citations."""

    async def resolve_citation(
        self,
        document: DocumentWithSourceAndMetadata[PostHogFeatureFlagDocumentMetadata],
        _excerpt: str,
        resolver: CitationResolver,
    ) -> str:
        """Generate PostHog feature flag URL.

        PostHog feature flag URLs follow the format:
        https://us.posthog.com/project/{project_id}/feature_flags/{flag_id}
        """
        flag_id = document.metadata.get("flag_id")
        project_id = document.metadata.get("project_id")

        if not flag_id or not project_id:
            return ""

        host = await _get_posthog_host(resolver)
        return f"{host}/project/{project_id}/feature_flags/{flag_id}"


class PostHogAnnotationCitationResolver(BaseCitationResolver[PostHogAnnotationDocumentMetadata]):
    """Resolver for PostHog annotation citations."""

    async def resolve_citation(
        self,
        document: DocumentWithSourceAndMetadata[PostHogAnnotationDocumentMetadata],
        _excerpt: str,
        resolver: CitationResolver,
    ) -> str:
        """Generate PostHog annotation URL.

        PostHog annotations are accessed via the Data Management section:
        https://us.posthog.com/project/{project_id}/data-management/annotations
        """
        project_id = document.metadata.get("project_id")

        if not project_id:
            return ""

        host = await _get_posthog_host(resolver)
        return f"{host}/project/{project_id}/data-management/annotations"


class PostHogExperimentCitationResolver(BaseCitationResolver[PostHogExperimentDocumentMetadata]):
    """Resolver for PostHog experiment citations."""

    async def resolve_citation(
        self,
        document: DocumentWithSourceAndMetadata[PostHogExperimentDocumentMetadata],
        _excerpt: str,
        resolver: CitationResolver,
    ) -> str:
        """Generate PostHog experiment URL.

        PostHog experiment URLs follow the format:
        https://us.posthog.com/project/{project_id}/experiments/{experiment_id}
        """
        experiment_id = document.metadata.get("experiment_id")
        project_id = document.metadata.get("project_id")

        if not experiment_id or not project_id:
            return ""

        host = await _get_posthog_host(resolver)
        return f"{host}/project/{project_id}/experiments/{experiment_id}"


class PostHogSurveyCitationResolver(BaseCitationResolver[PostHogSurveyDocumentMetadata]):
    """Resolver for PostHog survey citations."""

    async def resolve_citation(
        self,
        document: DocumentWithSourceAndMetadata[PostHogSurveyDocumentMetadata],
        _excerpt: str,
        resolver: CitationResolver,
    ) -> str:
        """Generate PostHog survey URL.

        PostHog survey URLs follow the format:
        https://us.posthog.com/project/{project_id}/surveys/{survey_id}
        """
        survey_id = document.metadata.get("survey_id")
        project_id = document.metadata.get("project_id")

        if not survey_id or not project_id:
            return ""

        host = await _get_posthog_host(resolver)
        return f"{host}/project/{project_id}/surveys/{survey_id}"
