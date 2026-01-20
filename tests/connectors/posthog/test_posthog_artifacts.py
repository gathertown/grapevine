"""Tests for PostHog artifact models."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from connectors.base.base_ingest_artifact import ArtifactEntity
from connectors.posthog.posthog_models import (
    PostHogAnnotationArtifact,
    PostHogDashboardArtifact,
    PostHogExperimentArtifact,
    PostHogFeatureFlagArtifact,
    PostHogInsightArtifact,
    PostHogSurveyArtifact,
)


@pytest.fixture
def job_id() -> UUID:
    """Create a test job ID."""
    return uuid4()


@pytest.fixture
def mock_dashboard_data():
    """Mock PostHog dashboard data from API."""
    return {
        "id": 123,
        "name": "Product Analytics",
        "description": "Main product metrics dashboard",
        "pinned": True,
        "is_shared": True,
        "created_at": "2024-01-15T10:00:00.000Z",
        "updated_at": "2024-02-20T15:30:00.000Z",
        "created_by": {"id": 1, "email": "user@example.com"},
        "tags": ["product", "metrics"],
        "tiles": [
            {"id": 1, "insight": {"id": 1, "name": "Daily Active Users"}},
            {"id": 2, "insight": {"id": 2, "name": "Page Views"}},
        ],
    }


@pytest.fixture
def mock_insight_data():
    """Mock PostHog insight data from API."""
    return {
        "id": 456,
        "short_id": "abc123",
        "name": "Daily Active Users",
        "description": "Tracks daily active users over time",
        "filters": {
            "insight": "TRENDS",
            "events": [{"id": "$pageview", "name": "Pageview", "math": "dau"}],
            "date_from": "-30d",
        },
        "query": None,
        "created_at": "2024-01-10T09:00:00.000Z",
        "updated_at": "2024-02-15T12:00:00.000Z",
        "last_modified_at": "2024-02-15T12:00:00.000Z",
        "created_by": {"id": 1, "email": "user@example.com"},
        "saved": True,
        "tags": ["engagement", "users"],
        "dashboards": [123, 456],
    }


@pytest.fixture
def mock_feature_flag_data():
    """Mock PostHog feature flag data from API."""
    return {
        "id": 789,
        "key": "new-checkout-flow",
        "name": "New Checkout Flow",
        "filters": {
            "groups": [
                {
                    "properties": [{"key": "email", "value": "@company.com"}],
                    "rollout_percentage": 100,
                },
                {"properties": [], "rollout_percentage": 50},
            ]
        },
        "active": True,
        "created_at": "2024-03-01T08:00:00.000Z",
        "created_by": {"id": 1, "email": "user@example.com"},
        "ensure_experience_continuity": True,
        "tags": ["checkout", "experiment"],
    }


@pytest.fixture
def mock_annotation_data():
    """Mock PostHog annotation data from API."""
    return {
        "id": 101,
        "content": "Product launch - v2.0 released",
        "date_marker": "2024-02-01T00:00:00.000Z",
        "created_at": "2024-02-01T10:00:00.000Z",
        "updated_at": "2024-02-01T10:30:00.000Z",
        "created_by": {"id": 1, "email": "user@example.com"},
        "scope": "organization",
        "dashboard_item": None,
    }


@pytest.fixture
def mock_experiment_data():
    """Mock PostHog experiment data from API."""
    return {
        "id": 202,
        "name": "Checkout Button Color Test",
        "description": "Testing green vs blue checkout button",
        "start_date": "2024-03-15T00:00:00.000Z",
        "end_date": None,
        "created_at": "2024-03-14T15:00:00.000Z",
        "updated_at": "2024-03-15T09:00:00.000Z",
        "created_by": {"id": 1, "email": "user@example.com"},
        "feature_flag_key": "checkout-button-color",
        "feature_flag": {"id": 303, "key": "checkout-button-color"},
        "parameters": {
            "feature_flag_variants": [
                {"key": "control", "rollout_percentage": 50},
                {"key": "test", "rollout_percentage": 50},
            ]
        },
        "filters": {},
        "archived": False,
    }


@pytest.fixture
def mock_survey_data():
    """Mock PostHog survey data from API."""
    return {
        "id": "survey_abc123",
        "name": "NPS Survey",
        "description": "Net Promoter Score survey for users",
        "type": "popover",
        "questions": [
            {
                "type": "rating",
                "question": "How likely are you to recommend us?",
                "scale": 10,
            },
            {
                "type": "open",
                "question": "What could we improve?",
            },
        ],
        "appearance": {"backgroundColor": "#ffffff"},
        "targeting_flag_filters": None,
        "start_date": "2024-04-01T00:00:00.000Z",
        "end_date": None,
        "created_at": "2024-03-25T14:00:00.000Z",
        "created_by": {"id": 1, "email": "user@example.com"},
        "archived": False,
    }


class TestPostHogDashboardArtifact:
    """Test suite for PostHogDashboardArtifact."""

    def test_from_api_response_basic(self, mock_dashboard_data, job_id):
        """Test creating artifact from basic dashboard data."""
        artifact = PostHogDashboardArtifact.from_api_response(
            dashboard_data=mock_dashboard_data,
            project_id=1,
            ingest_job_id=job_id,
        )

        assert artifact.entity == ArtifactEntity.POSTHOG_DASHBOARD
        assert artifact.entity_id == "posthog_dashboard_1_123"
        assert artifact.metadata.dashboard_id == 123
        assert artifact.metadata.project_id == 1
        assert artifact.metadata.name == "Product Analytics"
        assert artifact.metadata.is_pinned is True
        assert artifact.metadata.is_shared is True
        assert artifact.metadata.tile_count == 2
        assert artifact.metadata.tags == ["product", "metrics"]

    def test_from_api_response_content(self, mock_dashboard_data, job_id):
        """Test that content is properly extracted."""
        artifact = PostHogDashboardArtifact.from_api_response(
            dashboard_data=mock_dashboard_data,
            project_id=1,
            ingest_job_id=job_id,
        )

        assert artifact.content["dashboard_id"] == 123
        assert artifact.content["project_id"] == 1
        assert artifact.content["name"] == "Product Analytics"
        assert artifact.content["description"] == "Main product metrics dashboard"
        assert len(artifact.content["tiles"]) == 2

    def test_from_api_response_parses_timestamp(self, mock_dashboard_data, job_id):
        """Test that source_updated_at is properly parsed."""
        artifact = PostHogDashboardArtifact.from_api_response(
            dashboard_data=mock_dashboard_data,
            project_id=1,
            ingest_job_id=job_id,
        )

        assert artifact.source_updated_at == datetime(2024, 2, 20, 15, 30, 0, tzinfo=UTC)

    def test_from_api_response_uses_created_at_when_no_updated_at(self, job_id):
        """Test fallback to created_at when updated_at is missing."""
        data = {
            "id": 123,
            "name": "Test Dashboard",
            "created_at": "2024-01-15T10:00:00.000Z",
        }

        artifact = PostHogDashboardArtifact.from_api_response(
            dashboard_data=data,
            project_id=1,
            ingest_job_id=job_id,
        )

        assert artifact.source_updated_at == datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC)

    def test_from_api_response_defaults_empty_tiles(self, job_id):
        """Test that missing tiles defaults to empty list."""
        data = {
            "id": 123,
            "name": "Empty Dashboard",
            "created_at": "2024-01-15T10:00:00.000Z",
        }

        artifact = PostHogDashboardArtifact.from_api_response(
            dashboard_data=data,
            project_id=1,
            ingest_job_id=job_id,
        )

        assert artifact.content["tiles"] == []
        assert artifact.metadata.tile_count == 0


class TestPostHogInsightArtifact:
    """Test suite for PostHogInsightArtifact."""

    def test_from_api_response_basic(self, mock_insight_data, job_id):
        """Test creating artifact from basic insight data."""
        artifact = PostHogInsightArtifact.from_api_response(
            insight_data=mock_insight_data,
            project_id=1,
            ingest_job_id=job_id,
        )

        assert artifact.entity == ArtifactEntity.POSTHOG_INSIGHT
        assert artifact.entity_id == "posthog_insight_1_456"
        assert artifact.metadata.insight_id == 456
        assert artifact.metadata.project_id == 1
        assert artifact.metadata.short_id == "abc123"
        assert artifact.metadata.name == "Daily Active Users"
        assert artifact.metadata.is_saved is True
        assert artifact.metadata.dashboard_ids == [123, 456]
        assert artifact.metadata.tags == ["engagement", "users"]

    def test_from_api_response_content(self, mock_insight_data, job_id):
        """Test that content is properly extracted."""
        artifact = PostHogInsightArtifact.from_api_response(
            insight_data=mock_insight_data,
            project_id=1,
            ingest_job_id=job_id,
        )

        assert artifact.content["insight_id"] == 456
        assert artifact.content["filters"]["insight"] == "TRENDS"
        assert artifact.content["description"] == "Tracks daily active users over time"

    def test_from_api_response_uses_last_modified_at(self, mock_insight_data, job_id):
        """Test that last_modified_at is used for source_updated_at."""
        artifact = PostHogInsightArtifact.from_api_response(
            insight_data=mock_insight_data,
            project_id=1,
            ingest_job_id=job_id,
        )

        assert artifact.source_updated_at == datetime(2024, 2, 15, 12, 0, 0, tzinfo=UTC)

    def test_from_api_response_unsaved_insight(self, job_id):
        """Test handling unsaved insight."""
        data = {
            "id": 789,
            "short_id": "xyz789",
            "created_at": "2024-01-10T09:00:00.000Z",
            "saved": False,
        }

        artifact = PostHogInsightArtifact.from_api_response(
            insight_data=data,
            project_id=1,
            ingest_job_id=job_id,
        )

        assert artifact.metadata.is_saved is False


class TestPostHogFeatureFlagArtifact:
    """Test suite for PostHogFeatureFlagArtifact."""

    def test_from_api_response_basic(self, mock_feature_flag_data, job_id):
        """Test creating artifact from basic feature flag data."""
        artifact = PostHogFeatureFlagArtifact.from_api_response(
            flag_data=mock_feature_flag_data,
            project_id=1,
            ingest_job_id=job_id,
        )

        assert artifact.entity == ArtifactEntity.POSTHOG_FEATURE_FLAG
        assert artifact.entity_id == "posthog_feature_flag_1_789"
        assert artifact.metadata.flag_id == 789
        assert artifact.metadata.project_id == 1
        assert artifact.metadata.key == "new-checkout-flow"
        assert artifact.metadata.name == "New Checkout Flow"
        assert artifact.metadata.is_active is True
        assert artifact.metadata.tags == ["checkout", "experiment"]

    def test_from_api_response_extracts_rollout_percentage(self, mock_feature_flag_data, job_id):
        """Test that rollout percentage is extracted from filters."""
        artifact = PostHogFeatureFlagArtifact.from_api_response(
            flag_data=mock_feature_flag_data,
            project_id=1,
            ingest_job_id=job_id,
        )

        # Should extract from first group
        assert artifact.metadata.rollout_percentage == 100

    def test_from_api_response_explicit_rollout_percentage(self, job_id):
        """Test explicit rollout_percentage field."""
        data = {
            "id": 789,
            "key": "test-flag",
            "created_at": "2024-03-01T08:00:00.000Z",
            "rollout_percentage": 75,
            "filters": {},
        }

        artifact = PostHogFeatureFlagArtifact.from_api_response(
            flag_data=data,
            project_id=1,
            ingest_job_id=job_id,
        )

        assert artifact.metadata.rollout_percentage == 75

    def test_from_api_response_inactive_flag(self, job_id):
        """Test inactive feature flag."""
        data = {
            "id": 789,
            "key": "deprecated-flag",
            "created_at": "2024-03-01T08:00:00.000Z",
            "active": False,
        }

        artifact = PostHogFeatureFlagArtifact.from_api_response(
            flag_data=data,
            project_id=1,
            ingest_job_id=job_id,
        )

        assert artifact.metadata.is_active is False


class TestPostHogAnnotationArtifact:
    """Test suite for PostHogAnnotationArtifact."""

    def test_from_api_response_basic(self, mock_annotation_data, job_id):
        """Test creating artifact from basic annotation data."""
        artifact = PostHogAnnotationArtifact.from_api_response(
            annotation_data=mock_annotation_data,
            project_id=1,
            ingest_job_id=job_id,
        )

        assert artifact.entity == ArtifactEntity.POSTHOG_ANNOTATION
        assert artifact.entity_id == "posthog_annotation_1_101"
        assert artifact.metadata.annotation_id == 101
        assert artifact.metadata.project_id == 1
        assert artifact.metadata.scope == "organization"
        assert artifact.metadata.dashboard_item_id is None

    def test_from_api_response_content(self, mock_annotation_data, job_id):
        """Test that content is properly extracted."""
        artifact = PostHogAnnotationArtifact.from_api_response(
            annotation_data=mock_annotation_data,
            project_id=1,
            ingest_job_id=job_id,
        )

        assert artifact.content["content"] == "Product launch - v2.0 released"
        assert artifact.content["date_marker"] == "2024-02-01T00:00:00.000Z"

    def test_from_api_response_with_dashboard_item(self, job_id):
        """Test annotation with dashboard item."""
        data = {
            "id": 101,
            "content": "Dashboard-specific annotation",
            "date_marker": "2024-02-01T00:00:00.000Z",
            "created_at": "2024-02-01T10:00:00.000Z",
            "scope": "dashboard_item",
            "dashboard_item": 456,
        }

        artifact = PostHogAnnotationArtifact.from_api_response(
            annotation_data=data,
            project_id=1,
            ingest_job_id=job_id,
        )

        assert artifact.metadata.scope == "dashboard_item"
        assert artifact.metadata.dashboard_item_id == 456


class TestPostHogExperimentArtifact:
    """Test suite for PostHogExperimentArtifact."""

    def test_from_api_response_basic(self, mock_experiment_data, job_id):
        """Test creating artifact from basic experiment data."""
        artifact = PostHogExperimentArtifact.from_api_response(
            experiment_data=mock_experiment_data,
            project_id=1,
            ingest_job_id=job_id,
        )

        assert artifact.entity == ArtifactEntity.POSTHOG_EXPERIMENT
        assert artifact.entity_id == "posthog_experiment_1_202"
        assert artifact.metadata.experiment_id == 202
        assert artifact.metadata.project_id == 1
        assert artifact.metadata.name == "Checkout Button Color Test"
        assert artifact.metadata.feature_flag_key == "checkout-button-color"
        assert artifact.metadata.is_archived is False

    def test_from_api_response_content(self, mock_experiment_data, job_id):
        """Test that content is properly extracted."""
        artifact = PostHogExperimentArtifact.from_api_response(
            experiment_data=mock_experiment_data,
            project_id=1,
            ingest_job_id=job_id,
        )

        assert artifact.content["name"] == "Checkout Button Color Test"
        assert artifact.content["description"] == "Testing green vs blue checkout button"
        assert artifact.content["start_date"] == "2024-03-15T00:00:00.000Z"
        assert artifact.content["end_date"] is None
        assert len(artifact.content["parameters"]["feature_flag_variants"]) == 2

    def test_from_api_response_archived_experiment(self, job_id):
        """Test archived experiment."""
        data = {
            "id": 202,
            "name": "Old Experiment",
            "created_at": "2024-01-01T00:00:00.000Z",
            "archived": True,
        }

        artifact = PostHogExperimentArtifact.from_api_response(
            experiment_data=data,
            project_id=1,
            ingest_job_id=job_id,
        )

        assert artifact.metadata.is_archived is True


class TestPostHogSurveyArtifact:
    """Test suite for PostHogSurveyArtifact."""

    def test_from_api_response_basic(self, mock_survey_data, job_id):
        """Test creating artifact from basic survey data."""
        artifact = PostHogSurveyArtifact.from_api_response(
            survey_data=mock_survey_data,
            project_id=1,
            ingest_job_id=job_id,
        )

        assert artifact.entity == ArtifactEntity.POSTHOG_SURVEY
        assert artifact.entity_id == "posthog_survey_1_survey_abc123"
        assert artifact.metadata.survey_id == "survey_abc123"
        assert artifact.metadata.project_id == 1
        assert artifact.metadata.name == "NPS Survey"
        assert artifact.metadata.survey_type == "popover"
        assert artifact.metadata.question_count == 2
        assert artifact.metadata.is_archived is False

    def test_from_api_response_content(self, mock_survey_data, job_id):
        """Test that content is properly extracted."""
        artifact = PostHogSurveyArtifact.from_api_response(
            survey_data=mock_survey_data,
            project_id=1,
            ingest_job_id=job_id,
        )

        assert artifact.content["name"] == "NPS Survey"
        assert artifact.content["description"] == "Net Promoter Score survey for users"
        assert len(artifact.content["questions"]) == 2
        assert artifact.content["questions"][0]["type"] == "rating"

    def test_from_api_response_archived_survey(self, job_id):
        """Test archived survey."""
        data = {
            "id": "survey_old",
            "name": "Old Survey",
            "created_at": "2024-01-01T00:00:00.000Z",
            "archived": True,
            "questions": [],
        }

        artifact = PostHogSurveyArtifact.from_api_response(
            survey_data=data,
            project_id=1,
            ingest_job_id=job_id,
        )

        assert artifact.metadata.is_archived is True
        assert artifact.metadata.question_count == 0


class TestArtifactEntityIds:
    """Test suite for entity ID generation."""

    def test_dashboard_entity_id_format(self, mock_dashboard_data, job_id):
        """Test dashboard entity ID format."""
        artifact = PostHogDashboardArtifact.from_api_response(
            dashboard_data=mock_dashboard_data,
            project_id=42,
            ingest_job_id=job_id,
        )

        assert artifact.entity_id == "posthog_dashboard_42_123"

    def test_insight_entity_id_format(self, mock_insight_data, job_id):
        """Test insight entity ID format."""
        artifact = PostHogInsightArtifact.from_api_response(
            insight_data=mock_insight_data,
            project_id=42,
            ingest_job_id=job_id,
        )

        assert artifact.entity_id == "posthog_insight_42_456"

    def test_feature_flag_entity_id_format(self, mock_feature_flag_data, job_id):
        """Test feature flag entity ID format."""
        artifact = PostHogFeatureFlagArtifact.from_api_response(
            flag_data=mock_feature_flag_data,
            project_id=42,
            ingest_job_id=job_id,
        )

        assert artifact.entity_id == "posthog_feature_flag_42_789"

    def test_annotation_entity_id_format(self, mock_annotation_data, job_id):
        """Test annotation entity ID format."""
        artifact = PostHogAnnotationArtifact.from_api_response(
            annotation_data=mock_annotation_data,
            project_id=42,
            ingest_job_id=job_id,
        )

        assert artifact.entity_id == "posthog_annotation_42_101"

    def test_experiment_entity_id_format(self, mock_experiment_data, job_id):
        """Test experiment entity ID format."""
        artifact = PostHogExperimentArtifact.from_api_response(
            experiment_data=mock_experiment_data,
            project_id=42,
            ingest_job_id=job_id,
        )

        assert artifact.entity_id == "posthog_experiment_42_202"

    def test_survey_entity_id_format(self, mock_survey_data, job_id):
        """Test survey entity ID format."""
        artifact = PostHogSurveyArtifact.from_api_response(
            survey_data=mock_survey_data,
            project_id=42,
            ingest_job_id=job_id,
        )

        assert artifact.entity_id == "posthog_survey_42_survey_abc123"


class TestArtifactTimestampHandling:
    """Test suite for timestamp edge cases."""

    def test_uses_current_time_when_no_timestamps(self, job_id):
        """Test fallback to current time when both timestamps missing."""
        data = {
            "id": 123,
            "name": "No Timestamp Dashboard",
        }

        before = datetime.now(UTC)
        artifact = PostHogDashboardArtifact.from_api_response(
            dashboard_data=data,
            project_id=1,
            ingest_job_id=job_id,
        )
        after = datetime.now(UTC)

        assert before <= artifact.source_updated_at <= after

    def test_handles_z_suffix_timestamp(self, job_id):
        """Test parsing timestamps with Z suffix."""
        data = {
            "id": 123,
            "name": "Test",
            "created_at": "2024-01-15T10:00:00Z",
        }

        artifact = PostHogDashboardArtifact.from_api_response(
            dashboard_data=data,
            project_id=1,
            ingest_job_id=job_id,
        )

        assert artifact.source_updated_at == datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC)

    def test_handles_milliseconds_in_timestamp(self, job_id):
        """Test parsing timestamps with milliseconds."""
        data = {
            "id": 123,
            "name": "Test",
            "created_at": "2024-01-15T10:00:00.123Z",
        }

        artifact = PostHogDashboardArtifact.from_api_response(
            dashboard_data=data,
            project_id=1,
            ingest_job_id=job_id,
        )

        assert artifact.source_updated_at.microsecond == 123000
