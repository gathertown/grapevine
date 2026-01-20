"""
Salesforce Case document and chunk classes.
"""

from dataclasses import dataclass

from connectors.salesforce.salesforce_artifacts import SUPPORTED_SALESFORCE_OBJECTS
from connectors.salesforce.salesforce_base_document import (
    BaseSalesforceChunk,
    BaseSalesforceDocument,
    BaseSalesforceDocumentMetadata,
)


class SalesforceCaseDocumentMetadata(BaseSalesforceDocumentMetadata):
    """Metadata for Salesforce Case documents."""

    case_number: str | None
    status: str | None
    priority: str | None
    case_type: str | None
    origin: str | None
    account_name: str | None
    account_id: str | None
    contact_name: str | None
    contact_id: str | None
    is_closed: bool | None
    parent_case_id: str | None
    business_hours: str | None
    sla_start_date: str | None
    sla_exit_date: str | None
    is_stopped: bool | None
    entitlement_id: str | None
    contact_email: str | None
    contact_phone: str | None


@dataclass
class SalesforceCaseChunk(BaseSalesforceChunk):
    """Represents a single Salesforce Case chunk."""


@dataclass
class SalesforceCaseDocument(BaseSalesforceDocument):
    """Represents a Salesforce Case as a document."""

    def get_content(self) -> str:
        """Get the formatted Case record content."""
        record_data = self.raw_data.get("record_data", {})
        if not record_data:
            return "Case: [No data available]"

        lines = []

        # Header
        subject = record_data.get("Subject", "Unknown Case")
        case_number = record_data.get("CaseNumber", "")
        if case_number:
            lines.append(f"Case {case_number}: {subject}")
        else:
            lines.append(f"Case: {subject}")
        lines.append("")

        # Key fields
        if record_data.get("Status"):
            lines.append(f"Status: {record_data['Status']}")
        if record_data.get("Priority"):
            lines.append(f"Priority: {record_data['Priority']}")
        if record_data.get("Type"):
            lines.append(f"Type: {record_data['Type']}")
        if record_data.get("Origin"):
            lines.append(f"Origin: {record_data['Origin']}")

        # Relationships
        if record_data.get("Account", {}).get("Name"):
            lines.append(f"Account: {record_data['Account']['Name']}")
        if record_data.get("Contact", {}).get("Name"):
            lines.append(f"Contact: {record_data['Contact']['Name']}")
        if record_data.get("ParentId"):
            lines.append(f"Parent Case: {record_data['ParentId']}")

        # Owner
        if record_data.get("Owner", {}).get("Name"):
            lines.append(f"Owner: {record_data['Owner']['Name']}")

        # Dates
        if record_data.get("CreatedDate"):
            lines.append(f"Created: {record_data['CreatedDate']}")
        if record_data.get("ClosedDate"):
            lines.append(f"Closed: {record_data['ClosedDate']}")
        if record_data.get("SlaStartDate"):
            lines.append(f"SLA Start: {record_data['SlaStartDate']}")
        if record_data.get("SlaExitDate"):
            lines.append(f"SLA Exit: {record_data['SlaExitDate']}")

        # Product/Asset
        if record_data.get("Product", {}).get("Name"):
            lines.append(f"Product: {record_data['Product']['Name']}")
        if record_data.get("Asset", {}).get("Name"):
            lines.append(f"Asset: {record_data['Asset']['Name']}")

        # Status information
        if record_data.get("IsEscalated"):
            lines.append("Escalated: Yes")
        if record_data.get("IsStopped"):
            lines.append("Timer Stopped: Yes")
        if record_data.get("BusinessHoursId"):
            lines.append(f"Business Hours: {record_data['BusinessHoursId']}")
        if record_data.get("EntitlementId"):
            lines.append(f"Entitlement: {record_data['EntitlementId']}")

        # Contact information
        if record_data.get("ContactEmail"):
            lines.append(f"Contact Email: {record_data['ContactEmail']}")
        if record_data.get("ContactPhone"):
            lines.append(f"Contact Phone: {record_data['ContactPhone']}")
        if record_data.get("SuppliedEmail"):
            lines.append(f"Customer Email: {record_data['SuppliedEmail']}")
        if record_data.get("SuppliedPhone"):
            lines.append(f"Customer Phone: {record_data['SuppliedPhone']}")

        # Description
        if record_data.get("Description"):
            lines.extend(["", "Description:", record_data["Description"]])

        # Comments (if available)
        if record_data.get("Comments"):
            lines.extend(["", "Comments:", record_data["Comments"]])

        # Resolution
        if record_data.get("Resolution"):
            lines.extend(["", "Resolution:", record_data["Resolution"]])

        # Reason for closure
        if record_data.get("Reason"):
            lines.extend(["", f"Reason: {record_data['Reason']}"])

        # Custom fields
        lines.extend(self._format_custom_fields(record_data))

        return "\n".join(lines)

    def _create_chunk(self) -> SalesforceCaseChunk:
        """Create a Case-specific chunk."""
        return SalesforceCaseChunk(
            document=self,
            raw_data=self.raw_data,
        )

    def get_object_type(self) -> SUPPORTED_SALESFORCE_OBJECTS:
        return "Case"

    def get_metadata(self) -> SalesforceCaseDocumentMetadata:
        """Get Case-specific document metadata."""
        base_metadata = super().get_metadata()
        record_data = self.raw_data.get("record_data", {})

        # Convert to Case-specific metadata
        case_metadata: SalesforceCaseDocumentMetadata = {
            **base_metadata,
            "case_number": record_data.get("CaseNumber"),
            "status": record_data.get("Status"),
            "priority": record_data.get("Priority"),
            "case_type": record_data.get("Type"),
            "origin": record_data.get("Origin"),
            "account_name": record_data.get("Account", {}).get("Name"),
            "account_id": record_data.get("Account", {}).get("Id"),
            "contact_name": record_data.get("Contact", {}).get("Name"),
            "contact_id": record_data.get("Contact", {}).get("Id"),
            "is_closed": record_data.get("IsClosed"),
            "parent_case_id": record_data.get("ParentId"),
            "business_hours": record_data.get("BusinessHoursId"),
            "sla_start_date": record_data.get("SlaStartDate"),
            "sla_exit_date": record_data.get("SlaExitDate"),
            "is_stopped": record_data.get("IsStopped"),
            "entitlement_id": record_data.get("EntitlementId"),
            "contact_email": record_data.get("ContactEmail"),
            "contact_phone": record_data.get("ContactPhone"),
        }
        return case_metadata
