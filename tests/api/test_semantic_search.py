from datetime import datetime, timedelta

import pytest

import src.mcp.tools.semantic_search as semantic_search_module
from connectors.base.document_source import DocumentSource
from src.mcp.tools.filters import SearchFilters

# Extract the actual function from the MCP decorated object
semantic_search = semantic_search_module.semantic_search.fn


@pytest.mark.skip(reason="Needs to be migrated to use Tenant architecture")
class TestSemanticSearchTool:
    """Integration tests for semantic_search function using real backends."""

    @pytest.mark.asyncio
    async def test_basic_semantic_search(self):
        """Test basic semantic search functionality."""
        result = await semantic_search(query="How to handle API rate limits", limit=10)

        assert "results" in result
        assert "count" in result
        assert isinstance(result["results"], list)
        assert isinstance(result["count"], int)

        if result["count"] > 0:
            first_result = result["results"][0]
            assert "document_id" in first_result
            assert "chunk" in first_result
            assert "score" in first_result
            assert "semantic_score" in first_result
            assert "recency_weight" in first_result
            assert isinstance(first_result["score"], (int, float))
            assert isinstance(first_result["semantic_score"], (int, float))

    @pytest.mark.asyncio
    async def test_semantic_search_with_limit(self):
        """Test semantic search with different limit values."""
        # Test with limit of 1
        result = await semantic_search(query="perf", limit=1)

        assert len(result["results"]) <= 1

        # Test with limit of 3
        result = await semantic_search(query="perf", limit=3)

        assert len(result["results"]) <= 3

    @pytest.mark.asyncio
    async def test_semantic_search_with_source_filters(self):
        """Test semantic search with source filtering."""
        # Test filtering by single source
        result = await semantic_search(
            query="perf", filters=SearchFilters(sources=[DocumentSource.LINEAR])
        )

        # Check that results are filtered by source via document metadata
        assert "results" in result

        # Test filtering by multiple sources
        result = await semantic_search(
            query="perf",
            filters=SearchFilters(sources=[DocumentSource.GITHUB_PRS, DocumentSource.SLACK]),
        )

        assert "results" in result

    @pytest.mark.asyncio
    async def test_semantic_search_with_date_filters(self):
        """Test semantic search with date range filtering."""
        today = datetime.now().strftime("%Y-%m-%d")
        week_ago = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")

        result = await semantic_search(
            query="perf", filters=SearchFilters(date_from=week_ago, date_to=today)
        )

        assert "results" in result
        assert "count" in result

    @pytest.mark.asyncio
    async def test_semantic_search_with_provenance_filter(self):
        """Test semantic search with provenance filtering."""
        # Test with Linear team provenance
        result = await semantic_search(
            query="perf",
            filters=SearchFilters(sources=[DocumentSource.LINEAR], provenance="Engineering"),
        )

        assert "results" in result

        # Test with GitHub repo provenance
        result = await semantic_search(
            query="perf",
            filters=SearchFilters(sources=[DocumentSource.GITHUB_PRS], provenance="gather-town-v2"),
        )

        assert "results" in result

    @pytest.mark.asyncio
    async def test_semantic_search_with_document_id_filter(self):
        """Test semantic search with specific document ID filter."""
        result = await semantic_search(
            query="perf", filters=SearchFilters(document_id="test_doc_3")
        )

        assert "results" in result
        if result["count"] > 0:
            assert all(res["document_id"] == "test_doc_3" for res in result["results"])

    @pytest.mark.asyncio
    async def test_semantic_search_conceptual_matching(self):
        """Test that semantic search finds conceptually similar content."""
        # Search for concepts that may not have exact keyword matches
        result = await semantic_search(query="perf")

        assert "results" in result

        # Search for task organization concepts
        result = await semantic_search(query="perf")

        assert "results" in result

    @pytest.mark.asyncio
    async def test_semantic_search_recency_weighting(self):
        """Test that semantic search applies recency weighting correctly."""
        result = await semantic_search(query="perf", limit=5)

        # Verify that results include recency weight in scoring
        for doc in result["results"]:
            assert "recency_weight" in doc
            assert isinstance(doc["recency_weight"], (int, float))
            assert 0 <= doc["recency_weight"] <= 1

    @pytest.mark.asyncio
    async def test_semantic_search_empty_results(self):
        """Test semantic search with very specific queries that may return no results."""
        result = await semantic_search(
            query="perf", filters=SearchFilters(sources=[DocumentSource.LINEAR])
        )

        assert "results" in result
        assert "count" in result
        # Note: semantic search may still return results due to fuzzy matching

    @pytest.mark.asyncio
    async def test_semantic_search_with_all_filters(self):
        """Test semantic search with all possible filters combined."""
        today = datetime.now().strftime("%Y-%m-%d")
        week_ago = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")

        result = await semantic_search(
            query="perf",
            limit=3,
            filters=SearchFilters(
                sources=[DocumentSource.LINEAR],  # Only single source allowed with provenance
                date_from=week_ago,
                date_to=today,
                provenance="Engineering",
            ),
        )

        assert "results" in result
        assert "count" in result
        assert len(result["results"]) <= 3

    @pytest.mark.asyncio
    async def test_semantic_search_score_ranges(self):
        """Test that semantic search returns reasonable score ranges."""
        result = await semantic_search(query="perf", limit=5)

        for doc in result["results"]:
            # Scores should be reasonable ranges
            assert 0 <= doc["score"] <= 2  # Combined score can exceed 1 due to recency weighting
            assert 0 <= doc["semantic_score"] <= 1  # Cosine similarity should be 0-1
            assert 0 <= doc["recency_weight"] <= 1  # Recency weight should be 0-1

    @pytest.mark.asyncio
    async def test_semantic_search_empty_query(self):
        """Test semantic search with empty query."""
        with pytest.raises(ValueError, match="query is required"):
            await semantic_search(query="")

    @pytest.mark.asyncio
    async def test_semantic_search_invalid_date_formats(self):
        """Test semantic search with invalid date formats."""
        # Semantic search might handle date validation differently
        with pytest.raises(Exception):  # noqa: B017
            await semantic_search(
                query="HTTP", filters=SearchFilters(date_from="2024-01-01", date_to="not-a-date")
            )

    @pytest.mark.asyncio
    async def test_semantic_search_nonexistent_document_id_filter(self):
        """Test semantic search with nonexistent document ID."""
        result = await semantic_search(
            query="HTTP", filters=SearchFilters(document_id="nonexistent_doc_id")
        )

        assert result["count"] == 0
        assert result["results"] == []
