"""
HubSpot contact document classes for v2 implementation.
Simple single-chunk approach for contact data without activities.
"""

import logging
from dataclasses import dataclass
from typing import Any, TypedDict

from langchain_text_splitters import RecursiveCharacterTextSplitter

from connectors.base import BaseChunk, BaseDocument
from connectors.base.document_source import DocumentSource

logger = logging.getLogger(__name__)


class HubspotContactChunkMetadata(TypedDict):
    """Metadata for HubSpot contact chunks."""

    contact_id: str
    contact_name: str | None
    email: str | None
    source: str
    chunk_type: str
    source_created_at: str | None
    source_updated_at: str | None
    chunk_index: int
    total_chunks: int


class HubspotContactDocumentMetadata(TypedDict):
    """Metadata for HubSpot contact documents."""

    contact_id: str
    contact_name: str | None
    email: str | None
    source_created_at: str | None
    source_updated_at: str | None
    owner_id: str | None
    company_ids: list[str] | None
    company_names: list[str] | None
    lifecycle_stage: str | None
    source: str
    type: str


@dataclass
class HubspotContactChunk(BaseChunk[HubspotContactChunkMetadata]):
    """Single chunk representing entire HubSpot contact."""

    def get_content(self) -> str:
        """Return the formatted contact content."""
        content = self.raw_data.get("content", "")
        chunk_index = self.raw_data.get("chunk_index", 0)
        total_chunks = self.raw_data.get("total_chunks", 1)

        if total_chunks == 1:
            return content

        position_context = f"[Part {chunk_index + 1} of {total_chunks}]\n"
        return f"{position_context}{content}"

    def get_metadata(self) -> HubspotContactChunkMetadata:
        """Get chunk metadata."""
        return {
            "contact_id": self.raw_data.get("contact_id", ""),
            "contact_name": self.raw_data.get("contact_name"),
            "email": self.raw_data.get("email"),
            "source": "hubspot_contact",
            "chunk_type": "contact",
            "chunk_index": self.raw_data.get("chunk_index", 0),
            "total_chunks": self.raw_data.get("total_chunks", 1),
            "source_created_at": self.raw_data.get("source_created_at"),
            "source_updated_at": self.raw_data.get("source_updated_at"),
        }


@dataclass
class HubspotContactDocument(BaseDocument[HubspotContactChunk, HubspotContactDocumentMetadata]):
    """HubSpot contact document with formatted content."""

    raw_data: dict[str, Any]

    def get_content(self) -> str:
        """Generate formatted contact content following the v2 examples."""
        lines: list[str] = []

        # Header - construct name from firstname and lastname
        firstname = self.raw_data.get("firstname", "")
        lastname = self.raw_data.get("lastname", "")
        if firstname and lastname:
            contact_name = f"{firstname} {lastname}".strip() or "Unknown Contact"
        else:
            contact_name = self.raw_data.get("email", "")
        contact_id = self.id.replace("hubspot_contact_", "")
        lines.append(f"Contact: {contact_name} (#{contact_id})")
        lines.append("")
        lines.append("=== CONTACT INFORMATION ===")

        # Email
        email = self.raw_data.get("email")
        if email:
            lines.append(f"Email: {email}")

        # Phone
        phone = self.raw_data.get("phone")
        if phone:
            lines.append(f"Phone: {phone}")

        # Mobile phone
        mobilephone = self.raw_data.get("mobilephone")
        if mobilephone:
            lines.append(f"Mobile Phone: {mobilephone}")

        # Job title
        jobtitle = self.raw_data.get("jobtitle")
        if jobtitle:
            lines.append(f"Job Title: {jobtitle}")

        # Company name (primary)
        company = self.raw_data.get("company")
        if company:
            lines.append(f"Company: {company}")

        # Associated companies
        company_names = self.raw_data.get("company_names")
        if company_names:
            lines.append(f"Associated Companies: {', '.join(company_names)}")

        # Lifecycle stage
        lifecyclestage = self.raw_data.get("lifecyclestage")
        if lifecyclestage:
            lines.append(f"Lifecycle Stage: {lifecyclestage}")

        # Lead status
        hs_lead_status = self.raw_data.get("hs_lead_status")
        if hs_lead_status:
            lines.append(f"Lead Status: {hs_lead_status}")

        # Contact owner
        hubspot_owner_id = self.raw_data.get("hubspot_owner_id")
        if hubspot_owner_id:
            lines.append(f"Owner ID: {hubspot_owner_id}")

        # Location information
        city = self.raw_data.get("city")
        state = self.raw_data.get("state")
        country = self.raw_data.get("country")
        location_parts = [part for part in [city, state, country] if part]
        if location_parts:
            lines.append(f"Location: {', '.join(location_parts)}")

        # Annual revenue
        annualrevenue = self.raw_data.get("annualrevenue")
        if annualrevenue:
            lines.append(f"Annual Revenue: {annualrevenue}")

        # Number of employees
        numemployees = self.raw_data.get("numemployees")
        if numemployees:
            lines.append(f"Number of Employees: {numemployees}")

        # Object source
        hs_object_source_label = self.raw_data.get("hs_object_source_label")
        if hs_object_source_label:
            lines.append(f"Object Source: {hs_object_source_label}")

        # Create date
        createdate = self.raw_data.get("createdate")
        if createdate:
            lines.append(f"Create Date: {createdate}")

        # Last modified date
        lastmodifieddate = self.raw_data.get("lastmodifieddate")
        if lastmodifieddate:
            lines.append(f"Last Modified Date: {lastmodifieddate}")

        # Custom properties
        custom_properties = self.raw_data.get("custom_properties", {})
        if custom_properties:
            lines.append("")
            lines.append("=== CUSTOM PROPERTIES ===")
            for key in custom_properties:
                if key in self.raw_data and self.raw_data[key] is not None:
                    lines.append(f"{custom_properties[key]}: {self.raw_data[key]}")
            lines.append("")

        return "\n".join(lines)

    def to_embedding_chunks(self) -> list[HubspotContactChunk]:
        """Create single chunk for the entire contact."""
        content = self.get_content()

        if not content.strip():
            return []

        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=6000,
            chunk_overlap=100,
            length_function=len,
            separators=["\n\n", "\n", ". ", " ", ""],
        )

        text_chunks = text_splitter.split_text(content)

        logger.info(
            f"HubSpot contact {self.id.replace('hubspot_contact_', '')} created {len(text_chunks)} chunks from {len(content)} characters"
        )

        embedding_chunks: list[HubspotContactChunk] = []

        # Construct contact name for metadata
        firstname = self.raw_data.get("firstname", "")
        lastname = self.raw_data.get("lastname", "")
        if firstname and lastname:
            contact_name = f"{firstname} {lastname}".strip() or None
        else:
            contact_name = self.raw_data.get("email", "")

        for i, chunk_text in enumerate(text_chunks):
            chunk_data = {
                "contact_id": self.id.replace("hubspot_contact_", ""),
                "contact_name": contact_name,
                "source_created_at": self.raw_data.get("source_created_at"),
                "source_updated_at": self.raw_data.get("source_updated_at"),
                "content": chunk_text,
                "chunk_index": i,
                "total_chunks": len(text_chunks),
            }

            embedding_chunks.append(
                HubspotContactChunk(
                    document=self,
                    raw_data=chunk_data,
                )
            )

        return embedding_chunks

    def get_metadata(self) -> HubspotContactDocumentMetadata:
        """Get document metadata for search and filtering."""
        # Construct contact name for metadata
        firstname = self.raw_data.get("firstname", "")
        lastname = self.raw_data.get("lastname", "")
        if firstname and lastname:
            contact_name = f"{firstname} {lastname}".strip() or None
        else:
            contact_name = self.raw_data.get("email", "")

        return {
            "contact_id": self.id.replace("hubspot_contact_", ""),  # Extract from document ID
            "contact_name": contact_name,
            "email": self.raw_data.get("email"),
            "source_created_at": self.raw_data.get("source_created_at"),
            "source_updated_at": self.raw_data.get("source_updated_at"),
            "owner_id": self.raw_data.get("hubspot_owner_id"),
            "company_ids": self.raw_data.get("company_ids"),
            "company_names": self.raw_data.get("company_names"),
            "lifecycle_stage": self.raw_data.get("lifecyclestage"),
            "source": self.get_source(),
            "type": "hubspot_contact",
        }

    def get_source_enum(self) -> DocumentSource:
        return DocumentSource.HUBSPOT_CONTACT

    def get_reference_id(self) -> str:
        """Get reference ID for this document."""
        contact_id = self.id.replace("hubspot_contact_", "")  # Extract from document ID
        return f"r_hubspot_contact_{contact_id}"

    def _safe_float(self, value: Any) -> float | None:
        """Safely convert to float."""
        if value is None or value == "":
            return None
        try:
            return float(value)
        except (ValueError, TypeError):
            return None
