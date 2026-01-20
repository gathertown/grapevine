"""
Tests for Salesforce reference finding functionality.
"""

from src.ingest.references.find_references import find_references_in_doc


class TestFindReferencesSalesforce:
    """Test suite for Salesforce Lightning URL reference detection."""

    def test_salesforce_lightning_urls_with_view(self):
        """Test detection of Salesforce Lightning URLs with /view suffix."""
        content = """
        Contact record: https://orgfarm-0c36d862d2-dev-ed.develop.lightning.force.com/lightning/r/Contact/003gK00000AB08eQAD/view
        Account details: https://mycompany.my.salesforce.com/lightning/r/Account/001XX000003DHPh/view
        """
        result = find_references_in_doc(content, "test_doc")

        assert len(result) == 2
        assert result["r_salesforce_contact_003gK00000AB08eQAD"] == 1
        assert result["r_salesforce_account_001XX000003DHPh"] == 1

    def test_salesforce_lightning_urls_without_view(self):
        """Test detection of Salesforce Lightning URLs without /view suffix."""
        content = """
        Lead: https://na139.salesforce.com/lightning/r/Lead/00Q5Y00001qLfXzUAK
        Opportunity: https://demo.lightning.force.com/lightning/r/Opportunity/006XX000004TmiYYAS
        """
        result = find_references_in_doc(content, "test_doc")

        assert len(result) == 2
        assert result["r_salesforce_lead_00Q5Y00001qLfXzUAK"] == 1
        assert result["r_salesforce_opportunity_006XX000004TmiYYAS"] == 1

    def test_salesforce_different_domains(self):
        """Test Salesforce URLs across different domain formats."""
        content = """
        Lightning Force: https://test.lightning.force.com/lightning/r/Case/500XX000001TmiY
        My Salesforce: https://company.my.salesforce.com/lightning/r/Account/001XX000003DHPh
        Direct Salesforce: https://na139.salesforce.com/lightning/r/Lead/00Q5Y00001qLfXz
        """
        result = find_references_in_doc(content, "test_doc")

        assert len(result) == 3
        assert result["r_salesforce_case_500XX000001TmiY"] == 1
        assert result["r_salesforce_account_001XX000003DHPh"] == 1
        assert result["r_salesforce_lead_00Q5Y00001qLfXz"] == 1

    def test_salesforce_urls_with_additional_paths(self):
        """Test Salesforce URLs with additional path segments after record ID."""
        content = """
        Edit view: https://orgfarm.lightning.force.com/lightning/r/Contact/003gK00000AB08eQAD/edit
        With params: https://test.lightning.force.com/lightning/r/Opportunity/006XX000004TmiYYAS/view?0.source=alohaHeader
        Complex path: https://demo.my.salesforce.com/lightning/r/Account/001XX000003DHPh/related/Contacts/view
        """
        result = find_references_in_doc(content, "test_doc")

        assert len(result) == 3
        assert result["r_salesforce_contact_003gK00000AB08eQAD"] == 1
        assert result["r_salesforce_opportunity_006XX000004TmiYYAS"] == 1
        assert result["r_salesforce_account_001XX000003DHPh"] == 1

    def test_salesforce_15_and_18_character_ids(self):
        """Test both 15-character and 18-character Salesforce record IDs."""
        content = """
        15-char ID: https://demo.my.salesforce.com/lightning/r/Case/500XX000001TmiY
        18-char ID: https://test.lightning.force.com/lightning/r/Account/001XX000003DHPhYAO
        """
        result = find_references_in_doc(content, "test_doc")

        assert len(result) == 2
        assert result["r_salesforce_case_500XX000001TmiY"] == 1
        assert result["r_salesforce_account_001XX000003DHPhYAO"] == 1

    def test_salesforce_object_types(self):
        """Test various Salesforce object types."""
        content = """
        Account: https://demo.salesforce.com/lightning/r/Account/001XX000003DHPh/view
        Contact: https://demo.salesforce.com/lightning/r/Contact/003gK00000AB08eQAD/view
        Opportunity: https://demo.salesforce.com/lightning/r/Opportunity/006XX000004TmiYYAS/view
        Lead: https://demo.salesforce.com/lightning/r/Lead/00Q5Y00001qLfXz/view
        Case: https://demo.salesforce.com/lightning/r/Case/500XX000001TmiY/view
        CustomObject: https://demo.salesforce.com/lightning/r/CustomObject/a03XX000001TmiY/view
        """
        result = find_references_in_doc(content, "test_doc")

        assert len(result) == 6
        assert result["r_salesforce_account_001XX000003DHPh"] == 1
        assert result["r_salesforce_contact_003gK00000AB08eQAD"] == 1
        assert result["r_salesforce_opportunity_006XX000004TmiYYAS"] == 1
        assert result["r_salesforce_lead_00Q5Y00001qLfXz"] == 1
        assert result["r_salesforce_case_500XX000001TmiY"] == 1
        assert result["r_salesforce_customobject_a03XX000001TmiY"] == 1

    def test_salesforce_case_sensitivity_object_type(self):
        """Test case handling in Salesforce object types."""
        content = """
        Uppercase: https://demo.salesforce.com/lightning/r/ACCOUNT/001XX000003DHPh/view
        Lowercase: https://demo.salesforce.com/lightning/r/account/001XX000003DHPh/view
        Mixed case: https://demo.salesforce.com/lightning/r/Account/001XX000003DHPh/view
        """
        result = find_references_in_doc(content, "test_doc")

        # All should be normalized to lowercase in the reference ID
        assert len(result) == 1  # Same record referenced 3 times
        assert result["r_salesforce_account_001XX000003DHPh"] == 3

    def test_salesforce_false_positives(self):
        """Test that non-Salesforce URLs are not detected."""
        content = """
        Not Salesforce URLs:
        - GitHub: https://github.com/owner/repo/lightning/r/Account/123456789012345
        - Random site: https://example.com/lightning/r/Contact/003gK00000AB08eQAD/view
        - Wrong path: https://demo.salesforce.com/classic/r/Account/001XX000003DHPh/view
        - No object type: https://demo.salesforce.com/lightning/001XX000003DHPh/view
        - Too short ID: https://demo.salesforce.com/lightning/r/Account/123/view
        - Too long ID: https://demo.salesforce.com/lightning/r/Account/001XX000003DHPh12345/view
        - Wrong ID length: https://demo.salesforce.com/lightning/r/Account/001XX000003DHPh1234/view
        """
        result = find_references_in_doc(content, "test_doc")

        assert result == {}

    def test_self_reference_exclusion(self):
        """Test that self-references are excluded from results."""
        # This simulates a Salesforce document referencing itself
        self_reference_id = "r_salesforce_account_001XX000003DHPh"
        content = """
        Self reference: https://demo.salesforce.com/lightning/r/Account/001XX000003DHPh/view
        Other reference: https://demo.salesforce.com/lightning/r/Contact/003gK00000AB08eQAD/view
        """
        result = find_references_in_doc(content, self_reference_id)

        # Should only find the contact reference, not the self-reference
        assert len(result) == 1
        assert result["r_salesforce_contact_003gK00000AB08eQAD"] == 1
        assert self_reference_id not in result
