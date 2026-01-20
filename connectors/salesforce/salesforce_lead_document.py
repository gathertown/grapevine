"""
Salesforce Lead document and chunk classes.
"""

from dataclasses import dataclass

from connectors.salesforce.salesforce_artifacts import SUPPORTED_SALESFORCE_OBJECTS
from connectors.salesforce.salesforce_base_document import (
    BaseSalesforceChunk,
    BaseSalesforceDocument,
    BaseSalesforceDocumentMetadata,
)
from src.utils.type_conversion import safe_int


class SalesforceLeadDocumentMetadata(BaseSalesforceDocumentMetadata):
    """Metadata for Salesforce Lead documents."""

    email: str | None
    phone: str | None
    company: str | None
    title: str | None
    status: str | None
    rating: str | None
    industry: str | None
    lead_source: str | None
    number_of_employees: int | None
    salutation: str | None
    middle_name: str | None
    suffix: str | None
    website: str | None
    mobile_phone: str | None
    fax: str | None
    converted_opportunity_name: str | None
    do_not_call: bool | None
    has_opted_out_of_email: bool | None
    is_unread_by_owner: bool | None


@dataclass
class SalesforceLeadChunk(BaseSalesforceChunk):
    """Represents a single Salesforce Lead chunk."""


@dataclass
class SalesforceLeadDocument(BaseSalesforceDocument):
    """Represents a Salesforce Lead as a document."""

    def get_content(self) -> str:
        """Get the formatted Lead record content."""
        record_data = self.raw_data.get("record_data", {})
        if not record_data:
            return "Lead: [No data available]"

        lines = []

        # Header
        name = self._format_name_fields(record_data) or "Unknown Lead"
        lines.append(f"Lead: {name}")
        lines.append("")

        # Key fields
        if record_data.get("Email"):
            lines.append(f"Email: {record_data['Email']}")
        if record_data.get("Phone"):
            lines.append(f"Phone: {record_data['Phone']}")
        if record_data.get("MobilePhone"):
            lines.append(f"Mobile: {record_data['MobilePhone']}")
        if record_data.get("Fax"):
            lines.append(f"Fax: {record_data['Fax']}")
        if record_data.get("Company"):
            lines.append(f"Company: {record_data['Company']}")
        if record_data.get("Website"):
            lines.append(f"Website: {record_data['Website']}")
        if record_data.get("Title"):
            lines.append(f"Title: {record_data['Title']}")
        if record_data.get("Status"):
            lines.append(f"Status: {record_data['Status']}")
        if record_data.get("Rating"):
            lines.append(f"Rating: {record_data['Rating']}")
        if record_data.get("Industry"):
            lines.append(f"Industry: {record_data['Industry']}")
        if record_data.get("LeadSource"):
            lines.append(f"Lead Source: {record_data['LeadSource']}")
        if record_data.get("IsUnreadByOwner"):
            lines.append("Status: Unread")

        # Company size
        if record_data.get("NumberOfEmployees"):
            lines.append(f"Company Size: {record_data['NumberOfEmployees']} employees")

        # Annual Revenue
        if record_data.get("AnnualRevenue"):
            revenue_str = self._format_currency(record_data["AnnualRevenue"])
            if revenue_str:
                lines.append(f"Annual Revenue: {revenue_str}")

        # Address
        address = self._format_address(
            "Street", "City", "State", "PostalCode", "Country", record_data
        )
        if address:
            lines.append(f"Address: {address}")

        # Owner
        if record_data.get("Owner", {}).get("Name"):
            lines.append(f"Owner: {record_data['Owner']['Name']}")

        # Campaign
        if record_data.get("Campaign", {}).get("Name"):
            lines.append(f"Campaign: {record_data['Campaign']['Name']}")

        # Privacy preferences
        privacy_info = []
        if record_data.get("DoNotCall"):
            privacy_info.append("Do Not Call")
        if record_data.get("HasOptedOutOfEmail"):
            privacy_info.append("Opted Out of Email")
        if privacy_info:
            lines.append(f"Privacy Preferences: {', '.join(privacy_info)}")

        # Converted information
        if record_data.get("IsConverted"):
            lines.append("Status: Converted")
            if record_data.get("ConvertedDate"):
                lines.append(f"Converted Date: {record_data['ConvertedDate']}")
            if record_data.get("ConvertedAccount", {}).get("Name"):
                lines.append(f"Converted Account: {record_data['ConvertedAccount']['Name']}")
            if record_data.get("ConvertedContact", {}).get("Name"):
                lines.append(f"Converted Contact: {record_data['ConvertedContact']['Name']}")
            if record_data.get("ConvertedOpportunity", {}).get("Name"):
                lines.append(
                    f"Converted Opportunity: {record_data['ConvertedOpportunity']['Name']}"
                )

        # Description
        if record_data.get("Description"):
            lines.extend(["", "Description:", record_data["Description"]])

        # Custom fields
        lines.extend(self._format_custom_fields(record_data))

        return "\n".join(lines)

    def _create_chunk(self) -> SalesforceLeadChunk:
        """Create a Lead-specific chunk."""
        return SalesforceLeadChunk(
            document=self,
            raw_data=self.raw_data,
        )

    def get_object_type(self) -> SUPPORTED_SALESFORCE_OBJECTS:
        return "Lead"

    def get_metadata(self) -> SalesforceLeadDocumentMetadata:
        """Get Lead-specific document metadata."""
        base_metadata = super().get_metadata()
        record_data = self.raw_data.get("record_data", {})

        # Convert to Lead-specific metadata
        lead_metadata: SalesforceLeadDocumentMetadata = {
            **base_metadata,
            "email": record_data.get("Email"),
            "phone": record_data.get("Phone"),
            "company": record_data.get("Company"),
            "title": record_data.get("Title"),
            "status": record_data.get("Status"),
            "rating": record_data.get("Rating"),
            "industry": record_data.get("Industry"),
            "lead_source": record_data.get("LeadSource"),
            "number_of_employees": safe_int(record_data.get("NumberOfEmployees")),
            "salutation": record_data.get("Salutation"),
            "middle_name": record_data.get("MiddleName"),
            "suffix": record_data.get("Suffix"),
            "website": record_data.get("Website"),
            "mobile_phone": record_data.get("MobilePhone"),
            "fax": record_data.get("Fax"),
            "converted_opportunity_name": record_data.get("ConvertedOpportunity", {}).get("Name"),
            "do_not_call": record_data.get("DoNotCall"),
            "has_opted_out_of_email": record_data.get("HasOptedOutOfEmail"),
            "is_unread_by_owner": record_data.get("IsUnreadByOwner"),
        }
        return lead_metadata
