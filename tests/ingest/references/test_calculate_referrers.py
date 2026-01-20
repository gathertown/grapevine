"""
Tests for calculate_referrers functionality.
"""

from src.ingest.references.calculate_referrers import calculate_referrer_score


class TestCalculateReferrerScore:
    """Test suite for calculate_referrer_score function."""

    def test_empty_referrers(self):
        """Test with empty referrers dict."""
        result = calculate_referrer_score({})
        assert result == 0

    def test_single_referrer(self):
        """Test with single referrer."""
        referrers = {"r_github_pr_org_repo_123": 91}
        result = calculate_referrer_score(referrers)
        assert result == 2

    def test_multiple_referrers(self):
        """Test with multiple referrers."""
        referrers = {
            "r_github_pr_org_repo_123": 91,
            "r_linear_issue_eng-456": 1,
            "r_notion_page_abc123-def4-5678-90ab-cdef12345678": 1,
        }
        result = calculate_referrer_score(referrers)
        assert result == 4

    def test_zero_reference_counts(self):
        """Test with zero reference counts."""
        referrers = {
            "r_github_pr_org_repo_123": 0,
            "r_linear_issue_eng-456": 0,
        }
        result = calculate_referrer_score(referrers)
        assert result == 0
