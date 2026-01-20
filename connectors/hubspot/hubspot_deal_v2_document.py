"""
HubSpot deal document classes for v2 implementation.
Simple single-chunk approach for deal data without activities.
"""

import logging
from dataclasses import dataclass
from typing import Any, TypedDict

from langchain_text_splitters import RecursiveCharacterTextSplitter

from connectors.base import BaseChunk, BaseDocument
from connectors.base.document_source import DocumentSource
from connectors.hubspot.hubspot_artifacts import HUBSPOT_ACTIVITY_PROPERTY_NAMES
from src.utils.html_to_text import html_to_text_bs4

logger = logging.getLogger(__name__)


class HubspotDealChunkMetadata(TypedDict):
    """Metadata for HubSpot deal chunks."""

    deal_id: str
    deal_name: str | None
    source: str
    chunk_type: str
    source_created_at: str | None
    source_updated_at: str | None
    chunk_index: int
    total_chunks: int


class HubspotDealDocumentMetadata(TypedDict):
    """Metadata for HubSpot deal documents."""

    deal_id: str
    deal_name: str | None
    pipeline_id: str | None
    pipeline_name: str | None
    stage_id: str | None
    stage_name: str | None
    amount: float | None
    close_date: str | None
    source_created_at: str | None
    source_updated_at: str | None
    owner_id: str | None
    company_ids: list[str] | None
    company_names: list[str] | None
    num_contacts: int
    source: str
    type: str


@dataclass
class HubspotDealChunk(BaseChunk[HubspotDealChunkMetadata]):
    """Single chunk representing entire HubSpot deal."""

    def get_content(self) -> str:
        """Return the formatted deal content."""
        content = self.raw_data.get("content", "")
        chunk_index = self.raw_data.get("chunk_index", 0)
        total_chunks = self.raw_data.get("total_chunks", 1)

        if total_chunks == 1:
            return content

        position_context = f"[Part {chunk_index + 1} of {total_chunks}]\n"
        return f"{position_context}{content}"

    def get_metadata(self) -> HubspotDealChunkMetadata:
        """Get chunk metadata."""
        return {
            "deal_id": self.raw_data.get("deal_id", ""),
            "deal_name": self.raw_data.get("deal_name"),
            "source": "hubspot_deal",
            "chunk_type": "deal",
            "chunk_index": self.raw_data.get("chunk_index", 0),
            "total_chunks": self.raw_data.get("total_chunks", 1),
            "source_created_at": self.raw_data.get("source_created_at"),
            "source_updated_at": self.raw_data.get("source_updated_at"),
        }


@dataclass
class HubspotDealDocument(BaseDocument[HubspotDealChunk, HubspotDealDocumentMetadata]):
    """HubSpot deal document with formatted content."""

    raw_data: dict[str, Any]

    def get_content(self) -> str:
        """Generate formatted deal content following the v2 examples."""
        lines: list[str] = []

        # Header
        deal_name = self.raw_data.get("dealname", "Unnamed Deal")
        deal_id = self.id.replace("hubspot_deal_", "")  # Extract from document ID
        lines.append(f"Deal: {deal_name} (#{deal_id})")
        lines.append("")

        # Deal Information Section
        lines.append("=== DEAL INFORMATION ===")

        stage_name = self.raw_data.get("stage_name")
        if stage_name:
            lines.append(f"Stage Name: {stage_name}")

        pipeline_name = self.raw_data.get("pipeline_name")
        if pipeline_name:
            lines.append(f"Pipeline Name: {pipeline_name}")

        # Status calculation
        is_closed = self._parse_bool(self.raw_data.get("hs_is_closed"))
        is_won = self._parse_bool(self.raw_data.get("hs_is_closed_won"))
        is_lost = self._parse_bool(self.raw_data.get("hs_is_closed_lost"))

        status = ("Closed Won" if is_won else "Closed Lost") if is_closed else "Open"
        lines.append(f"Status: {status}")

        # Dates
        # Use actual createdAt if available, fallback to createdate property
        create_date = self.raw_data.get("created_at") or self.raw_data.get("createdate")
        if create_date:
            lines.append(f"Date created: {self._format_date(create_date)}")

        close_date = self.raw_data.get("closedate")
        if close_date:
            lines.append(f"Date closed: {self._format_date(close_date)}")
        else:
            lines.append("Date closed: Not set")

        days_to_close = self.raw_data.get("days_to_close")
        if days_to_close is not None:
            lines.append(f"Number of days the deal took to close: {days_to_close}")

        owner_id = self.raw_data.get("hubspot_owner_id")
        if owner_id:
            lines.append(f"User assigned to this deal: {owner_id}")
        else:
            lines.append("User assigned to this deal: Not assigned")

        num_contacts = self.raw_data.get("num_associated_contacts", "0")
        lines.append(f"Number of contacts associated: {num_contacts}")

        last_modified = self.raw_data.get("updated_at")
        if last_modified:
            lines.append(f"Most recent update: {self._format_date(last_modified)}")

        lines.append("")

        # Revenue Section
        lines.append("=== REVENUE ===")

        amount = self.raw_data.get("amount")
        currency = self.raw_data.get("deal_currency_code", "USD")
        if amount:
            lines.append(f"Total amount of the deal: ${self._format_number(amount)} ({currency})")
        else:
            lines.append("Total amount of the deal: Not set")

        amount_home = self.raw_data.get("amount_in_home_currency")
        if amount_home:
            lines.append(f"Amount in company currency: ${self._format_number(amount_home)}")
        else:
            lines.append("Amount in company currency: Not set")

        forecast_amount = self.raw_data.get("hs_forecast_amount")
        if forecast_amount:
            lines.append(
                f"Forecasted value (probability × amount): ${self._format_number(forecast_amount)}"
            )
        else:
            lines.append("Forecasted value (probability × amount): Not set")

        forecast_prob = self.raw_data.get("hs_forecast_probability")
        if forecast_prob:
            lines.append(
                f"Custom percent probability deal will close: {self._format_percentage(forecast_prob)}"
            )
        else:
            lines.append("Custom percent probability deal will close: Not set")

        stage_prob = self.raw_data.get("hs_deal_stage_probability")
        if stage_prob:
            lines.append(
                f"Default probability based on stage: {self._format_percentage(stage_prob)}"
            )

        # Recurring revenue fields
        arr = self.raw_data.get("hs_arr")
        if arr:
            lines.append(f"Annual recurring revenue: ${self._format_number(arr)}")
        else:
            lines.append("Annual recurring revenue: Not set")

        mrr = self.raw_data.get("hs_mrr")
        if mrr:
            lines.append(f"Monthly recurring revenue: ${self._format_number(mrr)}")
        else:
            lines.append("Monthly recurring revenue: Not set")

        tcv = self.raw_data.get("hs_tcv")
        if tcv:
            lines.append(f"Total contract value: ${self._format_number(tcv)}")
        else:
            lines.append("Total contract value: Not set")

        # Show closed amount if deal is closed
        if is_closed:
            closed_amount = self.raw_data.get("hs_closed_amount_in_home_currency")
            if closed_amount:
                lines.append(
                    f"Amount closed in home currency: ${self._format_number(closed_amount)}"
                )

        lines.append("")

        # Deal Outcome Section
        lines.append("=== DEAL OUTCOME ===")
        lines.append(f"Deal closed status: {'Closed' if is_closed else 'Open'}")
        lines.append(f"Won status: {'Yes' if is_won else 'No'}")
        lines.append(f"Lost status: {'Yes' if is_lost else 'No'}")

        won_reason = self.raw_data.get("closed_won_reason")
        if won_reason:
            lines.append(f"Reason why this deal was won: {won_reason}")
        else:
            lines.append(
                f"Reason why this deal was won: {'Not specified' if is_won else 'Not applicable'}"
            )

        lost_reason = self.raw_data.get("closed_lost_reason")
        if lost_reason:
            lines.append(f"Reason why this deal was lost: {lost_reason}")
        else:
            lines.append(
                f"Reason why this deal was lost: {'Not specified' if is_lost else 'Not applicable'}"
            )

        lines.append("")

        # Associated Companies Section
        lines.append("=== ASSOCIATED COMPANIES ===")

        primary_company_id = self.raw_data.get("hs_primary_associated_company")
        if primary_company_id:
            lines.append(f"Primary company ID: {primary_company_id}")

        company_names = self.raw_data.get("company_names", [])
        if company_names:
            lines.append(f"Companies: {', '.join(company_names)}")
        else:
            lines.append("Companies: None")

        custom_properties = self.raw_data.get("custom_properties", {})
        if custom_properties:
            lines.append("=== CUSTOM PROPERTIES ===")
            for key in custom_properties:
                if key in self.raw_data and self.raw_data[key] is not None:
                    lines.append(f"{custom_properties[key]}: {self.raw_data[key]}")
            lines.append("")

        # Description if present
        description = self.raw_data.get("description")
        if description:
            lines.extend(["", "=== NOTES ===", f"Description: {description}"])

        activities = self.raw_data.get("activities", [])
        if activities:
            lines.extend(["", "=== ACTIVITIES ==="])
        for activity in activities:
            lines.extend(["", f"=== {activity.upper()} ==="])

            if activity not in HUBSPOT_ACTIVITY_PROPERTY_NAMES:
                continue

            activity_property_names = HUBSPOT_ACTIVITY_PROPERTY_NAMES[activity]
            for activity_item in activities[activity]:
                if not activity_item:
                    continue

                lines.extend(["", f"{activity.upper()}: {activity_item.get('hs_object_id')}"])
                for key, value in activity_item.items():
                    if value is None:
                        continue

                    if key == "hs_email_html" or key == "hs_meeting_body":
                        value = html_to_text_bs4(value)

                    if key in activity_property_names:
                        lines.extend([f"{activity_property_names[key]}: {value}"])

        return "\n".join(lines)

    def to_embedding_chunks(self) -> list[HubspotDealChunk]:
        """Create single chunk for the entire deal."""
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
            f"HubSpot deal {self.id.replace('hubspot_deal_', '')} created {len(text_chunks)} chunks from {len(content)} characters"
        )

        embedding_chunks: list[HubspotDealChunk] = []

        for i, chunk_text in enumerate(text_chunks):
            chunk_data = {
                "deal_id": self.id.replace("hubspot_deal_", ""),
                "deal_name": self.raw_data.get("dealname"),
                "source_created_at": self.raw_data.get("source_created_at"),
                "source_updated_at": self.raw_data.get("source_updated_at"),
                "content": chunk_text,
                "chunk_index": i,
                "total_chunks": len(text_chunks),
            }

            embedding_chunks.append(
                HubspotDealChunk(
                    document=self,
                    raw_data=chunk_data,
                )
            )

        return embedding_chunks

    def get_metadata(self) -> HubspotDealDocumentMetadata:
        """Get document metadata for search and filtering."""
        return {
            "deal_id": self.id.replace("hubspot_deal_", ""),  # Extract from document ID
            "deal_name": self.raw_data.get("dealname"),
            "pipeline_id": self.raw_data.get("pipeline_id") or self.raw_data.get("pipeline"),
            "pipeline_name": self.raw_data.get("pipeline_name"),
            "stage_id": self.raw_data.get("stage_id") or self.raw_data.get("dealstage"),
            "stage_name": self.raw_data.get("stage_name"),
            "amount": self._safe_float(self.raw_data.get("amount")),
            "close_date": self.raw_data.get("closedate"),
            "source_created_at": self.raw_data.get("source_created_at"),
            "source_updated_at": self.raw_data.get("source_updated_at"),
            "owner_id": self.raw_data.get("hubspot_owner_id"),
            "company_ids": self.raw_data.get("company_ids"),
            "company_names": self.raw_data.get("company_names"),
            "num_contacts": int(self.raw_data.get("num_associated_contacts", 0)),
            "source": self.get_source(),
            "type": "hubspot_deal",
        }

    def get_source_enum(self) -> DocumentSource:
        return DocumentSource.HUBSPOT_DEAL

    def get_reference_id(self) -> str:
        """Get reference ID for this document."""
        deal_id = self.id.replace("hubspot_deal_", "")  # Extract from document ID
        return f"r_hubspot_deal_{deal_id}"

    def _parse_bool(self, value: Any) -> bool:
        """Parse string or bool to bool."""
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.lower() == "true"
        return False

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

    def _format_percentage(self, value: Any) -> str:
        """Format decimal as percentage."""
        try:
            num = float(value) if value else 0
            # Convert from decimal (0.6) to percentage (60%)
            return f"{num * 100:.0f}%"
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
