"""Tests for PostHog pruner functionality."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from connectors.posthog.posthog_pruner import (
    POSTHOG_ANNOTATION_DOC_ID_PREFIX,
    POSTHOG_DASHBOARD_DOC_ID_PREFIX,
    POSTHOG_EXPERIMENT_DOC_ID_PREFIX,
    POSTHOG_FEATURE_FLAG_DOC_ID_PREFIX,
    POSTHOG_INSIGHT_DOC_ID_PREFIX,
    POSTHOG_SURVEY_DOC_ID_PREFIX,
    PostHogPruner,
    _extract_project_id_from_entity_id,
)

from .mock_utils import create_mock_db_pool


@pytest.fixture
def mock_db_pool_fixture():
    """Fixture for mock database pool."""
    return create_mock_db_pool()


@pytest.fixture
def mock_posthog_client():
    """Fixture for mock PostHog client."""
    client = MagicMock()
    client.get_projects = AsyncMock(return_value=[])
    client.get_dashboards = AsyncMock(return_value=[])
    client.get_insights = AsyncMock(return_value=[])
    client.get_feature_flags = AsyncMock(return_value=[])
    client.get_annotations = AsyncMock(return_value=[])
    client.get_experiments = AsyncMock(return_value=[])
    client.get_surveys = AsyncMock(return_value=[])
    client.close = AsyncMock()
    return client


class TestPostHogPrunerSingleton:
    """Test singleton pattern."""

    def test_singleton_pattern(self):
        """Test that PostHogPruner follows singleton pattern."""
        pruner1 = PostHogPruner()
        pruner2 = PostHogPruner()
        assert pruner1 is pruner2


class TestPostHogPrunerHelpers:
    """Test helper functions."""

    def test_extract_project_id_dashboard(self):
        """Test extracting project ID from dashboard entity ID."""
        entity_id = "posthog_dashboard_123_456"
        project_id = _extract_project_id_from_entity_id(entity_id, POSTHOG_DASHBOARD_DOC_ID_PREFIX)
        assert project_id == 123

    def test_extract_project_id_insight(self):
        """Test extracting project ID from insight entity ID."""
        entity_id = "posthog_insight_789_101"
        project_id = _extract_project_id_from_entity_id(entity_id, POSTHOG_INSIGHT_DOC_ID_PREFIX)
        assert project_id == 789

    def test_extract_project_id_feature_flag(self):
        """Test extracting project ID from feature flag entity ID."""
        entity_id = "posthog_feature_flag_111_222"
        project_id = _extract_project_id_from_entity_id(
            entity_id, POSTHOG_FEATURE_FLAG_DOC_ID_PREFIX
        )
        assert project_id == 111

    def test_extract_project_id_invalid_format(self):
        """Test extracting project ID from invalid entity ID."""
        entity_id = "invalid_format"
        project_id = _extract_project_id_from_entity_id(entity_id, POSTHOG_DASHBOARD_DOC_ID_PREFIX)
        assert project_id is None

    def test_extract_project_id_non_numeric(self):
        """Test extracting project ID from non-numeric entity ID."""
        entity_id = "posthog_dashboard_abc_456"
        project_id = _extract_project_id_from_entity_id(entity_id, POSTHOG_DASHBOARD_DOC_ID_PREFIX)
        assert project_id is None

    def test_doc_id_prefix_constants(self):
        """Test that doc ID prefixes are correct."""
        assert POSTHOG_DASHBOARD_DOC_ID_PREFIX == "posthog_dashboard_"
        assert POSTHOG_INSIGHT_DOC_ID_PREFIX == "posthog_insight_"
        assert POSTHOG_FEATURE_FLAG_DOC_ID_PREFIX == "posthog_feature_flag_"
        assert POSTHOG_ANNOTATION_DOC_ID_PREFIX == "posthog_annotation_"
        assert POSTHOG_EXPERIMENT_DOC_ID_PREFIX == "posthog_experiment_"
        assert POSTHOG_SURVEY_DOC_ID_PREFIX == "posthog_survey_"


class TestPostHogPrunerFindStaleDocuments:
    """Test suite for find_stale_documents functionality."""

    @pytest.mark.asyncio
    async def test_find_stale_documents_no_indexed_documents(
        self, mock_db_pool_fixture, mock_posthog_client
    ):
        """Test find_stale_documents with no indexed documents."""
        pool, conn = mock_db_pool_fixture
        conn.fetch = AsyncMock(return_value=[])

        mock_sync_service = MagicMock()
        mock_sync_service.get_selected_project_ids = AsyncMock(return_value=[1])

        with (
            patch(
                "connectors.posthog.posthog_pruner.get_posthog_client_for_tenant",
                new=AsyncMock(return_value=mock_posthog_client),
            ),
            patch(
                "connectors.posthog.posthog_pruner.PostHogSyncService",
                return_value=mock_sync_service,
            ),
        ):
            pruner = PostHogPruner()
            result = await pruner.find_stale_documents(
                tenant_id="tenant123",
                db_pool=pool,
            )

        assert result == []
        mock_posthog_client.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_find_stale_dashboards(self, mock_db_pool_fixture, mock_posthog_client):
        """Test finding stale dashboards."""
        pool, conn = mock_db_pool_fixture

        # Setup: 3 indexed dashboards, API returns only 1
        conn.fetch = AsyncMock(
            side_effect=[
                # Dashboards
                [
                    {"id": "posthog_dashboard_1_100"},
                    {"id": "posthog_dashboard_1_200"},
                    {"id": "posthog_dashboard_1_300"},
                ],
                # Other entity types return empty
                [],
                [],
                [],
                [],
                [],
            ]
        )

        # API returns only dashboard 100 for project 1
        mock_dashboard = MagicMock()
        mock_dashboard.id = 100
        mock_posthog_client.get_dashboards = AsyncMock(return_value=[mock_dashboard])

        mock_sync_service = MagicMock()
        mock_sync_service.get_selected_project_ids = AsyncMock(return_value=[1])

        with (
            patch(
                "connectors.posthog.posthog_pruner.get_posthog_client_for_tenant",
                new=AsyncMock(return_value=mock_posthog_client),
            ),
            patch(
                "connectors.posthog.posthog_pruner.PostHogSyncService",
                return_value=mock_sync_service,
            ),
        ):
            pruner = PostHogPruner()
            result = await pruner.find_stale_documents(
                tenant_id="tenant123",
                db_pool=pool,
            )

        # Dashboards 200 and 300 should be stale
        assert len(result) == 2
        assert "posthog_dashboard_1_200" in result
        assert "posthog_dashboard_1_300" in result
        assert "posthog_dashboard_1_100" not in result

    @pytest.mark.asyncio
    async def test_find_stale_insights(self, mock_db_pool_fixture, mock_posthog_client):
        """Test finding stale insights."""
        pool, conn = mock_db_pool_fixture

        conn.fetch = AsyncMock(
            side_effect=[
                [],  # dashboards
                [
                    {"id": "posthog_insight_1_100"},
                    {"id": "posthog_insight_1_200"},
                ],
                [],  # feature flags
                [],  # annotations
                [],  # experiments
                [],  # surveys
            ]
        )

        # API returns only insight 100
        mock_insight = MagicMock()
        mock_insight.id = 100
        mock_posthog_client.get_insights = AsyncMock(return_value=[mock_insight])

        mock_sync_service = MagicMock()
        mock_sync_service.get_selected_project_ids = AsyncMock(return_value=[1])

        with (
            patch(
                "connectors.posthog.posthog_pruner.get_posthog_client_for_tenant",
                new=AsyncMock(return_value=mock_posthog_client),
            ),
            patch(
                "connectors.posthog.posthog_pruner.PostHogSyncService",
                return_value=mock_sync_service,
            ),
        ):
            pruner = PostHogPruner()
            result = await pruner.find_stale_documents(
                tenant_id="tenant123",
                db_pool=pool,
            )

        assert len(result) == 1
        assert "posthog_insight_1_200" in result

    @pytest.mark.asyncio
    async def test_find_stale_feature_flags(self, mock_db_pool_fixture, mock_posthog_client):
        """Test finding stale feature flags."""
        pool, conn = mock_db_pool_fixture

        conn.fetch = AsyncMock(
            side_effect=[
                [],  # dashboards
                [],  # insights
                [
                    {"id": "posthog_feature_flag_1_100"},
                    {"id": "posthog_feature_flag_1_200"},
                ],
                [],  # annotations
                [],  # experiments
                [],  # surveys
            ]
        )

        # API returns only flag 100
        mock_flag = MagicMock()
        mock_flag.id = 100
        mock_posthog_client.get_feature_flags = AsyncMock(return_value=[mock_flag])

        mock_sync_service = MagicMock()
        mock_sync_service.get_selected_project_ids = AsyncMock(return_value=[1])

        with (
            patch(
                "connectors.posthog.posthog_pruner.get_posthog_client_for_tenant",
                new=AsyncMock(return_value=mock_posthog_client),
            ),
            patch(
                "connectors.posthog.posthog_pruner.PostHogSyncService",
                return_value=mock_sync_service,
            ),
        ):
            pruner = PostHogPruner()
            result = await pruner.find_stale_documents(
                tenant_id="tenant123",
                db_pool=pool,
            )

        assert len(result) == 1
        assert "posthog_feature_flag_1_200" in result

    @pytest.mark.asyncio
    async def test_find_stale_documents_handles_client_error(self, mock_db_pool_fixture):
        """Test find_stale_documents handles client creation error."""
        pool, _ = mock_db_pool_fixture

        with patch(
            "connectors.posthog.posthog_pruner.get_posthog_client_for_tenant",
            new=AsyncMock(side_effect=Exception("API error")),
        ):
            pruner = PostHogPruner()
            result = await pruner.find_stale_documents(
                tenant_id="tenant123",
                db_pool=pool,
            )

        assert result == []

    @pytest.mark.asyncio
    async def test_find_stale_documents_skips_failed_projects(
        self, mock_db_pool_fixture, mock_posthog_client
    ):
        """Test that documents from failed project API calls are not marked stale."""
        pool, conn = mock_db_pool_fixture

        # Two projects indexed
        conn.fetch = AsyncMock(
            side_effect=[
                [
                    {"id": "posthog_dashboard_1_100"},  # Project 1
                    {"id": "posthog_dashboard_2_200"},  # Project 2
                ],
                [],
                [],
                [],
                [],
                [],
            ]
        )

        # Project 1 succeeds, Project 2 fails
        async def mock_get_dashboards(project_id):
            if project_id == 1:
                mock_dashboard = MagicMock()
                mock_dashboard.id = 100
                return [mock_dashboard]
            else:
                raise Exception("API error for project 2")

        mock_posthog_client.get_dashboards = AsyncMock(side_effect=mock_get_dashboards)

        mock_sync_service = MagicMock()
        mock_sync_service.get_selected_project_ids = AsyncMock(return_value=[1, 2])

        with (
            patch(
                "connectors.posthog.posthog_pruner.get_posthog_client_for_tenant",
                new=AsyncMock(return_value=mock_posthog_client),
            ),
            patch(
                "connectors.posthog.posthog_pruner.PostHogSyncService",
                return_value=mock_sync_service,
            ),
        ):
            pruner = PostHogPruner()
            result = await pruner.find_stale_documents(
                tenant_id="tenant123",
                db_pool=pool,
            )

        # Only project 1 dashboard should be checked, project 2 docs skipped
        # Dashboard 100 exists, so no stale docs from project 1
        # Dashboard 200 from project 2 is NOT marked stale because API failed
        assert result == []

    @pytest.mark.asyncio
    async def test_find_stale_surveys(self, mock_db_pool_fixture, mock_posthog_client):
        """Test finding stale surveys."""
        pool, conn = mock_db_pool_fixture

        conn.fetch = AsyncMock(
            side_effect=[
                [],  # dashboards
                [],  # insights
                [],  # feature flags
                [],  # annotations
                [],  # experiments
                [
                    {"id": "posthog_survey_1_100"},
                    {"id": "posthog_survey_1_200"},
                ],
            ]
        )

        # API returns only survey 100
        mock_survey = MagicMock()
        mock_survey.id = 100
        mock_posthog_client.get_surveys = AsyncMock(return_value=[mock_survey])

        mock_sync_service = MagicMock()
        mock_sync_service.get_selected_project_ids = AsyncMock(return_value=[1])

        with (
            patch(
                "connectors.posthog.posthog_pruner.get_posthog_client_for_tenant",
                new=AsyncMock(return_value=mock_posthog_client),
            ),
            patch(
                "connectors.posthog.posthog_pruner.PostHogSyncService",
                return_value=mock_sync_service,
            ),
        ):
            pruner = PostHogPruner()
            result = await pruner.find_stale_documents(
                tenant_id="tenant123",
                db_pool=pool,
            )

        assert len(result) == 1
        assert "posthog_survey_1_200" in result

    @pytest.mark.asyncio
    async def test_find_stale_experiments(self, mock_db_pool_fixture, mock_posthog_client):
        """Test finding stale experiments."""
        pool, conn = mock_db_pool_fixture

        conn.fetch = AsyncMock(
            side_effect=[
                [],  # dashboards
                [],  # insights
                [],  # feature flags
                [],  # annotations
                [
                    {"id": "posthog_experiment_1_100"},
                    {"id": "posthog_experiment_1_200"},
                ],
                [],  # surveys
            ]
        )

        # API returns only experiment 100
        mock_experiment = MagicMock()
        mock_experiment.id = 100
        mock_posthog_client.get_experiments = AsyncMock(return_value=[mock_experiment])

        mock_sync_service = MagicMock()
        mock_sync_service.get_selected_project_ids = AsyncMock(return_value=[1])

        with (
            patch(
                "connectors.posthog.posthog_pruner.get_posthog_client_for_tenant",
                new=AsyncMock(return_value=mock_posthog_client),
            ),
            patch(
                "connectors.posthog.posthog_pruner.PostHogSyncService",
                return_value=mock_sync_service,
            ),
        ):
            pruner = PostHogPruner()
            result = await pruner.find_stale_documents(
                tenant_id="tenant123",
                db_pool=pool,
            )

        assert len(result) == 1
        assert "posthog_experiment_1_200" in result

    @pytest.mark.asyncio
    async def test_find_stale_documents_empty_projects_aborts(
        self, mock_db_pool_fixture, mock_posthog_client
    ):
        """Test that staleness check aborts when no projects are found (safety guard)."""
        pool, _ = mock_db_pool_fixture

        # No selected projects and API returns empty
        mock_posthog_client.get_projects = AsyncMock(return_value=[])

        mock_sync_service = MagicMock()
        mock_sync_service.get_selected_project_ids = AsyncMock(return_value=[])

        with (
            patch(
                "connectors.posthog.posthog_pruner.get_posthog_client_for_tenant",
                new=AsyncMock(return_value=mock_posthog_client),
            ),
            patch(
                "connectors.posthog.posthog_pruner.PostHogSyncService",
                return_value=mock_sync_service,
            ),
        ):
            pruner = PostHogPruner()
            result = await pruner.find_stale_documents(
                tenant_id="tenant123",
                db_pool=pool,
            )

        # Safety guard: should return empty to prevent mass deletion
        assert result == []
        mock_posthog_client.close.assert_called_once()
