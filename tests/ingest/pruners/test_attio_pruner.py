"""Tests for Attio entity pruner."""

from connectors.attio import AttioPruner, attio_pruner
from connectors.base.doc_ids import (
    get_attio_company_doc_id,
    get_attio_deal_doc_id,
    get_attio_person_doc_id,
)


class TestAttioPruner:
    """Test suite for AttioPruner."""

    def test_singleton_pattern(self):
        """Test that AttioPruner follows singleton pattern."""
        pruner1 = AttioPruner()
        pruner2 = AttioPruner()
        assert pruner1 is pruner2

    def test_singleton_instance_exported(self):
        """Test that the singleton instance is properly exported."""
        assert attio_pruner is not None
        assert isinstance(attio_pruner, AttioPruner)

    def test_singleton_instance_same_as_new(self):
        """Test that exported singleton is same as newly created instance."""
        new_pruner = AttioPruner()
        assert attio_pruner is new_pruner


class TestAttioDocIds:
    """Test suite for Attio document ID generation functions."""

    def test_get_attio_company_doc_id(self):
        """Test Attio company document ID generation."""
        record_id = "rec_abc123"
        expected_doc_id = "attio_company_rec_abc123"
        assert get_attio_company_doc_id(record_id) == expected_doc_id

    def test_get_attio_company_doc_id_with_uuid(self):
        """Test Attio company document ID generation with UUID format."""
        record_id = "853cfb93-63e7-4eed-82e4-50e4fa054e59"
        expected_doc_id = "attio_company_853cfb93-63e7-4eed-82e4-50e4fa054e59"
        assert get_attio_company_doc_id(record_id) == expected_doc_id

    def test_get_attio_person_doc_id(self):
        """Test Attio person document ID generation."""
        record_id = "rec_person456"
        expected_doc_id = "attio_person_rec_person456"
        assert get_attio_person_doc_id(record_id) == expected_doc_id

    def test_get_attio_person_doc_id_with_uuid(self):
        """Test Attio person document ID generation with UUID format."""
        record_id = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
        expected_doc_id = "attio_person_a1b2c3d4-e5f6-7890-abcd-ef1234567890"
        assert get_attio_person_doc_id(record_id) == expected_doc_id

    def test_get_attio_deal_doc_id(self):
        """Test Attio deal document ID generation."""
        record_id = "rec_deal789"
        expected_doc_id = "attio_deal_rec_deal789"
        assert get_attio_deal_doc_id(record_id) == expected_doc_id

    def test_get_attio_deal_doc_id_with_uuid(self):
        """Test Attio deal document ID generation with UUID format."""
        record_id = "12345678-90ab-cdef-1234-567890abcdef"
        expected_doc_id = "attio_deal_12345678-90ab-cdef-1234-567890abcdef"
        assert get_attio_deal_doc_id(record_id) == expected_doc_id
