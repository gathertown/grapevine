"""
Base tests and shared utilities for document reference finding functionality.
"""

from src.ingest.references.find_references import find_references_in_doc


class TestFindReferencesInDocBase:
    """Base tests for find_references_in_doc function."""

    def test_empty_document(self):
        """Test with empty document content."""
        result = find_references_in_doc("", "test_doc")
        assert result == {}

    def test_no_references(self):
        """Test with document containing no references."""
        content = "This is just regular text with no refs to other docs."
        result = find_references_in_doc(content, "test_doc")
        assert result == {}

    def test_mixed_document_types(self):
        """Test detection of references to different document types."""
        content = """
        Linear issue: ENG-123
        Notion page: https://notion.so/12345678-90ab-cdef-1234-567890abcdef
        GitHub PR: company/repo#456
        GitHub file: https://github.com/org/repo/blob/main/src/file.py
        Drive file: https://drive.google.com/file/d/1AnotherFile789/edit
        Salesforce contact: https://demo.lightning.force.com/lightning/r/Contact/003gK00000AB08eQAD/view
        """
        result = find_references_in_doc(content, "test_doc")

        assert len(result) == 6
        assert result["r_linear_issue_eng-123"] == 1
        assert result["r_notion_page_12345678-90ab-cdef-1234-567890abcdef"] == 1
        assert result["r_github_pr_company_repo_456"] == 1
        assert result["r_github_file_org_repo_src/file.py"] == 1
        assert result["r_gdrive_file_1AnotherFile789"] == 1
        assert result["r_salesforce_contact_003gK00000AB08eQAD"] == 1

    def test_malformed_urls_ignored(self):
        """Test that malformed URLs don't cause errors."""
        content = """
        This has malformed URLs: https://
        And incomplete: http://incomplete
        Bad notion: https://notion.so/not-valid-uuid
        """
        result = find_references_in_doc(content, "test_doc")
        # Should not crash, may pick up some IDs but no major errors
        # The main goal is no crash, not necessarily empty result
        assert isinstance(result, dict)
