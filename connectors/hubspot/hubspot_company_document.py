"""
HubSpot company document classes for indexing.
Single-chunk approach for company data.
"""

from dataclasses import dataclass
from typing import Any, TypedDict

from connectors.base import BaseChunk, BaseDocument
from connectors.base.document_source import DocumentSource


class HubspotCompanyChunkMetadata(TypedDict):
    """Metadata for HubSpot company chunks."""

    company_id: str
    company_name: str | None
    source: str
    chunk_type: str


class HubspotCompanyDocumentMetadata(TypedDict):
    """Metadata for HubSpot company documents."""

    company_id: str
    company_name: str | None
    domain: str | None
    website: str | None
    industry: str | None
    lifecycle_stage: str | None
    country: str | None
    state: str | None
    city: str | None
    employees: str | None
    revenue: float | None
    source_created_at: str | None
    source_updated_at: str | None
    source: str
    type: str


@dataclass
class HubspotCompanyChunk(BaseChunk[HubspotCompanyChunkMetadata]):
    """Single chunk representing entire HubSpot company."""

    def get_content(self) -> str:
        """Return the formatted company content."""
        return self.raw_data.get("content", "")

    def get_metadata(self) -> HubspotCompanyChunkMetadata:
        """Get chunk metadata."""
        return {
            "company_id": self.raw_data.get("company_id", ""),
            "company_name": self.raw_data.get("company_name"),
            "source": "hubspot_company",
            "chunk_type": "company",
        }


@dataclass
class HubspotCompanyDocument(BaseDocument[HubspotCompanyChunk, HubspotCompanyDocumentMetadata]):
    """HubSpot company document with formatted content."""

    raw_data: dict[str, Any]

    def get_content(self) -> str:
        """Generate formatted company content."""
        lines: list[str] = []

        # Header
        # raw_data now contains properties directly (content = properties)
        company_name = self.raw_data.get("name", "Unnamed Company")
        company_id = self.id.replace("hubspot_company_", "")
        lines.append(f"Company: {company_name} (#{company_id})")
        lines.append("")

        # Company Overview Section
        lines.append("=== COMPANY OVERVIEW ===")
        lines.append(f"Name: {company_name}")

        description = self.raw_data.get("description")
        if description:
            lines.append(f"Description: {description}")

        lines.append("")

        # Business Details Section - only if we have any fields
        business_fields: list[str] = []

        industry = self.raw_data.get("industry")
        if industry:
            business_fields.append(f"Industry: {industry}")

        employees = self.raw_data.get("numberofemployees")
        if employees:
            business_fields.append(f"Number of employees: {employees}")

        revenue = self.raw_data.get("annualrevenue")
        if revenue:
            business_fields.append(f"Annual revenue: ${self._format_number(revenue)}")

        lifecycle = self.raw_data.get("lifecyclestage")
        if lifecycle:
            business_fields.append(f"Lifecycle stage: {lifecycle}")

        domain = self.raw_data.get("domain")
        if domain:
            business_fields.append(f"Company domain: {domain}")

        website = self.raw_data.get("website")
        if website:
            business_fields.append(f"Website: {website}")

        if business_fields:
            lines.append("=== BUSINESS DETAILS ===")
            lines.extend(business_fields)
            lines.append("")

        # Contact Information Section - only if we have any fields
        contact_fields = []

        phone = self.raw_data.get("phone")
        if phone:
            contact_fields.append(f"Phone: {phone}")

        address = self.raw_data.get("address")
        if address:
            contact_fields.append(f"Street address: {address}")

        address2 = self.raw_data.get("address2")
        if address2:
            contact_fields.append(f"Address line 2: {address2}")

        if contact_fields:
            lines.append("=== CONTACT INFORMATION ===")
            lines.extend(contact_fields)
            lines.append("")

        # Location Section - only if we have any fields
        location_fields = []

        country = self.raw_data.get("country")
        if country:
            location_fields.append(f"Country/Region: {country}")

        state = self.raw_data.get("state")
        if state:
            location_fields.append(f"State/Province: {state}")

        city = self.raw_data.get("city")
        if city:
            location_fields.append(f"City: {city}")

        if location_fields:
            lines.append("=== LOCATION ===")
            lines.extend(location_fields)
            lines.append("")

        # Custom Properties Section
        custom_properties = self.raw_data.get("custom_properties", {})
        if custom_properties:
            lines.append("=== CUSTOM PROPERTIES ===")
            for key in custom_properties:
                if key in self.raw_data and self.raw_data[key] is not None:
                    lines.append(f"{custom_properties[key]}: {self.raw_data[key]}")
            lines.append("")

        # Metadata Section
        lines.append("=== METADATA ===")

        # Get system fields from raw_data (where metadata was merged)
        create_date = self.raw_data.get("source_created_at")
        if create_date:
            lines.append(f"Company created date: {self._format_date(create_date)}")

        # Use source_updated_at from raw_data
        last_modified = self.raw_data.get("source_updated_at")
        if last_modified:
            lines.append(f"Last modified date: {self._format_date(last_modified)}")

        # HubSpot Object ID
        hs_object_id = self.raw_data.get("hs_object_id", company_id)
        lines.append(f"HubSpot Object ID: {hs_object_id}")

        return "\n".join(lines)

    def to_embedding_chunks(self) -> list[HubspotCompanyChunk]:
        """Create single chunk for the entire company."""
        content = self.get_content()

        chunk = HubspotCompanyChunk(
            document=self,
            raw_data={
                "content": content,
                "company_id": self.id.replace("hubspot_company_", ""),
                "company_name": self.raw_data.get("name"),
            },
        )

        return [chunk]

    def get_metadata(self) -> HubspotCompanyDocumentMetadata:
        """Get document metadata for search and filtering."""
        return {
            "company_id": self.id.replace("hubspot_company_", ""),
            "company_name": self.raw_data.get("name"),
            "domain": self.raw_data.get("domain"),
            "website": self.raw_data.get("website"),
            "industry": self.raw_data.get("industry"),
            "lifecycle_stage": self.raw_data.get("lifecyclestage"),
            "country": self.raw_data.get("country"),
            "state": self.raw_data.get("state"),
            "city": self.raw_data.get("city"),
            "employees": self.raw_data.get("numberofemployees"),
            "revenue": self._safe_float(self.raw_data.get("annualrevenue")),
            "source_created_at": self.raw_data.get("source_created_at"),
            "source_updated_at": self.raw_data.get("source_updated_at"),
            "source": self.get_source(),
            "type": "hubspot_company",
        }

    def get_source_enum(self) -> DocumentSource:
        return DocumentSource.HUBSPOT_COMPANY

    def get_reference_id(self) -> str:
        """Get reference ID for this document."""
        company_id = self.id.replace("hubspot_company_", "")
        return f"r_hubspot_company_{company_id}"

    def _format_date(self, date_str: str) -> str:
        """Format ISO date string to readable format."""
        if not date_str:
            return ""
        try:
            # Handle ISO format with timezone
            if "T" in date_str:
                date_str = date_str.split("T")[0]
            return date_str
        except:
            return date_str

    def _format_number(self, value: Any) -> str:
        """Format number with commas."""
        try:
            num = float(value) if value else 0
            return f"{num:,.2f}".rstrip("0").rstrip(".")
        except:
            return str(value)

    def _safe_float(self, value: Any) -> float | None:
        """Safely convert to float."""
        if value is None or value == "":
            return None
        try:
            return float(value)
        except (ValueError, TypeError):
            return None
