"""
Salesforce Contact document and chunk classes.
"""

from dataclasses import dataclass

from connectors.salesforce.salesforce_artifacts import SUPPORTED_SALESFORCE_OBJECTS
from connectors.salesforce.salesforce_base_document import (
    BaseSalesforceChunk,
    BaseSalesforceDocument,
    BaseSalesforceDocumentMetadata,
)


class SalesforceContactDocumentMetadata(BaseSalesforceDocumentMetadata):
    """Metadata for Salesforce Contact documents."""

    email: str | None
    phone: str | None
    title: str | None
    department: str | None
    account_name: str | None
    account_id: str | None
    salutation: str | None
    middle_name: str | None
    suffix: str | None
    assistant_name: str | None
    assistant_phone: str | None
    birthdate: str | None
    mobile_phone: str | None
    home_phone: str | None
    other_phone: str | None
    fax: str | None
    do_not_call: bool | None
    has_opted_out_of_email: bool | None


@dataclass
class SalesforceContactChunk(BaseSalesforceChunk):
    """Represents a single Salesforce Contact chunk."""


@dataclass
class SalesforceContactDocument(BaseSalesforceDocument):
    """Represents a Salesforce Contact as a document."""

    def get_content(self) -> str:
        """Get the formatted Contact record content."""
        record_data = self.raw_data.get("record_data", {})
        if not record_data:
            return "Contact: [No data available]"

        lines = []

        # Header
        name = self._format_name_fields(record_data) or "Unknown Contact"
        lines.append(f"Contact: {name}")
        lines.append("")

        # Key fields
        if record_data.get("Email"):
            lines.append(f"Email: {record_data['Email']}")
        if record_data.get("Phone"):
            lines.append(f"Phone: {record_data['Phone']}")
        if record_data.get("MobilePhone"):
            lines.append(f"Mobile: {record_data['MobilePhone']}")
        if record_data.get("HomePhone"):
            lines.append(f"Home Phone: {record_data['HomePhone']}")
        if record_data.get("OtherPhone"):
            lines.append(f"Other Phone: {record_data['OtherPhone']}")
        if record_data.get("Fax"):
            lines.append(f"Fax: {record_data['Fax']}")
        if record_data.get("Title"):
            lines.append(f"Title: {record_data['Title']}")
        if record_data.get("Department"):
            lines.append(f"Department: {record_data['Department']}")
        if record_data.get("Birthdate"):
            lines.append(f"Birthdate: {record_data['Birthdate']}")

        # Account relationship
        if record_data.get("Account", {}).get("Name"):
            lines.append(f"Account: {record_data['Account']['Name']}")

        # Assistant information
        if record_data.get("AssistantName"):
            lines.append(f"Assistant: {record_data['AssistantName']}")
            if record_data.get("AssistantPhone"):
                lines.append(f"Assistant Phone: {record_data['AssistantPhone']}")

        # Mailing Address
        mailing_address = self._format_address(
            "MailingStreet",
            "MailingCity",
            "MailingState",
            "MailingPostalCode",
            "MailingCountry",
            record_data,
        )
        if mailing_address:
            lines.append(f"Mailing Address: {mailing_address}")

        # Other Address
        other_address = self._format_address(
            "OtherStreet",
            "OtherCity",
            "OtherState",
            "OtherPostalCode",
            "OtherCountry",
            record_data,
        )
        if other_address:
            lines.append(f"Other Address: {other_address}")

        # Lead Source
        if record_data.get("LeadSource"):
            lines.append(f"Lead Source: {record_data['LeadSource']}")

        # Reports To
        if record_data.get("ReportsTo", {}).get("Name"):
            lines.append(f"Reports To: {record_data['ReportsTo']['Name']}")

        # Privacy preferences
        privacy_info = []
        if record_data.get("DoNotCall"):
            privacy_info.append("Do Not Call")
        if record_data.get("HasOptedOutOfEmail"):
            privacy_info.append("Opted Out of Email")
        if privacy_info:
            lines.append(f"Privacy Preferences: {', '.join(privacy_info)}")

        # Description
        if record_data.get("Description"):
            lines.extend(["", "Description:", record_data["Description"]])

        # Custom fields
        lines.extend(self._format_custom_fields(record_data))

        return "\n".join(lines)

    def _create_chunk(self) -> SalesforceContactChunk:
        """Create a Contact-specific chunk."""
        return SalesforceContactChunk(
            document=self,
            raw_data=self.raw_data,
        )

    def get_object_type(self) -> SUPPORTED_SALESFORCE_OBJECTS:
        return "Contact"

    def get_metadata(self) -> SalesforceContactDocumentMetadata:
        """Get Contact-specific document metadata."""
        base_metadata = super().get_metadata()
        record_data = self.raw_data.get("record_data", {})

        # Convert to Contact-specific metadata
        contact_metadata: SalesforceContactDocumentMetadata = {
            **base_metadata,
            "email": record_data.get("Email"),
            "phone": record_data.get("Phone"),
            "title": record_data.get("Title"),
            "department": record_data.get("Department"),
            "account_name": record_data.get("Account", {}).get("Name"),
            "account_id": record_data.get("Account", {}).get("Id"),
            "salutation": record_data.get("Salutation"),
            "middle_name": record_data.get("MiddleName"),
            "suffix": record_data.get("Suffix"),
            "assistant_name": record_data.get("AssistantName"),
            "assistant_phone": record_data.get("AssistantPhone"),
            "birthdate": record_data.get("Birthdate"),
            "mobile_phone": record_data.get("MobilePhone"),
            "home_phone": record_data.get("HomePhone"),
            "other_phone": record_data.get("OtherPhone"),
            "fax": record_data.get("Fax"),
            "do_not_call": record_data.get("DoNotCall"),
            "has_opted_out_of_email": record_data.get("HasOptedOutOfEmail"),
        }
        return contact_metadata
