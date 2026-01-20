from datetime import datetime, timedelta

import pytest

import src.mcp.tools.keyword_search as keyword_search_module
from connectors.base.document_source import DocumentSource
from src.mcp.tools.filters import SearchFilters

# Extract the actual function from the MCP decorated object
keyword_search = keyword_search_module.keyword_search.fn


@pytest.mark.skip(reason="Needs to be migrated to use Tenant architecture")
class TestKeywordSearchTool:
    """Integration tests for keyword_search function using real backends."""

    @pytest.mark.asyncio
    async def test_basic_keyword_search(self):
        """Test basic keyword search functionality."""
        result = await keyword_search(query="API rate limiting", limit=10)

        assert "results" in result
        assert "count" in result
        assert isinstance(result["results"], list)
        assert isinstance(result["count"], int)

        # Should find documents containing these terms
        if result["count"] > 0:
            first_result = result["results"][0]
            assert "id" in first_result
            assert "score" in first_result
            assert "source" in first_result
            assert "snippets" in first_result
            assert isinstance(first_result["snippets"], list)

    @pytest.mark.asyncio
    async def test_keyword_search_with_limit(self):
        """Test keyword search with different limit values."""
        # Test with limit of 1
        result = await keyword_search(query="HTTP", limit=1)

        assert len(result["results"]) <= 1

        # Test with limit of 5
        result = await keyword_search(query="HTTP", limit=5)

        assert len(result["results"]) <= 5

    @pytest.mark.asyncio
    async def test_keyword_search_with_source_filters(self):
        """Test keyword search with source filtering."""
        # Test filtering by single source
        result = await keyword_search(
            query="HTTP", filters=SearchFilters(sources=[DocumentSource.SLACK])
        )

        for doc in result["results"]:
            assert doc["source"] == DocumentSource.SLACK.value

        # Test filtering by multiple sources
        result = await keyword_search(
            query="HTTP",
            filters=SearchFilters(sources=[DocumentSource.GITHUB_PRS, DocumentSource.LINEAR]),
        )

        for doc in result["results"]:
            assert doc["source"] in [DocumentSource.GITHUB_PRS.value, DocumentSource.LINEAR.value]

    @pytest.mark.asyncio
    async def test_keyword_search_with_date_filters(self):
        """Test keyword search with date range filtering."""
        today = datetime.now().strftime("%Y-%m-%d")
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

        # Test date range filter
        result = await keyword_search(
            query="HTTP", filters=SearchFilters(date_from=yesterday, date_to=today)
        )

        assert "results" in result
        assert "count" in result

    @pytest.mark.asyncio
    async def test_keyword_search_with_provenance_filter(self):
        """Test keyword search with provenance filtering."""
        # Test with Slack channel provenance
        result = await keyword_search(
            query="Gather",
            filters=SearchFilters(sources=[DocumentSource.SLACK], provenance="general"),
        )

        assert len(result["results"]) > 0

        # Test with GitHub repo provenance
        result = await keyword_search(
            query="GS",
            filters=SearchFilters(sources=[DocumentSource.GITHUB_PRS], provenance="gather-town-v2"),
        )

        assert len(result["results"]) > 0

    @pytest.mark.asyncio
    async def test_keyword_search_with_document_id_filter(self):
        """Test keyword search with specific document ID filter."""
        result = await keyword_search(query="HTTP", filters=SearchFilters(document_id="test_doc_1"))

        assert "results" in result
        if result["count"] > 0:
            assert all(doc["id"] == "test_doc_1" for doc in result["results"])

    @pytest.mark.asyncio
    async def test_keyword_search_advanced_query_syntax(self):
        """Test keyword search with advanced query syntax."""
        # Test OR operator
        result = await keyword_search(query="API OR Linear")
        assert "results" in result

        # Test NOT operator
        result = await keyword_search(query="test NOT Linear")
        assert "results" in result

        # Test phrase search
        result = await keyword_search(query='"rate limiting"')
        assert "results" in result

        # Test wildcard search
        result = await keyword_search(query="docu*")
        assert "results" in result

    @pytest.mark.asyncio
    async def test_keyword_search_advanced_mode(self):
        """Test that advanced mode properly preserves OpenSearch operators."""
        # Test AND operator in advanced mode
        result_and = await keyword_search(query="error AND warning", advanced=True)
        assert "results" in result_and

        # Test OR operator in advanced mode
        result_or = await keyword_search(query="error OR warning", advanced=True)
        assert "results" in result_or

        # Test NOT operator in advanced mode
        result_not = await keyword_search(query="error NOT deprecated", advanced=True)
        assert "results" in result_not

        # Test mixed case operators (should still be recognized in advanced mode)
        result_mixed = await keyword_search(query="error and warning", advanced=True)
        assert "results" in result_mixed

        # Test grouping with operators
        result_grouped = await keyword_search(query="(error OR warning) AND api", advanced=True)
        assert "results" in result_grouped

        # Test plus/minus prefixes
        result_plus_minus = await keyword_search(query="+required -optional", advanced=True)
        assert "results" in result_plus_minus

        # Test field queries
        result_field = await keyword_search(query="content:error", advanced=True)
        assert "results" in result_field

    @pytest.mark.asyncio
    async def test_keyword_search_standard_mode(self):
        """Test that standard mode (advanced=false) does phrase boosting and doesn't treat operators as special."""
        # In standard mode, "AND" should be treated as a regular word, not an operator
        result_standard = await keyword_search(query="error AND warning", advanced=False)
        assert "results" in result_standard

        # Test that the same query behaves differently in standard vs advanced mode
        # Standard mode will look for documents containing the words "error", "AND", "warning"
        # while advanced mode requires both "error" and "warning"
        result_advanced = await keyword_search(query="error AND warning", advanced=True)
        assert "results" in result_advanced

        # Both should return results, but potentially different ones
        # This test mainly ensures no errors occur with the mode distinction

    @pytest.mark.asyncio
    async def test_keyword_search_quote_handling(self):
        """Test proper handling of quoted phrases in queries."""
        # Test fully quoted query
        result_full = await keyword_search(query='"API rate limiting"')
        assert "results" in result_full

        # Test mixed quoted/unquoted terms
        result_mixed = await keyword_search(query='error "rate limit" warning')
        assert "results" in result_mixed

        # Test quotes with operators
        result_quotes_ops = await keyword_search(query='"API error" OR "rate limit"')
        assert "results" in result_quotes_ops

        # Test nested quotes (should handle gracefully)
        result_nested = await keyword_search(query='"error with \\"quotes\\"" AND warning')
        assert "results" in result_nested

    @pytest.mark.asyncio
    async def test_keyword_search_default_operator_behavior(self):
        """Test that AND/OR variants use correct default_operator settings."""
        # Test simple multi-word query (should use both AND and OR variants)
        result = await keyword_search(query="database connection error")
        assert "results" in result
        assert "count" in result

        # The internal implementation should create both AND and OR variants
        # This test mainly ensures no errors occur with the new operator logic

    @pytest.mark.asyncio
    async def test_keyword_search_empty_results(self):
        """Test keyword search with queries that return no results."""
        result = await keyword_search(query="nonexistent_term_12345")

        assert "results" in result
        assert "count" in result
        assert result["count"] == 0
        assert result["results"] == []

    @pytest.mark.asyncio
    async def test_keyword_search_with_all_filters(self):
        """Test keyword search with all possible filters combined."""
        today = datetime.now().strftime("%Y-%m-%d")
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

        result = await keyword_search(
            query="test document",
            limit=5,
            filters=SearchFilters(
                sources=[DocumentSource.SLACK],  # Only single source allowed with provenance
                date_from=yesterday,
                date_to=today,
                provenance="general",
            ),
        )

        assert "results" in result
        assert "count" in result
        assert len(result["results"]) <= 5

    @pytest.mark.asyncio
    async def test_keyword_search_empty_query(self):
        """Test keyword search with empty query."""
        with pytest.raises(ValueError, match="query is required"):
            await keyword_search(query="")

    @pytest.mark.asyncio
    async def test_keyword_search_invalid_date_formats(self):
        """Test keyword search with invalid date formats."""
        # Test with invalid date format - should raise OpenSearch RequestError
        with pytest.raises(Exception):  # noqa: B017 Could be RequestError or other OpenSearch error
            await keyword_search(
                query="HTTP", filters=SearchFilters(date_from="invalid-date", date_to="2024-01-01")
            )

    @pytest.mark.asyncio
    async def test_keyword_search_nonexistent_document_id_filter(self):
        """Test keyword search with nonexistent document ID."""
        result = await keyword_search(
            query="HTTP", filters=SearchFilters(document_id="nonexistent_doc_id")
        )

        assert result["count"] == 0
        assert result["results"] == []
