"""Tests for Attio webhook handler.

This module tests:
1. HMAC-SHA256 signature verification
2. Metadata extraction from webhook payloads
3. AttioWebhookVerifier integration with BaseSigningSecretVerifier
"""

import hashlib
import hmac
import json
from typing import cast
from unittest.mock import AsyncMock, patch

import pytest

from connectors.attio import (
    AttioWebhookVerifier,
    extract_attio_webhook_metadata,
    extract_attio_workspace_id,
    verify_attio_webhook,
)
from src.ingest.gatekeeper.verification import BaseSigningSecretVerifier
from src.ingest.gatekeeper.verifier_registry import WebhookSourceType, get_verifier


class TestVerifyAttioWebhook:
    """Test suite for verify_attio_webhook function."""

    def test_valid_signature_passes(self):
        """Test that valid HMAC-SHA256 signature passes verification."""
        secret = "test-webhook-secret"
        body = b'{"event_type": "record.created", "data": {}}'

        # Calculate correct signature
        expected_signature = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()

        headers = {"attio-signature": expected_signature}

        # Should not raise
        verify_attio_webhook(headers, body, secret)

    def test_valid_signature_with_legacy_header(self):
        """Test that X-Attio-Signature header also works (legacy support)."""
        secret = "test-webhook-secret"
        body = b'{"event_type": "record.updated"}'

        expected_signature = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()

        # Using legacy header name
        headers = {"x-attio-signature": expected_signature}

        # Should not raise
        verify_attio_webhook(headers, body, secret)

    def test_invalid_signature_fails(self):
        """Test that invalid signature raises ValueError."""
        secret = "test-webhook-secret"
        body = b'{"event_type": "record.created"}'

        headers = {"attio-signature": "invalid_signature_abc123"}

        with pytest.raises(ValueError, match="Invalid Attio webhook signature"):
            verify_attio_webhook(headers, body, secret)

    def test_missing_signature_header_fails(self):
        """Test that missing signature header raises ValueError."""
        secret = "test-webhook-secret"
        body = b'{"event_type": "record.created"}'

        headers: dict[str, str] = {}  # No signature header

        with pytest.raises(ValueError, match="Missing Attio webhook signature header"):
            verify_attio_webhook(headers, body, secret)

    def test_empty_secret_raises_error(self):
        """Test that empty or missing secret raises ValueError for security."""
        body = b'{"event_type": "record.created"}'
        headers: dict[str, str] = {}

        # Should raise ValueError when secret is empty or None
        with pytest.raises(ValueError, match="Missing Attio webhook signing secret"):
            verify_attio_webhook(headers, body, "")

        with pytest.raises(ValueError, match="Missing Attio webhook signing secret"):
            verify_attio_webhook(headers, body, None)

    def test_signature_is_case_insensitive_header(self):
        """Test that header name lookup is case-insensitive."""
        secret = "test-webhook-secret"
        body = b'{"test": "data"}'

        expected_signature = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()

        # Headers dict with lowercase keys (as FastAPI normalizes)
        headers = {"attio-signature": expected_signature}

        verify_attio_webhook(headers, body, secret)

    def test_tampered_body_fails(self):
        """Test that signature verification fails if body is tampered."""
        secret = "test-webhook-secret"
        original_body = b'{"event_type": "record.created", "data": {"id": "123"}}'
        tampered_body = b'{"event_type": "record.created", "data": {"id": "456"}}'

        # Sign with original body
        signature = hmac.new(secret.encode("utf-8"), original_body, hashlib.sha256).hexdigest()

        headers = {"attio-signature": signature}

        # Verify with tampered body should fail
        with pytest.raises(ValueError, match="Invalid Attio webhook signature"):
            verify_attio_webhook(headers, tampered_body, secret)


class TestExtractAttioWorkspaceId:
    """Test suite for extract_attio_workspace_id function."""

    def test_extracts_workspace_id_from_events_array(self):
        """Test extraction of workspace_id from events array.

        Attio payload structure: { "webhook_id": "...", "events": [...] }
        """
        payload = {
            "webhook_id": "webhook-123",
            "events": [
                {
                    "event_type": "record.created",
                    "id": {
                        "workspace_id": "50cf242c-7fa3-4cad-87d0-75b1af71c57b",
                        "object_id": "companies",
                        "record_id": "rec_123",
                    },
                    "actor": {"type": "workspace-member", "id": "actor-456"},
                }
            ],
        }
        body_str = json.dumps(payload)

        result = extract_attio_workspace_id(body_str)
        assert result == "50cf242c-7fa3-4cad-87d0-75b1af71c57b"

    def test_returns_none_for_missing_events_array(self):
        """Test returns None when events array is missing."""
        payload = {"webhook_id": "webhook-123"}
        body_str = json.dumps(payload)

        result = extract_attio_workspace_id(body_str)
        assert result is None

    def test_returns_none_for_empty_events_array(self):
        """Test returns None when events array is empty."""
        payload = {"webhook_id": "webhook-123", "events": []}
        body_str = json.dumps(payload)

        result = extract_attio_workspace_id(body_str)
        assert result is None

    def test_returns_none_for_missing_workspace_id(self):
        """Test returns None when workspace_id is missing from id object."""
        payload = {
            "webhook_id": "webhook-123",
            "events": [
                {
                    "event_type": "record.created",
                    "id": {
                        "object_id": "companies",
                        "record_id": "rec_123",
                    },
                    "actor": {"type": "workspace-member", "id": "actor-456"},
                }
            ],
        }
        body_str = json.dumps(payload)

        result = extract_attio_workspace_id(body_str)
        assert result is None

    def test_returns_none_for_invalid_json(self):
        """Test returns None for invalid JSON."""
        result = extract_attio_workspace_id("not valid json {{{")
        assert result is None

    def test_returns_none_for_empty_workspace_id(self):
        """Test returns None when workspace_id is empty string."""
        payload = {
            "webhook_id": "webhook-123",
            "events": [
                {
                    "event_type": "record.created",
                    "id": {
                        "workspace_id": "",
                        "object_id": "companies",
                        "record_id": "rec_123",
                    },
                    "actor": {"type": "workspace-member", "id": "actor-456"},
                }
            ],
        }
        body_str = json.dumps(payload)

        result = extract_attio_workspace_id(body_str)
        assert result is None

    def test_strips_whitespace_from_workspace_id(self):
        """Test that workspace_id is stripped of whitespace."""
        payload = {
            "webhook_id": "webhook-123",
            "events": [
                {
                    "event_type": "record.created",
                    "id": {
                        "workspace_id": "  workspace-123  ",
                        "object_id": "companies",
                        "record_id": "rec_123",
                    },
                    "actor": {"type": "workspace-member", "id": "actor-456"},
                }
            ],
        }
        body_str = json.dumps(payload)

        result = extract_attio_workspace_id(body_str)
        assert result == "workspace-123"


class TestExtractAttioWebhookMetadata:
    """Test suite for extract_attio_webhook_metadata function.

    All payloads follow Attio's actual API structure with wrapper:
    { "webhook_id": "...", "events": [...] }
    See: https://docs.attio.com/rest-api/webhook-reference/record-events/
    """

    def test_extracts_payload_size(self):
        """Test that payload size is always extracted."""
        body_str = '{"webhook_id": "test", "events": []}'
        headers: dict[str, str] = {}

        metadata = extract_attio_webhook_metadata(headers, body_str)

        assert metadata["payload_size"] == len(body_str)
        assert "payload_size_human" in metadata

    def test_extracts_webhook_id_and_event_count(self):
        """Test extraction of webhook_id and event count."""
        payload = {
            "webhook_id": "webhook-123",
            "events": [
                {"event_type": "record.updated", "id": {}, "actor": {}},
                {"event_type": "record.created", "id": {}, "actor": {}},
            ],
        }
        body_str = json.dumps(payload)

        metadata = extract_attio_webhook_metadata({}, body_str)

        assert metadata["webhook_id"] == "webhook-123"
        assert metadata["event_count"] == 2

    def test_extracts_event_type(self):
        """Test extraction of event_type field from first event."""
        payload = {
            "webhook_id": "webhook-123",
            "events": [
                {
                    "event_type": "record.updated",
                    "id": {
                        "workspace_id": "ws-123",
                        "object_id": "companies",
                        "record_id": "rec-123",
                        "attribute_id": "attr-456",
                    },
                    "actor": {"type": "workspace-member", "id": "actor-456"},
                }
            ],
        }
        body_str = json.dumps(payload)

        metadata = extract_attio_webhook_metadata({}, body_str)

        assert metadata["event_type"] == "record.updated"

    def test_extracts_workspace_id(self):
        """Test extraction of workspace_id from first event."""
        payload = {
            "webhook_id": "webhook-123",
            "events": [
                {
                    "event_type": "record.created",
                    "id": {
                        "workspace_id": "50cf242c-7fa3-4cad-87d0-75b1af71c57b",
                        "object_id": "companies",
                        "record_id": "rec-123",
                    },
                    "actor": {"type": "workspace-member", "id": "actor-456"},
                }
            ],
        }
        body_str = json.dumps(payload)

        metadata = extract_attio_webhook_metadata({}, body_str)

        assert metadata["workspace_id"] == "50cf242c-7fa3-4cad-87d0-75b1af71c57b"

    def test_extracts_actor_information(self):
        """Test extraction of actor details from first event."""
        payload = {
            "webhook_id": "webhook-123",
            "events": [
                {
                    "event_type": "record.updated",
                    "id": {
                        "workspace_id": "ws-123",
                        "object_id": "people",
                        "record_id": "rec-123",
                    },
                    "actor": {"type": "workspace-member", "id": "actor-456"},
                }
            ],
        }
        body_str = json.dumps(payload)

        metadata = extract_attio_webhook_metadata({}, body_str)

        assert metadata["actor_type"] == "workspace-member"
        assert metadata["actor_id"] == "actor-456"

    def test_extracts_record_id_from_id_object(self):
        """Test extraction of record_id from first event's id object."""
        payload = {
            "webhook_id": "webhook-123",
            "events": [
                {
                    "event_type": "record.created",
                    "id": {
                        "workspace_id": "ws-123",
                        "object_id": "companies",
                        "record_id": "rec-789",
                    },
                    "actor": {"type": "workspace-member", "id": "actor-456"},
                }
            ],
        }
        body_str = json.dumps(payload)

        metadata = extract_attio_webhook_metadata({}, body_str)

        assert metadata["object_type"] == "companies"
        assert metadata["record_id"] == "rec-789"

    def test_extracts_attribute_id_for_updates(self):
        """Test extraction of attribute_id for record.updated events."""
        payload = {
            "webhook_id": "webhook-123",
            "events": [
                {
                    "event_type": "record.updated",
                    "id": {
                        "workspace_id": "ws-123",
                        "object_id": "companies",
                        "record_id": "rec-789",
                        "attribute_id": "attr-456",
                    },
                    "actor": {"type": "workspace-member", "id": "actor-456"},
                }
            ],
        }
        body_str = json.dumps(payload)

        metadata = extract_attio_webhook_metadata({}, body_str)

        assert metadata["attribute_id"] == "attr-456"

    def test_extracts_note_id(self):
        """Test extraction of note_id for note events."""
        payload = {
            "webhook_id": "webhook-123",
            "events": [
                {
                    "event_type": "note.created",
                    "id": {
                        "workspace_id": "ws-123",
                        "note_id": "note-abc",
                    },
                    "actor": {"type": "workspace-member", "id": "actor-456"},
                }
            ],
        }
        body_str = json.dumps(payload)

        metadata = extract_attio_webhook_metadata({}, body_str)

        assert metadata["note_id"] == "note-abc"

    def test_extracts_task_id(self):
        """Test extraction of task_id for task events."""
        payload = {
            "webhook_id": "webhook-123",
            "events": [
                {
                    "event_type": "task.updated",
                    "id": {
                        "workspace_id": "ws-123",
                        "task_id": "task-xyz",
                    },
                    "actor": {"type": "workspace-member", "id": "actor-456"},
                }
            ],
        }
        body_str = json.dumps(payload)

        metadata = extract_attio_webhook_metadata({}, body_str)

        assert metadata["task_id"] == "task-xyz"

    def test_handles_invalid_json_gracefully(self):
        """Test that invalid JSON doesn't crash, returns basic metadata."""
        body_str = "not valid json {{{"

        metadata = extract_attio_webhook_metadata({}, body_str)

        assert metadata["payload_size"] == len(body_str)
        assert "parse_error" in metadata

    def test_handles_empty_events_array_gracefully(self):
        """Test that empty events array doesn't crash."""
        payload = {"webhook_id": "webhook-123", "events": []}
        body_str = json.dumps(payload)

        metadata = extract_attio_webhook_metadata({}, body_str)

        assert metadata["webhook_id"] == "webhook-123"
        assert metadata["event_count"] == 0
        # Should not have event-specific fields
        assert "event_type" not in metadata
        assert "workspace_id" not in metadata

    def test_full_webhook_payload(self):
        """Test extraction from a complete realistic webhook payload following Attio's actual structure."""
        payload = {
            "webhook_id": "dd6b29bb-16a7-47b3-8deb-bddf5a4a64a1",
            "events": [
                {
                    "event_type": "record.updated",
                    "id": {
                        "workspace_id": "50cf242c-7fa3-4cad-87d0-75b1af71c57b",
                        "object_id": "deals",
                        "record_id": "deal-789",
                        "attribute_id": "attr-123",
                    },
                    "actor": {"type": "workspace-member", "id": "member-456"},
                }
            ],
        }
        body_str = json.dumps(payload)

        metadata = extract_attio_webhook_metadata({}, body_str)

        assert metadata["webhook_id"] == "dd6b29bb-16a7-47b3-8deb-bddf5a4a64a1"
        assert metadata["event_count"] == 1
        assert metadata["event_type"] == "record.updated"
        assert metadata["workspace_id"] == "50cf242c-7fa3-4cad-87d0-75b1af71c57b"
        assert metadata["actor_type"] == "workspace-member"
        assert metadata["actor_id"] == "member-456"
        assert metadata["object_type"] == "deals"
        assert metadata["record_id"] == "deal-789"
        assert metadata["attribute_id"] == "attr-123"


class TestAttioWebhookVerifier:
    """Test suite for AttioWebhookVerifier class."""

    def test_verifier_has_correct_source_type(self):
        """Test that verifier uses 'attio' as source_type."""
        verifier = AttioWebhookVerifier()
        assert verifier.source_type == "attio"

    def test_verifier_inherits_from_base(self):
        """Test that verifier inherits from BaseSigningSecretVerifier."""
        verifier = AttioWebhookVerifier()
        assert isinstance(verifier, BaseSigningSecretVerifier)

    def test_verifier_is_registered(self):
        """Test that Attio verifier is in the verifier registry."""
        verifier = get_verifier(WebhookSourceType.ATTIO)
        assert verifier is not None
        assert isinstance(verifier, AttioWebhookVerifier)

    @pytest.mark.asyncio
    async def test_verifier_fails_without_signing_secret(self):
        """Test that verification fails when SSM returns no signing secret."""
        verifier = AttioWebhookVerifier()

        with patch.object(verifier.ssm_client, "get_signing_secret", AsyncMock(return_value=None)):
            result = await verifier.verify(
                headers={"attio-signature": "test"},
                body=b'{"event_type": "record.created"}',
                tenant_id="test-tenant",
            )

        assert result.success is False
        assert result.error is not None
        assert "signing secret" in result.error.lower()
        assert "test-tenant" in result.error

    @pytest.mark.asyncio
    async def test_verifier_succeeds_with_valid_signature(self):
        """Test that verification succeeds with valid signature."""
        verifier = AttioWebhookVerifier()
        secret = "test-secret-123"
        body = b'{"event_type": "record.created", "data": {}}'

        # Calculate valid signature
        valid_signature = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()

        with patch.object(
            verifier.ssm_client, "get_signing_secret", AsyncMock(return_value=secret)
        ):
            result = await verifier.verify(
                headers={"attio-signature": valid_signature},
                body=body,
                tenant_id="test-tenant",
            )

        assert result.success is True
        assert result.error is None

    @pytest.mark.asyncio
    async def test_verifier_fails_with_invalid_signature(self):
        """Test that verification fails with invalid signature."""
        verifier = AttioWebhookVerifier()

        with patch.object(
            verifier.ssm_client,
            "get_signing_secret",
            AsyncMock(return_value="test-secret"),
        ):
            result = await verifier.verify(
                headers={"attio-signature": "invalid_signature"},
                body=b'{"event_type": "record.created"}',
                tenant_id="test-tenant",
            )

        assert result.success is False
        assert result.error is not None

    @pytest.mark.asyncio
    async def test_verifier_fetches_secret_with_correct_source_type(self):
        """Test that the verifier fetches secret using 'attio' source type."""
        verifier = AttioWebhookVerifier()
        mock_get_secret = AsyncMock(return_value=None)

        with patch.object(verifier.ssm_client, "get_signing_secret", mock_get_secret):
            await verifier.verify(
                headers={"attio-signature": "test"},
                body=b"test",
                tenant_id="tenant-xyz",
            )

        mock_get_secret.assert_called_once_with("tenant-xyz", "attio")


class TestAttioInHandlerVerificationTests:
    """Integration tests to ensure Attio is included in handler verification tests."""

    @pytest.mark.asyncio
    async def test_attio_handler_fails_without_signing_secret(self):
        """Test that Attio handler fails when no signing secret is configured."""
        verifier = get_verifier(WebhookSourceType.ATTIO)
        assert verifier is not None

        base_verifier = cast(BaseSigningSecretVerifier, verifier)

        with patch.object(
            base_verifier.ssm_client, "get_signing_secret", AsyncMock(return_value=None)
        ):
            result = await verifier.verify(
                headers={"attio-signature": "test"},
                body=b'{"test": "data"}',
                tenant_id="test-tenant",
            )

        assert result.success is False
        assert result.error is not None
        assert "signing secret" in result.error.lower()

    @pytest.mark.asyncio
    async def test_attio_handler_fails_with_invalid_signature(self):
        """Test that Attio handler fails with invalid signatures."""
        verifier = get_verifier(WebhookSourceType.ATTIO)
        assert verifier is not None

        base_verifier = cast(BaseSigningSecretVerifier, verifier)

        with patch.object(
            base_verifier.ssm_client,
            "get_signing_secret",
            AsyncMock(return_value="test-secret"),
        ):
            result = await verifier.verify(
                headers={"attio-signature": "invalid"},
                body=b'{"test": "data"}',
                tenant_id="test-tenant",
            )

        assert result.success is False
