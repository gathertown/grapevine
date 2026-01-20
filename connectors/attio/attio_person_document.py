"""
Attio person document classes for indexing.
Single-chunk approach for person data.
"""

from dataclasses import dataclass
from typing import Any, TypedDict

from connectors.attio.attio_artifacts import AttioPersonArtifact
from connectors.base import BaseChunk, BaseDocument
from connectors.base.document_source import DocumentSource
from connectors.base.utils import convert_timestamp_to_iso
from src.permissions.models import PermissionPolicy


class AttioPersonChunkMetadata(TypedDict, total=False):
    """Metadata for Attio person chunks."""

    person_id: str | None
    person_name: str | None
    source: str | None
    chunk_type: str | None


class AttioPersonDocumentMetadata(TypedDict, total=False):
    """Metadata for Attio person documents."""

    person_id: str
    person_name: str | None
    email_addresses: list[str] | None
    phone_numbers: list[str] | None
    job_title: str | None
    company_name: str | None
    primary_location: str | None
    source_created_at: str | None
    source_updated_at: str | None
    source: str
    type: str


@dataclass
class AttioPersonChunk(BaseChunk[AttioPersonChunkMetadata]):
    """Single chunk representing entire Attio person."""

    def get_content(self) -> str:
        """Return the formatted person content."""
        return self.raw_data.get("content", "")

    def get_metadata(self) -> AttioPersonChunkMetadata:
        """Get chunk metadata."""
        return {
            "person_id": self.raw_data.get("person_id", ""),
            "person_name": self.raw_data.get("person_name"),
            "source": "attio_person",
            "chunk_type": "person",
        }


@dataclass
class AttioPersonDocument(BaseDocument[AttioPersonChunk, AttioPersonDocumentMetadata]):
    """Attio person document with formatted content."""

    raw_data: dict[str, Any]
    metadata: AttioPersonDocumentMetadata | None = None
    chunk_class: type[AttioPersonChunk] = AttioPersonChunk

    @classmethod
    def from_artifact(
        cls,
        artifact: AttioPersonArtifact,
        permission_policy: PermissionPolicy = "tenant",
        permission_allowed_tokens: list[str] | None = None,
    ) -> "AttioPersonDocument":
        """Create document from artifact."""
        record_data = artifact.content.record_data
        record_id = artifact.metadata.record_id

        return cls(
            id=f"attio_person_{record_id}",
            raw_data=record_data,
            source_updated_at=artifact.source_updated_at,
            permission_policy=permission_policy,
            permission_allowed_tokens=permission_allowed_tokens,
        )

    def get_header_content(self) -> str:
        """Get header content for display."""
        metadata = self.get_metadata()
        name = metadata.get("person_name") or "Unknown Person"
        return f"Person: {name} ({metadata.get('person_id', self.id)})"

    def get_content(self) -> str:
        """Generate formatted person content."""
        lines: list[str] = []

        # Header
        person_name = self._get_name() or "Unnamed Person"
        person_id = self.id.replace("attio_person_", "")
        lines.append(f"Person: {person_name} (#{person_id})")
        lines.append("")

        # Person Overview Section
        lines.append("=== PERSON OVERVIEW ===")
        lines.append(f"Name: {person_name}")

        job_title = self._get_attribute_value("job_title")
        if job_title:
            lines.append(f"Job Title: {job_title}")

        description = self._get_attribute_value("description")
        if description:
            lines.append(f"About: {description}")

        lines.append("")

        # Contact Information Section
        contact_fields: list[str] = []

        email_addresses = self._get_attribute_value("email_addresses")
        if email_addresses and isinstance(email_addresses, list):
            contact_fields.append(f"Email: {', '.join(email_addresses)}")

        phone_numbers = self._get_attribute_value("phone_numbers")
        if phone_numbers and isinstance(phone_numbers, list):
            contact_fields.append(f"Phone: {', '.join(phone_numbers)}")

        if contact_fields:
            lines.append("=== CONTACT INFORMATION ===")
            lines.extend(contact_fields)
            lines.append("")

        # Company Association Section
        company = self._get_attribute_value("company")
        if company:
            lines.append("=== COMPANY ===")
            if isinstance(company, dict):
                company_name = company.get("name", "Unknown Company")
                lines.append(f"Company: {company_name}")
            elif isinstance(company, list) and company:
                for comp in company[:5]:  # Limit to first 5 companies
                    if isinstance(comp, dict):
                        comp_name = comp.get("name", "Unknown Company")
                        lines.append(f"- {comp_name}")
                    else:
                        lines.append(f"- {comp}")
            else:
                lines.append(f"Company: {company}")
            lines.append("")

        # Location Section
        location = self._get_attribute_value("primary_location")
        if location:
            lines.append("=== LOCATION ===")
            if isinstance(location, dict):
                location_parts = []
                if location.get("locality"):
                    location_parts.append(location["locality"])
                if location.get("region"):
                    location_parts.append(location["region"])
                if location.get("country_code"):
                    location_parts.append(location["country_code"])
                lines.append(f"Location: {', '.join(location_parts)}")
            else:
                lines.append(f"Location: {location}")
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

        create_date = self.raw_data.get("created_at")
        if create_date:
            lines.append(f"Created: {self._format_date(create_date)}")

        modified_date = self.raw_data.get("updated_at")
        if modified_date:
            lines.append(f"Last modified: {self._format_date(modified_date)}")

        lines.append(f"Attio Record ID: {person_id}")

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

    def _get_name(self) -> str | None:
        """Get person's full name from Attio record.

        Attio stores name as a complex object with multiple parts.
        We need to access the raw attribute data directly to get fallback fields.
        """
        # Access raw name attribute data directly to get full dict with all name parts
        values = self.raw_data.get("values", {})
        name_values = values.get("name", [])

        if not name_values or not isinstance(name_values, list):
            return None

        first_value = name_values[0]
        if not isinstance(first_value, dict):
            return str(first_value) if first_value else None

        # Try full_name first
        full_name = first_value.get("full_name")
        if full_name:
            return full_name

        # Fallback to first_name + last_name
        first = first_value.get("first_name", "")
        last = first_value.get("last_name", "")
        if first or last:
            return f"{first} {last}".strip()

        return None

    def to_embedding_chunks(self) -> list[AttioPersonChunk]:
        """Create single chunk for the entire person."""
        content = self.get_content()
        metadata = self.get_metadata()

        chunk = self.chunk_class(
            document=self,
            raw_data={
                "content": content,
                "person_id": metadata.get("person_id"),
                "person_name": metadata.get("person_name"),
            },
        )
        self.populate_chunk_permissions(chunk)

        return [chunk]

    def get_metadata(self) -> AttioPersonDocumentMetadata:
        """Get document metadata for search and filtering."""
        if self.metadata is not None:
            return self.metadata

        email_addresses = self._get_attribute_value("email_addresses")
        phone_numbers = self._get_attribute_value("phone_numbers")
        company = self._get_attribute_value("company")

        company_name = None
        if company:
            if isinstance(company, dict):
                company_name = company.get("name")
            elif isinstance(company, list) and company:
                first_company = company[0]
                if isinstance(first_company, dict):
                    company_name = first_company.get("name")

        return {
            "person_id": self.id.replace("attio_person_", ""),
            "person_name": self._get_name(),
            "email_addresses": email_addresses if isinstance(email_addresses, list) else None,
            "phone_numbers": phone_numbers if isinstance(phone_numbers, list) else None,
            "job_title": self._get_attribute_value("job_title"),
            "company_name": company_name,
            "primary_location": self._format_location(
                self._get_attribute_value("primary_location")
            ),
            "source_created_at": convert_timestamp_to_iso(self.raw_data.get("created_at")),
            "source_updated_at": convert_timestamp_to_iso(self.raw_data.get("updated_at")),
            "source": self.get_source(),
            "type": "attio_person",
        }

    def get_source_enum(self) -> DocumentSource:
        return DocumentSource.ATTIO_PERSON

    def get_reference_id(self) -> str:
        """Get reference ID for this document."""
        person_id = self.id.replace("attio_person_", "")
        return f"r_attio_person_{person_id}"

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
