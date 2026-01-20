"""Pydantic models for Custom Data job configurations."""

from typing import Any, Literal

from pydantic import BaseModel

from connectors.base.models import BackfillIngestConfig


class CustomDataDocumentPayload(BaseModel, frozen=True):
    """A single document payload in the custom data ingest message."""

    id: str
    name: str
    description: str | None = None
    content: str
    custom_fields: dict[str, Any] | None = None


class CustomDataIngestConfig(BackfillIngestConfig, frozen=True):
    """
    Custom data ingest job configuration.

    Unlike other connectors that fetch data from external APIs,
    custom data documents are passed directly in the message payload.

    WARNING: This must match the TypeScript CustomDataIngestConfigSchema!
    """

    source: Literal["custom_data_ingest"] = "custom_data_ingest"
    slug: str
    documents: list[CustomDataDocumentPayload]
