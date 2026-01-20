"""
Tests for update_referrers functionality.
"""

from src.ingest.references.update_referrers import compute_referenced_docs_diff


class TestComputeReferencedDocsDiff:
    """Test suite for `compute_referenced_docs_diff` function."""

    def test_compute_diff_no_changes(self):
        """Test when old and new refs are identical."""
        old_refs = {"r_github_pr_org_repo_123": 2, "r_linear_issue_eng-456": 1}
        new_refs = {"r_github_pr_org_repo_123": 2, "r_linear_issue_eng-456": 1}

        result = compute_referenced_docs_diff(old_refs, new_refs)
        assert result == {"added_or_changed": {}, "removed": {}}

    def test_compute_diff_added_references(self):
        """Test when new references are added."""
        old_refs = {"r_github_pr_org_repo_123": 2}
        new_refs = {"r_github_pr_org_repo_123": 2, "r_linear_issue_eng-456": 1}

        result = compute_referenced_docs_diff(old_refs, new_refs)
        assert result == {"added_or_changed": {"r_linear_issue_eng-456": 1}, "removed": {}}

    def test_compute_diff_removed_references(self):
        """Test when references are removed."""
        old_refs = {"r_github_pr_org_repo_123": 2, "r_linear_issue_eng-456": 1}
        new_refs = {"r_github_pr_org_repo_123": 2}

        result = compute_referenced_docs_diff(old_refs, new_refs)
        assert result == {"added_or_changed": {}, "removed": {"r_linear_issue_eng-456": 1}}

    def test_compute_diff_changed_counts(self):
        """Test when reference counts change."""
        old_refs = {"r_github_pr_org_repo_123": 2, "r_linear_issue_eng-456": 1}
        new_refs = {"r_github_pr_org_repo_123": 5, "r_linear_issue_eng-456": 1}

        result = compute_referenced_docs_diff(old_refs, new_refs)
        assert result == {"added_or_changed": {"r_github_pr_org_repo_123": 5}, "removed": {}}

    def test_compute_diff_empty_old_refs(self):
        """Test when old refs is empty."""
        old_refs: dict[str, int] = {}
        new_refs = {"r_github_pr_org_repo_123": 2, "r_linear_issue_eng-456": 1}

        result = compute_referenced_docs_diff(old_refs, new_refs)
        assert result == {
            "added_or_changed": {"r_github_pr_org_repo_123": 2, "r_linear_issue_eng-456": 1},
            "removed": {},
        }

    def test_compute_diff_empty_new_refs(self):
        """Test when new refs is empty."""
        old_refs = {"r_github_pr_org_repo_123": 2, "r_linear_issue_eng-456": 1}
        new_refs: dict[str, int] = {}

        result = compute_referenced_docs_diff(old_refs, new_refs)
        assert result == {
            "added_or_changed": {},
            "removed": {"r_github_pr_org_repo_123": 2, "r_linear_issue_eng-456": 1},
        }

    def test_compute_diff_complex_changes(self):
        """Test complex scenario with adds, removes, and changes."""
        old_refs = {
            "r_github_pr_org_repo_123": 2,
            "r_linear_issue_eng-456": 1,  # removed
            "r_notion_page_abc123": 3,
        }
        new_refs = {
            "r_github_pr_org_repo_123": 5,  # changed
            "r_linear_issue_eng-789": 2,  # added
            "r_notion_page_abc123": 3,  # unchanged
        }

        result = compute_referenced_docs_diff(old_refs, new_refs)
        assert result == {
            "added_or_changed": {"r_github_pr_org_repo_123": 5, "r_linear_issue_eng-789": 2},
            "removed": {"r_linear_issue_eng-456": 1},
        }

    def test_compute_diff_both_empty(self):
        """Test when both old and new refs are empty."""
        old_refs: dict[str, int] = {}
        new_refs: dict[str, int] = {}

        result = compute_referenced_docs_diff(old_refs, new_refs)
        assert result == {"added_or_changed": {}, "removed": {}}

    def test_compute_diff_zero_counts(self):
        """Test with zero reference counts."""
        old_refs = {"r_github_pr_org_repo_123": 0, "r_linear_issue_eng-456": 2}
        new_refs = {"r_github_pr_org_repo_123": 0, "r_linear_issue_eng-456": 0}

        result = compute_referenced_docs_diff(old_refs, new_refs)
        assert result == {"added_or_changed": {"r_linear_issue_eng-456": 0}, "removed": {}}
