"""
Tests for Linear issue reference finding functionality.
"""

from src.ingest.references.find_references import find_references_in_doc


class TestFindReferencesLinear:
    """Test suite for Linear issue reference detection."""

    def test_linear_issue_references(self):
        """Test detection of Linear issue references."""
        content = """
        We need to fix ENG-123 and also look at PROD-456.
        See issue ENG-123 mentioned again.
        Check https://linear.app/company/issue/BUG-789/fix-this-bug
        Real issue: https://linear.app/gather-town/issue/AIVP-277/bring-references-code-into-production
        """
        result = find_references_in_doc(content, "test_doc")

        assert len(result) == 4
        assert result["r_linear_issue_eng-123"] == 2  # Mentioned twice
        assert result["r_linear_issue_prod-456"] == 1
        assert result["r_linear_issue_bug-789"] == 1
        assert result["r_linear_issue_aivp-277"] == 1

    def test_multiple_references_same_document(self):
        """Test counting multiple references to the same document."""
        content = """
        This references ENG-123 multiple times.
        Another mention of ENG-123 here.
        And yet another ENG-123 reference.
        """
        result = find_references_in_doc(content, "test_doc")

        assert len(result) == 1
        assert result["r_linear_issue_eng-123"] == 3

    def test_linear_case_sensitivity(self):
        """Test case handling in Linear issue references."""
        content = """
        Linear issues: ENG-123 and eng-456
        """
        result = find_references_in_doc(content, "test_doc")

        # Linear issues should be normalized to lowercase
        assert len(result) == 1
        assert result["r_linear_issue_eng-123"] == 1
        # eng-456 won't match because pattern requires uppercase letters
        assert "r_linear_issue_eng-456" not in result

    def test_linear_false_positives(self):
        """Test that patterns that don't match Linear issue format are ignored."""
        content = """
        False positives that should NOT be detected:
        - Version numbers: v2-1 (starts with lowercase)
        - Version numbers: 3-14, 5-0 (starts with numbers)
        - File extensions: .tar-gz (starts with dot)
        - URLs: http://example-site.com/path-123 (lowercase letters)
        - Hyphenated words: long-term, state-of-the-art (lowercase)
        - Single letter: A-1, B-2 (only 1 letter, need 2+)
        - Numbers only: 123-456 (no letters at all)
        - Mixed case in number: ENG-12a3 (letter 'a' in number part)
        """
        result = find_references_in_doc(content, "test_doc")

        assert result == {}
