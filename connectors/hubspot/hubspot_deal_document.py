"""
HubSpot deal document classes for structured deal representation.
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, TypedDict

from connectors.base import BaseChunk, BaseDocument
from connectors.base.document_source import DocumentSource


class HubspotDealChunkMetadata(TypedDict):
    """Metadata for HubSpot deal chunks."""

    activity_type: str | None
    activity_id: str | None
    timestamp: str | None
    owner_id: str | None
    owner_first_name: str | None
    owner_last_name: str | None
    deal_id: str | None
    source: str | None
    chunk_type: str
    body_preview: str | None


class HubspotDealDocumentMetadata(TypedDict):
    """Metadata for HubSpot deal documents."""

    deal_id: str | None
    deal_name: str | None
    deal_stage: str | None
    deal_owner: str | None
    amount: float | None
    close_date: str | None
    created_date: str | None
    last_modified_date: str | None
    source: str
    type: str
    source_created_at: str | None


@dataclass
class HubspotDealActivityChunk(BaseChunk[HubspotDealChunkMetadata]):
    """Represents a single HubSpot deal activity chunk."""

    def get_content(self) -> str:
        """Get the formatted activity content."""
        activity_type = self.raw_data.get("type", "").upper()
        timestamp = self.raw_data.get("timestamp", "")

        timestamp_str = ""
        if timestamp:
            try:
                if isinstance(timestamp, (int, float)):
                    dt = datetime.fromtimestamp(timestamp / 1000, tz=UTC)
                elif str(timestamp).isdigit():
                    dt = datetime.fromtimestamp(int(timestamp) / 1000, tz=UTC)
                else:
                    dt = datetime.fromisoformat(str(timestamp).replace("Z", "+00:00"))
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=UTC)

                timestamp_str = dt.strftime("%Y-%m-%d %H:%M")
            except:
                timestamp_str = ""

        owner_first = self.raw_data.get("owner_first_name")
        owner_last = self.raw_data.get("owner_last_name")
        owner_id = self.raw_data.get("owner_id", "")

        owner_str = ""
        if owner_first or owner_last:
            owner_name = f"{owner_first or ''} {owner_last or ''}".strip()
            owner_str = f"<@{owner_id}|@{owner_name}> "

        preview = self.raw_data.get("body_preview", "")
        if preview:
            preview = preview.strip()
            preview = preview.replace("\n", " ").replace("\r", " ")
            preview = " ".join(preview.split())

        if activity_type == "NOTE":
            activity_line = f"{timestamp_str} {owner_str}added note: {preview}"
        elif activity_type == "EMAIL":
            activity_line = f"{timestamp_str} {owner_str}sent email: {preview}"
        elif activity_type == "INCOMING_EMAIL":
            activity_line = f"{timestamp_str} {owner_str}received email: {preview}"
        elif activity_type == "MEETING":
            activity_line = f"{timestamp_str} {owner_str}logged meeting: {preview}"
        elif activity_type == "CALL":
            activity_line = f"{timestamp_str} {owner_str}logged call: {preview}"
        elif activity_type == "TASK":
            activity_line = f"{timestamp_str} {owner_str}created task: {preview}"
        else:
            activity_line = f"{timestamp_str} {owner_str}{activity_type.lower()}: {preview}"

        return activity_line

    def get_metadata(self) -> HubspotDealChunkMetadata:
        """Get chunk-specific metadata."""
        metadata: HubspotDealChunkMetadata = {
            "activity_type": self.raw_data.get("type"),
            "activity_id": self.raw_data.get("id"),
            "timestamp": self.raw_data.get("timestamp"),
            "owner_id": self.raw_data.get("owner_id"),
            "owner_first_name": self.raw_data.get("owner_first_name"),
            "owner_last_name": self.raw_data.get("owner_last_name"),
            "deal_id": self.raw_data.get("deal_id"),
            "source": "hubspot_deal",
            "chunk_type": "activity",
            "body_preview": self.raw_data.get("body_preview"),
        }

        return metadata


@dataclass
class HubspotDealDocument(BaseDocument[HubspotDealActivityChunk, HubspotDealDocumentMetadata]):
    raw_data: dict[str, Any]

    def _clean_value(self, value: Any) -> Any:
        """Convert non-JSON serializable types to serializable ones."""
        if value is None:
            return value
        from decimal import Decimal

        if isinstance(value, Decimal):
            return float(value)
        elif hasattr(value, "isoformat"):
            return value.isoformat()
        return value

    def get_header_content(self) -> str:
        deal_id = self.raw_data.get("id", "")
        deal_name = self.raw_data.get("properties_dealname", "")
        return f"Deal: <{deal_id}|{deal_name}>"

    def get_content(self) -> str:
        lines = [self.get_header_content(), ""]

        amount = self.raw_data.get("properties_amount", "")
        if amount:
            try:
                lines.append(f"Amount: ${float(amount):,.2f}")
            except (ValueError, TypeError):
                lines.append(f"Amount: {amount}")

        pipeline_name = self.raw_data.get("pipeline_name") or self.raw_data.get(
            "properties_pipeline", ""
        )
        if pipeline_name:
            lines.append(f"Pipeline: {pipeline_name}")

        stage_name = self.raw_data.get("stage_name") or self.raw_data.get(
            "properties_dealstage", ""
        )
        if stage_name:
            lines.append(f"Stage: {stage_name}")

        is_closed = self.raw_data.get("properties_hs_is_closed", False)
        is_closed_won = self.raw_data.get("properties_hs_is_closed_won", False)
        status = ("Closed Won" if is_closed_won else "Closed Lost") if is_closed else "Open"
        lines.append(f"Status: {status}")

        create_date = self.raw_data.get("properties_createdate") or self.raw_data.get(
            "createdAt", ""
        )
        if create_date:
            try:
                dt = datetime.fromisoformat(str(create_date).replace("Z", "+00:00"))
                create_date_str = dt.strftime("%Y-%m-%d %H:%M")
                lines.append(f"Created: {create_date_str}")
            except:
                lines.append(f"Created: {create_date}")

        company_name = self.raw_data.get("properties_company_name", "")
        if company_name:
            lines.append(f"Company: {company_name}")

        notes: list[str] = []

        description = self.raw_data.get("properties_description", "")
        if description and description.strip():
            notes.append(description.strip())

        if is_closed_won:
            closed_won_notes = self.raw_data.get("properties_closed_won_notes", "")
            if closed_won_notes and closed_won_notes.strip():
                notes.append(closed_won_notes.strip())
        elif is_closed:
            closed_lost_reason = self.raw_data.get("properties_closed_lost_reason", "")
            closed_lost_notes = self.raw_data.get("properties_closed_lost_notes", "")
            if closed_lost_reason and closed_lost_reason.strip():
                notes.append(f"Closed Lost Reason: {closed_lost_reason.strip()}")
            if closed_lost_notes and closed_lost_notes.strip():
                notes.append(closed_lost_notes.strip())

        if notes:
            lines.extend(["", "Notes:"])
            for note in notes:
                if "\n" in note:
                    for line in note.split("\n"):
                        line = line.strip()
                        if line:
                            if not line.startswith("-"):
                                line = f"- {line}"
                            lines.append(line)
                else:
                    lines.append(f"- {note}")

        activities = self.raw_data.get("activities", [])
        if activities and isinstance(activities, list):
            lines.extend(["", "Activity:"])

            for activity in activities:
                if isinstance(activity, dict):
                    activity["deal_id"] = self.raw_data.get("id")
                    chunk = HubspotDealActivityChunk(
                        document=self,
                        raw_data=activity,
                    )
                    lines.append(chunk.get_content())

        return "\n".join(lines)

    def to_embedding_chunks(self) -> list[HubspotDealActivityChunk]:
        chunks: list[HubspotDealActivityChunk] = []

        header_lines: list[str] = []

        deal_id = self.raw_data.get("id", "")
        deal_name = self.raw_data.get("properties_dealname", "")
        header_lines.append(f"Deal: <{deal_id}|{deal_name}>")
        header_lines.append("")

        amount = self.raw_data.get("properties_amount", "")
        if amount:
            try:
                header_lines.append(f"Amount: ${float(amount):,.2f}")
            except (ValueError, TypeError):
                header_lines.append(f"Amount: {amount}")

        pipeline_name = self.raw_data.get("pipeline_name") or self.raw_data.get(
            "properties_pipeline", ""
        )
        if pipeline_name:
            header_lines.append(f"Pipeline: {pipeline_name}")

        stage_name = self.raw_data.get("stage_name") or self.raw_data.get(
            "properties_dealstage", ""
        )
        if stage_name:
            header_lines.append(f"Stage: {stage_name}")

        is_closed = self.raw_data.get("properties_hs_is_closed", False)
        is_closed_won = self.raw_data.get("properties_hs_is_closed_won", False)
        status = ("Closed Won" if is_closed_won else "Closed Lost") if is_closed else "Open"
        header_lines.append(f"Status: {status}")

        create_date = self.raw_data.get("properties_createdate") or self.raw_data.get(
            "createdAt", ""
        )
        if create_date:
            try:
                dt = datetime.fromisoformat(str(create_date).replace("Z", "+00:00"))
                create_date_str = dt.strftime("%Y-%m-%d %H:%M")
                header_lines.append(f"Created: {create_date_str}")
            except:
                header_lines.append(f"Created: {create_date}")

        close_date = self.raw_data.get("properties_closedate")
        if close_date:
            try:
                dt = datetime.fromisoformat(str(close_date).replace("Z", "+00:00"))
                close_date_str = dt.strftime("%Y-%m-%d")
                header_lines.append(f"Expected Close: {close_date_str}")
            except:
                header_lines.append(f"Expected Close: {close_date}")

        company_name = self.raw_data.get("properties_company_name", "")
        if company_name:
            header_lines.append(f"Company: {company_name}")

        header_content = f"[{self.id}]\n" + "\n".join(header_lines)
        header_chunk = HubspotDealActivityChunk(
            document=self,
            raw_data={
                "content": header_content,
                **self.get_metadata(),
                "chunk_type": "header",
            },
        )
        chunks.append(header_chunk)

        activities = self.raw_data.get("activities", [])
        for activity in activities:
            if isinstance(activity, dict):
                activity["deal_id"] = self.raw_data.get("id")
                chunk = HubspotDealActivityChunk(
                    document=self,
                    raw_data=activity,
                )
                chunks.append(chunk)

        return chunks

    def get_source_enum(self) -> DocumentSource:
        return DocumentSource.HUBSPOT_DEAL

    def get_reference_id(self) -> str:
        """Get the reference ID for this document."""
        return "r_hubspot_deal_placeholder_" + self.id

    def get_metadata(self) -> HubspotDealDocumentMetadata:
        metadata: HubspotDealDocumentMetadata = {
            "deal_id": self._clean_value(self.raw_data.get("id")),
            "deal_name": self._clean_value(self.raw_data.get("properties_dealname")),
            "deal_stage": self._clean_value(self.raw_data.get("properties_dealstage")),
            "deal_owner": self._clean_value(self.raw_data.get("properties_hubspot_owner_id")),
            "amount": self._clean_value(self.raw_data.get("properties_amount")),
            "close_date": self._clean_value(self.raw_data.get("properties_closedate")),
            "created_date": self._clean_value(self.raw_data.get("properties_createdate")),
            "last_modified_date": self._clean_value(self.raw_data.get("updatedAt")),
            "source": self.get_source(),
            "type": "hubspot_deal_document",
            "source_created_at": self._clean_value(self.raw_data.get("createdAt", "")),
        }

        return metadata

    def _format_date(self, date_str: str) -> str:
        if not date_str:
            return ""
        try:
            if "T" in date_str:
                dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
                return dt.strftime("%Y-%m-%d")
            return date_str
        except Exception:
            return date_str

    def _format_number(self, value: Any) -> str:
        try:
            num = float(value)
            if num >= 1000000:
                return f"{num / 1000000:.1f}M"
            elif num >= 1000:
                return f"{num / 1000:.1f}K"
            else:
                return f"{num:,.2f}"
        except (ValueError, TypeError):
            return str(value)
