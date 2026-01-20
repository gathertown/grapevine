"""Pipedrive Organization document and chunk definitions.

Uses dataclass pattern matching the Attio connector for consistency.
"""

from dataclasses import dataclass
from typing import Any, TypedDict

from connectors.base import BaseChunk, BaseDocument
from connectors.base.document_source import DocumentSource
from connectors.base.utils import convert_timestamp_to_iso
from connectors.pipedrive.pipedrive_artifacts import PipedriveOrganizationArtifact
from src.permissions.models import PermissionPolicy


class PipedriveOrganizationChunkMetadata(TypedDict, total=False):
    """Metadata for Pipedrive organization chunks."""

    org_id: int | None
    chunk_type: str | None
    content_preview: str | None
    source: str | None


class PipedriveOrganizationDocumentMetadata(TypedDict, total=False):
    """Metadata for Pipedrive organization documents."""

    org_id: int | None
    org_name: str | None
    org_address: str | None
    owner_name: str | None
    owner_email: str | None
    people_count: int | None
    open_deals_count: int | None
    closed_deals_count: int | None
    won_deals_count: int | None
    lost_deals_count: int | None
    activities_count: int | None
    label_names: list[str] | None
    source_created_at: str | None
    source_updated_at: str | None
    source: str
    type: str


@dataclass
class PipedriveOrganizationChunk(BaseChunk[PipedriveOrganizationChunkMetadata]):
    """A searchable chunk from a Pipedrive organization document."""

    def get_content(self) -> str:
        """Get the chunk content."""
        # Header chunks store pre-formatted content directly
        if self.raw_data.get("chunk_type") == "header":
            return self.raw_data.get("content", "")

        return self.raw_data.get("content", "")

    def get_metadata(self) -> PipedriveOrganizationChunkMetadata:
        """Get chunk-specific metadata."""
        chunk_type = self.raw_data.get("chunk_type", "header")
        content = self.get_content()
        content_preview = content[:200] if content else None

        return {
            "org_id": self.raw_data.get("org_id"),
            "chunk_type": chunk_type,
            "content_preview": content_preview,
            "source": "pipedrive_organization",
        }


@dataclass
class PipedriveOrganizationDocument(
    BaseDocument[PipedriveOrganizationChunk, PipedriveOrganizationDocumentMetadata]
):
    """Represents a Pipedrive organization (company) for indexing and search."""

    raw_data: dict[str, Any]
    metadata: PipedriveOrganizationDocumentMetadata | None = None
    chunk_class: type[PipedriveOrganizationChunk] = PipedriveOrganizationChunk

    @classmethod
    def from_artifact(
        cls,
        artifact: PipedriveOrganizationArtifact,
        hydrated_metadata: dict[str, Any] | None = None,
        permission_policy: PermissionPolicy = "tenant",
        permission_allowed_tokens: list[str] | None = None,
    ) -> "PipedriveOrganizationDocument":
        """Create document from artifact.

        Args:
            artifact: The Pipedrive organization artifact
            hydrated_metadata: Optional pre-hydrated metadata with enriched names
            permission_policy: Permission policy for the document
            permission_allowed_tokens: Allowed permission tokens

        Returns:
            PipedriveOrganizationDocument instance
        """
        org_data = artifact.content.org_data.copy()
        org_id = artifact.metadata.org_id

        # Merge hydrated metadata if provided
        if hydrated_metadata:
            org_data["_hydrated"] = hydrated_metadata

        return cls(
            id=f"pipedrive_organization_{org_id}",
            raw_data=org_data,
            source_updated_at=artifact.source_updated_at,
            permission_policy=permission_policy,
            permission_allowed_tokens=permission_allowed_tokens,
        )

    def _get_org_id(self) -> int:
        """Get the organization ID."""
        return self.raw_data.get("id", 0)

    def _get_name(self) -> str | None:
        """Get organization name."""
        return self.raw_data.get("name")

    def _get_hydrated_value(self, key: str) -> Any:
        """Get a hydrated value if available."""
        hydrated = self.raw_data.get("_hydrated", {})
        return hydrated.get(key)

    def get_header_content(self) -> str:
        """Get organization header for display."""
        org_id = self._get_org_id()
        org_name = self._get_name() or f"Organization #{org_id}"
        return f"Organization: <{org_id}|{org_name}>"

    def get_content(self) -> str:
        """Generate formatted organization content."""
        lines: list[str] = []
        org_id = self._get_org_id()

        # Name with ID for disambiguation
        name = self._get_name() or "Unnamed Organization"
        lines.append(f"# {name} ({org_id})")
        lines.append("")

        # Address
        address = self.raw_data.get("address")
        if address:
            lines.append(f"Address: {address}")
            lines.append("")

        # Contact details from raw data
        cc_email = self.raw_data.get("cc_email")
        if cc_email:
            lines.append(f"CC Email: {cc_email}")
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

        # Statistics
        lines.append("## Statistics")
        people_count = self.raw_data.get("people_count")
        open_deals = self.raw_data.get("open_deals_count")
        closed_deals = self.raw_data.get("closed_deals_count")
        won_deals = self.raw_data.get("won_deals_count")
        lost_deals = self.raw_data.get("lost_deals_count")
        activities = self.raw_data.get("activities_count")

        if people_count:
            lines.append(f"People: {people_count}")
        if open_deals:
            lines.append(f"Open Deals: {open_deals}")
        if closed_deals:
            lines.append(f"Closed Deals: {closed_deals}")
        if won_deals:
            lines.append(f"Won Deals: {won_deals}")
        if lost_deals:
            lines.append(f"Lost Deals: {lost_deals}")
        if activities:
            lines.append(f"Activities: {activities}")

        return "\n".join(lines)

    def to_embedding_chunks(self) -> list[PipedriveOrganizationChunk]:
        """Create chunks for organization document."""
        chunks: list[PipedriveOrganizationChunk] = []
        org_id = self._get_org_id()

        # Create header chunk with full content
        header_content = f"[{self.id}]\n{self.get_content()}"
        header_chunk = self.chunk_class(
            document=self,
            raw_data={
                "content": header_content,
                "org_id": org_id,
                "chunk_type": "header",
            },
        )
        self.populate_chunk_permissions(header_chunk)
        chunks.append(header_chunk)

        return chunks

    def get_source_enum(self) -> DocumentSource:
        return DocumentSource.PIPEDRIVE_ORGANIZATION

    def get_reference_id(self) -> str:
        """Get the reference ID for this document."""
        return "r_pipedrive_organization_" + str(self._get_org_id())

    def get_metadata(self) -> PipedriveOrganizationDocumentMetadata:
        """Get document metadata for search and filtering."""
        if self.metadata is not None:
            return self.metadata

        org_id = self._get_org_id()
        hydrated = self.raw_data.get("_hydrated", {})

        metadata: PipedriveOrganizationDocumentMetadata = {
            "org_id": org_id,
            "org_name": self._get_name(),
            "org_address": self.raw_data.get("address"),
            "owner_name": hydrated.get("owner_name"),
            "owner_email": hydrated.get("owner_email"),
            "people_count": self.raw_data.get("people_count"),
            "open_deals_count": self.raw_data.get("open_deals_count"),
            "closed_deals_count": self.raw_data.get("closed_deals_count"),
            "won_deals_count": self.raw_data.get("won_deals_count"),
            "lost_deals_count": self.raw_data.get("lost_deals_count"),
            "activities_count": self.raw_data.get("activities_count"),
            "label_names": hydrated.get("label_names"),
            "source_created_at": convert_timestamp_to_iso(self.raw_data.get("add_time")),
            "source_updated_at": convert_timestamp_to_iso(self.raw_data.get("update_time")),
            "source": self.get_source(),
            "type": "pipedrive_organization",
        }

        return metadata
