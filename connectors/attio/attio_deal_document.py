"""
Attio deal document classes for structured deal representation.
Multi-chunk approach with embedded notes and tasks as activities.
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, TypedDict

from connectors.attio.attio_artifacts import AttioDealArtifact
from connectors.base import BaseChunk, BaseDocument
from connectors.base.document_source import DocumentSource
from connectors.base.utils import convert_timestamp_to_iso
from src.permissions.models import PermissionPolicy


class AttioDealChunkMetadata(TypedDict, total=False):
    """Metadata for Attio deal chunks."""

    activity_type: str | None
    activity_id: str | None
    timestamp: str | None
    created_by: str | None
    deal_id: str | None
    source: str | None
    chunk_type: str | None
    content_preview: str | None


class AttioDealDocumentMetadata(TypedDict, total=False):
    """Metadata for Attio deal documents."""

    deal_id: str | None
    deal_name: str | None
    pipeline_stage: str | None
    value: float | None
    currency: str | None
    expected_close_date: str | None
    owner: str | None
    company_name: str | None
    source_created_at: str | None
    source_updated_at: str | None
    source: str
    type: str


@dataclass
class AttioDealActivityChunk(BaseChunk[AttioDealChunkMetadata]):
    """Represents a single Attio deal activity chunk (note or task)."""

    def get_content(self) -> str:
        """Get the formatted activity content."""
        # Header chunks store pre-formatted content directly
        if self.raw_data.get("chunk_type") == "header":
            return self.raw_data.get("content", "")

        activity_type = self.raw_data.get("type", "").upper()
        # Attio API returns timestamp in 'created_at' field
        timestamp = self.raw_data.get("created_at", "") or self.raw_data.get("timestamp", "")

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
            except Exception:
                timestamp_str = ""

        # Attio API returns creator in 'created_by_actor' with nested 'name.full_name'
        created_by = self.raw_data.get("created_by", "")
        if not created_by:
            created_by_actor = self.raw_data.get("created_by_actor")
            if isinstance(created_by_actor, dict):
                name = created_by_actor.get("name")
                if isinstance(name, dict):
                    created_by = name.get("full_name", "") or name.get("name", "")
                elif name:
                    created_by = str(name)
        created_by_str = f"by {created_by} " if created_by else ""

        # Attio API returns content in 'content_plaintext' field
        preview = self.raw_data.get("content_plaintext", "") or self.raw_data.get(
            "content_preview", ""
        )
        if preview:
            preview = preview.strip()
            preview = preview.replace("\n", " ").replace("\r", " ")
            preview = " ".join(preview.split())

        if activity_type == "NOTE":
            title = self.raw_data.get("title", "")
            if title:
                activity_line = f"{timestamp_str} {created_by_str}added note: {title} - {preview}"
            else:
                activity_line = f"{timestamp_str} {created_by_str}added note: {preview}"
        elif activity_type == "TASK":
            is_completed = self.raw_data.get("is_completed", False)
            # Attio API returns deadline in 'deadline_at' field
            deadline = self.raw_data.get("deadline_at", "") or self.raw_data.get("deadline", "")
            status = "[DONE]" if is_completed else "[TODO]"
            deadline_str = f" (due: {deadline})" if deadline else ""
            activity_line = (
                f"{timestamp_str} {created_by_str}created task {status}: {preview}{deadline_str}"
            )
        else:
            activity_line = f"{timestamp_str} {created_by_str}{activity_type.lower()}: {preview}"

        return activity_line

    def get_metadata(self) -> AttioDealChunkMetadata:
        """Get chunk-specific metadata."""
        # Use chunk_type from raw_data if set (e.g., "header"), otherwise default to "activity"
        chunk_type = self.raw_data.get("chunk_type", "activity")

        # Extract timestamp - Attio API returns 'created_at', fallback to 'timestamp'
        timestamp = self.raw_data.get("created_at") or self.raw_data.get("timestamp")

        # Extract created_by - Attio API returns 'created_by_actor' with nested name
        created_by = self.raw_data.get("created_by")
        if not created_by:
            created_by_actor = self.raw_data.get("created_by_actor")
            if isinstance(created_by_actor, dict):
                name = created_by_actor.get("name")
                if isinstance(name, dict):
                    created_by = name.get("full_name") or name.get("name")
                elif name:
                    created_by = str(name)

        # Extract content preview - Attio API returns 'content_plaintext'
        content_preview = self.raw_data.get("content_plaintext") or self.raw_data.get(
            "content_preview"
        )

        metadata: AttioDealChunkMetadata = {
            "activity_type": self.raw_data.get("type"),
            "activity_id": self.raw_data.get("id"),
            "timestamp": timestamp,
            "created_by": created_by,
            "deal_id": self.raw_data.get("deal_id"),
            "source": "attio_deal",
            "chunk_type": chunk_type,
            "content_preview": content_preview,
        }

        return metadata


@dataclass
class AttioDealDocument(BaseDocument[AttioDealActivityChunk, AttioDealDocumentMetadata]):
    """Attio deal document with embedded notes and tasks as activities."""

    raw_data: dict[str, Any]
    metadata: AttioDealDocumentMetadata | None = None
    chunk_class: type[AttioDealActivityChunk] = AttioDealActivityChunk

    @classmethod
    def from_artifact(
        cls,
        artifact: AttioDealArtifact,
        permission_policy: PermissionPolicy = "tenant",
        permission_allowed_tokens: list[str] | None = None,
    ) -> "AttioDealDocument":
        """Create document from artifact."""
        record_data = artifact.content.record_data.copy()
        record_id = artifact.metadata.record_id

        # Include notes and tasks from artifact content
        record_data["notes"] = artifact.content.notes
        record_data["tasks"] = artifact.content.tasks

        return cls(
            id=f"attio_deal_{record_id}",
            raw_data=record_data,
            source_updated_at=artifact.source_updated_at,
            permission_policy=permission_policy,
            permission_allowed_tokens=permission_allowed_tokens,
        )

    def _get_attribute_value(self, attribute_slug: str) -> Any:
        """Extract attribute value from Attio record format.

        Attio stores attributes in a nested structure with varying value keys:
        - Most attributes: {"value": actual_value}
        - Domains: {"domain": "example.com"}
        - Email addresses: {"email_address": "user@example.com"}
        - Names: {"first_name": "...", "last_name": "...", "full_name": "..."}
        - Currency: {"currency_value": 400, "currency_code": "USD"}
        - Record references: {"target_record_id": "...", "target_object": "..."}
        - Actor references: {"referenced_actor_id": "...", "name": {"full_name": "..."}}

        For list attributes (domains, email_addresses), returns all values as a list.
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
            # Handle currency attributes - extract the numeric value
            if "currency_value" in first_value:
                return first_value["currency_value"]
            # Handle select/status attributes - extract the option title
            if "option" in first_value and isinstance(first_value["option"], dict):
                return first_value["option"].get("title")
            # Handle actor reference attributes (owner) - extract the name
            if "referenced_actor_id" in first_value:
                name = first_value.get("name")
                if isinstance(name, dict):
                    return name.get("full_name") or name.get("name")
                return name
            # Handle record reference attributes - return full dict for name extraction
            if "target_record_id" in first_value:
                return first_value
            # Handle record reference attributes (alternate format)
            if "target_object" in first_value:
                return first_value
            return first_value

        # Return primitive values directly (string, number, etc.)
        return first_value

    def _get_currency_code(self, attribute_slug: str = "value") -> str | None:
        """Extract currency code from a currency attribute."""
        values = self.raw_data.get("values", {})
        attribute_values = values.get(attribute_slug, [])

        if not attribute_values or not isinstance(attribute_values, list):
            return None

        first_value = attribute_values[0]
        if isinstance(first_value, dict) and "currency_code" in first_value:
            return first_value.get("currency_code")
        return None

    def _get_record_reference_name(self, attribute_slug: str) -> str | None:
        """Extract the display name from a record reference attribute."""
        values = self.raw_data.get("values", {})
        attribute_values = values.get(attribute_slug, [])

        if not attribute_values or not isinstance(attribute_values, list):
            return None

        first_value = attribute_values[0]
        if isinstance(first_value, dict):
            # Record references store the name in a nested object
            name = first_value.get("name")
            if isinstance(name, dict):
                return name.get("full_name") or name.get("name")
            if name:
                return str(name)
        return None

    def _get_all_attribute_slugs(self) -> list[str]:
        """Get all attribute slugs that have values in this record."""
        values = self.raw_data.get("values", {})
        return list(values.keys())

    def _format_attribute_for_display(self, slug: str) -> str | None:
        """Format an attribute value for human-readable display.

        Returns None if the attribute has no meaningful display value.
        """
        value = self._get_attribute_value(slug)
        if value is None:
            return None

        # Handle different value types
        if isinstance(value, dict):
            # Record reference - try to get name
            name = value.get("name")
            if isinstance(name, dict):
                return name.get("full_name") or name.get("name")
            if name:
                return str(name)
            # Fall back to target_record_id if no name
            if value.get("target_record_id"):
                return None  # Skip raw IDs
            return None

        if isinstance(value, list):
            # Filter out None values and join
            str_values = [str(v) for v in value if v is not None]
            return ", ".join(str_values) if str_values else None

        if isinstance(value, bool):
            return "Yes" if value else "No"

        if isinstance(value, (int, float)):
            return str(value)

        return str(value) if value else None

    def _get_name(self) -> str | None:
        """Get deal name from Attio record.

        Access raw attribute data directly to get the full dict with all name parts.
        """
        values = self.raw_data.get("values", {})
        name_values = values.get("name", [])

        if not name_values or not isinstance(name_values, list):
            return None

        first_value = name_values[0]
        if not isinstance(first_value, dict):
            return str(first_value) if first_value else None

        # Try various name keys
        return first_value.get("full_name") or first_value.get("name") or first_value.get("value")

    def get_header_content(self) -> str:
        """Get deal header for display."""
        deal_id = self.id.replace("attio_deal_", "")
        deal_name = self._get_name() or "Unnamed Deal"
        return f"Deal: <{deal_id}|{deal_name}>"

    def get_content(self) -> str:
        """Generate formatted deal content with embedded activities."""
        lines = [self.get_header_content(), ""]

        # Value - use helper to get currency code separately
        value = self._get_attribute_value("value")
        currency = self._get_currency_code("value") or "USD"
        if value:
            try:
                lines.append(f"Value: {currency} {float(value):,.2f}")
            except (ValueError, TypeError):
                lines.append(f"Value: {currency} {value}")

        # Pipeline Stage
        pipeline_stage = self._get_attribute_value("pipeline_stage")
        if pipeline_stage:
            if isinstance(pipeline_stage, dict):
                stage_name = pipeline_stage.get("title") or pipeline_stage.get("name", "Unknown")
            else:
                stage_name = str(pipeline_stage)
            lines.append(f"Stage: {stage_name}")

        # Status (from pipeline stage if available)
        status = self._get_attribute_value("status")
        if status:
            lines.append(f"Status: {status}")

        # Expected Close Date
        expected_close = self._get_attribute_value("expected_close_date")
        if expected_close:
            lines.append(f"Expected Close: {self._format_date(expected_close)}")

        # Owner - try multiple possible attribute slugs
        # Attio may use different slugs: owner, deal_owner, assigned_to, assignee
        owner = (
            self._get_attribute_value("owner")
            or self._get_attribute_value("deal_owner")
            or self._get_attribute_value("assigned_to")
            or self._get_attribute_value("assignee")
        )
        if owner:
            lines.append(f"Owner: {owner}")

        # Associated Company - use helper to get display name
        company_name = self._get_record_reference_name("associated_company")
        if company_name:
            lines.append(f"Company: {company_name}")

        # Associated People
        people = self._get_attribute_value("associated_people")
        if people:
            people_names = []
            if isinstance(people, dict):
                # Single person returned
                name = people.get("name")
                if isinstance(name, dict):
                    people_names.append(name.get("full_name", "Unknown"))
                elif name:
                    people_names.append(str(name))
            elif isinstance(people, list):
                for person in people[:5]:  # Limit to first 5 people
                    if isinstance(person, dict):
                        name = person.get("name")
                        if isinstance(name, dict):
                            people_names.append(name.get("full_name", "Unknown"))
                        elif name:
                            people_names.append(str(name))
            if people_names:
                lines.append(f"Contacts: {', '.join(people_names)}")

        # Created date
        create_date = self.raw_data.get("created_at")
        if create_date:
            lines.append(f"Created: {self._format_date(create_date)}")

        # Additional custom attributes (not already handled above)
        handled_slugs = {
            "name",
            "value",
            "pipeline_stage",
            "status",
            "expected_close_date",
            "owner",
            "deal_owner",
            "assigned_to",
            "assignee",
            "associated_company",
            "associated_people",
        }
        for slug in self._get_all_attribute_slugs():
            if slug in handled_slugs:
                continue
            display_value = self._format_attribute_for_display(slug)
            if display_value:
                # Convert slug to human-readable label
                label = slug.replace("_", " ").title()
                lines.append(f"{label}: {display_value}")

        # Notes embedded in deal
        notes = self.raw_data.get("notes", [])
        if notes and isinstance(notes, list):
            lines.extend(["", "Notes:"])
            for note in notes:
                if isinstance(note, dict):
                    # Create a copy to avoid mutating original data
                    note_data = {
                        **note,
                        "deal_id": self.id.replace("attio_deal_", ""),
                        "type": "NOTE",
                    }
                    chunk = AttioDealActivityChunk(
                        document=self,
                        raw_data=note_data,
                    )
                    lines.append(chunk.get_content())

        # Tasks embedded in deal
        tasks = self.raw_data.get("tasks", [])
        if tasks and isinstance(tasks, list):
            lines.extend(["", "Tasks:"])
            for task in tasks:
                if isinstance(task, dict):
                    # Create a copy to avoid mutating original data
                    task_data = {
                        **task,
                        "deal_id": self.id.replace("attio_deal_", ""),
                        "type": "TASK",
                    }
                    chunk = AttioDealActivityChunk(
                        document=self,
                        raw_data=task_data,
                    )
                    lines.append(chunk.get_content())

        return "\n".join(lines)

    def to_embedding_chunks(self) -> list[AttioDealActivityChunk]:
        """Create chunks for deal header and each activity."""
        chunks: list[AttioDealActivityChunk] = []

        # Build header content
        header_lines: list[str] = []
        deal_id = self.id.replace("attio_deal_", "")
        deal_name = self._get_name() or "Unnamed Deal"
        header_lines.append(f"Deal: <{deal_id}|{deal_name}>")
        header_lines.append("")

        # Value - use helper to get currency code separately
        value = self._get_attribute_value("value")
        currency = self._get_currency_code("value") or "USD"
        if value:
            try:
                header_lines.append(f"Value: {currency} {float(value):,.2f}")
            except (ValueError, TypeError):
                header_lines.append(f"Value: {currency} {value}")

        # Pipeline Stage
        pipeline_stage = self._get_attribute_value("pipeline_stage")
        if pipeline_stage:
            if isinstance(pipeline_stage, dict):
                stage_name = pipeline_stage.get("title") or pipeline_stage.get("name", "Unknown")
            else:
                stage_name = str(pipeline_stage)
            header_lines.append(f"Stage: {stage_name}")

        # Status
        status = self._get_attribute_value("status")
        if status:
            header_lines.append(f"Status: {status}")

        # Expected Close Date
        expected_close = self._get_attribute_value("expected_close_date")
        if expected_close:
            header_lines.append(f"Expected Close: {self._format_date(expected_close)}")

        # Owner - try multiple possible attribute slugs (same as get_content)
        # Attio may use different slugs: owner, deal_owner, assigned_to, assignee
        owner = (
            self._get_attribute_value("owner")
            or self._get_attribute_value("deal_owner")
            or self._get_attribute_value("assigned_to")
            or self._get_attribute_value("assignee")
        )
        if owner:
            header_lines.append(f"Owner: {owner}")

        # Company - use helper to get display name
        company_name = self._get_record_reference_name("associated_company")
        if company_name:
            header_lines.append(f"Company: {company_name}")

        # Create header chunk
        header_content = f"[{self.id}]\n" + "\n".join(header_lines)
        header_chunk = self.chunk_class(
            document=self,
            raw_data={
                "content": header_content,
                **self.get_metadata(),
                "chunk_type": "header",
            },
        )
        self.populate_chunk_permissions(header_chunk)
        chunks.append(header_chunk)

        # Add notes as activity chunks
        notes = self.raw_data.get("notes", [])
        for note in notes:
            if isinstance(note, dict):
                # Create a copy to avoid mutating original data
                note_data = {
                    **note,
                    "deal_id": deal_id,
                    "type": "NOTE",
                }
                chunk = self.chunk_class(
                    document=self,
                    raw_data=note_data,
                )
                self.populate_chunk_permissions(chunk)
                chunks.append(chunk)

        # Add tasks as activity chunks
        tasks = self.raw_data.get("tasks", [])
        for task in tasks:
            if isinstance(task, dict):
                # Create a copy to avoid mutating original data
                task_data = {
                    **task,
                    "deal_id": deal_id,
                    "type": "TASK",
                }
                chunk = self.chunk_class(
                    document=self,
                    raw_data=task_data,
                )
                self.populate_chunk_permissions(chunk)
                chunks.append(chunk)

        return chunks

    def get_source_enum(self) -> DocumentSource:
        return DocumentSource.ATTIO_DEAL

    def get_reference_id(self) -> str:
        """Get the reference ID for this document."""
        return "r_attio_deal_" + self.id.replace("attio_deal_", "")

    def get_metadata(self) -> AttioDealDocumentMetadata:
        """Get document metadata for search and filtering."""
        if self.metadata is not None:
            return self.metadata

        # Extract company name using helper
        company_name = self._get_record_reference_name("associated_company")

        # Extract owner name - try multiple possible attribute slugs
        owner_name = (
            self._get_attribute_value("owner")
            or self._get_attribute_value("deal_owner")
            or self._get_attribute_value("assigned_to")
            or self._get_attribute_value("assignee")
        )
        if owner_name and not isinstance(owner_name, str):
            owner_name = None  # Fallback if extraction failed

        # Extract pipeline stage name
        pipeline_stage = self._get_attribute_value("pipeline_stage")
        stage_name = None
        if pipeline_stage:
            if isinstance(pipeline_stage, dict):
                stage_name = pipeline_stage.get("title") or pipeline_stage.get("name")
            else:
                stage_name = str(pipeline_stage)

        metadata: AttioDealDocumentMetadata = {
            "deal_id": self.id.replace("attio_deal_", ""),
            "deal_name": self._get_name(),
            "pipeline_stage": stage_name,
            "value": self._safe_float(self._get_attribute_value("value")),
            "currency": self._get_currency_code("value"),
            "expected_close_date": self._get_attribute_value("expected_close_date"),
            "owner": owner_name,
            "company_name": company_name,
            "source_created_at": convert_timestamp_to_iso(self.raw_data.get("created_at")),
            "source_updated_at": convert_timestamp_to_iso(self.raw_data.get("updated_at")),
            "source": self.get_source(),
            "type": "attio_deal",
        }

        return metadata

    def _format_date(self, date_str: str | None) -> str:
        """Format ISO date string to readable format."""
        if not date_str:
            return ""
        try:
            if "T" in date_str:
                dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
                return dt.strftime("%Y-%m-%d")
            return date_str
        except Exception:
            return str(date_str)

    def _safe_float(self, value: Any) -> float | None:
        """Safely convert to float."""
        if value is None or value == "":
            return None
        try:
            return float(value)
        except (ValueError, TypeError):
            return None
