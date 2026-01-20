"""
Salesforce Opportunity document and chunk classes.
"""

from dataclasses import dataclass

from connectors.salesforce.salesforce_artifacts import SUPPORTED_SALESFORCE_OBJECTS
from connectors.salesforce.salesforce_base_document import (
    BaseSalesforceChunk,
    BaseSalesforceDocument,
    BaseSalesforceDocumentMetadata,
)
from src.utils.type_conversion import safe_float


class SalesforceOpportunityDocumentMetadata(BaseSalesforceDocumentMetadata):
    """Metadata for Salesforce Opportunity documents."""

    stage_name: str | None
    amount: float | None
    close_date: str | None
    probability: float | None
    account_name: str | None
    account_id: str | None
    opportunity_type: str | None
    lead_source: str | None
    is_won: bool | None
    is_closed: bool | None
    expected_revenue: float | None
    total_opportunity_quantity: float | None
    contact_id: str | None
    contact_name: str | None
    pricebook_id: str | None
    is_private: bool | None


@dataclass
class SalesforceOpportunityChunk(BaseSalesforceChunk):
    """Represents a single Salesforce Opportunity chunk."""


@dataclass
class SalesforceOpportunityDocument(BaseSalesforceDocument):
    """Represents a Salesforce Opportunity as a document."""

    def get_content(self) -> str:
        """Get the formatted Opportunity record content."""
        record_data = self.raw_data.get("record_data", {})
        if not record_data:
            return "Opportunity: [No data available]"

        lines = []

        # Header
        name = record_data.get("Name", "Unknown Opportunity")
        lines.append(f"Opportunity: {name}")
        lines.append("")

        # Key fields
        if record_data.get("StageName"):
            lines.append(f"Stage: {record_data['StageName']}")

        # Status indicators
        if record_data.get("IsWon"):
            lines.append("Status: Won")
        elif record_data.get("IsClosed"):
            lines.append("Status: Closed")

        # Amount
        if record_data.get("Amount"):
            amount_str = self._format_currency(record_data["Amount"])
            if amount_str:
                lines.append(f"Amount: {amount_str}")

        # Expected Revenue
        if record_data.get("ExpectedRevenue"):
            expected_str = self._format_currency(record_data["ExpectedRevenue"])
            if expected_str:
                lines.append(f"Expected Revenue: {expected_str}")

        # Quantity
        if record_data.get("TotalOpportunityQuantity"):
            lines.append(f"Quantity: {record_data['TotalOpportunityQuantity']}")

        if record_data.get("CloseDate"):
            lines.append(f"Close Date: {record_data['CloseDate']}")
        if record_data.get("Probability"):
            lines.append(f"Probability: {record_data['Probability']}%")

        # Relationships
        if record_data.get("Account", {}).get("Name"):
            lines.append(f"Account: {record_data['Account']['Name']}")
        if record_data.get("Contact", {}).get("Name"):
            lines.append(f"Primary Contact: {record_data['Contact']['Name']}")

        if record_data.get("Type"):
            lines.append(f"Type: {record_data['Type']}")
        if record_data.get("LeadSource"):
            lines.append(f"Lead Source: {record_data['LeadSource']}")

        # Owner
        if record_data.get("Owner", {}).get("Name"):
            lines.append(f"Owner: {record_data['Owner']['Name']}")

        # Forecast Category
        if record_data.get("ForecastCategoryName"):
            lines.append(f"Forecast Category: {record_data['ForecastCategoryName']}")

        # Campaign
        if record_data.get("Campaign", {}).get("Name"):
            lines.append(f"Campaign: {record_data['Campaign']['Name']}")

        # Pricebook
        if record_data.get("Pricebook2Id"):
            lines.append(f"Pricebook: {record_data['Pricebook2Id']}")

        # Privacy
        if record_data.get("IsPrivate"):
            lines.append("Privacy: Private")

        # Description
        if record_data.get("Description"):
            lines.extend(["", "Description:", record_data["Description"]])

        # Next steps
        if record_data.get("NextStep"):
            lines.extend(["", "Next Step:", record_data["NextStep"]])

        # Custom fields
        lines.extend(self._format_custom_fields(record_data))

        return "\n".join(lines)

    def _create_chunk(self) -> SalesforceOpportunityChunk:
        """Create an Opportunity-specific chunk."""
        return SalesforceOpportunityChunk(
            document=self,
            raw_data=self.raw_data,
        )

    def get_object_type(self) -> SUPPORTED_SALESFORCE_OBJECTS:
        return "Opportunity"

    def get_metadata(self) -> SalesforceOpportunityDocumentMetadata:
        """Get Opportunity-specific document metadata."""
        base_metadata = super().get_metadata()
        record_data = self.raw_data.get("record_data", {})

        # Convert to Opportunity-specific metadata
        opportunity_metadata: SalesforceOpportunityDocumentMetadata = {
            **base_metadata,
            "stage_name": record_data.get("StageName"),
            "amount": safe_float(record_data.get("Amount")),
            "close_date": record_data.get("CloseDate"),
            "probability": safe_float(record_data.get("Probability")),
            "account_name": record_data.get("Account", {}).get("Name"),
            "account_id": record_data.get("Account", {}).get("Id"),
            "opportunity_type": record_data.get("Type"),
            "lead_source": record_data.get("LeadSource"),
            "is_won": record_data.get("IsWon"),
            "is_closed": record_data.get("IsClosed"),
            "expected_revenue": safe_float(record_data.get("ExpectedRevenue")),
            "total_opportunity_quantity": safe_float(record_data.get("TotalOpportunityQuantity")),
            "contact_id": record_data.get("ContactId"),
            "contact_name": record_data.get("Contact", {}).get("Name"),
            "pricebook_id": record_data.get("Pricebook2Id"),
            "is_private": record_data.get("IsPrivate"),
        }
        return opportunity_metadata
