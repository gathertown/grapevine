"""Handler functions for Custom Data API endpoints.

This module handles custom data document ingestion via API key authentication,
separate from webhook-based ingestion flows.
"""

import json
import math
import re
import uuid
from typing import Any

from fastapi import HTTPException, Request
from pydantic import BaseModel

from connectors.base.base_ingest_artifact import ArtifactEntity
from connectors.base.document_source import DocumentSource
from connectors.custom_data import get_custom_data_document_entity_id
from connectors.custom_data.custom_data_models import (
    CustomDataDocumentPayload,
    CustomDataIngestConfig,
)
from src.clients.sqs import SQSClient
from src.clients.tenant_db import tenant_db_manager
from src.mcp.utils.api_keys import verify_api_key
from src.utils.logging import get_logger

logger = get_logger(__name__)


def _get_custom_data_document_id(slug: str, item_id: str) -> str:
    """Generate document ID for search index. Format: custom_data_{slug}_{item_id}"""
    return f"{DocumentSource.CUSTOM_DATA}_{slug}_{item_id}"


class CustomDataDocumentInfo(BaseModel):
    """Document info returned in ingest responses."""

    id: str
    name: str
    entity_id: str


class CustomDataIngestResponse(BaseModel):
    """Response model for custom data document ingestion (single or batch)."""

    success: bool
    message: str
    # For single document ingest
    document: CustomDataDocumentInfo | None = None
    # For batch ingest
    documents_accepted: int | None = None
    documents: list[CustomDataDocumentInfo] | None = None


class CustomDataDocumentResponse(BaseModel):
    """Response model for custom data document GET operations."""

    success: bool
    message: str
    document: dict[str, Any] | None = None


class CustomDataDeleteResponse(BaseModel):
    """Response model for custom data document deletion."""

    success: bool
    deleted_id: str


# Constants for custom data validation
BATCH_MAX_DOCUMENTS = 100


async def _authenticate_request(request: Request, tenant_id: str) -> None:
    """Authenticate request using API key and verify tenant match.

    Raises HTTPException on auth failure.
    """
    auth_header = request.headers.get("authorization", "")
    api_key = auth_header.replace("Bearer ", "").strip() if auth_header else ""
    if not api_key:
        raise HTTPException(status_code=401, detail="Missing Authorization header")

    verified_tenant_id = await verify_api_key(api_key)
    if not verified_tenant_id or verified_tenant_id != tenant_id:
        logger.warning(f"Invalid API key for tenant {tenant_id}")
        raise HTTPException(status_code=401, detail="Invalid API key")


async def _get_custom_document_artifact(
    tenant_id: str, slug: str, item_id: str
) -> dict[str, Any] | None:
    """Fetch a custom document artifact from the database.

    Args:
        tenant_id: Tenant identifier
        slug: Custom data type slug
        item_id: Document item ID

    Returns:
        Document artifact dict or None if not found
    """
    entity_id = get_custom_data_document_entity_id(slug=slug, item_id=item_id)
    try:
        async with (
            tenant_db_manager.acquire_pool(tenant_id, readonly=True) as pool,
            pool.acquire() as conn,
        ):
            result = await conn.fetchrow(
                """
                SELECT id, entity, entity_id, content, metadata, source_updated_at
                FROM ingest_artifact
                WHERE entity = $1 AND entity_id = $2
                """,
                ArtifactEntity.CUSTOM_DATA_DOCUMENT,
                entity_id,
            )
            if result:
                return {
                    "id": result["id"],
                    "entity": result["entity"],
                    "entity_id": result["entity_id"],
                    "content": result["content"],
                    "metadata": result["metadata"],
                    "source_updated_at": (
                        result["source_updated_at"].isoformat()
                        if result["source_updated_at"]
                        else None
                    ),
                }
            return None
    except Exception as e:
        logger.error(
            "Error fetching custom document artifact",
            tenant_id=tenant_id,
            slug=slug,
            item_id=item_id,
            error=str(e),
        )
        raise HTTPException(status_code=500, detail="Failed to fetch document")


async def _delete_custom_document_artifact(tenant_id: str, slug: str, item_id: str) -> bool:
    """Delete a custom document artifact from the database.

    Args:
        tenant_id: Tenant identifier
        slug: Custom data type slug
        item_id: Document item ID

    Returns:
        True if deleted, False if not found
    """
    entity_id = get_custom_data_document_entity_id(slug=slug, item_id=item_id)
    try:
        async with (
            tenant_db_manager.acquire_pool(tenant_id) as pool,
            pool.acquire() as conn,
        ):
            result = await conn.fetchrow(
                """
                DELETE FROM ingest_artifact
                WHERE entity = $1 AND entity_id = $2
                RETURNING id
                """,
                ArtifactEntity.CUSTOM_DATA_DOCUMENT,
                entity_id,
            )
            return result is not None
    except Exception as e:
        logger.error(
            "Error deleting custom document artifact",
            tenant_id=tenant_id,
            slug=slug,
            item_id=item_id,
            error=str(e),
        )
        raise HTTPException(status_code=500, detail="Failed to delete document")


def _validate_tenant_id(tenant_id: str) -> None:
    """Validate tenant ID format and raise HTTPException if invalid."""
    if not tenant_id.replace("-", "").replace("_", "").isalnum():
        raise HTTPException(
            status_code=400,
            detail=f"Invalid tenant ID format: {tenant_id}. Must contain only alphanumeric characters, hyphens, and underscores",
        )


async def _get_custom_data_type_by_slug(tenant_id: str, slug: str) -> dict | None:
    """Fetch custom data type and its schema by slug from tenant database.

    Args:
        tenant_id: Tenant identifier
        slug: The slug of the custom data type

    Returns:
        Dict with type info and custom_fields schema, or None if not found
    """
    try:
        async with (
            tenant_db_manager.acquire_pool(tenant_id, readonly=True) as pool,
            pool.acquire() as conn,
        ):
            result = await conn.fetchrow(
                """
                SELECT id, slug, display_name, description, custom_fields, state
                FROM custom_data_types
                WHERE slug = $1 AND state = 'enabled'
                """,
                slug,
            )
            if result:
                return {
                    "id": result["id"],
                    "slug": result["slug"],
                    "display_name": result["display_name"],
                    "description": result["description"],
                    "custom_fields": result["custom_fields"] or {},
                    "state": result["state"],
                }
            return None
    except Exception as e:
        logger.error(
            "Error fetching custom data type",
            tenant_id=tenant_id,
            slug=slug,
            error=str(e),
        )
        return None


def _validate_custom_fields(
    data: dict,
    schema_fields: list[dict],
) -> tuple[bool, str | None]:
    """Validate custom fields against the schema definition.

    Args:
        data: Dict of field name -> value
        schema_fields: List of field definitions from custom_fields.fields

    Returns:
        Tuple of (is_valid, error_message)
    """
    valid_field_names = {f["name"] for f in schema_fields}

    # Check for unknown fields
    for key in data:
        if key not in valid_field_names:
            return False, f'Unknown field "{key}" is not defined in the schema'

    # Validate each schema field
    for field in schema_fields:
        field_name = field["name"]
        field_type = field.get("type", "text")
        required = field.get("required", False)
        value = data.get(field_name)

        # Check required fields
        if required and (value is None or value == ""):
            return False, f'Required field "{field_name}" is missing'

        # Skip validation if field is not provided and not required
        if value is None:
            continue

        # Type validation
        if field_type == "text":
            if not isinstance(value, str):
                return False, f'Field "{field_name}" must be a string'
        elif field_type == "number":
            # Reject booleans (bool is a subclass of int in Python), NaN, and Infinity
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or math.isnan(value)
                or math.isinf(value)
            ):
                return False, f'Field "{field_name}" must be a finite number'
        elif field_type == "date":
            if not isinstance(value, str):
                return False, f'Field "{field_name}" must be a valid date string (ISO 8601 format)'
            # Basic ISO 8601 date validation
            try:
                # Try parsing as ISO date
                from datetime import datetime as dt

                dt.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError:
                return False, f'Field "{field_name}" must be a valid date string (ISO 8601 format)'

    return True, None


def _extract_custom_fields(
    data: dict,
    schema_fields: list[dict],
) -> dict:
    """Extract custom fields from request body based on schema.

    Args:
        data: Full request body dict
        schema_fields: List of field definitions

    Returns:
        Dict containing only the defined custom fields
    """
    custom_fields = {}
    for field in schema_fields:
        field_name = field["name"]
        if field_name in data:
            custom_fields[field_name] = data[field_name]
    return custom_fields


def _validate_document_core_fields(doc: dict) -> tuple[bool, str | None]:
    """Validate the core document fields (name, content, description).

    Args:
        doc: Document dict

    Returns:
        Tuple of (is_valid, error_message)
    """
    name = doc.get("name")
    content = doc.get("content")
    description = doc.get("description")

    if not name or not isinstance(name, str) or not name.strip():
        return False, "name is required and must be a non-empty string"

    if not content or not isinstance(content, str) or not content.strip():
        return False, "content is required and must be a non-empty string"

    if description is not None and not isinstance(description, str):
        return False, "description must be a string"

    return True, None


def _validate_no_user_provided_id(doc: dict) -> tuple[bool, str | None]:
    """Validate that user-provided ID is rejected.

    Args:
        doc: Document dict

    Returns:
        Tuple of (is_valid, error_message)
    """
    if "id" in doc:
        return False, 'The "id" field should not be provided. Document IDs are auto-generated.'
    return True, None


def _validate_slug(slug: str) -> None:
    """Validate slug format and raise HTTPException if invalid.

    Slugs must be alphanumeric with hyphens or underscores, 1-64 characters.
    """
    if not re.match(r"^[a-zA-Z0-9_-]{1,64}$", slug):
        raise HTTPException(
            status_code=400,
            detail="Slug must be alphanumeric with hyphens or underscores (max 64 chars)",
        )


async def handle_custom_data_ingest(
    request: Request,
    tenant_id: str,
    slug: str,
) -> CustomDataIngestResponse:
    """Handle custom data document ingestion with API key authentication.

    Args:
        request: FastAPI request
        tenant_id: Tenant ID from URL path
        slug: Custom data type slug from URL path

    Returns:
        CustomDataIngestResponse with document info

    Raises:
        HTTPException: On validation or auth failures
    """
    _validate_tenant_id(tenant_id)
    _validate_slug(slug)

    # Authenticate using API key
    auth_header = request.headers.get("authorization", "")
    api_key = auth_header.replace("Bearer ", "").strip() if auth_header else ""
    if not api_key:
        raise HTTPException(status_code=401, detail="Missing Authorization header")

    # Verify API key matches tenant
    verified_tenant_id = await verify_api_key(api_key)
    if not verified_tenant_id or verified_tenant_id != tenant_id:
        logger.warning(f"Invalid API key for tenant {tenant_id}")
        raise HTTPException(status_code=401, detail="Invalid API key")

    # Fetch custom data type to get schema
    custom_data_type = await _get_custom_data_type_by_slug(tenant_id, slug)
    if not custom_data_type:
        raise HTTPException(
            status_code=404,
            detail=f"Custom data type '{slug}' not found or not enabled",
        )

    # Parse request body
    try:
        body = await request.body()
        body_str = body.decode("utf-8")
        payload = json.loads(body_str)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    # Get schema fields
    custom_fields_schema = custom_data_type.get("custom_fields", {})
    schema_fields = custom_fields_schema.get("fields", [])

    # Check if this is a batch request or single document
    if "documents" in payload:
        # Batch request
        documents = payload["documents"]

        if not isinstance(documents, list):
            raise HTTPException(status_code=400, detail="documents must be an array")

        if len(documents) == 0:
            raise HTTPException(status_code=400, detail="documents array cannot be empty")

        if len(documents) > BATCH_MAX_DOCUMENTS:
            raise HTTPException(
                status_code=400,
                detail=f"Maximum {BATCH_MAX_DOCUMENTS} documents per batch",
            )

        # Validate and process each document
        document_payloads = []
        for idx, doc in enumerate(documents):
            if not isinstance(doc, dict):
                raise HTTPException(status_code=400, detail=f"Document {idx}: must be an object")

            # Validate no user-provided ID
            valid, error = _validate_no_user_provided_id(doc)
            if not valid:
                raise HTTPException(status_code=400, detail=f"Document {idx}: {error}")

            # Validate core fields
            valid, error = _validate_document_core_fields(doc)
            if not valid:
                raise HTTPException(status_code=400, detail=f"Document {idx}: {error}")

            # Extract and validate custom fields
            core_keys = {"name", "content", "description"}
            other_fields = {k: v for k, v in doc.items() if k not in core_keys}

            valid, error = _validate_custom_fields(other_fields, schema_fields)
            if not valid:
                raise HTTPException(status_code=400, detail=f"Document {idx}: {error}")

            custom_fields = _extract_custom_fields(other_fields, schema_fields)

            # Generate document ID
            doc_id = str(uuid.uuid4())

            document_payloads.append(
                CustomDataDocumentPayload(
                    id=doc_id,
                    name=doc["name"].strip(),
                    description=doc.get("description", "").strip()
                    if doc.get("description")
                    else None,
                    content=doc["content"].strip(),
                    custom_fields=custom_fields if custom_fields else None,
                )
            )

        logger.info(
            f"Validated {len(document_payloads)} documents for custom data type",
            tenant_id=tenant_id,
            slug=slug,
        )

    else:
        # Single document request
        # Validate no user-provided ID
        valid, error = _validate_no_user_provided_id(payload)
        if not valid:
            raise HTTPException(status_code=400, detail=error)

        # Validate core fields
        valid, error = _validate_document_core_fields(payload)
        if not valid:
            raise HTTPException(status_code=400, detail=error)

        # Extract and validate custom fields
        core_keys = {"name", "content", "description"}
        other_fields = {k: v for k, v in payload.items() if k not in core_keys}

        valid, error = _validate_custom_fields(other_fields, schema_fields)
        if not valid:
            raise HTTPException(status_code=400, detail=error)

        custom_fields = _extract_custom_fields(other_fields, schema_fields)

        # Generate document ID
        doc_id = str(uuid.uuid4())

        document_payloads = [
            CustomDataDocumentPayload(
                id=doc_id,
                name=payload["name"].strip(),
                description=payload.get("description", "").strip()
                if payload.get("description")
                else None,
                content=payload["content"].strip(),
                custom_fields=custom_fields if custom_fields else None,
            )
        ]

    # Create ingest config and send to SQS
    ingest_config = CustomDataIngestConfig(
        tenant_id=tenant_id,
        slug=slug,
        documents=document_payloads,
    )

    sqs_client: SQSClient = request.app.state.sqs_client
    message_id = await sqs_client.send_backfill_ingest_message(ingest_config)

    if not message_id:
        logger.error(
            "Failed to publish custom data ingest message to SQS",
            tenant_id=tenant_id,
            slug=slug,
        )
        raise HTTPException(
            status_code=500,
            detail="Failed to publish message to processing queue",
        )

    logger.info(
        "Successfully accepted custom data documents for ingestion",
        tenant_id=tenant_id,
        slug=slug,
        document_count=len(document_payloads),
        message_id=message_id,
    )

    # Build document info for response
    doc_infos = [
        CustomDataDocumentInfo(
            id=doc.id,
            name=doc.name,
            entity_id=get_custom_data_document_entity_id(slug=slug, item_id=doc.id),
        )
        for doc in document_payloads
    ]

    # Return appropriate response format based on single vs batch
    if len(doc_infos) == 1 and "documents" not in payload:
        # Single document response
        return CustomDataIngestResponse(
            success=True,
            message="Document accepted for processing",
            document=doc_infos[0],
        )
    else:
        # Batch response
        return CustomDataIngestResponse(
            success=True,
            message="Documents accepted for processing",
            documents_accepted=len(doc_infos),
            documents=doc_infos,
        )


async def handle_custom_data_get(
    request: Request,
    tenant_id: str,
    slug: str,
    item_id: str,
) -> CustomDataDocumentResponse:
    """Get a custom data document by slug and item ID.

    Args:
        request: FastAPI request
        tenant_id: Tenant ID from URL path
        slug: Custom data type slug from URL path
        item_id: Document item ID from URL path

    Returns:
        CustomDataDocumentResponse with document data

    Raises:
        HTTPException: On validation, auth, or not found errors
    """
    _validate_tenant_id(tenant_id)
    _validate_slug(slug)

    await _authenticate_request(request, tenant_id)

    artifact = await _get_custom_document_artifact(tenant_id, slug, item_id)
    if not artifact:
        raise HTTPException(status_code=404, detail="Document not found")

    logger.info(
        "Retrieved custom data document",
        tenant_id=tenant_id,
        slug=slug,
        item_id=item_id,
    )

    return CustomDataDocumentResponse(
        success=True,
        message="Document retrieved successfully",
        document=artifact,
    )


async def handle_custom_data_update(
    request: Request,
    tenant_id: str,
    slug: str,
    item_id: str,
) -> CustomDataIngestResponse:
    """Update a custom data document by slug and item ID.

    Args:
        request: FastAPI request
        tenant_id: Tenant ID from URL path
        slug: Custom data type slug from URL path
        item_id: Document item ID from URL path

    Returns:
        CustomDataIngestResponse with updated document info

    Raises:
        HTTPException: On validation, auth, or not found errors
    """
    _validate_tenant_id(tenant_id)
    _validate_slug(slug)

    await _authenticate_request(request, tenant_id)

    # Check if document exists
    existing_artifact = await _get_custom_document_artifact(tenant_id, slug, item_id)
    if not existing_artifact:
        raise HTTPException(status_code=404, detail="Document not found")

    # Fetch custom data type to get schema
    custom_data_type = await _get_custom_data_type_by_slug(tenant_id, slug)
    if not custom_data_type:
        raise HTTPException(
            status_code=404,
            detail=f"Custom data type '{slug}' not found or not enabled",
        )

    # Parse request body
    try:
        body = await request.body()
        body_str = body.decode("utf-8")
        payload = json.loads(body_str)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    # Validate user-provided id is not present (can't change ID)
    valid, error = _validate_no_user_provided_id(payload)
    if not valid:
        raise HTTPException(status_code=400, detail=error)

    # Validate core fields
    valid, error = _validate_document_core_fields(payload)
    if not valid:
        raise HTTPException(status_code=400, detail=error)

    # Get schema fields
    custom_fields_schema = custom_data_type.get("custom_fields", {})
    schema_fields = custom_fields_schema.get("fields", [])

    # Extract and validate custom fields
    core_keys = {"name", "content", "description"}
    other_fields = {k: v for k, v in payload.items() if k not in core_keys}

    valid, error = _validate_custom_fields(other_fields, schema_fields)
    if not valid:
        raise HTTPException(status_code=400, detail=error)

    custom_fields = _extract_custom_fields(other_fields, schema_fields)

    # Build document payload using existing ID
    document_payload = CustomDataDocumentPayload(
        id=item_id,
        name=payload["name"].strip(),
        description=payload.get("description", "").strip() if payload.get("description") else None,
        content=payload["content"].strip(),
        custom_fields=custom_fields if custom_fields else None,
    )

    # Create ingest config and send to SQS
    ingest_config = CustomDataIngestConfig(
        tenant_id=tenant_id,
        slug=slug,
        documents=[document_payload],
    )

    sqs_client: SQSClient = request.app.state.sqs_client
    message_id = await sqs_client.send_backfill_ingest_message(ingest_config)

    if not message_id:
        logger.error(
            "Failed to publish custom data update message to SQS",
            tenant_id=tenant_id,
            slug=slug,
            item_id=item_id,
        )
        raise HTTPException(
            status_code=500,
            detail="Failed to publish message to processing queue",
        )

    logger.info(
        "Successfully accepted custom data document update for processing",
        tenant_id=tenant_id,
        slug=slug,
        item_id=item_id,
        message_id=message_id,
    )

    return CustomDataIngestResponse(
        success=True,
        message="Document update accepted for processing",
        document=CustomDataDocumentInfo(
            id=item_id,
            name=document_payload.name,
            entity_id=get_custom_data_document_entity_id(slug=slug, item_id=item_id),
        ),
    )


async def handle_custom_data_delete(
    request: Request,
    tenant_id: str,
    slug: str,
    item_id: str,
) -> CustomDataDeleteResponse:
    """Delete a custom data document by slug and item ID.

    Args:
        request: FastAPI request
        tenant_id: Tenant ID from URL path
        slug: Custom data type slug from URL path
        item_id: Document item ID from URL path

    Returns:
        CustomDataDeleteResponse indicating success

    Raises:
        HTTPException: On validation, auth, or not found errors
    """
    _validate_tenant_id(tenant_id)
    _validate_slug(slug)

    await _authenticate_request(request, tenant_id)

    # Delete the artifact from database
    deleted = await _delete_custom_document_artifact(tenant_id, slug, item_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Document not found")

    logger.info(
        "Deleted custom data document artifact",
        tenant_id=tenant_id,
        slug=slug,
        item_id=item_id,
    )

    # Trigger deletion from search index (OpenSearch/Turbopuffer)
    sqs_client: SQSClient = request.app.state.sqs_client
    document_id = _get_custom_data_document_id(slug, item_id)

    try:
        await sqs_client.send_delete_message(
            tenant_id=tenant_id,
            document_ids=[document_id],
        )
        logger.info(
            "Triggered search index deletion for custom data document",
            tenant_id=tenant_id,
            slug=slug,
            document_id=document_id,
        )
    except Exception as e:
        # Log but don't fail - artifact is already deleted from DB
        logger.error(
            "Failed to trigger search index deletion for custom data document",
            tenant_id=tenant_id,
            slug=slug,
            item_id=item_id,
            error=str(e),
        )

    return CustomDataDeleteResponse(
        success=True,
        deleted_id=item_id,
    )
