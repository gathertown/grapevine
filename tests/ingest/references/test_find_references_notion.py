"""
Tests for Notion page reference finding functionality.
"""

from src.ingest.references.find_references import find_references_in_doc


class TestFindReferencesNotion:
    """Test suite for Notion page reference detection."""

    def test_notion_page_references(self):
        """Test detection of Notion page references."""
        content = """
        Check this page: https://www.notion.so/company/Page-Title-12345678-90ab-cdef-1234-567890abcdef
        Also see https://notion.so/1234567890abcdef1234567890abcdef
        Direct UUID: 87654321-abcd-1234-5678-123456789012
        No dash UUID: abcdef1234567890abcdef1234567890
        """
        result = find_references_in_doc(content, "test_doc")

        assert len(result) == 3
        assert result["r_notion_page_12345678-90ab-cdef-1234-567890abcdef"] == 2
        assert result["r_notion_page_87654321-abcd-1234-5678-123456789012"] == 1
        assert result["r_notion_page_abcdef12-3456-7890-abcd-ef1234567890"] == 1

    def test_notion_case_sensitivity(self):
        """Test case handling in Notion UUID references."""
        content = """
        Notion UUID: ABCDEF12-3456-7890-ABCD-EF1234567890
        """
        result = find_references_in_doc(content, "test_doc")

        # UUIDs should be normalized to lowercase
        assert len(result) == 1
        assert result["r_notion_page_abcdef12-3456-7890-abcd-ef1234567890"] == 1

    def test_notion_false_positives(self):
        """Test that UUID-like patterns that aren't actual Notion pages are ignored."""
        content = """
        False positives that should NOT be detected:
        - Short hex strings: abc123, def456, 12345678
        - Almost UUIDs (wrong length): 12345678-90ab-cdef-1234-567890abcdef123 (too long)
        - Almost UUIDs (wrong format): 12345678-90ab-cdef-1234 (too short)
        - Invalid characters: 12345678-90xy-cdef-1234-567890abcdef (contains x,y)
        - Wrong section lengths: 123456789-0ab-cdef-1234-567890abcdef
        - Base64-like strings: eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9 (contains non-hex)
        - MAC addresses: 12:34:56:78:90:ab (wrong separators)
        - Version numbers: 1.2.3-4567-8901-2345-6789
        - File hashes (SHA1): 356a192b7913b04c54574d18c28d46e6395428ab (40 chars)
        - Random text: not a uuid at all, just regular words
        """
        result = find_references_in_doc(content, "test_doc")

        assert result == {}

    def test_real_notion_doc_simple_example(self):
        """Test detection with real Notion document content."""
        # The document's own UUID that should be excluded
        doc_own_uuid = "25aeba3b-d2c2-80a2-9399-e9af98c657ce"
        doc_reference_id = f"r_notion_page_{doc_own_uuid.lower()}"

        content = """
Page: <25aeba3b-d2c2-80a2-9399-e9af98c657ce|vic test page>
URL: https://www.notion.so/vic-test-page-25aeba3bd2c280a29399e9af98c657ce
Contributors: <@e28f708f-b738-4537-9144-5b4283918eca|@Victor Zhou>, <@abcdef12-3456-7890-abcd-ef1234567890|@John Doe>

Content:

created on 2025-08-25
testing page notion mention: Testing page
testing page url: https://www.notion.so/Testing-page-24feba3bd2c2805cb320f556804c0285?source=copy_link
        """

        result = find_references_in_doc(content, doc_reference_id)

        # Should only detect the referenced testing page UUID, not the document's own UUID or contributor UUID
        assert len(result) == 1
        assert result["r_notion_page_24feba3b-d2c2-805c-b320-f556804c0285"] == 1
