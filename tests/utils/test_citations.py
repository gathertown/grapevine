"""Tests for citation utilities."""

from src.utils.citations import collapse_duplicate_citations


class TestCollapseDuplicateCitations:
    """Test cases for collapse_duplicate_citations function."""

    def test_standard_markdown_consecutive_duplicates(self):
        """Test removing consecutive duplicate citations in standard markdown format."""
        text = "The feature was released[[1]](https://example.com/1)[[1]](https://example.com/1) in Q3."
        result = collapse_duplicate_citations(text)
        assert result == "The feature was released[[1]](https://example.com/1) in Q3."

    def test_slack_format_consecutive_duplicates(self):
        """Test removing consecutive duplicate citations in Slack format."""
        text = (
            "The feature was released<https://example.com/1|[1]><https://example.com/1|[1]> in Q3."
        )
        result = collapse_duplicate_citations(text, output_format="slack")
        assert result == "The feature was released<https://example.com/1|[1]> in Q3."

    def test_multiple_consecutive_duplicates(self):
        """Test removing chains of consecutive duplicates."""
        text = "Deploy on Friday[[1]](https://a.com)[[1]](https://b.com)[[1]](https://c.com) works."
        result = collapse_duplicate_citations(text)
        assert result == "Deploy on Friday[[1]](https://a.com) works."

    def test_consecutive_duplicates_with_whitespace(self):
        """Test that whitespace between consecutive duplicates is discarded."""
        text = "The feature[[1]](https://example.com/1) [[1]](https://example.com/1) was released."
        result = collapse_duplicate_citations(text)
        assert result == "The feature[[1]](https://example.com/1) was released."

    def test_consecutive_duplicates_with_comma(self):
        """Test removing consecutive duplicates separated by comma (comma is discarded)."""
        text = "The feature[[1]](https://example.com/1),[[1]](https://example.com/1) was released."
        result = collapse_duplicate_citations(text)
        assert result == "The feature[[1]](https://example.com/1) was released."

    def test_consecutive_duplicates_with_comma_and_space(self):
        """Test removing consecutive duplicates separated by comma and space (both discarded)."""
        text = "The feature[[1]](https://example.com/1), [[1]](https://example.com/1) was released."
        result = collapse_duplicate_citations(text)
        assert result == "The feature[[1]](https://example.com/1) was released."

    def test_slack_consecutive_duplicates_with_comma(self):
        """Test removing consecutive duplicates in Slack format separated by comma (comma discarded)."""
        text = "The feature<https://example.com/1|[1]>,<https://example.com/1|[1]> was released."
        result = collapse_duplicate_citations(text, output_format="slack")
        assert result == "The feature<https://example.com/1|[1]> was released."

    def test_no_duplicates(self):
        """Test that text without duplicates is not modified."""
        text = "Feature A[[1]](https://a.com) and Feature B[[2]](https://b.com)."
        result = collapse_duplicate_citations(text)
        assert result == text

    def test_non_consecutive_duplicates_kept(self):
        """Test that non-consecutive duplicates are NOT removed."""
        text = "Feature A[[1]](https://a.com) was released. Later, Feature B[[1]](https://a.com) was added."
        result = collapse_duplicate_citations(text)
        # Both should remain since they're not consecutive
        assert result == text

    def test_different_citation_numbers_not_affected(self):
        """Test that different citation numbers are not removed."""
        text = "Feature A[[1]](https://a.com)[[2]](https://b.com)[[3]](https://c.com)."
        result = collapse_duplicate_citations(text)
        assert result == text

    def test_mixed_duplicates_and_unique(self):
        """Test text with both consecutive duplicates and unique citations."""
        text = "A[[1]](https://a.com)[[1]](https://a.com) and B[[2]](https://b.com) and C[[1]](https://a.com)."
        result = collapse_duplicate_citations(text)
        # First [1][1] should collapse, but third [1] should remain (not consecutive with first)
        assert (
            result == "A[[1]](https://a.com) and B[[2]](https://b.com) and C[[1]](https://a.com)."
        )

    def test_slack_format_multiple_duplicates(self):
        """Test Slack format with multiple consecutive duplicates."""
        text = "Deploy<https://a.com|[1]><https://b.com|[1]><https://c.com|[1]> on Friday."
        result = collapse_duplicate_citations(text, output_format="slack")
        assert result == "Deploy<https://a.com|[1]> on Friday."

    def test_slack_format_no_duplicates(self):
        """Test Slack format with no duplicates."""
        text = "Feature A<https://a.com|[1]> and B<https://b.com|[2]>."
        result = collapse_duplicate_citations(text, output_format="slack")
        assert result == text

    def test_empty_text(self):
        """Test that empty text is handled correctly."""
        text = ""
        result = collapse_duplicate_citations(text)
        assert result == ""

    def test_text_without_citations(self):
        """Test that text without citations is not modified."""
        text = "This is plain text without any citations."
        result = collapse_duplicate_citations(text)
        assert result == text

    def test_real_world_scenario(self):
        """Test a realistic scenario with multiple factual claims."""
        text = (
            "The deployment process[[1]](https://slack.com/ts1)[[1]](https://slack.com/ts1) "
            "requires approval from two reviewers[[2]](https://github.com/pr123). "
            "The feature was released in Q3[[3]](https://notion.com/page1)[[3]](https://notion.com/page1)[[3]](https://notion.com/page1)."
        )
        result = collapse_duplicate_citations(text)
        expected = (
            "The deployment process[[1]](https://slack.com/ts1) "
            "requires approval from two reviewers[[2]](https://github.com/pr123). "
            "The feature was released in Q3[[3]](https://notion.com/page1)."
        )
        assert result == expected

    def test_slack_real_world_scenario(self):
        """Test a realistic Slack scenario with multiple factual claims."""
        text = (
            "The deployment process<https://slack.com/ts1|[1]><https://slack.com/ts1|[1]> "
            "requires approval from two reviewers<https://github.com/pr123|[2]>. "
            "The feature was released in Q3<https://notion.com/page1|[3]><https://notion.com/page1|[3]>."
        )
        result = collapse_duplicate_citations(text, output_format="slack")
        expected = (
            "The deployment process<https://slack.com/ts1|[1]> "
            "requires approval from two reviewers<https://github.com/pr123|[2]>. "
            "The feature was released in Q3<https://notion.com/page1|[3]>."
        )
        assert result == expected

    def test_alternating_citations_in_cluster(self):
        """Test that duplicates sandwiched by other citations are removed."""
        text = (
            "The feature[[1]](https://a.com)[[2]](https://b.com)[[1]](https://a.com) was released."
        )
        result = collapse_duplicate_citations(text)
        # Second [1] should be removed because it's in the same cluster
        assert result == "The feature[[1]](https://a.com)[[2]](https://b.com) was released."

    def test_alternating_citations_complex_cluster(self):
        """Test complex alternating pattern within a cluster."""
        text = "Deploy[[1]](https://a.com)[[2]](https://b.com)[[3]](https://c.com)[[1]](https://a.com)[[2]](https://b.com) done."
        result = collapse_duplicate_citations(text)
        # Second [1] and second [2] should be removed (same cluster)
        assert result == "Deploy[[1]](https://a.com)[[2]](https://b.com)[[3]](https://c.com) done."

    def test_citations_separated_by_text_different_clusters(self):
        """Test that citations separated by text are in different clusters."""
        text = (
            "Feature A[[1]](https://a.com) was released. Feature B[[1]](https://a.com) was added."
        )
        result = collapse_duplicate_citations(text)
        # Both [1] should remain (different clusters due to text separation)
        assert result == text

    def test_multiple_clusters_in_text(self):
        """Test text with multiple separate citation clusters."""
        text = "A[[1]](https://a.com)[[2]](https://b.com)[[1]](https://a.com) and B[[3]](https://c.com)[[1]](https://a.com)[[3]](https://c.com) done."
        result = collapse_duplicate_citations(text)
        # First cluster: [1][2][1] → [1][2]
        # Second cluster: [3][1][3] → [3][1] (new cluster, so [1] is first occurrence here)
        assert (
            result
            == "A[[1]](https://a.com)[[2]](https://b.com) and B[[3]](https://c.com)[[1]](https://a.com) done."
        )

    def test_slack_alternating_citations_in_cluster(self):
        """Test Slack format with alternating citations in a cluster."""
        text = "The feature<https://a.com|[1]><https://b.com|[2]><https://a.com|[1]> was released."
        result = collapse_duplicate_citations(text, output_format="slack")
        # Second [1] should be removed (same cluster)
        assert result == "The feature<https://a.com|[1]><https://b.com|[2]> was released."

    def test_slack_citations_separated_by_text(self):
        """Test Slack format with citations separated by text."""
        text = "Feature A<https://a.com|[1]> was released. Feature B<https://a.com|[1]> was added."
        result = collapse_duplicate_citations(text, output_format="slack")
        # Both [1] should remain (different clusters)
        assert result == text

    def test_cluster_with_comma_separators(self):
        """Test cluster with commas between citations."""
        text = (
            "Sources:[[1]](https://a.com), [[2]](https://b.com), [[1]](https://a.com) confirm this."
        )
        result = collapse_duplicate_citations(text)
        # Second [1] removed (same cluster despite commas)
        assert result == "Sources:[[1]](https://a.com), [[2]](https://b.com) confirm this."
