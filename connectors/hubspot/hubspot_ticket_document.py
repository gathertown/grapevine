"""
HubSpot ticket document classes for v2 implementation.
Simple single-chunk approach for ticket data without activities.
"""

import logging
from dataclasses import dataclass
from typing import Any, TypedDict

from langchain_text_splitters import RecursiveCharacterTextSplitter

from connectors.base import BaseChunk, BaseDocument
from connectors.base.document_source import DocumentSource

logger = logging.getLogger(__name__)


class HubspotTicketChunkMetadata(TypedDict):
    """Metadata for HubSpot ticket chunks."""

    ticket_id: str
    ticket_name: str | None
    source: str
    chunk_type: str
    source_created_at: str | None
    source_updated_at: str | None
    chunk_index: int
    total_chunks: int


class HubspotTicketDocumentMetadata(TypedDict):
    """Metadata for HubSpot ticket documents."""

    ticket_id: str
    ticket_name: str | None
    pipeline_id: str | None
    pipeline_name: str | None
    stage_id: str | None
    stage_name: str | None
    source_created_at: str | None
    source_updated_at: str | None
    owner_id: str | None
    company_ids: list[str] | None
    company_names: list[str] | None
    source: str
    type: str


@dataclass
class HubspotTicketChunk(BaseChunk[HubspotTicketChunkMetadata]):
    """Single chunk representing entire HubSpot ticket."""

    def get_content(self) -> str:
        """Return the formatted ticket content."""
        content = self.raw_data.get("content", "")
        chunk_index = self.raw_data.get("chunk_index", 0)
        total_chunks = self.raw_data.get("total_chunks", 1)

        if total_chunks == 1:
            return content

        position_context = f"[Part {chunk_index + 1} of {total_chunks}]\n"
        return f"{position_context}{content}"

    def get_metadata(self) -> HubspotTicketChunkMetadata:
        """Get chunk metadata."""
        return {
            "ticket_id": self.raw_data.get("ticket_id", ""),
            "ticket_name": self.raw_data.get("ticket_name"),
            "source": "hubspot_ticket",
            "chunk_type": "ticket",
            "chunk_index": self.raw_data.get("chunk_index", 0),
            "total_chunks": self.raw_data.get("total_chunks", 1),
            "source_created_at": self.raw_data.get("source_created_at"),
            "source_updated_at": self.raw_data.get("source_updated_at"),
        }


@dataclass
class HubspotTicketDocument(BaseDocument[HubspotTicketChunk, HubspotTicketDocumentMetadata]):
    """HubSpot ticket document with formatted content."""

    raw_data: dict[str, Any]

    def get_content(self) -> str:
        """Generate formatted ticket content following the v2 examples."""
        lines: list[str] = []

        # Header
        ticket_name = self.raw_data.get("subject")
        ticket_id = self.id.replace("hubspot_ticket_", "")
        lines.append(f"Ticket: {ticket_name} (#{ticket_id})")
        lines.append("")
        lines.append("=== TICKET INFORMATION ===")
        hs_primary_company_name = self.raw_data.get("hs_primary_company_name")
        if hs_primary_company_name:
            lines.append(f"Primary Company: {hs_primary_company_name}")

        hs_all_associated_contact_emails = self.raw_data.get("hs_all_associated_contact_emails")
        if hs_all_associated_contact_emails:
            lines.append(f"Associated Contact Emails: {hs_all_associated_contact_emails}")

        content = self.raw_data.get("content")
        if content:
            lines.append(content)

        hs_object_source_label = self.raw_data.get("hs_object_source_label")
        if hs_object_source_label:
            lines.append(f"Object Source: {hs_object_source_label}")

        hs_ticket_priority = self.raw_data.get("hs_ticket_priority")
        if hs_ticket_priority:
            lines.append(f"Ticket Priority: {hs_ticket_priority}")

        stage_name = self.raw_data.get("stage_name")
        if stage_name:
            lines.append(f"Stage: {stage_name}")

        pipeline_name = self.raw_data.get("pipeline_name")
        if pipeline_name:
            lines.append(f"Pipeline: {pipeline_name}")

        closed_date = self.raw_data.get("closed_date")
        if closed_date:
            lines.append(f"Closed Date: {closed_date}")

        custom_properties = self.raw_data.get("custom_properties", {})
        if custom_properties:
            lines.append("=== CUSTOM PROPERTIES ===")
            for key in custom_properties:
                if key in self.raw_data and self.raw_data[key] is not None:
                    lines.append(f"{custom_properties[key]}: {self.raw_data[key]}")
            lines.append("")

        return "\n".join(lines)

    def to_embedding_chunks(self) -> list[HubspotTicketChunk]:
        """Create single chunk for the entire ticket."""
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
            f"HubSpot ticket {self.id.replace('hubspot_ticket_', '')} created {len(text_chunks)} chunks from {len(content)} characters"
        )

        embedding_chunks = []

        for i, chunk_text in enumerate(text_chunks):
            chunk_data = {
                "ticket_id": self.id.replace("hubspot_ticket_", ""),
                "ticket_name": self.raw_data.get("ticketname"),
                "source_created_at": self.raw_data.get("source_created_at"),
                "source_updated_at": self.raw_data.get("source_updated_at"),
                "content": chunk_text,
                "chunk_index": i,
                "total_chunks": len(text_chunks),
            }

            embedding_chunks.append(
                HubspotTicketChunk(
                    document=self,
                    raw_data=chunk_data,
                )
            )

        return embedding_chunks

    def get_metadata(self) -> HubspotTicketDocumentMetadata:
        """Get document metadata for search and filtering."""
        return {
            "ticket_id": self.id.replace("hubspot_ticket_", ""),  # Extract from document ID
            "ticket_name": self.raw_data.get("subject"),
            "pipeline_id": self.raw_data.get("pipeline_id") or self.raw_data.get("pipeline"),
            "pipeline_name": self.raw_data.get("pipeline_name"),
            "stage_id": self.raw_data.get("stage_id") or self.raw_data.get("pipeline_stage"),
            "stage_name": self.raw_data.get("stage_name"),
            "source_created_at": self.raw_data.get("source_created_at"),
            "source_updated_at": self.raw_data.get("source_updated_at"),
            "owner_id": self.raw_data.get("hubspot_owner_id"),
            "company_ids": self.raw_data.get("company_ids"),
            "company_names": self.raw_data.get("company_names"),
            "source": self.get_source(),
            "type": "hubspot_ticket",
        }

    def get_source_enum(self) -> DocumentSource:
        return DocumentSource.HUBSPOT_TICKET

    def get_reference_id(self) -> str:
        """Get reference ID for this document."""
        ticket_id = self.id.replace("hubspot_ticket_", "")  # Extract from document ID
        return f"r_hubspot_ticket_{ticket_id}"

    def _safe_float(self, value: Any) -> float | None:
        """Safely convert to float."""
        if value is None or value == "":
            return None
        try:
            return float(value)
        except (ValueError, TypeError):
            return None
