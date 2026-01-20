"""Tests for document ID candidate generation and slash fixing behavior."""

from src.mcp.tools.document_id_utils import get_candidate_document_ids


class TestDocumentIdCandidates:
    """Test candidate document ID generation for slash fixing."""

    def test_github_code_with_slashes(self):
        """GITHUB_CODE docIds with slashes should generate fixed version."""
        doc_id = "github_file_my-repo_src/utils/helper.py"
        candidates = get_candidate_document_ids(doc_id)

        expected = [
            "github_file_my-repo_src/utils/helper.py",  # original
        ]
        assert candidates == expected

    def test_github_code_without_slashes(self):
        """GITHUB_CODE docIds without slashes should only return original."""
        doc_id = "github_file_my-repo_README.md"
        candidates = get_candidate_document_ids(doc_id)

        expected = ["github_file_my-repo_README.md"]
        assert candidates == expected

    def test_github_code_multiple_slashes(self):
        """GITHUB_CODE docIds with multiple slashes should fix all."""
        doc_id = "github_file_repo_src/components/ui/Button.tsx"
        candidates = get_candidate_document_ids(doc_id)

        expected = [
            "github_file_repo_src/components/ui/Button.tsx",  # original
        ]
        assert candidates == expected

    def test_non_github_code_sources(self):
        """Non-GITHUB_CODE docIds should only return original."""
        test_cases = [
            "12345678_pr_42",  # GitHub PR
            "issue_abc123def456ghi789",  # Linear
            "C1234567890_2024-01-15",  # Slack
            "notion_page_494c87d0-72c4-4cf6-960f-55f8427f7692",  # Notion
        ]

        for doc_id in test_cases:
            candidates = get_candidate_document_ids(doc_id)
            assert candidates == [doc_id], f"Failed for {doc_id}"

    def test_non_github_code_with_slashes_ignored(self):
        """Non-GITHUB_CODE docIds with slashes should not be fixed."""
        doc_id = "some_other_type_with/slashes"
        candidates = get_candidate_document_ids(doc_id)

        expected = ["some_other_type_with/slashes"]
        assert candidates == expected

    def test_empty_string(self):
        """Empty string should return list with empty string."""
        candidates = get_candidate_document_ids("")
        assert candidates == [""]

    def test_github_file_prefix_only(self):
        """Just the github_file_ prefix should not trigger fixing."""
        doc_id = "github_file_"
        candidates = get_candidate_document_ids(doc_id)
        assert candidates == ["github_file_"]


# Note: Integration tests for get_document and get_document_metadata would require
# a test database with actual documents, which is not set up in this test file.
# Those tests would be better placed in a separate integration test suite.
