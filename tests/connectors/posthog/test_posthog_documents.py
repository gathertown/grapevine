"""Tests for PostHog document models."""

from uuid import uuid4

import pytest

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


@pytest.fixture
def job_id():
    """Create a test job ID."""
    return uuid4()


@pytest.fixture
def mock_dashboard_data():
    """Complete mock PostHog dashboard data."""
    return {
        "id": 123,
        "name": "Product Analytics Dashboard",
        "description": "Main product metrics and KPIs",
        "pinned": True,
        "is_shared": True,
        "created_at": "2024-01-15T10:00:00.000Z",
        "updated_at": "2024-02-20T15:30:00.000Z",
        "created_by": {"id": 1, "email": "user@example.com"},
        "tags": ["product", "metrics", "kpi"],
        "tiles": [
            {"id": 1, "insight": {"id": 1, "name": "Daily Active Users", "short_id": "dau1"}},
            {"id": 2, "insight": {"id": 2, "name": "Page Views", "short_id": "pv2"}},
            {"id": 3, "insight": {"id": 3, "name": "Conversion Rate", "short_id": "cr3"}},
        ],
    }


@pytest.fixture
def mock_insight_data():
    """Complete mock PostHog insight data."""
    return {
        "id": 456,
        "short_id": "abc123",
        "name": "Daily Active Users Trend",
        "description": "Shows the trend of daily active users over 30 days",
        "filters": {
            "insight": "TRENDS",
            "events": [
                {"id": "$pageview", "name": "Pageview", "math": "dau"},
                {"id": "signup", "name": "Sign Up", "math": "total"},
            ],
            "actions": [
                {"id": 1, "name": "Completed Purchase", "math": "unique_group"},
            ],
            "date_from": "-30d",
            "date_to": None,
            "interval": "day",
            "compare": True,
            "breakdown": "browser",
            "breakdown_type": "event",
            "formula": "A / B",
            "filter_groups": [
                {
                    "values": [
                        {"key": "country", "value": "US", "operator": "exact"},
                    ]
                }
            ],
        },
        "query": {
            "kind": "HogQLQuery",
            "query": "SELECT count() FROM events WHERE event = '$pageview'",
        },
        "created_at": "2024-01-10T09:00:00.000Z",
        "updated_at": "2024-02-15T12:00:00.000Z",
        "last_modified_at": "2024-02-15T12:00:00.000Z",
        "created_by": {"id": 1, "email": "user@example.com"},
        "saved": True,
        "tags": ["engagement", "users"],
        "dashboards": [123, 456, 789],
    }


@pytest.fixture
def mock_feature_flag_data():
    """Complete mock PostHog feature flag data."""
    return {
        "id": 789,
        "key": "new-checkout-flow",
        "name": "New Checkout Flow",
        "filters": {
            "groups": [
                {
                    "properties": [
                        {"key": "email", "value": "@company.com", "operator": "icontains"},
                    ],
                    "rollout_percentage": 100,
                },
                {"properties": [], "rollout_percentage": 50},
            ]
        },
        "active": True,
        "created_at": "2024-03-01T08:00:00.000Z",
        "created_by": {"id": 1, "email": "user@example.com"},
        "ensure_experience_continuity": True,
        "rollout_percentage": 50,
        "tags": ["checkout", "experiment"],
    }


@pytest.fixture
def mock_annotation_data():
    """Complete mock PostHog annotation data."""
    return {
        "id": 101,
        "content": "Product launch - Version 2.0 released with new features",
        "date_marker": "2024-02-01T00:00:00.000Z",
        "created_at": "2024-02-01T10:00:00.000Z",
        "updated_at": "2024-02-01T10:30:00.000Z",
        "created_by": {"id": 1, "email": "user@example.com", "name": {"full_name": "John Doe"}},
        "scope": "organization",
        "dashboard_item": None,
    }


@pytest.fixture
def mock_experiment_data():
    """Complete mock PostHog experiment data."""
    return {
        "id": 202,
        "name": "Checkout Button Color Test",
        "description": "A/B testing green vs blue checkout button to improve conversion",
        "start_date": "2024-03-15T00:00:00.000Z",
        "end_date": "2024-04-15T00:00:00.000Z",
        "created_at": "2024-03-14T15:00:00.000Z",
        "updated_at": "2024-03-15T09:00:00.000Z",
        "created_by": {"id": 1, "email": "user@example.com"},
        "feature_flag_key": "checkout-button-color",
        "feature_flag": {"id": 303, "key": "checkout-button-color"},
        "parameters": {
            "feature_flag_variants": [
                {"key": "control", "rollout_percentage": 50},
                {"key": "test-green", "rollout_percentage": 25},
                {"key": "test-blue", "rollout_percentage": 25},
            ]
        },
        "filters": {},
        "archived": False,
    }


@pytest.fixture
def mock_survey_data():
    """Complete mock PostHog survey data."""
    return {
        "id": "survey_nps_2024",
        "name": "Q1 NPS Survey",
        "description": "Quarterly Net Promoter Score survey",
        "type": "popover",
        "questions": [
            {
                "type": "rating",
                "question": "How likely are you to recommend us to a friend?",
                "scale": 10,
            },
            {
                "type": "single_choice",
                "question": "What's your primary use case?",
                "choices": ["Personal", "Work", "Both", "Other"],
            },
            {
                "type": "open",
                "question": "What could we improve?",
            },
        ],
        "appearance": {"backgroundColor": "#ffffff", "textColor": "#000000"},
        "targeting_flag_filters": None,
        "start_date": "2024-04-01T00:00:00.000Z",
        "end_date": "2024-04-30T23:59:59.000Z",
        "created_at": "2024-03-25T14:00:00.000Z",
        "created_by": {"id": 1, "email": "user@example.com"},
        "archived": False,
    }


class TestPostHogDashboardDocument:
    """Test suite for PostHogDashboardDocument."""

    def test_from_artifact_basic(self, mock_dashboard_data, job_id):
        """Test creating document from dashboard artifact."""
        artifact = PostHogDashboardArtifact.from_api_response(
            dashboard_data=mock_dashboard_data,
            project_id=1,
            ingest_job_id=job_id,
        )

        document = PostHogDashboardDocument.from_artifact(artifact)

        assert document.id == "posthog_dashboard_1_123"

    def test_get_content(self, mock_dashboard_data, job_id):
        """Test document content contains dashboard info."""
        artifact = PostHogDashboardArtifact.from_api_response(
            dashboard_data=mock_dashboard_data,
            project_id=1,
            ingest_job_id=job_id,
        )
        document = PostHogDashboardDocument.from_artifact(artifact)

        content = document.get_content()

        assert "Product Analytics Dashboard" in content
        assert "Main product metrics and KPIs" in content
        assert "Tiles: 3" in content
        assert "Pinned" in content
        assert "Shared" in content
        assert "product, metrics, kpi" in content

    def test_get_content_includes_tiles(self, mock_dashboard_data, job_id):
        """Test that dashboard tiles are listed in content."""
        artifact = PostHogDashboardArtifact.from_api_response(
            dashboard_data=mock_dashboard_data,
            project_id=1,
            ingest_job_id=job_id,
        )
        document = PostHogDashboardDocument.from_artifact(artifact)

        content = document.get_content()

        assert "Dashboard Tiles:" in content
        assert "Daily Active Users" in content
        assert "Page Views" in content
        assert "Conversion Rate" in content

    def test_to_embedding_chunks(self, mock_dashboard_data, job_id):
        """Test document generates embedding chunks."""
        artifact = PostHogDashboardArtifact.from_api_response(
            dashboard_data=mock_dashboard_data,
            project_id=1,
            ingest_job_id=job_id,
        )
        document = PostHogDashboardDocument.from_artifact(artifact)

        chunks = document.to_embedding_chunks()

        assert len(chunks) >= 1
        all_content = " ".join(chunk.get_content() for chunk in chunks)
        assert "Product Analytics Dashboard" in all_content

    def test_get_reference_id(self, mock_dashboard_data, job_id):
        """Test reference ID format."""
        artifact = PostHogDashboardArtifact.from_api_response(
            dashboard_data=mock_dashboard_data,
            project_id=1,
            ingest_job_id=job_id,
        )
        document = PostHogDashboardDocument.from_artifact(artifact)

        ref_id = document.get_reference_id()

        assert ref_id == "r_posthog_dashboard_1_123"

    def test_get_metadata_includes_type(self, mock_dashboard_data, job_id):
        """Test metadata includes correct type field."""
        artifact = PostHogDashboardArtifact.from_api_response(
            dashboard_data=mock_dashboard_data,
            project_id=1,
            ingest_job_id=job_id,
        )
        document = PostHogDashboardDocument.from_artifact(artifact)

        metadata = document.get_metadata()

        assert metadata["type"] == "posthog_dashboard"
        assert metadata["dashboard_id"] == 123
        assert metadata["project_id"] == 1

    def test_get_source_enum(self, mock_dashboard_data, job_id):
        """Test source enum is correct."""
        artifact = PostHogDashboardArtifact.from_api_response(
            dashboard_data=mock_dashboard_data,
            project_id=1,
            ingest_job_id=job_id,
        )
        document = PostHogDashboardDocument.from_artifact(artifact)

        assert document.get_source_enum() == DocumentSource.POSTHOG_DASHBOARD


class TestPostHogInsightDocument:
    """Test suite for PostHogInsightDocument."""

    def test_from_artifact_basic(self, mock_insight_data, job_id):
        """Test creating document from insight artifact."""
        artifact = PostHogInsightArtifact.from_api_response(
            insight_data=mock_insight_data,
            project_id=1,
            ingest_job_id=job_id,
        )

        document = PostHogInsightDocument.from_artifact(artifact)

        assert document.id == "posthog_insight_1_456"

    def test_get_content(self, mock_insight_data, job_id):
        """Test document content contains insight info."""
        artifact = PostHogInsightArtifact.from_api_response(
            insight_data=mock_insight_data,
            project_id=1,
            ingest_job_id=job_id,
        )
        document = PostHogInsightDocument.from_artifact(artifact)

        content = document.get_content()

        assert "Daily Active Users Trend" in content
        assert "Shows the trend of daily active users" in content
        assert "Type: TRENDS" in content

    def test_get_content_includes_date_range(self, mock_insight_data, job_id):
        """Test that date range is formatted in content."""
        artifact = PostHogInsightArtifact.from_api_response(
            insight_data=mock_insight_data,
            project_id=1,
            ingest_job_id=job_id,
        )
        document = PostHogInsightDocument.from_artifact(artifact)

        content = document.get_content()

        assert "Date Range: Last 30 days" in content

    def test_get_content_includes_events(self, mock_insight_data, job_id):
        """Test that events are listed in content."""
        artifact = PostHogInsightArtifact.from_api_response(
            insight_data=mock_insight_data,
            project_id=1,
            ingest_job_id=job_id,
        )
        document = PostHogInsightDocument.from_artifact(artifact)

        content = document.get_content()

        assert "Events:" in content
        assert "Pageview" in content
        assert "Sign Up" in content

    def test_get_content_includes_actions(self, mock_insight_data, job_id):
        """Test that actions are listed in content."""
        artifact = PostHogInsightArtifact.from_api_response(
            insight_data=mock_insight_data,
            project_id=1,
            ingest_job_id=job_id,
        )
        document = PostHogInsightDocument.from_artifact(artifact)

        content = document.get_content()

        assert "Actions:" in content
        assert "Completed Purchase" in content

    def test_get_content_includes_breakdown(self, mock_insight_data, job_id):
        """Test that breakdown is included in content."""
        artifact = PostHogInsightArtifact.from_api_response(
            insight_data=mock_insight_data,
            project_id=1,
            ingest_job_id=job_id,
        )
        document = PostHogInsightDocument.from_artifact(artifact)

        content = document.get_content()

        assert "Breakdown: browser" in content

    def test_get_content_includes_formula(self, mock_insight_data, job_id):
        """Test that formula is included in content."""
        artifact = PostHogInsightArtifact.from_api_response(
            insight_data=mock_insight_data,
            project_id=1,
            ingest_job_id=job_id,
        )
        document = PostHogInsightDocument.from_artifact(artifact)

        content = document.get_content()

        assert "Formula: A / B" in content

    def test_get_content_includes_hogql_query(self, mock_insight_data, job_id):
        """Test that HogQL query is included in content."""
        artifact = PostHogInsightArtifact.from_api_response(
            insight_data=mock_insight_data,
            project_id=1,
            ingest_job_id=job_id,
        )
        document = PostHogInsightDocument.from_artifact(artifact)

        content = document.get_content()

        assert "HogQL Query:" in content
        assert "SELECT count() FROM events" in content

    def test_get_content_includes_dashboards_count(self, mock_insight_data, job_id):
        """Test that dashboard count is included."""
        artifact = PostHogInsightArtifact.from_api_response(
            insight_data=mock_insight_data,
            project_id=1,
            ingest_job_id=job_id,
        )
        document = PostHogInsightDocument.from_artifact(artifact)

        content = document.get_content()

        assert "Dashboards: 3 dashboard(s)" in content

    def test_to_embedding_chunks(self, mock_insight_data, job_id):
        """Test document generates embedding chunks."""
        artifact = PostHogInsightArtifact.from_api_response(
            insight_data=mock_insight_data,
            project_id=1,
            ingest_job_id=job_id,
        )
        document = PostHogInsightDocument.from_artifact(artifact)

        chunks = document.to_embedding_chunks()

        assert len(chunks) >= 1

    def test_get_reference_id(self, mock_insight_data, job_id):
        """Test reference ID format."""
        artifact = PostHogInsightArtifact.from_api_response(
            insight_data=mock_insight_data,
            project_id=1,
            ingest_job_id=job_id,
        )
        document = PostHogInsightDocument.from_artifact(artifact)

        ref_id = document.get_reference_id()

        assert ref_id == "r_posthog_insight_1_456"

    def test_get_source_enum(self, mock_insight_data, job_id):
        """Test source enum is correct."""
        artifact = PostHogInsightArtifact.from_api_response(
            insight_data=mock_insight_data,
            project_id=1,
            ingest_job_id=job_id,
        )
        document = PostHogInsightDocument.from_artifact(artifact)

        assert document.get_source_enum() == DocumentSource.POSTHOG_INSIGHT


class TestPostHogFeatureFlagDocument:
    """Test suite for PostHogFeatureFlagDocument."""

    def test_from_artifact_basic(self, mock_feature_flag_data, job_id):
        """Test creating document from feature flag artifact."""
        artifact = PostHogFeatureFlagArtifact.from_api_response(
            flag_data=mock_feature_flag_data,
            project_id=1,
            ingest_job_id=job_id,
        )

        document = PostHogFeatureFlagDocument.from_artifact(artifact)

        assert document.id == "posthog_feature_flag_1_789"

    def test_get_content(self, mock_feature_flag_data, job_id):
        """Test document content contains feature flag info."""
        artifact = PostHogFeatureFlagArtifact.from_api_response(
            flag_data=mock_feature_flag_data,
            project_id=1,
            ingest_job_id=job_id,
        )
        document = PostHogFeatureFlagDocument.from_artifact(artifact)

        content = document.get_content()

        assert "New Checkout Flow" in content
        assert "Key: new-checkout-flow" in content
        assert "Status: Active" in content

    def test_get_content_includes_rollout(self, mock_feature_flag_data, job_id):
        """Test that rollout percentage is included."""
        artifact = PostHogFeatureFlagArtifact.from_api_response(
            flag_data=mock_feature_flag_data,
            project_id=1,
            ingest_job_id=job_id,
        )
        document = PostHogFeatureFlagDocument.from_artifact(artifact)

        content = document.get_content()

        assert "Rollout: 50%" in content

    def test_get_content_includes_targeting_rules(self, mock_feature_flag_data, job_id):
        """Test that targeting rules are included."""
        artifact = PostHogFeatureFlagArtifact.from_api_response(
            flag_data=mock_feature_flag_data,
            project_id=1,
            ingest_job_id=job_id,
        )
        document = PostHogFeatureFlagDocument.from_artifact(artifact)

        content = document.get_content()

        assert "Targeting Rules:" in content
        assert "Group 1:" in content
        assert "email" in content

    def test_get_content_includes_tags(self, mock_feature_flag_data, job_id):
        """Test that tags are included."""
        artifact = PostHogFeatureFlagArtifact.from_api_response(
            flag_data=mock_feature_flag_data,
            project_id=1,
            ingest_job_id=job_id,
        )
        document = PostHogFeatureFlagDocument.from_artifact(artifact)

        content = document.get_content()

        assert "Tags: checkout, experiment" in content

    def test_to_embedding_chunks(self, mock_feature_flag_data, job_id):
        """Test document generates embedding chunks."""
        artifact = PostHogFeatureFlagArtifact.from_api_response(
            flag_data=mock_feature_flag_data,
            project_id=1,
            ingest_job_id=job_id,
        )
        document = PostHogFeatureFlagDocument.from_artifact(artifact)

        chunks = document.to_embedding_chunks()

        assert len(chunks) >= 1

    def test_get_reference_id(self, mock_feature_flag_data, job_id):
        """Test reference ID format."""
        artifact = PostHogFeatureFlagArtifact.from_api_response(
            flag_data=mock_feature_flag_data,
            project_id=1,
            ingest_job_id=job_id,
        )
        document = PostHogFeatureFlagDocument.from_artifact(artifact)

        ref_id = document.get_reference_id()

        assert ref_id == "r_posthog_feature_flag_1_789"

    def test_get_source_enum(self, mock_feature_flag_data, job_id):
        """Test source enum is correct."""
        artifact = PostHogFeatureFlagArtifact.from_api_response(
            flag_data=mock_feature_flag_data,
            project_id=1,
            ingest_job_id=job_id,
        )
        document = PostHogFeatureFlagDocument.from_artifact(artifact)

        assert document.get_source_enum() == DocumentSource.POSTHOG_FEATURE_FLAG


class TestPostHogAnnotationDocument:
    """Test suite for PostHogAnnotationDocument."""

    def test_from_artifact_basic(self, mock_annotation_data, job_id):
        """Test creating document from annotation artifact."""
        artifact = PostHogAnnotationArtifact.from_api_response(
            annotation_data=mock_annotation_data,
            project_id=1,
            ingest_job_id=job_id,
        )

        document = PostHogAnnotationDocument.from_artifact(artifact)

        assert document.id == "posthog_annotation_1_101"

    def test_get_content(self, mock_annotation_data, job_id):
        """Test document content contains annotation info."""
        artifact = PostHogAnnotationArtifact.from_api_response(
            annotation_data=mock_annotation_data,
            project_id=1,
            ingest_job_id=job_id,
        )
        document = PostHogAnnotationDocument.from_artifact(artifact)

        content = document.get_content()

        assert "PostHog Annotation" in content
        assert "Product launch - Version 2.0" in content
        assert "Scope: organization" in content

    def test_get_content_includes_date(self, mock_annotation_data, job_id):
        """Test that date marker is formatted."""
        artifact = PostHogAnnotationArtifact.from_api_response(
            annotation_data=mock_annotation_data,
            project_id=1,
            ingest_job_id=job_id,
        )
        document = PostHogAnnotationDocument.from_artifact(artifact)

        content = document.get_content()

        assert "Date:" in content
        assert "2024-02-01" in content

    def test_to_embedding_chunks(self, mock_annotation_data, job_id):
        """Test document generates embedding chunks."""
        artifact = PostHogAnnotationArtifact.from_api_response(
            annotation_data=mock_annotation_data,
            project_id=1,
            ingest_job_id=job_id,
        )
        document = PostHogAnnotationDocument.from_artifact(artifact)

        chunks = document.to_embedding_chunks()

        assert len(chunks) >= 1

    def test_get_reference_id(self, mock_annotation_data, job_id):
        """Test reference ID format."""
        artifact = PostHogAnnotationArtifact.from_api_response(
            annotation_data=mock_annotation_data,
            project_id=1,
            ingest_job_id=job_id,
        )
        document = PostHogAnnotationDocument.from_artifact(artifact)

        ref_id = document.get_reference_id()

        assert ref_id == "r_posthog_annotation_1_101"

    def test_get_source_enum(self, mock_annotation_data, job_id):
        """Test source enum is correct."""
        artifact = PostHogAnnotationArtifact.from_api_response(
            annotation_data=mock_annotation_data,
            project_id=1,
            ingest_job_id=job_id,
        )
        document = PostHogAnnotationDocument.from_artifact(artifact)

        assert document.get_source_enum() == DocumentSource.POSTHOG_ANNOTATION


class TestPostHogExperimentDocument:
    """Test suite for PostHogExperimentDocument."""

    def test_from_artifact_basic(self, mock_experiment_data, job_id):
        """Test creating document from experiment artifact."""
        artifact = PostHogExperimentArtifact.from_api_response(
            experiment_data=mock_experiment_data,
            project_id=1,
            ingest_job_id=job_id,
        )

        document = PostHogExperimentDocument.from_artifact(artifact)

        assert document.id == "posthog_experiment_1_202"

    def test_get_content(self, mock_experiment_data, job_id):
        """Test document content contains experiment info."""
        artifact = PostHogExperimentArtifact.from_api_response(
            experiment_data=mock_experiment_data,
            project_id=1,
            ingest_job_id=job_id,
        )
        document = PostHogExperimentDocument.from_artifact(artifact)

        content = document.get_content()

        assert "Checkout Button Color Test" in content
        assert "A/B testing green vs blue" in content

    def test_get_content_includes_status(self, mock_experiment_data, job_id):
        """Test that experiment status is determined correctly."""
        artifact = PostHogExperimentArtifact.from_api_response(
            experiment_data=mock_experiment_data,
            project_id=1,
            ingest_job_id=job_id,
        )
        document = PostHogExperimentDocument.from_artifact(artifact)

        content = document.get_content()

        # Has end_date so should be "Completed"
        assert "Status: Completed" in content

    def test_get_content_includes_dates(self, mock_experiment_data, job_id):
        """Test that dates are included."""
        artifact = PostHogExperimentArtifact.from_api_response(
            experiment_data=mock_experiment_data,
            project_id=1,
            ingest_job_id=job_id,
        )
        document = PostHogExperimentDocument.from_artifact(artifact)

        content = document.get_content()

        assert "Start Date:" in content
        assert "End Date:" in content
        assert "2024-03-15" in content

    def test_get_content_includes_feature_flag(self, mock_experiment_data, job_id):
        """Test that feature flag key is included."""
        artifact = PostHogExperimentArtifact.from_api_response(
            experiment_data=mock_experiment_data,
            project_id=1,
            ingest_job_id=job_id,
        )
        document = PostHogExperimentDocument.from_artifact(artifact)

        content = document.get_content()

        assert "Feature Flag: checkout-button-color" in content

    def test_get_content_includes_variants(self, mock_experiment_data, job_id):
        """Test that variants are listed."""
        artifact = PostHogExperimentArtifact.from_api_response(
            experiment_data=mock_experiment_data,
            project_id=1,
            ingest_job_id=job_id,
        )
        document = PostHogExperimentDocument.from_artifact(artifact)

        content = document.get_content()

        assert "Variants:" in content
        assert "control: 50%" in content
        assert "test-green: 25%" in content
        assert "test-blue: 25%" in content

    def test_to_embedding_chunks(self, mock_experiment_data, job_id):
        """Test document generates embedding chunks."""
        artifact = PostHogExperimentArtifact.from_api_response(
            experiment_data=mock_experiment_data,
            project_id=1,
            ingest_job_id=job_id,
        )
        document = PostHogExperimentDocument.from_artifact(artifact)

        chunks = document.to_embedding_chunks()

        assert len(chunks) >= 1

    def test_get_reference_id(self, mock_experiment_data, job_id):
        """Test reference ID format."""
        artifact = PostHogExperimentArtifact.from_api_response(
            experiment_data=mock_experiment_data,
            project_id=1,
            ingest_job_id=job_id,
        )
        document = PostHogExperimentDocument.from_artifact(artifact)

        ref_id = document.get_reference_id()

        assert ref_id == "r_posthog_experiment_1_202"

    def test_get_source_enum(self, mock_experiment_data, job_id):
        """Test source enum is correct."""
        artifact = PostHogExperimentArtifact.from_api_response(
            experiment_data=mock_experiment_data,
            project_id=1,
            ingest_job_id=job_id,
        )
        document = PostHogExperimentDocument.from_artifact(artifact)

        assert document.get_source_enum() == DocumentSource.POSTHOG_EXPERIMENT


class TestPostHogSurveyDocument:
    """Test suite for PostHogSurveyDocument."""

    def test_from_artifact_basic(self, mock_survey_data, job_id):
        """Test creating document from survey artifact."""
        artifact = PostHogSurveyArtifact.from_api_response(
            survey_data=mock_survey_data,
            project_id=1,
            ingest_job_id=job_id,
        )

        document = PostHogSurveyDocument.from_artifact(artifact)

        assert document.id == "posthog_survey_1_survey_nps_2024"

    def test_get_content(self, mock_survey_data, job_id):
        """Test document content contains survey info."""
        artifact = PostHogSurveyArtifact.from_api_response(
            survey_data=mock_survey_data,
            project_id=1,
            ingest_job_id=job_id,
        )
        document = PostHogSurveyDocument.from_artifact(artifact)

        content = document.get_content()

        assert "Q1 NPS Survey" in content
        assert "Type: popover" in content
        assert "Quarterly Net Promoter Score" in content

    def test_get_content_includes_questions(self, mock_survey_data, job_id):
        """Test that questions are listed."""
        artifact = PostHogSurveyArtifact.from_api_response(
            survey_data=mock_survey_data,
            project_id=1,
            ingest_job_id=job_id,
        )
        document = PostHogSurveyDocument.from_artifact(artifact)

        content = document.get_content()

        assert "Questions:" in content
        assert "[rating]" in content
        assert "How likely are you to recommend us" in content
        assert "[single_choice]" in content
        assert "What's your primary use case?" in content
        assert "[open]" in content
        assert "What could we improve?" in content

    def test_get_content_includes_choices(self, mock_survey_data, job_id):
        """Test that question choices are listed."""
        artifact = PostHogSurveyArtifact.from_api_response(
            survey_data=mock_survey_data,
            project_id=1,
            ingest_job_id=job_id,
        )
        document = PostHogSurveyDocument.from_artifact(artifact)

        content = document.get_content()

        assert "Personal" in content
        assert "Work" in content
        assert "Both" in content

    def test_to_embedding_chunks(self, mock_survey_data, job_id):
        """Test document generates embedding chunks."""
        artifact = PostHogSurveyArtifact.from_api_response(
            survey_data=mock_survey_data,
            project_id=1,
            ingest_job_id=job_id,
        )
        document = PostHogSurveyDocument.from_artifact(artifact)

        chunks = document.to_embedding_chunks()

        assert len(chunks) >= 1

    def test_get_reference_id(self, mock_survey_data, job_id):
        """Test reference ID format."""
        artifact = PostHogSurveyArtifact.from_api_response(
            survey_data=mock_survey_data,
            project_id=1,
            ingest_job_id=job_id,
        )
        document = PostHogSurveyDocument.from_artifact(artifact)

        ref_id = document.get_reference_id()

        assert ref_id == "r_posthog_survey_1_survey_nps_2024"

    def test_get_metadata_includes_question_count(self, mock_survey_data, job_id):
        """Test that metadata includes question count."""
        artifact = PostHogSurveyArtifact.from_api_response(
            survey_data=mock_survey_data,
            project_id=1,
            ingest_job_id=job_id,
        )
        document = PostHogSurveyDocument.from_artifact(artifact)

        metadata = document.get_metadata()

        assert metadata["question_count"] == 3

    def test_get_source_enum(self, mock_survey_data, job_id):
        """Test source enum is correct."""
        artifact = PostHogSurveyArtifact.from_api_response(
            survey_data=mock_survey_data,
            project_id=1,
            ingest_job_id=job_id,
        )
        document = PostHogSurveyDocument.from_artifact(artifact)

        assert document.get_source_enum() == DocumentSource.POSTHOG_SURVEY


class TestInsightDateRangeFormatting:
    """Test date range formatting for insights."""

    def test_relative_days(self, job_id):
        """Test formatting relative day ranges."""
        data = {
            "id": 1,
            "short_id": "test",
            "created_at": "2024-01-01T00:00:00Z",
            "filters": {"date_from": "-7d"},
        }
        artifact = PostHogInsightArtifact.from_api_response(
            insight_data=data,
            project_id=1,
            ingest_job_id=job_id,
        )
        document = PostHogInsightDocument.from_artifact(artifact)

        content = document.get_content()

        assert "Last 7 days" in content

    def test_relative_weeks(self, job_id):
        """Test formatting relative week ranges."""
        data = {
            "id": 1,
            "short_id": "test",
            "created_at": "2024-01-01T00:00:00Z",
            "filters": {"date_from": "-4w"},
        }
        artifact = PostHogInsightArtifact.from_api_response(
            insight_data=data,
            project_id=1,
            ingest_job_id=job_id,
        )
        document = PostHogInsightDocument.from_artifact(artifact)

        content = document.get_content()

        assert "Last 4 weeks" in content

    def test_relative_months(self, job_id):
        """Test formatting relative month ranges."""
        data = {
            "id": 1,
            "short_id": "test",
            "created_at": "2024-01-01T00:00:00Z",
            "filters": {"date_from": "-3m"},
        }
        artifact = PostHogInsightArtifact.from_api_response(
            insight_data=data,
            project_id=1,
            ingest_job_id=job_id,
        )
        document = PostHogInsightDocument.from_artifact(artifact)

        content = document.get_content()

        assert "Last 3 months" in content

    def test_today_shortcut(self, job_id):
        """Test 'Today' shortcut."""
        data = {
            "id": 1,
            "short_id": "test",
            "created_at": "2024-01-01T00:00:00Z",
            "filters": {"date_from": "dStart"},
        }
        artifact = PostHogInsightArtifact.from_api_response(
            insight_data=data,
            project_id=1,
            ingest_job_id=job_id,
        )
        document = PostHogInsightDocument.from_artifact(artifact)

        content = document.get_content()

        assert "Today" in content

    def test_this_month_shortcut(self, job_id):
        """Test 'This month' shortcut."""
        data = {
            "id": 1,
            "short_id": "test",
            "created_at": "2024-01-01T00:00:00Z",
            "filters": {"date_from": "mStart"},
        }
        artifact = PostHogInsightArtifact.from_api_response(
            insight_data=data,
            project_id=1,
            ingest_job_id=job_id,
        )
        document = PostHogInsightDocument.from_artifact(artifact)

        content = document.get_content()

        assert "This month" in content


class TestInsightAggregationFormatting:
    """Test aggregation type formatting for insights."""

    def test_dau_aggregation(self, job_id):
        """Test DAU aggregation formatting."""
        data = {
            "id": 1,
            "short_id": "test",
            "created_at": "2024-01-01T00:00:00Z",
            "filters": {
                "events": [{"id": "$pageview", "name": "Pageview", "math": "dau"}],
            },
        }
        artifact = PostHogInsightArtifact.from_api_response(
            insight_data=data,
            project_id=1,
            ingest_job_id=job_id,
        )
        document = PostHogInsightDocument.from_artifact(artifact)

        content = document.get_content()

        assert "unique users per day" in content

    def test_sum_aggregation_with_property(self, job_id):
        """Test sum aggregation with math_property."""
        data = {
            "id": 1,
            "short_id": "test",
            "created_at": "2024-01-01T00:00:00Z",
            "filters": {
                "events": [
                    {
                        "id": "purchase",
                        "name": "Purchase",
                        "math": "sum",
                        "math_property": "amount",
                    }
                ],
            },
        }
        artifact = PostHogInsightArtifact.from_api_response(
            insight_data=data,
            project_id=1,
            ingest_job_id=job_id,
        )
        document = PostHogInsightDocument.from_artifact(artifact)

        content = document.get_content()

        assert "sum of amount" in content

    def test_percentile_aggregation(self, job_id):
        """Test percentile aggregation formatting."""
        data = {
            "id": 1,
            "short_id": "test",
            "created_at": "2024-01-01T00:00:00Z",
            "filters": {
                "events": [
                    {
                        "id": "page_load",
                        "name": "Page Load",
                        "math": "p95",
                        "math_property": "load_time",
                    }
                ],
            },
        }
        artifact = PostHogInsightArtifact.from_api_response(
            insight_data=data,
            project_id=1,
            ingest_job_id=job_id,
        )
        document = PostHogInsightDocument.from_artifact(artifact)

        content = document.get_content()

        assert "95th percentile of load_time" in content
