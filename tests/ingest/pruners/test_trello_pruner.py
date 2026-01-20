"""Tests for Trello card pruner."""

from connectors.base.doc_ids import get_trello_card_doc_id
from connectors.trello import TrelloPruner


class TestTrelloPruner:
    """Test suite for TrelloPruner."""

    def test_singleton_pattern(self):
        """Test that TrelloPruner follows singleton pattern."""
        pruner1 = TrelloPruner()
        pruner2 = TrelloPruner()
        assert pruner1 is pruner2

    def test_get_trello_card_doc_id(self):
        """Test Trello card document ID generation."""
        card_id = "abc123xyz"
        expected_doc_id = "trello_card_abc123xyz"
        assert get_trello_card_doc_id(card_id) == expected_doc_id

    def test_get_trello_card_doc_id_with_real_id(self):
        """Test Trello card document ID generation with realistic ID."""
        card_id = "5f3d8a1b2c4e5f6a7b8c9d0e"
        expected_doc_id = "trello_card_5f3d8a1b2c4e5f6a7b8c9d0e"
        assert get_trello_card_doc_id(card_id) == expected_doc_id
