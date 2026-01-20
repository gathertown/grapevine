"""Tests for MCP tools filters module."""

from __future__ import annotations

from datetime import date
from typing import Any

import pytest

from connectors.base.document_source import DocumentSource
from src.mcp.tools.filters import (
    SearchFilters,
    build_opensearch_filters,
    build_postgres_filters,
    build_turbopuffer_filters,
    get_filter_description,
)


class TestSearchFilters:
    """Test SearchFilters model validation."""

    def test_default_values(self):
        """Test that default values are set correctly."""
        filters = SearchFilters()

        assert filters.sources == []
        assert filters.date_from is None
        assert filters.date_to is None
        assert filters.provenance is None
        assert filters.document_id is None

    def test_with_values(self):
        """Test SearchFilters with various values."""
        filters = SearchFilters(
            sources=[DocumentSource.SLACK, DocumentSource.GITHUB_PRS],
            date_from="2024-01-01",
            date_to="2024-12-31",
            provenance="team-platform",
            document_id="doc123",
        )

        assert filters.sources == [DocumentSource.SLACK, DocumentSource.GITHUB_PRS]
        assert filters.date_from == "2024-01-01"
        assert filters.date_to == "2024-12-31"
        assert filters.provenance == "team-platform"
        assert filters.document_id == "doc123"


class TestBuildOpensearchFilters:
    """Test OpenSearch filter building."""

    def test_empty_filters_with_no_permission_token(self):
        """Test that empty filters with no permission token only adds tenant filter."""
        filters = SearchFilters()
        result = build_opensearch_filters(filters, None)

        expected = {"term": {"permission_policy": "tenant"}}
        assert result == expected

    def test_empty_filters_with_permission_token(self):
        """Test empty filters with permission token but no audience defaults to tenant only."""
        filters = SearchFilters()
        permission_token = "e:user@example.com"
        result = build_opensearch_filters(filters, permission_token)

        # Without permission_audience="private", should only return tenant docs
        expected = {"term": {"permission_policy": "tenant"}}
        assert result == expected

    def test_empty_filters_with_permission_token_and_private_audience(self):
        """Test empty filters with permission token and private audience includes both tenant and private access."""
        filters = SearchFilters()
        permission_token = "e:user@example.com"
        result = build_opensearch_filters(filters, permission_token, permission_audience="private")

        expected: dict[str, Any] = {
            "bool": {
                "should": [
                    {"term": {"permission_policy": "tenant"}},
                    {
                        "bool": {
                            "must": [
                                {"term": {"permission_policy": "private"}},
                                {"term": {"permission_allowed_tokens": permission_token}},
                            ]
                        }
                    },
                ]
            }
        }
        assert result == expected

    def test_document_id_filter_ignores_others(self):
        """Test that document_id filter ignores all other filters."""
        filters = SearchFilters(
            document_id="doc123",
            sources=[DocumentSource.SLACK],
            date_from="2024-01-01",
            provenance="team-platform",
        )
        result = build_opensearch_filters(filters, "e:user@example.com")

        expected = {"term": {"id": "doc123"}}
        assert result == expected

    def test_single_source_filter(self):
        """Test filter with single source."""
        filters = SearchFilters(sources=[DocumentSource.SLACK])
        result = build_opensearch_filters(filters, None)
        assert result is not None

        assert "bool" in result
        assert "must" in result["bool"]
        filters_list = result["bool"]["must"]

        # Should have source filter and permission filter
        source_filter = {"term": {"source": "slack"}}
        assert source_filter in filters_list

    def test_multiple_sources_filter(self):
        """Test filter with multiple sources."""
        filters = SearchFilters(sources=[DocumentSource.SLACK, DocumentSource.GITHUB_PRS])
        result = build_opensearch_filters(filters, None)
        assert result is not None

        assert "bool" in result
        assert "must" in result["bool"]
        filters_list = result["bool"]["must"]

        # Should have sources filter
        source_filter = {"terms": {"source": ["slack", "github"]}}
        assert source_filter in filters_list

    def test_date_range_filters(self):
        """Test date range filtering."""
        filters = SearchFilters(date_from="2024-01-01", date_to="2024-12-31")
        result = build_opensearch_filters(filters, None)
        assert result is not None

        assert "bool" in result
        filters_list = result["bool"]["must"]

        date_filter = {"range": {"source_created_at": {"gte": "2024-01-01", "lte": "2024-12-31"}}}
        assert date_filter in filters_list

    def test_date_from_only(self):
        """Test date_from only filter."""
        filters = SearchFilters(date_from="2024-01-01")
        result = build_opensearch_filters(filters, None)
        assert result is not None

        filters_list = result["bool"]["must"]
        date_filter = {"range": {"source_created_at": {"gte": "2024-01-01"}}}
        assert date_filter in filters_list

    def test_date_to_only(self):
        """Test date_to only filter."""
        filters = SearchFilters(date_to="2024-12-31")
        result = build_opensearch_filters(filters, None)
        assert result is not None

        filters_list = result["bool"]["must"]
        date_filter = {"range": {"source_created_at": {"lte": "2024-12-31"}}}
        assert date_filter in filters_list

    def test_slack_provenance_filter(self):
        """Test Slack provenance filtering."""
        filters = SearchFilters(sources=[DocumentSource.SLACK], provenance="team-platform")
        result = build_opensearch_filters(filters, None)
        assert result is not None

        filters_list = result["bool"]["must"]
        provenance_filter = {
            "bool": {
                "should": [
                    {"term": {"metadata.channel_id.keyword": "team-platform"}},
                    {"term": {"metadata.channel_name.keyword": "team-platform"}},
                ]
            }
        }
        assert provenance_filter in filters_list

    def test_github_provenance_filter(self):
        """Test GitHub provenance filtering."""
        filters = SearchFilters(sources=[DocumentSource.GITHUB_PRS], provenance="my-repo")
        result = build_opensearch_filters(filters, None)
        assert result is not None

        filters_list = result["bool"]["must"]
        provenance_filter = {"term": {"metadata.repository.keyword": "my-repo"}}
        assert provenance_filter in filters_list

    def test_linear_provenance_filter(self):
        """Test Linear provenance filtering."""
        filters = SearchFilters(sources=[DocumentSource.LINEAR], provenance="Engineering")
        result = build_opensearch_filters(filters, None)
        assert result is not None

        filters_list = result["bool"]["must"]
        provenance_filter = {"term": {"metadata.team_name.keyword": "Engineering"}}
        assert provenance_filter in filters_list

    def test_provenance_with_multiple_sources_raises_error(self):
        """Test that provenance with multiple sources raises error."""
        filters = SearchFilters(
            sources=[DocumentSource.SLACK, DocumentSource.GITHUB_PRS], provenance="test"
        )

        with pytest.raises(
            ValueError, match="Provenance filtering is only supported for a single source"
        ):
            build_opensearch_filters(filters, None)

    def test_provenance_with_unsupported_source_raises_error(self):
        """Test that provenance with unsupported source raises error."""
        filters = SearchFilters(sources=[DocumentSource.NOTION], provenance="test")

        with pytest.raises(ValueError, match="Provenance filtering is not supported for source"):
            build_opensearch_filters(filters, None)


class TestBuildPostgresFilters:
    """Test PostgreSQL filter building."""

    def test_empty_filters_with_no_permission_token(self):
        """Test empty filters with no permission token."""
        filters = SearchFilters()
        where_clause, params = build_postgres_filters(filters, None)

        assert where_clause == "dp.permission_policy = 'tenant'"
        assert params == []

    def test_empty_filters_with_permission_token(self):
        """Test empty filters with permission token but no audience defaults to tenant only."""
        filters = SearchFilters()
        permission_token = "e:user@example.com"
        where_clause, params = build_postgres_filters(filters, permission_token)

        # Without permission_audience="private", should only return tenant docs
        assert where_clause == "dp.permission_policy = 'tenant'"
        assert params == []

    def test_empty_filters_with_permission_token_and_private_audience(self):
        """Test empty filters with permission token and private audience."""
        filters = SearchFilters()
        permission_token = "e:user@example.com"
        where_clause, params = build_postgres_filters(
            filters, permission_token, permission_audience="private"
        )

        expected_clause = "(dp.permission_policy = 'tenant' OR\n         (dp.permission_policy = 'private' AND $1::text = ANY(dp.permission_allowed_tokens)))"
        assert where_clause == expected_clause
        assert params == [permission_token]

    def test_document_id_filter_ignores_others(self):
        """Test that document_id filter ignores all other filters."""
        filters = SearchFilters(
            document_id="doc123", sources=[DocumentSource.SLACK], date_from="2024-01-01"
        )
        where_clause, params = build_postgres_filters(filters, None)

        assert where_clause == "c.document_id = $1"
        assert params == ["doc123"]

    def test_single_source_filter(self):
        """Test single source filtering."""
        filters = SearchFilters(sources=[DocumentSource.SLACK])
        where_clause, params = build_postgres_filters(filters, None)

        assert "d.source = $1" in where_clause
        assert "dp.permission_policy = 'tenant'" in where_clause
        assert params == ["slack"]

    def test_multiple_sources_filter(self):
        """Test multiple sources filtering."""
        filters = SearchFilters(sources=[DocumentSource.SLACK, DocumentSource.GITHUB_PRS])
        where_clause, params = build_postgres_filters(filters, None)

        assert "d.source = ANY($1::varchar[])" in where_clause
        assert params == [["slack", "github"]]

    def test_date_range_filters(self):
        """Test date range filtering."""
        filters = SearchFilters(date_from="2024-01-01", date_to="2024-12-31")

        from datetime import date
        from unittest.mock import patch

        with patch("src.mcp.tools.filters.validate_and_convert_date") as mock_validate:
            mock_validate.side_effect = [date(2024, 1, 1), date(2024, 12, 31)]

            where_clause, params = build_postgres_filters(filters, None)

            assert "d.source_created_at::date >= $1" in where_clause
            assert "d.source_created_at::date <= $2" in where_clause
            assert len(params) == 2  # 2 dates only (no permission token since None passed)

    def test_slack_provenance_filter(self):
        """Test Slack provenance filtering in PostgreSQL."""
        filters = SearchFilters(sources=[DocumentSource.SLACK], provenance="team-platform")
        where_clause, params = build_postgres_filters(filters, None)

        assert "d.metadata @> jsonb_build_object('channel_id', $2::text)" in where_clause
        assert "d.metadata @> jsonb_build_object('channel_name', $2::text)" in where_clause
        assert params == ["slack", "team-platform"]

    def test_github_provenance_filter(self):
        """Test GitHub provenance filtering in PostgreSQL."""
        filters = SearchFilters(sources=[DocumentSource.GITHUB_PRS], provenance="my-repo")
        where_clause, params = build_postgres_filters(filters, None)

        assert "d.metadata @> jsonb_build_object('repository', $2::text)" in where_clause
        assert params == ["github", "my-repo"]

    def test_linear_provenance_filter(self):
        """Test Linear provenance filtering in PostgreSQL."""
        filters = SearchFilters(sources=[DocumentSource.LINEAR], provenance="Engineering")
        where_clause, params = build_postgres_filters(filters, None)

        assert "d.metadata @> jsonb_build_object('team_name', $2::text)" in where_clause
        assert params == ["linear", "Engineering"]

    def test_provenance_with_multiple_sources_raises_error(self):
        """Test that provenance with multiple sources raises error."""
        filters = SearchFilters(
            sources=[DocumentSource.SLACK, DocumentSource.GITHUB_PRS], provenance="test"
        )

        with pytest.raises(
            ValueError, match="Provenance filtering is only supported for a single source"
        ):
            build_postgres_filters(filters, None)


class TestBuildTurbopufferFilters:
    """Test Turbopuffer filter building."""

    def test_empty_filters_with_no_permission_token(self):
        """Test empty filters with no permission token."""
        filters = SearchFilters()
        result = build_turbopuffer_filters(filters, None)

        expected = ("permission_policy", "Eq", "tenant")
        assert result == expected

    def test_empty_filters_with_permission_token(self):
        """Test empty filters with permission token but no audience defaults to tenant only."""
        filters = SearchFilters()
        permission_token = "e:user@example.com"
        result = build_turbopuffer_filters(filters, permission_token)

        # Without permission_audience="private", should only return tenant docs
        expected = ("permission_policy", "Eq", "tenant")
        assert result == expected

    def test_empty_filters_with_permission_token_and_private_audience(self):
        """Test empty filters with permission token and private audience."""
        filters = SearchFilters()
        permission_token = "e:user@example.com"
        result = build_turbopuffer_filters(filters, permission_token, permission_audience="private")

        expected: tuple[str, list[Any]] = (
            "Or",
            [
                ("permission_policy", "Eq", "tenant"),
                (
                    "And",
                    [
                        ("permission_policy", "Eq", "private"),
                        ("permission_allowed_tokens", "Contains", permission_token),
                    ],
                ),
            ],
        )
        assert result == expected

    def test_document_id_filter_ignores_others(self):
        """Test that document_id filter ignores all other filters."""
        filters = SearchFilters(
            document_id="doc123", sources=[DocumentSource.SLACK], date_from="2024-01-01"
        )
        result = build_turbopuffer_filters(filters, None)

        expected = ("document_id", "Eq", "doc123")
        assert result == expected

    def test_single_source_filter(self):
        """Test single source filtering."""
        filters = SearchFilters(sources=[DocumentSource.SLACK])
        result = build_turbopuffer_filters(filters, None)

        expected = ("And", [("source", "Eq", "slack"), ("permission_policy", "Eq", "tenant")])
        assert result == expected

    def test_multiple_sources_filter(self):
        """Test multiple sources filtering."""
        filters = SearchFilters(sources=[DocumentSource.SLACK, DocumentSource.GITHUB_PRS])
        result = build_turbopuffer_filters(filters, None)
        assert result is not None

        # Should be an And condition with source Or condition and permission
        assert result[0] == "And"
        conditions = result[1]

        # Find the source condition
        source_condition = next(c for c in conditions if c[0] == "Or")
        assert source_condition == (
            "Or",
            [
                ("source", "Eq", "slack"),
                ("source", "Eq", "github"),
            ],
        )

    def test_date_range_filters(self):
        """Test date range filtering."""
        filters = SearchFilters(date_from="2024-01-01", date_to="2024-12-31")

        from unittest.mock import patch

        with patch("src.mcp.tools.filters.validate_and_convert_date") as mock_validate:
            mock_validate.side_effect = [date(2024, 1, 1), date(2024, 12, 31)]

            result = build_turbopuffer_filters(filters, None)
            assert result is not None

            # Should have And condition with date filters and permission
            assert result[0] == "And"
            conditions = result[1]

            # Should have gte and lte conditions
            gte_condition = ("source_created_at", "Gte", "2024-01-01")
            lte_condition = ("source_created_at", "Lte", "2024-12-31")
            permission_condition = ("permission_policy", "Eq", "tenant")

            assert gte_condition in conditions
            assert lte_condition in conditions
            assert permission_condition in conditions

    def test_slack_provenance_filter(self):
        """Test Slack provenance filtering."""
        filters = SearchFilters(sources=[DocumentSource.SLACK], provenance="team-platform")
        result = build_turbopuffer_filters(filters, None)
        assert result is not None

        assert result[0] == "And"
        conditions = result[1]

        # Should have source, provenance, and permission filters
        source_condition = ("source", "Eq", "slack")
        provenance_condition = (
            "Or",
            [
                ("slack_channel_id", "Eq", "team-platform"),
                ("slack_channel_name", "Eq", "team-platform"),
            ],
        )
        permission_condition = ("permission_policy", "Eq", "tenant")

        assert source_condition in conditions
        assert provenance_condition in conditions
        assert permission_condition in conditions

    def test_github_provenance_filter(self):
        """Test GitHub provenance filtering."""
        filters = SearchFilters(sources=[DocumentSource.GITHUB_PRS], provenance="my-repo")
        result = build_turbopuffer_filters(filters, None)
        assert result is not None

        conditions = result[1]
        provenance_condition = ("github_repository", "Eq", "my-repo")
        assert provenance_condition in conditions

    def test_linear_provenance_filter(self):
        """Test Linear provenance filtering."""
        filters = SearchFilters(sources=[DocumentSource.LINEAR], provenance="Engineering")
        result = build_turbopuffer_filters(filters, None)
        assert result is not None

        conditions = result[1]
        provenance_condition = ("linear_team_name", "Eq", "Engineering")
        assert provenance_condition in conditions

    def test_provenance_with_multiple_sources_raises_error(self):
        """Test that provenance with multiple sources raises error."""
        filters = SearchFilters(
            sources=[DocumentSource.SLACK, DocumentSource.GITHUB_PRS], provenance="test"
        )

        with pytest.raises(
            ValueError, match="Provenance filtering is only supported for a single source"
        ):
            build_turbopuffer_filters(filters, None)

    def test_provenance_with_unsupported_source_raises_error(self):
        """Test that provenance with unsupported source raises error."""
        filters = SearchFilters(sources=[DocumentSource.NOTION], provenance="test")

        with pytest.raises(ValueError, match="Provenance filtering is not supported for source"):
            build_turbopuffer_filters(filters, None)


class TestGetFilterDescription:
    """Test filter description utility."""

    def test_get_filter_description(self):
        """Test that filter description contains expected information."""
        description = get_filter_description()

        assert "Filtering options:" in description
        assert "sources:" in description
        assert "date_from/date_to:" in description
        assert "provenance:" in description
        assert "document_id:" in description

        # Check that it mentions specific sources
        assert "slack" in description
        assert "github" in description
        assert "linear" in description

        # Check that it mentions provenance requirements
        assert "Specify exactly one source if you are using provenance!" in description
