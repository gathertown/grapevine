"""Tests for webhook handler verification behavior.

This module tests:
1. Handlers using BaseSigningSecretVerifier fail appropriately without signing secrets
2. Handlers using BaseSigningSecretVerifier succeed with valid signatures
3. Custom handlers (Gmail, Gong, HubSpot, Trello) have correct verification behavior
4. Unknown source types are handled gracefully
"""

from typing import cast
from unittest.mock import AsyncMock, patch

import pytest

from src.ingest.gatekeeper.verification import BaseSigningSecretVerifier
from src.ingest.gatekeeper.verifier_registry import WebhookSourceType, get_verifier


class TestBaseSigningSecretVerifier:
    """Test the BaseSigningSecretVerifier base class behavior."""

    @pytest.mark.asyncio
    async def test_fails_when_no_signing_secret_configured(self):
        """Test that verification fails when SSM returns no signing secret."""

        # Create a concrete implementation for testing
        class TestVerifier(BaseSigningSecretVerifier):
            source_type = "test_source"
            verify_func = staticmethod(lambda h, b, s: None)  # Would succeed if called

        verifier = TestVerifier()

        with patch.object(verifier.ssm_client, "get_signing_secret", AsyncMock(return_value=None)):
            result = await verifier.verify(
                headers={"x-signature": "test"},
                body=b'{"test": "data"}',
                tenant_id="test-tenant",
            )

        assert result.success is False
        assert result.error is not None
        assert "signing secret" in result.error.lower()
        assert "test-tenant" in result.error

    @pytest.mark.asyncio
    async def test_succeeds_when_verify_func_passes(self):
        """Test that verification succeeds when verify_func doesn't raise."""

        class TestVerifier(BaseSigningSecretVerifier):
            source_type = "test_source"
            verify_func = staticmethod(lambda h, b, s: None)  # Success - no exception

        verifier = TestVerifier()

        with patch.object(
            verifier.ssm_client, "get_signing_secret", AsyncMock(return_value="test-secret")
        ):
            result = await verifier.verify(
                headers={"x-signature": "test"},
                body=b'{"test": "data"}',
                tenant_id="test-tenant",
            )

        assert result.success is True
        assert result.error is None

    @pytest.mark.asyncio
    async def test_fails_when_verify_func_raises_valueerror(self):
        """Test that verification fails when verify_func raises ValueError."""

        def failing_verify(headers, body, secret):
            raise ValueError("Signature mismatch")

        class TestVerifier(BaseSigningSecretVerifier):
            source_type = "test_source"
            verify_func = staticmethod(failing_verify)

        verifier = TestVerifier()

        with patch.object(
            verifier.ssm_client, "get_signing_secret", AsyncMock(return_value="test-secret")
        ):
            result = await verifier.verify(
                headers={"x-signature": "test"},
                body=b'{"test": "data"}',
                tenant_id="test-tenant",
            )

        assert result.success is False
        assert result.error is not None
        assert "Signature mismatch" in result.error

    @pytest.mark.asyncio
    async def test_fetches_signing_secret_with_correct_source_type(self):
        """Test that the correct source_type is passed to SSM."""

        class TestVerifier(BaseSigningSecretVerifier):
            source_type = "my_custom_source"
            verify_func = staticmethod(lambda h, b, s: None)

        verifier = TestVerifier()
        mock_get_secret = AsyncMock(return_value="test-secret")

        with patch.object(verifier.ssm_client, "get_signing_secret", mock_get_secret):
            await verifier.verify(
                headers={},
                body=b"test",
                tenant_id="tenant-123",
            )

        mock_get_secret.assert_called_once_with("tenant-123", "my_custom_source")


class TestSigningSecretHandlers:
    """Test that handlers using signing secrets fail appropriately without them."""

    @pytest.mark.parametrize(
        "source_type",
        [
            WebhookSourceType.GITHUB,
            WebhookSourceType.SLACK,
            WebhookSourceType.LINEAR,
            WebhookSourceType.NOTION,
            WebhookSourceType.JIRA,
            WebhookSourceType.CONFLUENCE,
            WebhookSourceType.GOOGLE_DRIVE,
            WebhookSourceType.GATHER,
            WebhookSourceType.ATTIO,
        ],
    )
    @pytest.mark.asyncio
    async def test_handler_fails_without_signing_secret(self, source_type: WebhookSourceType):
        """Test that HMAC-based handlers fail when no signing secret is configured."""
        verifier = get_verifier(source_type)
        assert verifier is not None

        # These handlers all inherit from BaseSigningSecretVerifier
        base_verifier = cast(BaseSigningSecretVerifier, verifier)

        # Mock SSM to return None (no signing secret)
        with patch.object(
            base_verifier.ssm_client, "get_signing_secret", AsyncMock(return_value=None)
        ):
            result = await verifier.verify(
                headers={"x-signature": "test"},
                body=b'{"test": "data"}',
                tenant_id="test-tenant",
            )

        assert result.success is False
        assert result.error is not None
        assert "signing secret" in result.error.lower()

    @pytest.mark.parametrize(
        "source_type",
        [
            WebhookSourceType.GITHUB,
            WebhookSourceType.SLACK,
            WebhookSourceType.LINEAR,
            WebhookSourceType.NOTION,
            WebhookSourceType.ATTIO,
        ],
    )
    @pytest.mark.asyncio
    async def test_handler_fails_with_invalid_signature(self, source_type: WebhookSourceType):
        """Test that HMAC-based handlers fail with invalid signatures."""
        verifier = get_verifier(source_type)
        assert verifier is not None

        # These handlers all inherit from BaseSigningSecretVerifier
        base_verifier = cast(BaseSigningSecretVerifier, verifier)

        # Mock SSM to return a secret, but signature won't match
        with patch.object(
            base_verifier.ssm_client, "get_signing_secret", AsyncMock(return_value="test-secret")
        ):
            result = await verifier.verify(
                headers={"x-signature": "invalid"},
                body=b'{"test": "data"}',
                tenant_id="test-tenant",
            )

        assert result.success is False
        # Error message varies by handler but should indicate verification failure


class TestGoogleEmailHandler:
    """Test Google Email (Gmail) webhook verification behavior."""

    @pytest.mark.asyncio
    async def test_google_email_uses_jwt_verification(self):
        """Test that google_email uses JWT verification, not signing secret."""
        verifier = get_verifier(WebhookSourceType.GOOGLE_EMAIL)
        assert verifier is not None

        # Gmail verifier should NOT inherit from BaseSigningSecretVerifier
        assert not isinstance(verifier, BaseSigningSecretVerifier)

    @pytest.mark.asyncio
    async def test_google_email_fails_without_authorization_header(self):
        """Test that google_email fails when Authorization header is missing."""
        verifier = get_verifier(WebhookSourceType.GOOGLE_EMAIL)
        assert verifier is not None

        # The simplified Gmail verifier uses JWT verification only (no SSM calls)
        # It should fail when Authorization header is missing
        result = await verifier.verify(
            headers={},  # No Authorization header
            body=b'{"message": {"data": "dGVzdA=="}}',  # Valid Pub/Sub message structure
            tenant_id="test-tenant",
        )

        assert result.success is False
        assert result.error is not None
        assert "Authorization" in result.error


class TestGongHandler:
    """Test Gong webhook verification behavior."""

    @pytest.mark.asyncio
    async def test_gong_uses_jwt_verification(self):
        """Test that Gong uses JWT verification with public key."""
        verifier = get_verifier(WebhookSourceType.GONG)
        assert verifier is not None

        # Gong verifier should NOT inherit from BaseSigningSecretVerifier
        assert not isinstance(verifier, BaseSigningSecretVerifier)

    @pytest.mark.asyncio
    async def test_gong_fails_without_authorization_header(self):
        """Test that Gong fails when Authorization header is missing."""
        verifier = get_verifier(WebhookSourceType.GONG)
        assert verifier is not None

        result = await verifier.verify(
            headers={},  # No Authorization header
            body=b'{"test": "data"}',
            tenant_id="test-tenant",
        )

        assert result.success is False
        assert result.error is not None
        assert "authorization" in result.error.lower()


class TestHubSpotHandler:
    """Test HubSpot webhook verification behavior."""

    @pytest.mark.asyncio
    async def test_hubspot_requires_request_url(self):
        """Test that HubSpot verification requires request_url parameter."""
        verifier = get_verifier(WebhookSourceType.HUBSPOT)
        assert verifier is not None

        # HubSpot requires request_url for signature verification
        result = await verifier.verify(
            headers={"x-hubspot-signature-v3": "test", "x-hubspot-request-timestamp": "123"},
            body=b'{"test": "data"}',
            tenant_id="test-tenant",
            request_url=None,  # Missing required URL
        )

        assert result.success is False
        assert result.error is not None
        assert "request_url" in result.error.lower()

    @pytest.mark.asyncio
    async def test_hubspot_does_not_use_per_tenant_secret(self):
        """Test that HubSpot uses global secret, not per-tenant SSM lookup."""
        verifier = get_verifier(WebhookSourceType.HUBSPOT)

        # HubSpot verifier should NOT inherit from BaseSigningSecretVerifier
        assert not isinstance(verifier, BaseSigningSecretVerifier)


class TestTrelloHandler:
    """Test Trello webhook verification behavior."""

    @pytest.mark.asyncio
    async def test_trello_fails_without_signing_secret(self):
        """Test that Trello fails when no signing secret is configured."""
        verifier = get_verifier(WebhookSourceType.TRELLO)
        assert verifier is not None

        # Trello verifier has ssm_client attribute
        # Mock SSM to return None
        with patch.object(
            verifier,
            "ssm_client",
            AsyncMock(get_signing_secret=AsyncMock(return_value=None)),
        ):
            result = await verifier.verify(
                headers={},
                body=b'{"test": "data"}',
                tenant_id="test-tenant",
            )

        assert result.success is False


class TestUnknownSourceHandling:
    """Test handling of unknown source types."""

    def test_unknown_source_returns_none(self):
        """Test that unknown source types return None from get_verifier."""
        verifier = get_verifier("salesforce")
        assert verifier is None

        verifier = get_verifier("unknown_source_xyz")
        assert verifier is None

    def test_invalid_enum_value_returns_none(self):
        """Test that invalid enum values return None."""
        verifier = get_verifier("not_a_real_source")
        assert verifier is None
