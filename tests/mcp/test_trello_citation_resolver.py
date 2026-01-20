"""Tests for Trello citation resolver."""

from typing import cast

import pytest

from connectors.base.document_source import DocumentSource, DocumentWithSourceAndMetadata
from connectors.trello.trello_card_document import TrelloCardDocumentMetadata
from connectors.trello.trello_citation_resolver import TrelloCitationResolver
from src.mcp.api.citation_resolver import CitationResolver


@pytest.mark.asyncio
async def test_trello_citation_resolver():
    """Test that TrelloCitationResolver extracts URL from metadata."""
    resolver = TrelloCitationResolver()

    # Create a mock document with Trello card metadata
    document = DocumentWithSourceAndMetadata(
        id="test-doc-id",
        source=DocumentSource.TRELLO,
        metadata=TrelloCardDocumentMetadata(
            card_id="abc123",
            card_name="Test Card",
            board_id="board123",
            board_name="Test Board",
            list_id="list123",
            list_name="To Do",
            url="https://trello.com/c/abc123/test-card",
            source_created_at="2024-01-01T00:00:00Z",
            assigned_members_text="John Doe",
            labels_text="bug, urgent",
        ),
    )

    # Mock citation resolver (not needed for this test)
    mock_citation_resolver = cast(CitationResolver, None)

    # Resolve citation
    url = await resolver.resolve_citation(
        document, excerpt="some excerpt", resolver=mock_citation_resolver
    )

    # Verify the URL is extracted correctly
    assert url == "https://trello.com/c/abc123/test-card"


@pytest.mark.asyncio
async def test_trello_citation_resolver_missing_url():
    """Test that TrelloCitationResolver returns empty string when URL is missing."""
    resolver = TrelloCitationResolver()

    # Create a mock document without URL
    document = DocumentWithSourceAndMetadata(
        id="test-doc-id",
        source=DocumentSource.TRELLO,
        metadata=TrelloCardDocumentMetadata(
            card_id="abc123",
            card_name="Test Card",
            board_id="board123",
            board_name="Test Board",
            list_id="list123",
            list_name="To Do",
            url=None,  # Missing URL
            source_created_at="2024-01-01T00:00:00Z",
            assigned_members_text="",
            labels_text="",
        ),
    )

    # Mock citation resolver (not needed for this test)
    mock_citation_resolver = cast(CitationResolver, None)

    # Resolve citation
    url = await resolver.resolve_citation(
        document, excerpt="some excerpt", resolver=mock_citation_resolver
    )

    # Verify empty string is returned
    assert url == ""
