"""Pipedrive Person document and chunk definitions.

Uses dataclass pattern matching the Attio connector for consistency.
"""

from dataclasses import dataclass
from typing import Any, TypedDict

from connectors.base import BaseChunk, BaseDocument
from connectors.base.document_source import DocumentSource
from connectors.base.utils import convert_timestamp_to_iso
from connectors.pipedrive.pipedrive_artifacts import (
    PipedrivePersonArtifact,
    _extract_entity_id,
)
from src.permissions.models import PermissionPolicy


class PipedrivePersonChunkMetadata(TypedDict, total=False):
    """Metadata for Pipedrive person chunks."""

    person_id: int | None
    chunk_type: str | None
    content_preview: str | None
    source: str | None


class PipedrivePersonDocumentMetadata(TypedDict, total=False):
    """Metadata for Pipedrive person documents."""

    person_id: int | None
    person_name: str | None
    person_email: str | None
    person_phone: str | None
    org_name: str | None
    org_id: int | None
    owner_name: str | None
    owner_email: str | None
    open_deals_count: int | None
    closed_deals_count: int | None
    activities_count: int | None
    label_names: list[str] | None
    source_created_at: str | None
    source_updated_at: str | None
    source: str
    type: str


@dataclass
class PipedrivePersonChunk(BaseChunk[PipedrivePersonChunkMetadata]):
    """A searchable chunk from a Pipedrive person document."""

    def get_content(self) -> str:
        """Get the chunk content."""
        # Header chunks store pre-formatted content directly
        if self.raw_data.get("chunk_type") == "header":
            return self.raw_data.get("content", "")

        return self.raw_data.get("content", "")

    def get_metadata(self) -> PipedrivePersonChunkMetadata:
        """Get chunk-specific metadata."""
        chunk_type = self.raw_data.get("chunk_type", "header")
        content = self.get_content()
        content_preview = content[:200] if content else None

        return {
            "person_id": self.raw_data.get("person_id"),
            "chunk_type": chunk_type,
            "content_preview": content_preview,
            "source": "pipedrive_person",
        }


@dataclass
class PipedrivePersonDocument(BaseDocument[PipedrivePersonChunk, PipedrivePersonDocumentMetadata]):
    """Represents a Pipedrive person (contact) for indexing and search."""

    raw_data: dict[str, Any]
    metadata: PipedrivePersonDocumentMetadata | None = None
    chunk_class: type[PipedrivePersonChunk] = PipedrivePersonChunk

    @classmethod
    def from_artifact(
        cls,
        artifact: PipedrivePersonArtifact,
        hydrated_metadata: dict[str, Any] | None = None,
        permission_policy: PermissionPolicy = "tenant",
        permission_allowed_tokens: list[str] | None = None,
    ) -> "PipedrivePersonDocument":
        """Create document from artifact.

        Args:
            artifact: The Pipedrive person artifact
            hydrated_metadata: Optional pre-hydrated metadata with enriched names
            permission_policy: Permission policy for the document
            permission_allowed_tokens: Allowed permission tokens

        Returns:
            PipedrivePersonDocument instance
        """
        person_data = artifact.content.person_data.copy()
        person_id = artifact.metadata.person_id

        # Merge hydrated metadata if provided
        if hydrated_metadata:
            person_data["_hydrated"] = hydrated_metadata

        return cls(
            id=f"pipedrive_person_{person_id}",
            raw_data=person_data,
            source_updated_at=artifact.source_updated_at,
            permission_policy=permission_policy,
            permission_allowed_tokens=permission_allowed_tokens,
        )

    def _get_person_id(self) -> int:
        """Get the person ID."""
        return self.raw_data.get("id", 0)

    def _get_name(self) -> str | None:
        """Get person name."""
        return self.raw_data.get("name")

    def _get_primary_email(self) -> str | None:
        """Get the primary email address from v2 API response."""
        emails = self.raw_data.get("emails") or []
        if isinstance(emails, list) and emails:
            primary = next((e for e in emails if e.get("primary")), emails[0])
            return primary.get("value") if isinstance(primary, dict) else primary
        return None

    def _get_primary_phone(self) -> str | None:
        """Get the primary phone number from v2 API response."""
        phones = self.raw_data.get("phones") or []
        if isinstance(phones, list) and phones:
            primary = next((p for p in phones if p.get("primary")), phones[0])
            return primary.get("value") if isinstance(primary, dict) else primary
        return None

    def _get_hydrated_value(self, key: str) -> Any:
        """Get a hydrated value if available."""
        hydrated = self.raw_data.get("_hydrated", {})
        return hydrated.get(key)

    def get_header_content(self) -> str:
        """Get person header for display."""
        person_id = self._get_person_id()
        person_name = self._get_name() or f"Person #{person_id}"
        return f"Person: <{person_id}|{person_name}>"

    def get_content(self) -> str:
        """Generate formatted person content."""
        lines: list[str] = []
        person_id = self._get_person_id()

        # Name with ID for disambiguation
        name = self._get_name() or "Unnamed Person"
        lines.append(f"# {name} ({person_id})")
        lines.append("")

        # Contact details
        lines.append("## Contact Information")
        email = self._get_primary_email()
        phone = self._get_primary_phone()
        if email:
            lines.append(f"Email: {email}")
        if phone:
            lines.append(f"Phone: {phone}")

        # Additional emails/phones from v2 API response
        emails = self.raw_data.get("emails") or []
        if isinstance(emails, list) and len(emails) > 1:
            other_emails: list[str] = [
                str(e.get("value"))
                for e in emails
                if isinstance(e, dict) and e.get("value") and e.get("value") != email
            ]
            if other_emails:
                lines.append(f"Other Emails: {', '.join(other_emails)}")

        phones = self.raw_data.get("phones") or []
        if isinstance(phones, list) and len(phones) > 1:
            other_phones: list[str] = [
                str(p.get("value"))
                for p in phones
                if isinstance(p, dict) and p.get("value") and p.get("value") != phone
            ]
            if other_phones:
                lines.append(f"Other Phones: {', '.join(other_phones)}")

        lines.append("")

        # Organization
        org_name = self._get_hydrated_value("org_name")
        org_id = _extract_entity_id(self.raw_data.get("org_id"))
        if org_name:
            org_ref = f"{org_name} ({org_id})" if org_id else org_name
            lines.append(f"Organization: {org_ref}")
            lines.append("")

        # Owner
        owner_name = self._get_hydrated_value("owner_name")
        owner_email = self._get_hydrated_value("owner_email")
        if owner_name:
            lines.append(f"Owner: {owner_name}")
            if owner_email:
                lines.append(f"Owner Email: {owner_email}")
            lines.append("")

        # Labels
        label_names = self._get_hydrated_value("label_names")
        if label_names and isinstance(label_names, list):
            lines.append(f"Labels: {', '.join(label_names)}")
            lines.append("")

        # Deal stats
        stats: list[str] = []
        open_deals = self.raw_data.get("open_deals_count")
        closed_deals = self.raw_data.get("closed_deals_count")
        activities = self.raw_data.get("activities_count")

        if open_deals:
            stats.append(f"Open Deals: {open_deals}")
        if closed_deals:
            stats.append(f"Closed Deals: {closed_deals}")
        if activities:
            stats.append(f"Activities: {activities}")
        if stats:
            lines.append("## Statistics")
            lines.extend(stats)

        return "\n".join(lines)

    def to_embedding_chunks(self) -> list[PipedrivePersonChunk]:
        """Create chunks for person document."""
        chunks: list[PipedrivePersonChunk] = []
        person_id = self._get_person_id()

        # Create header chunk with full content
        header_content = f"[{self.id}]\n{self.get_content()}"
        header_chunk = self.chunk_class(
            document=self,
            raw_data={
                "content": header_content,
                "person_id": person_id,
                "chunk_type": "header",
            },
        )
        self.populate_chunk_permissions(header_chunk)
        chunks.append(header_chunk)

        return chunks

    def get_source_enum(self) -> DocumentSource:
        return DocumentSource.PIPEDRIVE_PERSON

    def get_reference_id(self) -> str:
        """Get the reference ID for this document."""
        return "r_pipedrive_person_" + str(self._get_person_id())

    def get_metadata(self) -> PipedrivePersonDocumentMetadata:
        """Get document metadata for search and filtering."""
        if self.metadata is not None:
            return self.metadata

        person_id = self._get_person_id()
        hydrated = self.raw_data.get("_hydrated", {})

        metadata: PipedrivePersonDocumentMetadata = {
            "person_id": person_id,
            "person_name": self._get_name(),
            "person_email": self._get_primary_email(),
            "person_phone": self._get_primary_phone(),
            "org_name": hydrated.get("org_name"),
            "org_id": _extract_entity_id(self.raw_data.get("org_id")),
            "owner_name": hydrated.get("owner_name"),
            "owner_email": hydrated.get("owner_email"),
            "open_deals_count": self.raw_data.get("open_deals_count"),
            "closed_deals_count": self.raw_data.get("closed_deals_count"),
            "activities_count": self.raw_data.get("activities_count"),
            "label_names": hydrated.get("label_names"),
            "source_created_at": convert_timestamp_to_iso(self.raw_data.get("add_time")),
            "source_updated_at": convert_timestamp_to_iso(self.raw_data.get("update_time")),
            "source": self.get_source(),
            "type": "pipedrive_person",
        }

        return metadata
