"""
Tests for GitHub reference finding functionality.
"""

from src.ingest.references.find_references import find_references_in_doc


class TestFindReferencesGitHub:
    """Test suite for GitHub reference detection."""

    def test_github_pr_references(self):
        """Test detection of GitHub PR references."""
        content = """
        See PR https://github.com/company/repo/pull/123
        See another PR https://github.com/company/repo/pull/456/files
        Related to company/repo#456
        Also check org/other-repo#789
        """
        result = find_references_in_doc(content, "test_doc")

        assert len(result) == 3
        assert result["r_github_pr_company_repo_123"] == 1
        assert result["r_github_pr_company_repo_456"] == 2
        assert result["r_github_pr_org_other-repo_789"] == 1

    def test_graphite_pr_references(self):
        """Test detection of Graphite PR references."""
        content = """
        See Graphite PR https://app.graphite.dev/github/pr/gathertown/corporate-context/615/%5B24%2Fx%5D-Remove-legacy-num_references-column
        Also check https://app.graphite.dev/github/pr/company/repo/456/
        And https://app.graphite.dev/github/pr/org/other-repo/789
        """
        result = find_references_in_doc(content, "test_doc")

        assert len(result) == 3
        assert result["r_github_pr_gathertown_corporate-context_615"] == 1
        assert result["r_github_pr_company_repo_456"] == 1
        assert result["r_github_pr_org_other-repo_789"] == 1

    def test_github_file_references(self):
        """Test detection of GitHub file references."""
        content = """
        Check this file: https://github.com/company/repo/blob/main/src/utils/helper.py
        Also see https://github.com/org/project/blob/develop/docs/README.md
        """
        result = find_references_in_doc(content, "test_doc")

        assert len(result) == 2
        assert result["r_github_file_company_repo_src/utils/helper.py"] == 1
        assert result["r_github_file_org_project_docs/README.md"] == 1

    def test_github_url_with_fragments(self):
        """Test GitHub URLs with query parameters and fragments."""
        content = """
        GitHub file with anchor: https://github.com/org/repo/blob/main/file.py#L123
        GitHub PR with anchor: https://github.com/gathertown/corporate-context/pull/617#issuecomment-3235221910
        """
        result = find_references_in_doc(content, "test_doc")

        # GitHub file should still be detected even with fragment
        assert len(result) == 2
        assert result["r_github_file_org_repo_file.py"] == 1
        assert result["r_github_pr_gathertown_corporate-context_617"] == 1

    def test_github_false_positives(self):
        """Test that GitHub-like patterns that aren't actual GitHub references are ignored."""
        content = """
        False positives that should NOT be detected:
        - Incomplete URLs: github.com/org/repo (no protocol)
        - Wrong paths: https://github.com/org (missing repo)
        - Non-GitHub domains: https://gitlab.com/org/repo/pull/123
        - Local references: org/repo without # (missing issue number)
        - Invalid issue format: org/repo#abc (non-numeric issue)
        - Empty parts: https://github.com//repo/pull/123
        - Wrong URL structure: https://github.com/org/repo/issues/123 (issues, not pull)
        - Private/personal: git@github.com:org/repo.git (SSH format)
        - Documentation: https://github.com/org/repo#readme (fragment, not issue)
        - Raw content: https://raw.githubusercontent.com/org/repo/main/file.py
        """
        result = find_references_in_doc(content, "test_doc")

        assert result == {}
