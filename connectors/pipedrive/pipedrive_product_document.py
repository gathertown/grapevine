"""Pipedrive Product document and chunk definitions.

Uses dataclass pattern matching the Attio connector for consistency.
"""

from dataclasses import dataclass
from typing import Any, TypedDict

from connectors.base import BaseChunk, BaseDocument
from connectors.base.document_source import DocumentSource
from connectors.base.utils import convert_timestamp_to_iso
from connectors.pipedrive.pipedrive_artifacts import PipedriveProductArtifact
from src.permissions.models import PermissionPolicy


class PipedriveProductChunkMetadata(TypedDict, total=False):
    """Metadata for Pipedrive product chunks."""

    product_id: int | None
    chunk_type: str | None
    content_preview: str | None
    source: str | None


class PipedriveProductDocumentMetadata(TypedDict, total=False):
    """Metadata for Pipedrive product documents."""

    product_id: int | None
    product_name: str | None
    product_code: str | None
    product_unit: str | None
    product_tax: float | None
    owner_name: str | None
    owner_email: str | None
    is_linkable: bool | None
    billing_frequency: str | None
    prices: list[dict[str, Any]] | None
    source_created_at: str | None
    source_updated_at: str | None
    source: str
    type: str


@dataclass
class PipedriveProductChunk(BaseChunk[PipedriveProductChunkMetadata]):
    """A searchable chunk from a Pipedrive product document."""

    def get_content(self) -> str:
        """Get the chunk content."""
        # Header chunks store pre-formatted content directly
        if self.raw_data.get("chunk_type") == "header":
            return self.raw_data.get("content", "")

        return self.raw_data.get("content", "")

    def get_metadata(self) -> PipedriveProductChunkMetadata:
        """Get chunk-specific metadata."""
        chunk_type = self.raw_data.get("chunk_type", "header")
        content = self.get_content()
        content_preview = content[:200] if content else None

        return {
            "product_id": self.raw_data.get("product_id"),
            "chunk_type": chunk_type,
            "content_preview": content_preview,
            "source": "pipedrive_product",
        }


@dataclass
class PipedriveProductDocument(
    BaseDocument[PipedriveProductChunk, PipedriveProductDocumentMetadata]
):
    """Represents a Pipedrive product for indexing and search."""

    raw_data: dict[str, Any]
    metadata: PipedriveProductDocumentMetadata | None = None
    chunk_class: type[PipedriveProductChunk] = PipedriveProductChunk

    @classmethod
    def from_artifact(
        cls,
        artifact: PipedriveProductArtifact,
        hydrated_metadata: dict[str, Any] | None = None,
        permission_policy: PermissionPolicy = "tenant",
        permission_allowed_tokens: list[str] | None = None,
    ) -> "PipedriveProductDocument":
        """Create document from artifact.

        Args:
            artifact: The Pipedrive product artifact
            hydrated_metadata: Optional pre-hydrated metadata with enriched names
            permission_policy: Permission policy for the document
            permission_allowed_tokens: Allowed permission tokens

        Returns:
            PipedriveProductDocument instance
        """
        product_data = artifact.content.product_data.copy()
        product_id = artifact.metadata.product_id

        # Merge hydrated metadata if provided
        if hydrated_metadata:
            product_data["_hydrated"] = hydrated_metadata

        return cls(
            id=f"pipedrive_product_{product_id}",
            raw_data=product_data,
            source_updated_at=artifact.source_updated_at,
            permission_policy=permission_policy,
            permission_allowed_tokens=permission_allowed_tokens,
        )

    def _get_product_id(self) -> int:
        """Get the product ID."""
        return self.raw_data.get("id", 0)

    def _get_name(self) -> str | None:
        """Get product name."""
        return self.raw_data.get("name")

    def _get_hydrated_value(self, key: str) -> Any:
        """Get a hydrated value if available."""
        hydrated = self.raw_data.get("_hydrated", {})
        return hydrated.get(key)

    def get_header_content(self) -> str:
        """Get product header for display."""
        product_id = self._get_product_id()
        product_name = self._get_name() or f"Product #{product_id}"
        return f"Product: <{product_id}|{product_name}>"

    def get_content(self) -> str:
        """Generate formatted product content."""
        lines: list[str] = []
        product_id = self._get_product_id()

        # Name with ID for disambiguation
        name = self._get_name() or "Unnamed Product"
        lines.append(f"# {name} ({product_id})")
        lines.append("")

        # Product code
        code = self.raw_data.get("code")
        if code:
            lines.append(f"Product Code: {code}")

        # Unit
        unit = self.raw_data.get("unit")
        if unit:
            lines.append(f"Unit: {unit}")

        # Tax
        tax = self.raw_data.get("tax")
        if tax is not None:
            lines.append(f"Tax: {tax}%")

        # Billing frequency
        billing_frequency = self.raw_data.get("billing_frequency")
        if billing_frequency:
            lines.append(f"Billing: {billing_frequency}")

        if code or unit or tax or billing_frequency:
            lines.append("")

        # Prices
        prices = self.raw_data.get("prices", [])
        if prices and isinstance(prices, list):
            lines.append("## Pricing")
            for price_entry in prices:
                if isinstance(price_entry, dict):
                    currency = price_entry.get("currency", "USD")
                    price = price_entry.get("price", 0)
                    cost = price_entry.get("cost")
                    price_str = f"- {currency}: {price}"
                    if cost:
                        price_str += f" (cost: {cost})"
                    lines.append(price_str)
            lines.append("")

        # Owner
        owner_name = self._get_hydrated_value("owner_name")
        owner_email = self._get_hydrated_value("owner_email")
        if owner_name:
            lines.append(f"Owner: {owner_name}")
            if owner_email:
                lines.append(f"Owner Email: {owner_email}")
            lines.append("")

        # Visibility/linkability
        is_linkable = self.raw_data.get("selectable", True)
        if not is_linkable:
            lines.append("Note: This product cannot be added to deals")

        return "\n".join(lines)

    def to_embedding_chunks(self) -> list[PipedriveProductChunk]:
        """Create chunks for product document."""
        chunks: list[PipedriveProductChunk] = []
        product_id = self._get_product_id()

        # Create header chunk with full content
        header_content = f"[{self.id}]\n{self.get_content()}"
        header_chunk = self.chunk_class(
            document=self,
            raw_data={
                "content": header_content,
                "product_id": product_id,
                "chunk_type": "header",
            },
        )
        self.populate_chunk_permissions(header_chunk)
        chunks.append(header_chunk)

        return chunks

    def get_source_enum(self) -> DocumentSource:
        return DocumentSource.PIPEDRIVE_PRODUCT

    def get_reference_id(self) -> str:
        """Get the reference ID for this document."""
        return "r_pipedrive_product_" + str(self._get_product_id())

    def get_metadata(self) -> PipedriveProductDocumentMetadata:
        """Get document metadata for search and filtering."""
        if self.metadata is not None:
            return self.metadata

        product_id = self._get_product_id()
        hydrated = self.raw_data.get("_hydrated", {})

        # Extract prices
        prices = self.raw_data.get("prices", [])
        prices_list = prices if isinstance(prices, list) else None

        metadata: PipedriveProductDocumentMetadata = {
            "product_id": product_id,
            "product_name": self._get_name(),
            "product_code": self.raw_data.get("code"),
            "product_unit": self.raw_data.get("unit"),
            "product_tax": self.raw_data.get("tax"),
            "owner_name": hydrated.get("owner_name"),
            "owner_email": hydrated.get("owner_email"),
            "is_linkable": self.raw_data.get("selectable", True),
            "billing_frequency": self.raw_data.get("billing_frequency"),
            "prices": prices_list,
            "source_created_at": convert_timestamp_to_iso(self.raw_data.get("add_time")),
            "source_updated_at": convert_timestamp_to_iso(self.raw_data.get("update_time")),
            "source": self.get_source(),
            "type": "pipedrive_product",
        }

        return metadata
