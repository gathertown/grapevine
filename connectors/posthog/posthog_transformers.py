"""
PostHog transformers for converting PostHog artifacts to documents.
"""

import logging

import asyncpg

from connectors.base import BaseTransformer
from connectors.base.document_source import DocumentSource
from connectors.posthog.posthog_documents import (
    PostHogAnnotationDocument,
    PostHogDashboardDocument,
    PostHogExperimentDocument,
    PostHogFeatureFlagDocument,
    PostHogInsightDocument,
    PostHogSurveyDocument,
)
from connectors.posthog.posthog_models import (
    PostHogAnnotationArtifact,
    PostHogDashboardArtifact,
    PostHogExperimentArtifact,
    PostHogFeatureFlagArtifact,
    PostHogInsightArtifact,
    PostHogSurveyArtifact,
)
from src.ingest.repositories.artifact_repository import ArtifactRepository
from src.utils.error_handling import ErrorCounter, record_exception_and_ignore

logger = logging.getLogger(__name__)


class PostHogDashboardTransformer(BaseTransformer[PostHogDashboardDocument]):
    """Transformer for PostHog dashboard artifacts."""

    def __init__(self):
        super().__init__(DocumentSource.POSTHOG_DASHBOARD)

    async def transform_artifacts(
        self, entity_ids: list[str], readonly_db_pool: asyncpg.Pool
    ) -> list[PostHogDashboardDocument]:
        """Transform PostHog dashboard artifacts into documents.

        Args:
            entity_ids: List of dashboard entity IDs to transform
            readonly_db_pool: Database connection pool

        Returns:
            List of PostHogDashboardDocument instances
        """
        repo = ArtifactRepository(readonly_db_pool)

        artifacts = await repo.get_artifacts_by_entity_ids(PostHogDashboardArtifact, entity_ids)

        logger.info(
            f"Loaded {len(artifacts)} PostHog dashboard artifacts for {len(entity_ids)} entity IDs"
        )

        documents = []
        counter: ErrorCounter = {}

        for artifact in artifacts:
            with record_exception_and_ignore(
                logger, f"Failed to transform PostHog dashboard artifact {artifact.id}", counter
            ):
                document = PostHogDashboardDocument.from_artifact(artifact)
                documents.append(document)

                if len(documents) % 100 == 0:
                    logger.info(f"Processed {len(documents)}/{len(artifacts)} dashboards")

        successful = counter.get("successful", 0)
        failed = counter.get("failed", 0)

        logger.info(
            f"PostHog dashboard transformation complete: {successful} successful, {failed} failed. "
            f"Created {len(documents)} documents from {len(artifacts)} artifacts"
        )

        return documents


class PostHogInsightTransformer(BaseTransformer[PostHogInsightDocument]):
    """Transformer for PostHog insight artifacts."""

    def __init__(self):
        super().__init__(DocumentSource.POSTHOG_INSIGHT)

    async def transform_artifacts(
        self, entity_ids: list[str], readonly_db_pool: asyncpg.Pool
    ) -> list[PostHogInsightDocument]:
        """Transform PostHog insight artifacts into documents.

        Args:
            entity_ids: List of insight entity IDs to transform
            readonly_db_pool: Database connection pool

        Returns:
            List of PostHogInsightDocument instances
        """
        repo = ArtifactRepository(readonly_db_pool)

        artifacts = await repo.get_artifacts_by_entity_ids(PostHogInsightArtifact, entity_ids)

        logger.info(
            f"Loaded {len(artifacts)} PostHog insight artifacts for {len(entity_ids)} entity IDs"
        )

        documents = []
        counter: ErrorCounter = {}

        for artifact in artifacts:
            with record_exception_and_ignore(
                logger, f"Failed to transform PostHog insight artifact {artifact.id}", counter
            ):
                document = PostHogInsightDocument.from_artifact(artifact)
                documents.append(document)

                if len(documents) % 100 == 0:
                    logger.info(f"Processed {len(documents)}/{len(artifacts)} insights")

        successful = counter.get("successful", 0)
        failed = counter.get("failed", 0)

        logger.info(
            f"PostHog insight transformation complete: {successful} successful, {failed} failed. "
            f"Created {len(documents)} documents from {len(artifacts)} artifacts"
        )

        return documents


class PostHogFeatureFlagTransformer(BaseTransformer[PostHogFeatureFlagDocument]):
    """Transformer for PostHog feature flag artifacts."""

    def __init__(self):
        super().__init__(DocumentSource.POSTHOG_FEATURE_FLAG)

    async def transform_artifacts(
        self, entity_ids: list[str], readonly_db_pool: asyncpg.Pool
    ) -> list[PostHogFeatureFlagDocument]:
        """Transform PostHog feature flag artifacts into documents.

        Args:
            entity_ids: List of feature flag entity IDs to transform
            readonly_db_pool: Database connection pool

        Returns:
            List of PostHogFeatureFlagDocument instances
        """
        repo = ArtifactRepository(readonly_db_pool)

        artifacts = await repo.get_artifacts_by_entity_ids(PostHogFeatureFlagArtifact, entity_ids)

        logger.info(
            f"Loaded {len(artifacts)} PostHog feature flag artifacts for {len(entity_ids)} entity IDs"
        )

        documents = []
        counter: ErrorCounter = {}

        for artifact in artifacts:
            with record_exception_and_ignore(
                logger,
                f"Failed to transform PostHog feature flag artifact {artifact.id}",
                counter,
            ):
                document = PostHogFeatureFlagDocument.from_artifact(artifact)
                documents.append(document)

                if len(documents) % 100 == 0:
                    logger.info(f"Processed {len(documents)}/{len(artifacts)} feature flags")

        successful = counter.get("successful", 0)
        failed = counter.get("failed", 0)

        logger.info(
            f"PostHog feature flag transformation complete: {successful} successful, {failed} failed. "
            f"Created {len(documents)} documents from {len(artifacts)} artifacts"
        )

        return documents


class PostHogAnnotationTransformer(BaseTransformer[PostHogAnnotationDocument]):
    """Transformer for PostHog annotation artifacts."""

    def __init__(self):
        super().__init__(DocumentSource.POSTHOG_ANNOTATION)

    async def transform_artifacts(
        self, entity_ids: list[str], readonly_db_pool: asyncpg.Pool
    ) -> list[PostHogAnnotationDocument]:
        """Transform PostHog annotation artifacts into documents.

        Args:
            entity_ids: List of annotation entity IDs to transform
            readonly_db_pool: Database connection pool

        Returns:
            List of PostHogAnnotationDocument instances
        """
        repo = ArtifactRepository(readonly_db_pool)

        artifacts = await repo.get_artifacts_by_entity_ids(PostHogAnnotationArtifact, entity_ids)

        logger.info(
            f"Loaded {len(artifacts)} PostHog annotation artifacts for {len(entity_ids)} entity IDs"
        )

        documents = []
        counter: ErrorCounter = {}

        for artifact in artifacts:
            with record_exception_and_ignore(
                logger,
                f"Failed to transform PostHog annotation artifact {artifact.id}",
                counter,
            ):
                document = PostHogAnnotationDocument.from_artifact(artifact)
                documents.append(document)

                if len(documents) % 100 == 0:
                    logger.info(f"Processed {len(documents)}/{len(artifacts)} annotations")

        successful = counter.get("successful", 0)
        failed = counter.get("failed", 0)

        logger.info(
            f"PostHog annotation transformation complete: {successful} successful, {failed} failed. "
            f"Created {len(documents)} documents from {len(artifacts)} artifacts"
        )

        return documents


class PostHogExperimentTransformer(BaseTransformer[PostHogExperimentDocument]):
    """Transformer for PostHog experiment artifacts."""

    def __init__(self):
        super().__init__(DocumentSource.POSTHOG_EXPERIMENT)

    async def transform_artifacts(
        self, entity_ids: list[str], readonly_db_pool: asyncpg.Pool
    ) -> list[PostHogExperimentDocument]:
        """Transform PostHog experiment artifacts into documents.

        Args:
            entity_ids: List of experiment entity IDs to transform
            readonly_db_pool: Database connection pool

        Returns:
            List of PostHogExperimentDocument instances
        """
        repo = ArtifactRepository(readonly_db_pool)

        artifacts = await repo.get_artifacts_by_entity_ids(PostHogExperimentArtifact, entity_ids)

        logger.info(
            f"Loaded {len(artifacts)} PostHog experiment artifacts for {len(entity_ids)} entity IDs"
        )

        documents = []
        counter: ErrorCounter = {}

        for artifact in artifacts:
            with record_exception_and_ignore(
                logger,
                f"Failed to transform PostHog experiment artifact {artifact.id}",
                counter,
            ):
                document = PostHogExperimentDocument.from_artifact(artifact)
                documents.append(document)

                if len(documents) % 100 == 0:
                    logger.info(f"Processed {len(documents)}/{len(artifacts)} experiments")

        successful = counter.get("successful", 0)
        failed = counter.get("failed", 0)

        logger.info(
            f"PostHog experiment transformation complete: {successful} successful, {failed} failed. "
            f"Created {len(documents)} documents from {len(artifacts)} artifacts"
        )

        return documents


class PostHogSurveyTransformer(BaseTransformer[PostHogSurveyDocument]):
    """Transformer for PostHog survey artifacts."""

    def __init__(self):
        super().__init__(DocumentSource.POSTHOG_SURVEY)

    async def transform_artifacts(
        self, entity_ids: list[str], readonly_db_pool: asyncpg.Pool
    ) -> list[PostHogSurveyDocument]:
        """Transform PostHog survey artifacts into documents.

        Args:
            entity_ids: List of survey entity IDs to transform
            readonly_db_pool: Database connection pool

        Returns:
            List of PostHogSurveyDocument instances
        """
        repo = ArtifactRepository(readonly_db_pool)

        artifacts = await repo.get_artifacts_by_entity_ids(PostHogSurveyArtifact, entity_ids)

        logger.info(
            f"Loaded {len(artifacts)} PostHog survey artifacts for {len(entity_ids)} entity IDs"
        )

        documents = []
        counter: ErrorCounter = {}

        for artifact in artifacts:
            with record_exception_and_ignore(
                logger,
                f"Failed to transform PostHog survey artifact {artifact.id}",
                counter,
            ):
                document = PostHogSurveyDocument.from_artifact(artifact)
                documents.append(document)

                if len(documents) % 100 == 0:
                    logger.info(f"Processed {len(documents)}/{len(artifacts)} surveys")

        successful = counter.get("successful", 0)
        failed = counter.get("failed", 0)

        logger.info(
            f"PostHog survey transformation complete: {successful} successful, {failed} failed. "
            f"Created {len(documents)} documents from {len(artifacts)} artifacts"
        )

        return documents
