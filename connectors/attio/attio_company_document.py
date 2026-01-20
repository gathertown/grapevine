"""
Attio company document classes for indexing.
Single-chunk approach for company data.
"""

from dataclasses import dataclass
from typing import Any, TypedDict

from connectors.attio.attio_artifacts import AttioCompanyArtifact
from connectors.base import BaseChunk, BaseDocument
from connectors.base.document_source import DocumentSource
from connectors.base.utils import convert_timestamp_to_iso
from src.permissions.models import PermissionPolicy


class AttioCompanyChunkMetadata(TypedDict, total=False):
    """Metadata for Attio company chunks."""

    company_id: str | None
    company_name: str | None
    created_at: str | None
    updated_at: str | None


class AttioCompanyDocumentMetadata(TypedDict, total=False):
    """Metadata for Attio company documents."""

    company_id: str
    company_name: str | None
    domains: list[str] | None
    description: str | None
    categories: list[str] | None
    estimated_arr: float | None
    primary_location: str | None
    source_created_at: str | None
    source_updated_at: str | None
    source: str
    type: str


@dataclass
class AttioCompanyChunk(BaseChunk[AttioCompanyChunkMetadata]):
    """Single chunk representing entire Attio company."""

    def get_content(self) -> str:
        """Return the formatted company content."""
        parts = []
        if self.raw_data.get("name"):
            parts.append(f"Company Name: {self.raw_data.get('name')}")
        if self.raw_data.get("domains"):
            domains = self.raw_data.get("domains", [])
            if domains:
                parts.append(f"Domains: {', '.join(domains)}")
        if self.raw_data.get("description"):
            parts.append(f"Description: {self.raw_data.get('description')}")
        if self.raw_data.get("categories"):
            categories = self.raw_data.get("categories", [])
            if categories:
                parts.append(f"Categories: {', '.join(categories)}")
        if self.raw_data.get("estimated_arr"):
            parts.append(f"Estimated ARR: ${self.raw_data.get('estimated_arr'):,.2f}")
        if self.raw_data.get("location"):
            parts.append(f"Location: {self.raw_data.get('location')}")

        return "\n".join(parts) if parts else "Company information"

    def get_metadata(self) -> AttioCompanyChunkMetadata:
        """Get chunk metadata."""
        return {
            "company_id": self.raw_data.get("company_id"),
            "company_name": self.raw_data.get("name"),
            "created_at": self.raw_data.get("created_at"),
            "updated_at": self.raw_data.get("updated_at"),
        }


@dataclass
class AttioCompanyDocument(BaseDocument[AttioCompanyChunk, AttioCompanyDocumentMetadata]):
    """Attio company document with formatted content."""

    raw_data: dict[str, Any]
    metadata: AttioCompanyDocumentMetadata | None = None
    chunk_class: type[AttioCompanyChunk] = AttioCompanyChunk

    @classmethod
    def from_artifact(
        cls,
        artifact: AttioCompanyArtifact,
        permission_policy: PermissionPolicy = "tenant",
        permission_allowed_tokens: list[str] | None = None,
    ) -> "AttioCompanyDocument":
        """Create document from artifact."""
        record_data = artifact.content.record_data
        record_id = artifact.metadata.record_id

        return cls(
            id=f"attio_company_{record_id}",
            raw_data=record_data,
            source_updated_at=artifact.source_updated_at,
            permission_policy=permission_policy,
            permission_allowed_tokens=permission_allowed_tokens,
        )

    def get_content(self) -> str:
        """Generate formatted company content."""
        record_data = self.raw_data
        lines: list[str] = []

        # Header
        company_name = self._get_attribute_value("name") or "Unnamed Company"
        company_id = self.id.replace("attio_company_", "")
        lines.append(f"Company: {company_name} (#{company_id})")
        lines.append("")

        # Company Overview Section
        lines.append("=== COMPANY OVERVIEW ===")
        lines.append(f"Name: {company_name}")

        description = self._get_attribute_value("description")
        if description:
            lines.append(f"Description: {description}")

        categories = self._get_attribute_value("categories")
        if categories and isinstance(categories, list):
            lines.append(f"Categories: {', '.join(categories)}")

        lines.append("")

        # Business Details Section
        business_fields: list[str] = []

        estimated_arr = self._get_attribute_value("estimated_arr_usd")
        if estimated_arr:
            business_fields.append(f"Estimated ARR: ${self._format_number(estimated_arr)}")

        domains = self._get_attribute_value("domains")
        if domains and isinstance(domains, list):
            business_fields.append(f"Domains: {', '.join(domains)}")

        if business_fields:
            lines.append("=== BUSINESS DETAILS ===")
            lines.extend(business_fields)
            lines.append("")

        # Location Section
        location = self._get_attribute_value("primary_location")
        if location:
            lines.append("=== LOCATION ===")
            lines.append(f"Location: {self._format_location(location)}")
            lines.append("")

        # Social Links Section
        social_fields: list[str] = []

        linkedin = self._get_attribute_value("linkedin")
        if linkedin:
            social_fields.append(f"LinkedIn: {linkedin}")

        twitter = self._get_attribute_value("twitter")
        if twitter:
            social_fields.append(f"Twitter: {twitter}")

        if social_fields:
            lines.append("=== SOCIAL LINKS ===")
            lines.extend(social_fields)
            lines.append("")

        # Metadata Section
        lines.append("=== METADATA ===")

        create_date = record_data.get("created_at")
        if create_date:
            lines.append(f"Created: {self._format_date(create_date)}")

        modified_date = record_data.get("updated_at")
        if modified_date:
            lines.append(f"Last modified: {self._format_date(modified_date)}")

        lines.append(f"Attio Record ID: {company_id}")

        return "\n".join(lines)

    def _get_attribute_value(self, attribute_slug: str) -> Any:
        """Extract attribute value from Attio record format.

        Attio stores attributes in a nested structure with varying value keys:
        - Most attributes: {"value": actual_value}
        - Domains: {"domain": "example.com"}
        - Email addresses: {"email_address": "user@example.com"}
        - Names: {"first_name": "...", "last_name": "...", "full_name": "..."}
        - Select/Status: {"option": {"title": "..."}}
        - Record references: {"target_record_id": "...", "target_object": "...", "name": {...}}

        For list attributes (domains, email_addresses), returns all values as a list.
        For record references, returns the full dict to allow name extraction.
        """
        values = self.raw_data.get("values", {})
        attribute_values = values.get(attribute_slug, [])

        if not attribute_values or not isinstance(attribute_values, list):
            return None

        # Handle list attributes that return multiple values
        if attribute_slug == "domains":
            return [v.get("domain") for v in attribute_values if v.get("domain")]

        if attribute_slug == "email_addresses":
            return [v.get("email_address") for v in attribute_values if v.get("email_address")]

        if attribute_slug == "phone_numbers":
            return [
                v.get("phone_number") or v.get("original_phone_number")
                for v in attribute_values
                if v.get("phone_number") or v.get("original_phone_number")
            ]

        # Single value attributes
        first_value = attribute_values[0]
        if isinstance(first_value, dict):
            # Try common value keys in order of specificity
            # Use 'in' check to handle falsy values like 0, False, ""
            if "value" in first_value:
                return first_value["value"]
            if "full_name" in first_value:
                return first_value["full_name"]
            # Handle select/status attributes - extract the option title
            if "option" in first_value and isinstance(first_value["option"], dict):
                return first_value["option"].get("title")
            # Handle record reference attributes - return full dict for name extraction
            if "target_record_id" in first_value:
                return first_value
            # Handle record reference attributes (alternate format)
            if "target_object" in first_value:
                return first_value
            return first_value

        # Return primitive values directly (string, number, etc.)
        return first_value

    def to_embedding_chunks(self) -> list[AttioCompanyChunk]:
        """Create single chunk for the entire company."""
        metadata = self.get_metadata()

        chunk = self.chunk_class(
            document=self,
            raw_data={
                "company_id": metadata.get("company_id"),
                "name": metadata.get("company_name"),
                "domains": metadata.get("domains"),
                "description": metadata.get("description"),
                "categories": metadata.get("categories"),
                "estimated_arr": metadata.get("estimated_arr"),
                "location": metadata.get("primary_location"),
                "created_at": metadata.get("source_created_at"),
                "updated_at": metadata.get("source_updated_at"),
            },
        )
        self.populate_chunk_permissions(chunk)

        return [chunk]

    def get_metadata(self) -> AttioCompanyDocumentMetadata:
        """Get document metadata for search and filtering."""
        if self.metadata is not None:
            return self.metadata

        domains = self._get_attribute_value("domains")
        categories = self._get_attribute_value("categories")

        return {
            "company_id": self.id.replace("attio_company_", ""),
            "company_name": self._get_attribute_value("name"),
            "domains": domains if isinstance(domains, list) else None,
            "description": self._get_attribute_value("description"),
            "categories": categories if isinstance(categories, list) else None,
            "estimated_arr": self._safe_float(self._get_attribute_value("estimated_arr_usd")),
            "primary_location": self._format_location(
                self._get_attribute_value("primary_location")
            ),
            "source_created_at": convert_timestamp_to_iso(self.raw_data.get("created_at")),
            "source_updated_at": convert_timestamp_to_iso(self.raw_data.get("updated_at")),
            "source": DocumentSource.ATTIO_COMPANY.value,
            "type": "attio_company",
        }

    def get_source_enum(self) -> DocumentSource:
        return DocumentSource.ATTIO_COMPANY

    def get_reference_id(self) -> str:
        """Get reference ID for this document."""
        company_id = self.id.replace("attio_company_", "")
        return f"r_attio_company_{company_id}"

    def get_header_content(self) -> str:
        """Get header content for display."""
        metadata = self.get_metadata()
        name = metadata.get("company_name") or "Unknown Company"
        return f"Company: {name} ({metadata.get('company_id', self.id)})"

    def _format_date(self, date_str: str) -> str:
        """Format ISO date string to readable format."""
        if not date_str:
            return ""
        try:
            if "T" in date_str:
                date_str = date_str.split("T")[0]
            return date_str
        except Exception:
            return date_str

    def _format_number(self, value: Any) -> str:
        """Format number with commas."""
        try:
            num = float(value) if value else 0
            return f"{num:,.2f}".rstrip("0").rstrip(".")
        except Exception:
            return str(value)

    def _format_location(self, location: Any) -> str | None:
        """Format location object to string."""
        if not location:
            return None
        if isinstance(location, dict):
            parts = []
            if location.get("locality"):
                parts.append(location["locality"])
            if location.get("region"):
                parts.append(location["region"])
            if location.get("country_code"):
                parts.append(location["country_code"])
            return ", ".join(parts) if parts else None
        return str(location)

    def _safe_float(self, value: Any) -> float | None:
        """Safely convert to float."""
        if value is None or value == "":
            return None
        try:
            return float(value)
        except (ValueError, TypeError):
            return None
