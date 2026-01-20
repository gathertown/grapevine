"""Tests for permission_audience filtering in search operations."""

from connectors.base.document_source import DocumentSource
from src.mcp.tools.filters import (
    SearchFilters,
    build_opensearch_filters,
    build_postgres_filters,
    build_turbopuffer_filters,
)
from src.permissions.models import PermissionAudience


class TestPermissionAudienceFiltering:
    """Test permission_audience filtering across different backends."""

    def test_opensearch_public_audience_filters_to_tenant_only(self):
        """Test that public audience only returns tenant documents in OpenSearch."""
        filters = SearchFilters()
        permission_token = "e:user@example.com"
        permission_audience: PermissionAudience = "tenant"

        result = build_opensearch_filters(filters, permission_token, permission_audience)

        # Should only include tenant documents
        assert result == {"term": {"permission_policy": "tenant"}}

    def test_opensearch_private_audience_includes_private_docs(self):
        """Test that private audience includes private documents user has access to."""
        filters = SearchFilters()
        permission_token = "e:user@example.com"
        permission_audience: PermissionAudience = "private"

        result = build_opensearch_filters(filters, permission_token, permission_audience)

        # Should include both tenant and private documents
        assert result == {
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

    def test_opensearch_no_audience_defaults_to_tenant_only(self):
        """Test that missing audience defaults to tenant only (public behavior)."""
        filters = SearchFilters()
        permission_token = "e:user@example.com"
        permission_audience = None

        result = build_opensearch_filters(filters, permission_token, permission_audience)

        # Should only include tenant documents (even though token is present)
        assert result == {"term": {"permission_policy": "tenant"}}

    def test_opensearch_no_token_public_audience(self):
        """Test public audience with no permission token."""
        filters = SearchFilters()
        permission_token = None
        permission_audience: PermissionAudience = "tenant"

        result = build_opensearch_filters(filters, permission_token, permission_audience)

        # Should only include tenant documents
        assert result == {"term": {"permission_policy": "tenant"}}

    def test_opensearch_no_token_no_audience(self):
        """Test missing token and audience defaults to tenant only."""
        filters = SearchFilters()
        permission_token = None
        permission_audience = None

        result = build_opensearch_filters(filters, permission_token, permission_audience)

        # Should only include tenant documents
        assert result == {"term": {"permission_policy": "tenant"}}

    def test_postgres_public_audience_filters_to_tenant_only(self):
        """Test that public audience only returns tenant documents in PostgreSQL."""
        filters = SearchFilters()
        permission_token = "e:user@example.com"
        permission_audience: PermissionAudience = "tenant"

        where_clause, params = build_postgres_filters(
            filters, permission_token, permission_audience
        )

        # Should only include tenant documents
        assert "dp.permission_policy = 'tenant'" in where_clause
        assert "dp.permission_policy = 'private'" not in where_clause
        assert permission_token not in params

    def test_postgres_private_audience_includes_private_docs(self):
        """Test that private audience includes private documents user has access to."""
        filters = SearchFilters()
        permission_token = "e:user@example.com"
        permission_audience: PermissionAudience = "private"

        where_clause, params = build_postgres_filters(
            filters, permission_token, permission_audience
        )

        # Should include both tenant and private documents
        assert "dp.permission_policy = 'tenant'" in where_clause
        assert "dp.permission_policy = 'private'" in where_clause
        assert permission_token in params

    def test_postgres_no_audience_defaults_to_tenant_only(self):
        """Test that missing audience defaults to tenant only (public behavior)."""
        filters = SearchFilters()
        permission_token = "e:user@example.com"
        permission_audience = None

        where_clause, params = build_postgres_filters(
            filters, permission_token, permission_audience
        )

        # Should only include tenant documents (even though token is present)
        assert "dp.permission_policy = 'tenant'" in where_clause
        assert "dp.permission_policy = 'private'" not in where_clause
        assert permission_token not in params

    def test_turbopuffer_public_audience_filters_to_tenant_only(self):
        """Test that public audience only returns tenant documents in Turbopuffer."""
        filters = SearchFilters()
        permission_token = "e:user@example.com"
        permission_audience: PermissionAudience = "tenant"

        result = build_turbopuffer_filters(filters, permission_token, permission_audience)

        # Should only include tenant documents
        assert result == ("permission_policy", "Eq", "tenant")

    def test_turbopuffer_private_audience_includes_private_docs(self):
        """Test that private audience includes private documents user has access to."""
        filters = SearchFilters()
        permission_token = "e:user@example.com"
        permission_audience: PermissionAudience = "private"

        result = build_turbopuffer_filters(filters, permission_token, permission_audience)

        # Should include both tenant and private documents
        assert result == (
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

    def test_turbopuffer_no_audience_defaults_to_tenant_only(self):
        """Test that missing audience defaults to tenant only (public behavior)."""
        filters = SearchFilters()
        permission_token = "e:user@example.com"
        permission_audience = None

        result = build_turbopuffer_filters(filters, permission_token, permission_audience)

        # Should only include tenant documents (even though token is present)
        assert result == ("permission_policy", "Eq", "tenant")

    def test_combined_filters_with_public_audience(self):
        """Test that public audience works correctly with other filters."""
        filters = SearchFilters(
            sources=[DocumentSource.SLACK, DocumentSource.GITHUB_PRS],
            date_from="2025-01-01",
        )
        permission_token = "e:user@example.com"
        permission_audience: PermissionAudience = "tenant"

        result = build_opensearch_filters(filters, permission_token, permission_audience)
        assert result is not None

        # Should have multiple filters including audience filter
        assert "bool" in result
        assert "must" in result["bool"]
        filters_list = result["bool"]["must"]

        # Should contain source filter, date filter, and permission filter
        assert any("terms" in f and "source" in f["terms"] for f in filters_list)
        assert any("range" in f and "source_created_at" in f["range"] for f in filters_list)
        assert any("term" in f and "permission_policy" in f["term"] for f in filters_list)

        # Permission filter should be tenant only
        permission_filter = next(
            f for f in filters_list if "term" in f and "permission_policy" in f["term"]
        )
        assert permission_filter == {"term": {"permission_policy": "tenant"}}

    def test_combined_filters_with_private_audience(self):
        """Test that private audience works correctly with other filters."""
        filters = SearchFilters(
            sources=[DocumentSource.SLACK],
            date_from="2025-01-01",
        )
        permission_token = "e:user@example.com"
        permission_audience: PermissionAudience = "private"

        result = build_opensearch_filters(filters, permission_token, permission_audience)
        assert result is not None

        # Should have multiple filters
        assert "bool" in result
        assert "must" in result["bool"]
        filters_list = result["bool"]["must"]

        # Should contain source filter, date filter, and permission filter
        assert any("term" in f and "source" in f["term"] for f in filters_list)
        assert any("range" in f and "source_created_at" in f["range"] for f in filters_list)

        # Permission filter should allow both tenant and private
        permission_filter = next(
            f
            for f in filters_list
            if "bool" in f and "should" in f["bool"] and "permission_policy" in str(f)
        )
        assert permission_filter == {
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
