"""
Tests for Google Drive reference finding functionality.
"""

from src.ingest.references.find_references import find_references_in_doc


class TestFindReferencesGoogleDrive:
    """Test suite for Google Drive reference detection."""

    def test_basic_google_drive_references(self):
        """Test detection of basic Google Drive file references."""
        content = """
        Check this document: https://drive.google.com/file/d/1ItuQi1zuL7hl_saIf3mfDXiSdpUmX1MT
        Another file: https://drive.google.com/file/d/1AbCdEfGhIjKlMnOpQrStUvWxYz1234567
        """
        result = find_references_in_doc(content, "test_doc")

        assert len(result) == 2
        assert result["r_gdrive_file_1ItuQi1zuL7hl_saIf3mfDXiSdpUmX1MT"] == 1
        assert result["r_gdrive_file_1AbCdEfGhIjKlMnOpQrStUvWxYz1234567"] == 1

    def test_google_drive_url_variations(self):
        """Test detection of different Google Drive URL variations."""
        content = """
        Basic URL: https://drive.google.com/file/d/1ItuQi1zuL7hl_saIf3mfDXiSdpUmX1MT
        Edit URL: https://drive.google.com/file/d/1ItuQi1zuL7hl_saIf3mfDXiSdpUmX1MT/edit
        View URL: https://drive.google.com/file/d/1ItuQi1zuL7hl_saIf3mfDXiSdpUmX1MT/view
        With sharing: https://drive.google.com/file/d/1ItuQi1zuL7hl_saIf3mfDXiSdpUmX1MT/view?usp=sharing
        With other params: https://drive.google.com/file/d/1ItuQi1zuL7hl_saIf3mfDXiSdpUmX1MT/view?usp=drive_link&other=param
        """
        result = find_references_in_doc(content, "test_doc")

        # All should resolve to the same file ID, so count should be 5
        assert len(result) == 1
        assert result["r_gdrive_file_1ItuQi1zuL7hl_saIf3mfDXiSdpUmX1MT"] == 5

    def test_multiple_different_files(self):
        """Test detection of multiple different Google Drive files."""
        content = """
        File A: https://drive.google.com/file/d/1FileA123456789
        File B: https://drive.google.com/file/d/1FileB987654321/edit
        File C: https://drive.google.com/file/d/1FileC555666777/view?usp=sharing
        """
        result = find_references_in_doc(content, "test_doc")

        assert len(result) == 3
        assert result["r_gdrive_file_1FileA123456789"] == 1
        assert result["r_gdrive_file_1FileB987654321"] == 1
        assert result["r_gdrive_file_1FileC555666777"] == 1

    def test_self_reference_exclusion(self):
        """Test that self-references are properly excluded."""
        self_reference_id = "r_gdrive_file_1SelfReference123"
        content = """
        Self reference: https://drive.google.com/file/d/1SelfReference123
        Other reference: https://drive.google.com/file/d/1OtherFile456
        """
        result = find_references_in_doc(content, self_reference_id)

        # Should only detect the other file, not the self-reference
        assert len(result) == 1
        assert result["r_gdrive_file_1OtherFile456"] == 1

    def test_google_drive_false_positives(self):
        """Test that non-Google Drive URLs are not detected as Google Drive references."""
        content = """
        False positives that should NOT be detected:
        - Google Docs: https://docs.google.com/document/d/1DocId123/edit
        - Google Sheets: https://sheets.google.com/spreadsheets/d/1SheetId456/edit
        - Google Slides: https://docs.google.com/presentation/d/1SlideId789/edit
        - Other Google services: https://calendar.google.com/calendar
        - Non-Google drives: https://onedrive.live.com/redir?resid=123
        - Invalid Drive URLs: https://drive.google.com/folder/d/1FolderId (folder, not file)
        - Incomplete URLs: drive.google.com/file/d/123 (no protocol)
        - Wrong domain: https://drive.example.com/file/d/123
        - Missing file ID: https://drive.google.com/file/d/
        - Empty file ID: https://drive.google.com/file/d//edit
        """
        result = find_references_in_doc(content, "test_doc")

        assert result == {}

    def test_valid_file_id_formats(self):
        """Test various valid Google Drive file ID formats."""
        content = """
        Standard ID: https://drive.google.com/file/d/1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms
        Short ID: https://drive.google.com/file/d/1AbC2DeF3GhI
        With hyphens: https://drive.google.com/file/d/1-Abc_DeF-GhI_234
        With underscores: https://drive.google.com/file/d/1_Test_File_ID_123
        """
        result = find_references_in_doc(content, "test_doc")

        assert len(result) == 4
        assert "r_gdrive_file_1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms" in result
        assert "r_gdrive_file_1AbC2DeF3GhI" in result
        assert "r_gdrive_file_1-Abc_DeF-GhI_234" in result
        assert "r_gdrive_file_1_Test_File_ID_123" in result

    def test_edge_cases_with_whitespace_and_punctuation(self):
        """Test Google Drive URLs with various surrounding characters."""
        content = """
        In parentheses: (https://drive.google.com/file/d/1ParenTest123)
        With quotes: "https://drive.google.com/file/d/1QuoteTest456"
        In brackets: [https://drive.google.com/file/d/1BracketTest789]
        With comma: Check this file, https://drive.google.com/file/d/1CommaTest000, for details.
        At end of sentence: See https://drive.google.com/file/d/1EndTest111.
        Line break before URL:
        https://drive.google.com/file/d/1NewlineTest222
        """
        result = find_references_in_doc(content, "test_doc")

        assert len(result) == 6
        assert result["r_gdrive_file_1ParenTest123"] == 1
        assert result["r_gdrive_file_1QuoteTest456"] == 1
        assert result["r_gdrive_file_1BracketTest789"] == 1
        assert result["r_gdrive_file_1CommaTest000"] == 1
        assert result["r_gdrive_file_1EndTest111"] == 1
        assert result["r_gdrive_file_1NewlineTest222"] == 1
