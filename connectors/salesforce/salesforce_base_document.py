"""
Base classes for Salesforce document types.
"""

from abc import abstractmethod
from dataclasses import dataclass
from typing import Any, TypedDict

from connectors.base import BaseChunk, BaseDocument
from connectors.base.document_source import DocumentSource
from connectors.salesforce.salesforce_artifacts import SUPPORTED_SALESFORCE_OBJECTS
from src.utils.type_conversion import safe_float


class BaseSalesforceChunkMetadata(TypedDict):
    """Base metadata for Salesforce object chunks."""

    object_type: SUPPORTED_SALESFORCE_OBJECTS
    record_id: str
    record_name: str | None
    source: str
    chunk_type: str


class BaseSalesforceDocumentMetadata(TypedDict):
    """Base metadata for Salesforce object documents."""

    object_type: SUPPORTED_SALESFORCE_OBJECTS
    record_id: str
    record_name: str | None
    source: str
    source_created_at: str | None


@dataclass
class BaseSalesforceChunk(BaseChunk[BaseSalesforceChunkMetadata]):
    """Base class for Salesforce object chunks."""

    document: "BaseSalesforceDocument"

    def get_content(self) -> str:
        """Get the formatted record content from the parent document."""
        return self.document.get_content()

    def get_metadata(self) -> BaseSalesforceChunkMetadata:
        """Get chunk-specific metadata from document metadata."""
        doc_metadata = self.document.get_metadata()

        return {
            "object_type": self.document.get_object_type(),
            "record_id": self.document.get_record_id(),
            "record_name": doc_metadata.get("record_name"),
            "source": doc_metadata.get("source", "salesforce"),
            "chunk_type": "record",
        }


@dataclass
class BaseSalesforceDocument(BaseDocument[BaseSalesforceChunk, BaseSalesforceDocumentMetadata]):
    """Base class for Salesforce object documents."""

    raw_data: dict[str, Any]

    def get_record_id(self) -> str:
        """Get the Salesforce record ID for this document."""
        return self.raw_data.get("record_id", "")

    @abstractmethod
    def get_content(self) -> str:
        """Get the full document content. Must be implemented by subclasses."""
        pass

    def _format_address(
        self,
        street_key: str,
        city_key: str,
        state_key: str,
        postal_key: str,
        country_key: str,
        data: dict[str, Any],
    ) -> str | None:
        """Format address fields into a single string if any are present."""
        street = (data.get(street_key) or "").strip()
        city = (data.get(city_key) or "").strip()
        state = (data.get(state_key) or "").strip()
        postal = (data.get(postal_key) or "").strip()
        country = (data.get(country_key) or "").strip()

        address_parts = [p for p in [street, city, state, postal, country] if p]
        return ", ".join(address_parts) if address_parts else None

    def _format_currency(self, amount: object) -> str | None:
        """Format currency amounts."""
        amount = safe_float(amount)
        if amount is None:
            return None
        return f"${amount:,.2f}"

    def _format_name_fields(
        self, data: dict[str, object], first_key: str = "FirstName", last_key: str = "LastName"
    ) -> str:
        """Format first/last name fields into a full name."""
        first_name = data.get(first_key) or ""
        last_name = data.get(last_key) or ""
        return f"{first_name} {last_name}".strip()

    def _format_custom_fields(self, record_data: dict[str, Any]) -> list[str]:
        """Format custom fields section for display."""
        custom_fields = {
            # Salesforce custom fields are typically named with a __c suffix
            k: v
            for k, v in record_data.items()
            if k.endswith("__c") and v is not None and v != ""
        }

        if not custom_fields:
            return []

        lines = ["", "Custom Fields:"]
        for key, value in sorted(custom_fields.items()):
            clean_name = key.replace("__c", "").replace("_", " ").title()
            lines.append(f"{clean_name}: {value}")

        return lines

    def to_embedding_chunks(self) -> list[BaseSalesforceChunk]:
        return [self._create_chunk()]

    @abstractmethod
    def _create_chunk(self) -> BaseSalesforceChunk:
        """Create the appropriate chunk type for this document. Must be implemented by subclasses."""
        pass

    @abstractmethod
    def get_object_type(self) -> SUPPORTED_SALESFORCE_OBJECTS:
        """Get the object type for this document. Must be implemented by subclasses."""
        pass

    def get_source_enum(self) -> DocumentSource:
        return DocumentSource.SALESFORCE

    def get_reference_id(self) -> str:
        """Get the reference ID for this document."""
        return f"r_salesforce_{self.get_object_type().lower()}_{self.get_record_id()}"

    def get_metadata(self) -> BaseSalesforceDocumentMetadata:
        """Get document metadata."""
        object_type = self.get_object_type()
        return {
            "object_type": object_type,
            "record_id": self.get_record_id(),
            "record_name": self.raw_data.get("record_name"),
            "source": self.get_source(),
            "source_created_at": self.raw_data.get("source_created_at"),
        }
