"""Pydantic models for gatekeeper service."""

from pydantic import BaseModel


class WebhookRequest(BaseModel):
    """Base webhook request model."""

    headers: dict[str, str]
    body: str


class WebhookResponse(BaseModel):
    """Webhook response model."""

    success: bool
    message: str
    tenant_id: str | None = None
    message_id: str | None = None


class TenantSourceLink(BaseModel):
    """Tenant source link model."""

    id: str
    tenant_id: str
    source_type: str
    external_id: str
    is_active: bool


class TenantFromHostResult(BaseModel):
    """Result of tenant extraction from Host header."""

    tenant_id: str | None
    error: str | None = None


class CustomDataDocumentRequest(BaseModel):
    """Request model for a single custom data document."""

    name: str
    content: str
    description: str | None = None
    # Additional custom fields are allowed via model_config
    model_config = {"extra": "allow"}


class CustomDataBatchRequest(BaseModel):
    """Request model for batch custom data document ingestion."""

    documents: list[dict]  # We validate each document manually to provide better errors
