"""Tests for citation resolver and URL deduplication."""

from unittest.mock import AsyncMock, patch

import pytest

from connectors.base.document_source import DocumentSource, DocumentWithSourceAndMetadata
from src.mcp.api.citation_resolver import replace_citations_with_deeplinks


@pytest.mark.asyncio
async def test_same_url_gets_same_citation_number():
    """Test that multiple citations to the same URL get the same citation number."""
    # Answer with two different documents that resolve to the same URL
    answer = "Feature A[doc1|excerpt1] and Feature B[doc2|excerpt2] are related."

    # Mock documents
    documents = {
        "doc1": DocumentWithSourceAndMetadata(
            id="doc1",
            source=DocumentSource.SLACK,
            metadata={"channel_id": "C123", "ts": "1234567890.123456"},
        ),
        "doc2": DocumentWithSourceAndMetadata(
            id="doc2",
            source=DocumentSource.SLACK,
            metadata={"channel_id": "C123", "ts": "1234567890.123456"},
        ),
    }

    mock_pool = AsyncMock()

    with (
        patch("src.mcp.api.citation_resolver.fetch_documents_batch") as mock_fetch,
        patch("src.mcp.api.citation_resolver.CitationResolver.resolve_citation") as mock_resolve,
    ):
        mock_fetch.return_value = documents
        mock_resolve.return_value = "https://slack.com/archives/C123/p1234567890123456"

        result = await replace_citations_with_deeplinks(
            answer=answer, db_pool=mock_pool, tenant_id="test-tenant"
        )

        # Both citations should have number [1] since they resolve to same URL
        assert "[[1]]" in result
        assert "[[2]]" not in result
        assert result.count("[[1]]") == 2


@pytest.mark.asyncio
async def test_different_urls_get_different_citation_numbers():
    """Test that citations to different URLs get different citation numbers."""
    answer = "Feature A[doc1|excerpt1] and Feature B[doc2|excerpt2] are different."

    documents = {
        "doc1": DocumentWithSourceAndMetadata(
            id="doc1",
            source=DocumentSource.SLACK,
            metadata={"channel_id": "C123", "ts": "1111111111.111111"},
        ),
        "doc2": DocumentWithSourceAndMetadata(
            id="doc2",
            source=DocumentSource.SLACK,
            metadata={"channel_id": "C456", "ts": "2222222222.222222"},
        ),
    }

    urls = {
        ("doc1", "excerpt1"): "https://slack.com/archives/C123/p1111111111111111",
        ("doc2", "excerpt2"): "https://slack.com/archives/C456/p2222222222222222",
    }

    mock_pool = AsyncMock()

    with (
        patch("src.mcp.api.citation_resolver.fetch_documents_batch") as mock_fetch,
        patch("src.mcp.api.citation_resolver.CitationResolver.resolve_citation") as mock_resolve,
    ):
        mock_fetch.return_value = documents

        def resolve_side_effect(doc, excerpt, *args, **kwargs):
            return urls.get((doc.id, excerpt), "")

        mock_resolve.side_effect = resolve_side_effect

        result = await replace_citations_with_deeplinks(
            answer=answer, db_pool=mock_pool, tenant_id="test-tenant"
        )

        # Should have both [1] and [2] for different URLs
        assert "[[1]]" in result
        assert "[[2]]" in result
        assert result.count("[[1]]") == 1
        assert result.count("[[2]]") == 1


@pytest.mark.asyncio
async def test_citation_numbering_is_sequential():
    """Test that citation numbers are assigned sequentially."""
    answer = "A[doc1|ex1], B[doc2|ex2], C[doc3|ex3], D[doc4|ex4]."

    documents: dict[str, DocumentWithSourceAndMetadata] = {
        f"doc{i}": DocumentWithSourceAndMetadata(
            id=f"doc{i}",
            source=DocumentSource.SLACK,
            metadata={},
        )
        for i in range(1, 5)
    }

    urls = {
        ("doc1", "ex1"): "https://example.com/1",
        ("doc2", "ex2"): "https://example.com/2",
        ("doc3", "ex3"): "https://example.com/3",
        ("doc4", "ex4"): "https://example.com/4",
    }

    mock_pool = AsyncMock()

    with (
        patch("src.mcp.api.citation_resolver.fetch_documents_batch") as mock_fetch,
        patch("src.mcp.api.citation_resolver.CitationResolver.resolve_citation") as mock_resolve,
    ):
        mock_fetch.return_value = documents

        def resolve_side_effect(doc, excerpt, *args, **kwargs):
            return urls.get((doc.id, excerpt), "")

        mock_resolve.side_effect = resolve_side_effect

        result = await replace_citations_with_deeplinks(
            answer=answer, db_pool=mock_pool, tenant_id="test-tenant"
        )

        # Citations should be numbered in order of appearance
        assert (
            result
            == "A[[1]](https://example.com/1), B[[2]](https://example.com/2), C[[3]](https://example.com/3), D[[4]](https://example.com/4)."
        )


@pytest.mark.asyncio
async def test_same_url_different_excerpts_same_number():
    """Test that same URL with different excerpts gets the same citation number."""
    # Same document, different excerpts
    answer = "First mention[doc1|excerpt1] and second mention[doc1|excerpt2]."

    documents = {
        "doc1": DocumentWithSourceAndMetadata(
            id="doc1",
            source=DocumentSource.SLACK,
            metadata={"channel_id": "C123", "ts": "1234567890.123456"},
        )
    }

    mock_pool = AsyncMock()

    with (
        patch("src.mcp.api.citation_resolver.fetch_documents_batch") as mock_fetch,
        patch("src.mcp.api.citation_resolver.CitationResolver.resolve_citation") as mock_resolve,
    ):
        mock_fetch.return_value = documents
        # Both excerpts resolve to the same URL
        mock_resolve.return_value = "https://slack.com/archives/C123/p1234567890123456"

        result = await replace_citations_with_deeplinks(
            answer=answer, db_pool=mock_pool, tenant_id="test-tenant"
        )

        # Both should get [1] since URL is the same
        assert result.count("[[1]]") == 2
        assert "[[2]]" not in result


@pytest.mark.asyncio
async def test_slack_output_format():
    """Test that Slack output format uses <url|[number]> syntax."""
    answer = "Feature A[doc1|excerpt1] was released."

    documents: dict[str, DocumentWithSourceAndMetadata] = {
        "doc1": DocumentWithSourceAndMetadata(id="doc1", source=DocumentSource.SLACK, metadata={})
    }

    mock_pool = AsyncMock()

    with (
        patch("src.mcp.api.citation_resolver.fetch_documents_batch") as mock_fetch,
        patch("src.mcp.api.citation_resolver.CitationResolver.resolve_citation") as mock_resolve,
    ):
        mock_fetch.return_value = documents
        mock_resolve.return_value = "https://example.com/doc1"

        result = await replace_citations_with_deeplinks(
            answer=answer,
            db_pool=mock_pool,
            tenant_id="test-tenant",
            output_format="slack",
        )

        # Should use Slack format
        assert "<https://example.com/doc1|[1]>" in result
        assert "[[1]]" not in result


@pytest.mark.asyncio
async def test_multiple_same_urls_deduplicated_in_slack_format():
    """Test URL deduplication works in Slack format."""
    answer = "Feature A[doc1|ex1] and Feature B[doc2|ex2] are related."

    documents: dict[str, DocumentWithSourceAndMetadata] = {
        "doc1": DocumentWithSourceAndMetadata(id="doc1", source=DocumentSource.SLACK, metadata={}),
        "doc2": DocumentWithSourceAndMetadata(id="doc2", source=DocumentSource.SLACK, metadata={}),
    }

    mock_pool = AsyncMock()

    with (
        patch("src.mcp.api.citation_resolver.fetch_documents_batch") as mock_fetch,
        patch("src.mcp.api.citation_resolver.CitationResolver.resolve_citation") as mock_resolve,
    ):
        mock_fetch.return_value = documents
        # Both resolve to same URL
        mock_resolve.return_value = "https://example.com/same"

        result = await replace_citations_with_deeplinks(
            answer=answer,
            db_pool=mock_pool,
            tenant_id="test-tenant",
            output_format="slack",
        )

        # Both should use [1]
        assert result.count("<https://example.com/same|[1]>") == 2
        assert "[2]" not in result


@pytest.mark.asyncio
async def test_url_deduplication_with_citation_collapse():
    """Test that URL deduplication and citation collapse work together."""
    # Two citations with same URL right next to each other
    answer = "Feature[doc1|ex1][doc2|ex2] works."

    documents: dict[str, DocumentWithSourceAndMetadata] = {
        "doc1": DocumentWithSourceAndMetadata(id="doc1", source=DocumentSource.SLACK, metadata={}),
        "doc2": DocumentWithSourceAndMetadata(id="doc2", source=DocumentSource.SLACK, metadata={}),
    }

    mock_pool = AsyncMock()

    with (
        patch("src.mcp.api.citation_resolver.fetch_documents_batch") as mock_fetch,
        patch("src.mcp.api.citation_resolver.CitationResolver.resolve_citation") as mock_resolve,
    ):
        mock_fetch.return_value = documents
        # Both resolve to same URL
        mock_resolve.return_value = "https://example.com/same"

        result = await replace_citations_with_deeplinks(
            answer=answer, db_pool=mock_pool, tenant_id="test-tenant"
        )

        # Should get two [1] citations, then collapsed to one
        # Final result should have only one [[1]]
        assert "[[1]]" in result
        assert result.count("[[1]]") == 1
        assert "[[2]]" not in result
