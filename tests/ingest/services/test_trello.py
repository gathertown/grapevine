"""Tests for Trello webhook signature verification and utilities.

This module tests Trello-specific webhook functionality including:
- HMAC-SHA1 signature verification with callback URL
- Callback URL construction for different environments
- Error handling for invalid signatures
"""

import base64
import hashlib
import hmac
from unittest.mock import patch

import pytest

from connectors.trello import get_trello_webhook_callback_url, verify_trello_webhook


class TestTrelloWebhookCallbackURL:
    """Test suite for Trello webhook callback URL construction."""

    @patch("src.utils.config.get_base_domain")
    def test_callback_url_production(self, mock_get_domain):
        """Test callback URL construction for production environment.

        Production uses BASE_DOMAIN=example.com
        Result: https://{tenant}.ingest.example.com/webhooks/trello
        """
        mock_get_domain.return_value = "example.com"
        tenant_id = "abc123def456"

        url = get_trello_webhook_callback_url(tenant_id)

        assert url == f"https://{tenant_id}.ingest.example.com/webhooks/trello"

    @patch("src.utils.config.get_base_domain")
    def test_callback_url_staging(self, mock_get_domain):
        """Test callback URL construction for staging environment.

        Staging uses BASE_DOMAIN=stg.example.com
        Result: https://{tenant}.ingest.stg.example.com/webhooks/trello
        """
        mock_get_domain.return_value = "stg.example.com"
        tenant_id = "abc123def456"

        url = get_trello_webhook_callback_url(tenant_id)

        assert url == f"https://{tenant_id}.ingest.stg.example.com/webhooks/trello"

    @patch("src.utils.config.get_base_domain")
    def test_callback_url_development(self, mock_get_domain):
        """Test callback URL construction for development environment.

        Development uses BASE_DOMAIN=localhost
        Result: https://{tenant}.ingest.localhost/webhooks/trello
        """
        mock_get_domain.return_value = "localhost"
        tenant_id = "abc123def456"

        url = get_trello_webhook_callback_url(tenant_id)

        assert url == f"https://{tenant_id}.ingest.localhost/webhooks/trello"

    @patch("src.utils.config.get_base_domain")
    def test_callback_url_different_tenant_ids(self, mock_get_domain):
        """Test callback URL construction with different tenant IDs."""
        mock_get_domain.return_value = "example.com"

        url1 = get_trello_webhook_callback_url("tenant123")
        url2 = get_trello_webhook_callback_url("tenant456")

        assert "tenant123" in url1
        assert "tenant456" in url2
        assert url1 != url2


class TestTrelloWebhookSignatureVerification:
    """Test suite for Trello webhook signature verification."""

    def _generate_valid_signature(self, callback_url: str, body: bytes, secret: str) -> str:
        """Helper to generate a valid Trello webhook signature.

        Args:
            callback_url: The webhook callback URL
            body: The request body
            secret: The signing secret

        Returns:
            Base64-encoded HMAC-SHA1 signature
        """
        body_str = body.decode("utf-8")
        content = body_str + callback_url
        signature_bytes = hmac.new(secret.encode(), content.encode(), hashlib.sha1).digest()
        return base64.b64encode(signature_bytes).decode()

    @patch("connectors.trello.trello_webhook_handler.get_trello_webhook_callback_url")
    def test_valid_signature_passes(self, mock_callback_url):
        """Test that a valid signature passes verification."""
        tenant_id = "test-tenant-123"
        callback_url = "https://test-tenant-123.ingest.example.com/webhooks/trello"
        secret = "test-secret-key"
        body = b'{"action": {"type": "createCard"}}'

        mock_callback_url.return_value = callback_url

        # Generate valid signature
        valid_signature = self._generate_valid_signature(callback_url, body, secret)
        headers = {"x-trello-webhook": valid_signature}

        # Should not raise any exception
        verify_trello_webhook(headers, body, tenant_id, secret)

    @patch("connectors.trello.trello_webhook_handler.get_trello_webhook_callback_url")
    def test_invalid_signature_fails(self, mock_callback_url):
        """Test that an invalid signature raises ValueError."""
        tenant_id = "test-tenant-123"
        callback_url = "https://test-tenant-123.ingest.example.com/webhooks/trello"
        secret = "test-secret-key"
        body = b'{"action": {"type": "createCard"}}'

        mock_callback_url.return_value = callback_url

        # Use wrong signature
        headers = {"x-trello-webhook": "invalid-signature-abc123"}

        with pytest.raises(ValueError, match="Invalid Trello webhook signature"):
            verify_trello_webhook(headers, body, tenant_id, secret)

    @patch("connectors.trello.trello_webhook_handler.get_trello_webhook_callback_url")
    def test_missing_signature_header_fails(self, mock_callback_url):
        """Test that missing signature header raises ValueError."""
        tenant_id = "test-tenant-123"
        callback_url = "https://test-tenant-123.ingest.example.com/webhooks/trello"
        secret = "test-secret-key"
        body = b'{"action": {"type": "createCard"}}'

        mock_callback_url.return_value = callback_url

        # Missing x-trello-webhook header
        headers: dict[str, str] = {}

        with pytest.raises(ValueError, match="Missing Trello webhook signature header"):
            verify_trello_webhook(headers, body, tenant_id, secret)

    @patch("connectors.trello.trello_webhook_handler.get_trello_webhook_callback_url")
    def test_empty_signature_header_fails(self, mock_callback_url):
        """Test that empty signature header raises ValueError."""
        tenant_id = "test-tenant-123"
        callback_url = "https://test-tenant-123.ingest.example.com/webhooks/trello"
        secret = "test-secret-key"
        body = b'{"action": {"type": "createCard"}}'

        mock_callback_url.return_value = callback_url

        # Empty signature
        headers = {"x-trello-webhook": ""}

        with pytest.raises(ValueError, match="Missing Trello webhook signature header"):
            verify_trello_webhook(headers, body, tenant_id, secret)

    def test_missing_secret_fails(self):
        """Test that missing secret raises ValueError."""
        tenant_id = "test-tenant-123"
        body = b'{"action": {"type": "createCard"}}'
        headers = {"x-trello-webhook": "some-signature"}

        with pytest.raises(
            ValueError, match="Trello Power-Up OAuth secret is required for webhook verification"
        ):
            verify_trello_webhook(headers, body, tenant_id, "")

    @patch("connectors.trello.trello_webhook_handler.get_trello_webhook_callback_url")
    def test_signature_with_different_body_fails(self, mock_callback_url):
        """Test that signature is validated against the actual body content."""
        tenant_id = "test-tenant-123"
        callback_url = "https://test-tenant-123.ingest.example.com/webhooks/trello"
        secret = "test-secret-key"
        original_body = b'{"action": {"type": "createCard"}}'
        different_body = b'{"action": {"type": "deleteCard"}}'

        mock_callback_url.return_value = callback_url

        # Generate signature for original body
        valid_signature = self._generate_valid_signature(callback_url, original_body, secret)
        headers = {"x-trello-webhook": valid_signature}

        # Verify with different body should fail
        with pytest.raises(ValueError, match="Invalid Trello webhook signature"):
            verify_trello_webhook(headers, different_body, tenant_id, secret)

    @patch("connectors.trello.trello_webhook_handler.get_trello_webhook_callback_url")
    def test_signature_with_different_callback_url_fails(self, mock_callback_url):
        """Test that signature verification uses the constructed callback URL."""
        tenant_id = "test-tenant-123"
        wrong_callback_url = "https://wrong-url.com/webhooks/trello"
        correct_callback_url = "https://test-tenant-123.ingest.example.com/webhooks/trello"
        secret = "test-secret-key"
        body = b'{"action": {"type": "createCard"}}'

        # Generate signature with wrong callback URL
        wrong_signature = self._generate_valid_signature(wrong_callback_url, body, secret)
        headers = {"x-trello-webhook": wrong_signature}

        # Mock returns correct callback URL (different from what was used to sign)
        mock_callback_url.return_value = correct_callback_url

        # Should fail because callback URL mismatch
        with pytest.raises(ValueError, match="Invalid Trello webhook signature"):
            verify_trello_webhook(headers, body, tenant_id, secret)

    @patch("connectors.trello.trello_webhook_handler.get_trello_webhook_callback_url")
    def test_signature_case_sensitive(self, mock_callback_url):
        """Test that signature verification is case-sensitive."""
        tenant_id = "test-tenant-123"
        callback_url = "https://test-tenant-123.ingest.example.com/webhooks/trello"
        secret = "test-secret-key"
        body = b'{"action": {"type": "createCard"}}'

        mock_callback_url.return_value = callback_url

        # Generate valid signature
        valid_signature = self._generate_valid_signature(callback_url, body, secret)

        # Change case of one character
        invalid_signature = valid_signature[0].swapcase() + valid_signature[1:]
        headers = {"x-trello-webhook": invalid_signature}

        with pytest.raises(ValueError, match="Invalid Trello webhook signature"):
            verify_trello_webhook(headers, body, tenant_id, secret)

    @patch("connectors.trello.trello_webhook_handler.get_trello_webhook_callback_url")
    def test_signature_with_special_characters_in_body(self, mock_callback_url):
        """Test signature verification with special characters in body."""
        tenant_id = "test-tenant-123"
        callback_url = "https://test-tenant-123.ingest.example.com/webhooks/trello"
        secret = "test-secret-key"
        body = (
            b'{"name": "Test \xe2\x9c\x93 Card", "desc": "Special: \xc2\xa9\xc2\xae\xe2\x84\xa2"}'
        )

        mock_callback_url.return_value = callback_url

        # Generate valid signature
        valid_signature = self._generate_valid_signature(callback_url, body, secret)
        headers = {"x-trello-webhook": valid_signature}

        # Should handle special characters correctly
        verify_trello_webhook(headers, body, tenant_id, secret)

    @patch("connectors.trello.trello_webhook_handler.get_trello_webhook_callback_url")
    def test_signature_with_empty_body(self, mock_callback_url):
        """Test signature verification with empty body."""
        tenant_id = "test-tenant-123"
        callback_url = "https://test-tenant-123.ingest.example.com/webhooks/trello"
        secret = "test-secret-key"
        body = b""

        mock_callback_url.return_value = callback_url

        # Generate valid signature for empty body
        valid_signature = self._generate_valid_signature(callback_url, body, secret)
        headers = {"x-trello-webhook": valid_signature}

        # Should work with empty body
        verify_trello_webhook(headers, body, tenant_id, secret)


class TestTrelloWebhookSignatureAlgorithm:
    """Test suite verifying Trello's specific signature algorithm."""

    @patch("connectors.trello.trello_webhook_handler.get_trello_webhook_callback_url")
    def test_signature_includes_callback_url(self, mock_callback_url):
        """Test that Trello signature algorithm includes callback URL in signed data.

        Trello signature: base64(HMAC-SHA1(secret, body + callback_url))
        """
        tenant_id = "test-tenant"
        callback_url = "https://test-tenant.ingest.example.com/webhooks/trello"
        secret = "secret123"
        body = b'{"test": "data"}'

        mock_callback_url.return_value = callback_url

        # Manually compute signature using Trello's algorithm
        body_str = body.decode("utf-8")
        content = body_str + callback_url
        expected_signature = base64.b64encode(
            hmac.new(secret.encode(), content.encode(), hashlib.sha1).digest()
        ).decode()

        headers = {"x-trello-webhook": expected_signature}

        # Should verify successfully
        verify_trello_webhook(headers, body, tenant_id, secret)

    @patch("connectors.trello.trello_webhook_handler.get_trello_webhook_callback_url")
    def test_signature_order_matters(self, mock_callback_url):
        """Test that the order of body + callback_url matters."""
        tenant_id = "test-tenant"
        callback_url = "https://test-tenant.ingest.example.com/webhooks/trello"
        secret = "secret123"
        body = b'{"test": "data"}'

        mock_callback_url.return_value = callback_url

        # Try using callback_url + body (WRONG order - should be body + callback_url)
        body_str = body.decode("utf-8")
        wrong_content = callback_url + body_str  # Wrong order!
        wrong_signature = base64.b64encode(
            hmac.new(secret.encode(), wrong_content.encode(), hashlib.sha1).digest()
        ).decode()

        headers = {"x-trello-webhook": wrong_signature}

        # Should fail because order is wrong
        with pytest.raises(ValueError, match="Invalid Trello webhook signature"):
            verify_trello_webhook(headers, body, tenant_id, secret)

    @patch("connectors.trello.trello_webhook_handler.get_trello_webhook_callback_url")
    def test_signature_base64_encoded(self, mock_callback_url):
        """Test that signature is base64-encoded."""
        tenant_id = "test-tenant"
        callback_url = "https://test-tenant.ingest.example.com/webhooks/trello"
        secret = "secret123"
        body = b'{"test": "data"}'

        mock_callback_url.return_value = callback_url

        # Use hex-encoded bytes instead of base64 (invalid format)
        body_str = body.decode("utf-8")
        content = body_str + callback_url
        raw_signature_bytes = hmac.new(secret.encode(), content.encode(), hashlib.sha1).digest()
        # Convert to hex instead of base64
        hex_signature = raw_signature_bytes.hex()

        headers = {"x-trello-webhook": hex_signature}

        # Should fail because not base64-encoded (it's hex-encoded)
        with pytest.raises(ValueError, match="Invalid Trello webhook signature"):
            verify_trello_webhook(headers, body, tenant_id, secret)
