"""Tests for webhook error code handling in gatekeeper service.

This module tests that the gatekeeper returns appropriate HTTP status codes
for different error conditions when processing webhooks.

Since handlers now call verifiers directly (not via WebhookProcessor.verify_webhook),
we mock the verifiers at the module level to control verification behavior.
"""

from unittest.mock import AsyncMock, Mock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.ingest.gatekeeper.services.webhook_processor import WebhookProcessor
from src.ingest.gatekeeper.verification import VerificationResult


@pytest.fixture
def mock_webhook_processor():
    """Create a mock webhook processor (for SSM client access)."""
    processor = Mock(spec=WebhookProcessor)
    processor.ssm_client = Mock()
    return processor


@pytest.fixture
def mock_sqs_client():
    """Create a mock SQS client."""
    client = Mock()
    client.send_ingest_webhook_message = AsyncMock(return_value="msg-12345")
    client.send_slackbot_webhook_message = AsyncMock(return_value="msg-67890")
    return client


@pytest.fixture
def test_app(mock_webhook_processor, mock_sqs_client):
    """Create test app with mocked dependencies."""
    test_app = FastAPI()

    # Import routes after app creation to avoid circular imports
    from src.ingest.gatekeeper.routes import router

    test_app.include_router(router)

    # Set up app state
    test_app.state.webhook_processor = mock_webhook_processor
    test_app.state.sqs_client = mock_sqs_client
    test_app.state.dangerously_disable_webhook_validation = False

    return test_app


@pytest.fixture
def client(test_app):
    """Create test client."""
    return TestClient(test_app)


class TestWebhookErrorCodes:
    """Test suite for webhook error code handling."""

    def test_missing_signing_secret_returns_400(self, client):
        """Test that missing signing secret returns 400 Bad Request."""
        # Mock the Linear verifier to return failure with missing signing secret
        with patch(
            "src.ingest.gatekeeper.webhook_handlers.LinearWebhookVerifier"
        ) as mock_verifier_class:
            mock_verifier = Mock()
            mock_verifier.verify = AsyncMock(
                return_value=VerificationResult(
                    success=False,
                    error="No signing secret configured for tenant test-tenant",
                )
            )
            mock_verifier_class.return_value = mock_verifier

            response = client.post(
                "/test-tenant/webhooks/linear",
                json={"action": "create", "type": "Issue"},
            )

            # Should return 400 Bad Request (misconfiguration issue)
            assert response.status_code == 400
            assert "signing secret" in response.json()["detail"].lower()

    def test_signature_verification_failed_returns_401(self, client):
        """Test that signature verification failure returns 401 Unauthorized."""
        # Mock the Linear verifier to return failure with signature error
        with patch(
            "src.ingest.gatekeeper.webhook_handlers.LinearWebhookVerifier"
        ) as mock_verifier_class:
            mock_verifier = Mock()
            mock_verifier.verify = AsyncMock(
                return_value=VerificationResult(
                    success=False,
                    error="Invalid Linear webhook signature",
                )
            )
            mock_verifier_class.return_value = mock_verifier

            response = client.post(
                "/test-tenant/webhooks/linear",
                json={"action": "create", "type": "Issue"},
            )

            # Should return 401 Unauthorized
            assert response.status_code == 401
            assert "signature" in response.json()["detail"].lower()

    def test_valid_tenant_id_format_accepted(self, client):
        """Test that valid tenant ID formats are accepted."""
        # The tenant_id format validation (validate_tenant_id) accepts
        # alphanumeric characters, hyphens, and underscores
        with patch(
            "src.ingest.gatekeeper.webhook_handlers.LinearWebhookVerifier"
        ) as mock_verifier_class:
            mock_verifier = Mock()
            mock_verifier.verify = AsyncMock(return_value=VerificationResult(success=True))
            mock_verifier_class.return_value = mock_verifier

            # Valid tenant IDs should be accepted
            for tenant_id in ["test-tenant", "tenant_123", "abc123def456"]:
                response = client.post(
                    f"/{tenant_id}/webhooks/linear",
                    json={"action": "create", "type": "Issue"},
                )

                # Should return 200 OK (tenant format is valid)
                assert response.status_code == 200, f"Failed for tenant_id: {tenant_id}"

    def test_invalid_tenant_id_format_returns_400(self, client):
        """Test that invalid tenant ID format returns 400 Bad Request."""
        # Send webhook request with invalid tenant ID format in Host header
        response = client.post(
            "/webhooks/linear",
            json={"action": "create", "type": "Issue"},
            headers={"Host": "invalid!tenant@id.webhooks.example.com"},
        )

        # Should return 400 Bad Request
        assert response.status_code == 400
        assert "tenant" in response.json()["detail"].lower()

    def test_generic_verification_failure_returns_400(self, client):
        """Test that generic verification failure returns 400 Bad Request."""
        # Mock the Linear verifier to return generic failure
        with patch(
            "src.ingest.gatekeeper.webhook_handlers.LinearWebhookVerifier"
        ) as mock_verifier_class:
            mock_verifier = Mock()
            mock_verifier.verify = AsyncMock(
                return_value=VerificationResult(
                    success=False,
                    error="Invalid webhook payload format",
                )
            )
            mock_verifier_class.return_value = mock_verifier

            response = client.post(
                "/test-tenant/webhooks/linear",
                json={"action": "create", "type": "Issue"},
            )

            # Should return 400 Bad Request for generic errors
            assert response.status_code == 400

    def test_successful_webhook_returns_200(self, client):
        """Test that successful webhook processing returns 200 OK."""
        # Mock the Linear verifier to return success
        with patch(
            "src.ingest.gatekeeper.webhook_handlers.LinearWebhookVerifier"
        ) as mock_verifier_class:
            mock_verifier = Mock()
            mock_verifier.verify = AsyncMock(return_value=VerificationResult(success=True))
            mock_verifier_class.return_value = mock_verifier

            response = client.post(
                "/test-tenant/webhooks/linear",
                json={"action": "create", "type": "Issue"},
            )

            # Should return 200 OK
            assert response.status_code == 200
            assert response.json()["success"] is True


class TestWebhookErrorCodesAllSources:
    """Test error codes across different webhook sources."""

    @pytest.mark.parametrize(
        "endpoint,webhook_body,verifier_path",
        [
            (
                "github",
                {"action": "opened", "pull_request": {}},
                "src.ingest.gatekeeper.webhook_handlers.GitHubWebhookVerifier",
            ),
            (
                "slack",
                {"type": "event_callback", "event": {}},
                "src.ingest.gatekeeper.webhook_handlers.SlackWebhookVerifier",
            ),
            (
                "linear",
                {"action": "create", "type": "Issue"},
                "src.ingest.gatekeeper.webhook_handlers.LinearWebhookVerifier",
            ),
            (
                "notion",
                {"type": "page", "data": {}},
                "src.ingest.gatekeeper.webhook_handlers.NotionWebhookVerifier",
            ),
        ],
    )
    def test_missing_signing_secret_returns_400_all_sources(
        self, client, endpoint, webhook_body, verifier_path
    ):
        """Test that missing signing secret returns 400 for all webhook sources."""
        with patch(verifier_path) as mock_verifier_class:
            mock_verifier = Mock()
            mock_verifier.verify = AsyncMock(
                return_value=VerificationResult(
                    success=False,
                    error="No signing secret configured for tenant test-tenant",
                )
            )
            mock_verifier_class.return_value = mock_verifier

            response = client.post(
                f"/test-tenant/webhooks/{endpoint}",
                json=webhook_body,
            )

            # Should return 400 Bad Request for all sources
            assert response.status_code == 400
            assert "signing secret" in response.json()["detail"].lower()

    @pytest.mark.parametrize(
        "endpoint,webhook_body,verifier_path",
        [
            (
                "github",
                {"action": "opened", "pull_request": {}},
                "src.ingest.gatekeeper.webhook_handlers.GitHubWebhookVerifier",
            ),
            (
                "slack",
                {"type": "event_callback", "event": {}},
                "src.ingest.gatekeeper.webhook_handlers.SlackWebhookVerifier",
            ),
            (
                "linear",
                {"action": "create", "type": "Issue"},
                "src.ingest.gatekeeper.webhook_handlers.LinearWebhookVerifier",
            ),
            (
                "notion",
                {"type": "page", "data": {}},
                "src.ingest.gatekeeper.webhook_handlers.NotionWebhookVerifier",
            ),
        ],
    )
    def test_signature_verification_failed_returns_401_all_sources(
        self, client, endpoint, webhook_body, verifier_path
    ):
        """Test that signature verification failure returns 401 for all sources."""
        with patch(verifier_path) as mock_verifier_class:
            mock_verifier = Mock()
            mock_verifier.verify = AsyncMock(
                return_value=VerificationResult(
                    success=False,
                    error="Invalid webhook signature",
                )
            )
            mock_verifier_class.return_value = mock_verifier

            response = client.post(
                f"/test-tenant/webhooks/{endpoint}",
                json=webhook_body,
            )

            # Should return 401 Unauthorized for all sources
            assert response.status_code == 401
            assert "signature" in response.json()["detail"].lower()


class TestWebhookErrorCodesWithTenantInPath:
    """Test error codes for webhook endpoints with tenant ID in URL path."""

    def test_missing_signing_secret_returns_400_tenant_in_path(self, client):
        """Test missing signing secret with tenant ID in URL path."""
        with patch(
            "src.ingest.gatekeeper.webhook_handlers.LinearWebhookVerifier"
        ) as mock_verifier_class:
            mock_verifier = Mock()
            mock_verifier.verify = AsyncMock(
                return_value=VerificationResult(
                    success=False,
                    error="No signing secret configured for tenant test-tenant",
                )
            )
            mock_verifier_class.return_value = mock_verifier

            response = client.post(
                "/test-tenant/webhooks/linear",
                json={"action": "create", "type": "Issue"},
            )

            # Should return 400 Bad Request
            assert response.status_code == 400
            assert "signing secret" in response.json()["detail"].lower()

    def test_successful_webhook_with_tenant_in_path(self, client):
        """Test successful webhook with tenant ID in URL path."""
        with patch(
            "src.ingest.gatekeeper.webhook_handlers.LinearWebhookVerifier"
        ) as mock_verifier_class:
            mock_verifier = Mock()
            mock_verifier.verify = AsyncMock(return_value=VerificationResult(success=True))
            mock_verifier_class.return_value = mock_verifier

            response = client.post(
                "/test-tenant/webhooks/linear",
                json={"action": "create", "type": "Issue"},
            )

            # Should return 200 OK
            assert response.status_code == 200
            assert response.json()["success"] is True


class TestWebhookErrorMessages:
    """Test that error messages are properly returned to clients."""

    def test_error_detail_includes_helpful_message(self, client):
        """Test that error responses include helpful detail messages."""
        error_message = "No signing secret configured for tenant test-tenant"
        with patch(
            "src.ingest.gatekeeper.webhook_handlers.LinearWebhookVerifier"
        ) as mock_verifier_class:
            mock_verifier = Mock()
            mock_verifier.verify = AsyncMock(
                return_value=VerificationResult(
                    success=False,
                    error=error_message,
                )
            )
            mock_verifier_class.return_value = mock_verifier

            response = client.post(
                "/test-tenant/webhooks/linear",
                json={"action": "create", "type": "Issue"},
            )

            # Error message should be in response detail
            assert response.status_code == 400
            assert response.json()["detail"] == error_message

    def test_multiple_error_conditions_return_correct_codes(self, client):
        """Test that different error conditions return their specific status codes."""
        error_test_cases = [
            ("No signing secret configured for tenant", 400),
            ("Invalid webhook signature", 401),
            ("Invalid webhook payload", 400),
        ]

        for error_message, expected_status in error_test_cases:
            with patch(
                "src.ingest.gatekeeper.webhook_handlers.LinearWebhookVerifier"
            ) as mock_verifier_class:
                mock_verifier = Mock()
                mock_verifier.verify = AsyncMock(
                    return_value=VerificationResult(
                        success=False,
                        error=error_message,
                    )
                )
                mock_verifier_class.return_value = mock_verifier

                response = client.post(
                    "/test-tenant/webhooks/linear",
                    json={"action": "create", "type": "Issue"},
                )

                assert response.status_code == expected_status, (
                    f"Expected {expected_status} for error '{error_message}', "
                    f"got {response.status_code}"
                )
