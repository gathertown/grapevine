"""Tests for Figma entity pruner."""

from connectors.base.doc_ids import (
    get_figma_comment_doc_id,
    get_figma_file_doc_id,
)
from connectors.figma import FigmaPruner, figma_pruner, get_figma_entity_id


class TestFigmaPruner:
    """Test suite for FigmaPruner."""

    def test_singleton_pattern(self):
        """Test that FigmaPruner follows singleton pattern."""
        pruner1 = FigmaPruner()
        pruner2 = FigmaPruner()
        assert pruner1 is pruner2

    def test_singleton_instance_exported(self):
        """Test that the singleton instance is properly exported."""
        assert figma_pruner is not None
        assert isinstance(figma_pruner, FigmaPruner)

    def test_singleton_instance_same_as_new(self):
        """Test that exported singleton is same as newly created instance."""
        new_pruner = FigmaPruner()
        assert figma_pruner is new_pruner


class TestFigmaEntityIds:
    """Test suite for Figma entity ID generation."""

    def test_get_figma_entity_id_file(self):
        """Test Figma file entity ID generation."""
        file_key = "abc123XYZ"
        expected_entity_id = "figma_file_abc123XYZ"
        assert get_figma_entity_id("file", file_key) == expected_entity_id

    def test_get_figma_entity_id_comment(self):
        """Test Figma comment entity ID generation."""
        comment_id = "123456789"
        expected_entity_id = "figma_comment_123456789"
        assert get_figma_entity_id("comment", comment_id) == expected_entity_id

    def test_entity_id_matches_doc_id_format_file(self):
        """Test that entity ID format matches document ID format for files.

        This is critical for pruner to work correctly - the entity_id used
        in delete_entity must match the format used when storing artifacts.
        """
        file_key = "abc123XYZ"
        entity_id = get_figma_entity_id("file", file_key)
        doc_id = get_figma_file_doc_id(file_key)
        # Both should have the same "figma_file_{file_key}" format
        assert entity_id == doc_id

    def test_entity_id_matches_doc_id_format_comment(self):
        """Test that entity ID format matches document ID format for comments.

        This is critical for pruner to work correctly - the entity_id used
        in delete_entity must match the format used when storing artifacts.
        """
        comment_id = "123456789"
        entity_id = get_figma_entity_id("comment", comment_id)
        doc_id = get_figma_comment_doc_id(comment_id)
        # Both should have the same "figma_comment_{comment_id}" format
        assert entity_id == doc_id


class TestFigmaDocIds:
    """Test suite for Figma document ID generation functions."""

    def test_get_figma_file_doc_id(self):
        """Test Figma file document ID generation."""
        file_key = "abc123XYZ"
        expected_doc_id = "figma_file_abc123XYZ"
        assert get_figma_file_doc_id(file_key) == expected_doc_id

    def test_get_figma_file_doc_id_with_special_chars(self):
        """Test Figma file document ID generation with special characters."""
        file_key = "abcDEF123_-"
        expected_doc_id = "figma_file_abcDEF123_-"
        assert get_figma_file_doc_id(file_key) == expected_doc_id

    def test_get_figma_comment_doc_id(self):
        """Test Figma comment document ID generation."""
        comment_id = "123456789"
        expected_doc_id = "figma_comment_123456789"
        assert get_figma_comment_doc_id(comment_id) == expected_doc_id

    def test_get_figma_comment_doc_id_with_long_id(self):
        """Test Figma comment document ID generation with long ID."""
        comment_id = "1234567890123456789"
        expected_doc_id = "figma_comment_1234567890123456789"
        assert get_figma_comment_doc_id(comment_id) == expected_doc_id
