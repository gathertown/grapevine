"""Tests for PermissionsMiddleware authentication flows."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, Mock, patch

import jwt
import pytest
from fastmcp.server.context import Context
from fastmcp.server.middleware import MiddlewareContext
from httpx import Response

from src.mcp.middleware.permissions import PermissionsMiddleware


class SimpleAccessToken:
    def __init__(self, token: str) -> None:
        self.token = token


class SimpleUser:
    def __init__(self, token: str) -> None:
        self.access_token = SimpleAccessToken(token)


class DummyRequest:
    def __init__(self, token: str) -> None:
        self.user = SimpleUser(token)


def create_jwt_token(payload: dict[str, Any]) -> str:
    """Create a JWT token for testing."""
    return jwt.encode(payload, "secret", algorithm="HS256")


@pytest.fixture
def middleware():
    """Create PermissionsMiddleware instance."""
    return PermissionsMiddleware()


@pytest.fixture
def mock_context():
    """Create mock FastMCP context."""
    context = Mock(spec=Context)
    context.get_state = Mock()
    context.set_state = Mock()
    return context


@pytest.fixture
def middleware_context(mock_context):
    """Create mock middleware context."""
    mw_context = Mock(spec=MiddlewareContext)
    mw_context.fastmcp_context = mock_context
    return mw_context


@pytest.fixture
def mock_call_next():
    """Create mock call_next function."""
    return AsyncMock(return_value="next_result")


class TestPermissionsMiddleware:
    """Test PermissionsMiddleware functionality."""

    @pytest.mark.asyncio
    async def test_no_context_passes_through(self, middleware, middleware_context, mock_call_next):
        """Test that requests without context pass through unchanged."""
        middleware_context.fastmcp_context = None

        result = await middleware.on_call_tool(middleware_context, mock_call_next)

        assert result == "next_result"
        mock_call_next.assert_called_once_with(middleware_context)

    @pytest.mark.asyncio
    async def test_no_email_logs_debug_message(
        self, middleware, middleware_context, mock_call_next, mock_context
    ):
        """Test that when no email is found, debug message is logged."""
        with (
            patch.object(middleware, "_get_principal_email", return_value=None),
            patch.object(middleware, "_extract_jwt_audience", return_value=None),
            patch("src.mcp.middleware.permissions.logger") as mock_logger,
        ):
            result = await middleware.on_call_tool(middleware_context, mock_call_next)

            assert result == "next_result"
            mock_logger.debug.assert_any_call("PermissionsMiddleware - No principal email found")
            # Should still set permission_audience even without email
            mock_context.set_state.assert_called_with("permission_audience", None)

    @pytest.mark.asyncio
    async def test_email_creates_permission_token(
        self, middleware, middleware_context, mock_call_next, mock_context
    ):
        """Test that when email is found, permission token is created."""
        test_email = "test@example.com"

        with (
            patch.object(middleware, "_get_principal_email", return_value=test_email),
            patch.object(middleware, "_extract_jwt_audience", return_value=None),
            patch("src.mcp.middleware.permissions.make_email_permission_token") as mock_make_token,
        ):
            mock_make_token.return_value = "e:test@example.com"

            result = await middleware.on_call_tool(middleware_context, mock_call_next)

            assert result == "next_result"
            mock_make_token.assert_called_once_with(test_email)
            # Should set both token and audience
            assert mock_context.set_state.call_count == 2
            mock_context.set_state.assert_any_call(
                "permission_principal_token", "e:test@example.com"
            )
            mock_context.set_state.assert_any_call("permission_audience", None)

    @pytest.mark.asyncio
    async def test_permission_token_creation_error(
        self, middleware, middleware_context, mock_call_next, mock_context
    ):
        """Test error handling when permission token creation fails."""
        test_email = "test@example.com"

        with (
            patch.object(middleware, "_get_principal_email", return_value=test_email),
            patch.object(middleware, "_extract_jwt_audience", return_value=None),
            patch(
                "src.mcp.middleware.permissions.make_email_permission_token",
                side_effect=Exception("Token error"),
            ),
            patch("src.mcp.middleware.permissions.logger") as mock_logger,
        ):
            result = await middleware.on_call_tool(middleware_context, mock_call_next)

            assert result == "next_result"
            mock_logger.warning.assert_called_with(
                "PermissionsMiddleware - Error creating permission token: Token error"
            )
            # Should still set permission_audience even if token creation fails
            mock_context.set_state.assert_called_once_with("permission_audience", None)


class TestSlackBotJWTExtraction:
    """Test Slack bot JWT email extraction."""

    def test_jwt_claims_extraction_success(self, middleware, monkeypatch):
        """Test successful JWT claims extraction."""
        payload = {"email": "slackbot@example.com", "tenant_id": "tn_123"}
        token = create_jwt_token(payload)
        request = DummyRequest(token)

        monkeypatch.setattr("src.mcp.middleware.permissions.get_http_request", lambda: request)

        result = middleware._extract_jwt_claims()

        assert result == payload

    def test_jwt_claims_extraction_error(self, middleware):
        """Test JWT claims extraction error handling."""
        with (
            patch(
                "src.mcp.middleware.permissions.get_http_request",
                side_effect=Exception("Request error"),
            ),
            patch("src.mcp.middleware.permissions.logger") as mock_logger,
        ):
            result = middleware._extract_jwt_claims()

            assert result is None
            mock_logger.warning.assert_called_with(
                "PermissionsMiddleware - Error getting JWT claims: Request error"
            )

    def test_slackbot_email_extraction_success(self, middleware):
        """Test successful Slack bot email extraction from claims."""
        claims = {"email": "slackbot@example.com", "tenant_id": "tn_123"}

        result = middleware._extract_slackbot_email(claims)

        assert result == "slackbot@example.com"

    def test_slackbot_email_extraction_no_email(self, middleware):
        """Test Slack bot email extraction when no email in claims."""
        claims = {"tenant_id": "tn_123"}  # No email

        result = middleware._extract_slackbot_email(claims)

        assert result is None

    @pytest.mark.asyncio
    async def test_jwt_email_prioritizes_slackbot_over_workos(self, middleware):
        """Test that Slack bot email is prioritized over WorkOS lookup."""
        claims = {"email": "slackbot@example.com", "sub": "workos_user_123"}

        with (
            patch.object(middleware, "_extract_jwt_claims", return_value=claims),
            patch.object(
                middleware, "_extract_slackbot_email", return_value="slackbot@example.com"
            ),
            patch.object(middleware, "_fetch_workos_email") as mock_workos,
        ):
            result = await middleware._extract_jwt_email()

            assert result == "slackbot@example.com"
            mock_workos.assert_not_called()  # Should not call WorkOS if Slack bot email found


class TestWorkOSEmailExtraction:
    """Test WorkOS email extraction via API."""

    @pytest.mark.asyncio
    async def test_workos_email_extraction_success(self, middleware):
        """Test successful WorkOS email extraction."""
        claims = {"sub": "workos_user_123"}

        mock_response = Mock(spec=Response)
        mock_response.status_code = 200
        mock_response.json.return_value = {"email": "workos@example.com"}

        with (
            patch("src.mcp.middleware.permissions.get_config_value", return_value="test_api_key"),
            patch("httpx.AsyncClient") as mock_client,
        ):
            mock_client.return_value.__aenter__.return_value.get.return_value = mock_response

            result = await middleware._fetch_workos_email(claims)

            assert result == "workos@example.com"

    @pytest.mark.asyncio
    async def test_workos_email_extraction_no_user_id(self, middleware):
        """Test WorkOS email extraction when no sub claim."""
        claims = {"tenant_id": "tn_123"}  # No sub

        result = await middleware._fetch_workos_email(claims)

        assert result is None

    @pytest.mark.asyncio
    async def test_workos_email_extraction_no_api_key(self, middleware):
        """Test WorkOS email extraction when API key not configured."""
        claims = {"sub": "workos_user_123"}

        with (
            patch("src.mcp.middleware.permissions.get_config_value", return_value=None),
            patch("src.mcp.middleware.permissions.logger") as mock_logger,
        ):
            result = await middleware._fetch_workos_email(claims)

            assert result is None
            mock_logger.warning.assert_called_with(
                "PermissionsMiddleware - WORKOS_API_KEY not configured for email lookup"
            )

    @pytest.mark.asyncio
    async def test_workos_email_extraction_api_error(self, middleware):
        """Test WorkOS email extraction when API returns error."""
        claims = {"sub": "workos_user_123"}

        mock_response = Mock(spec=Response)
        mock_response.status_code = 404
        mock_response.text = "User not found"

        with (
            patch("src.mcp.middleware.permissions.get_config_value", return_value="test_api_key"),
            patch("httpx.AsyncClient") as mock_client,
            patch("src.mcp.middleware.permissions.logger") as mock_logger,
        ):
            mock_client.return_value.__aenter__.return_value.get.return_value = mock_response
            result = await middleware._fetch_workos_email(claims)

            assert result is None
            mock_logger.warning.assert_called_with(
                "PermissionsMiddleware - WorkOS user API error: 404 User not found"
            )

    @pytest.mark.asyncio
    async def test_workos_email_extraction_no_email_in_response(self, middleware):
        """Test WorkOS email extraction when user has no email."""
        claims = {"sub": "workos_user_123"}

        mock_response = Mock(spec=Response)
        mock_response.status_code = 200
        mock_response.json.return_value = {"id": "workos_user_123"}  # No email

        with (
            patch("src.mcp.middleware.permissions.get_config_value", return_value="test_api_key"),
            patch("httpx.AsyncClient") as mock_client,
            patch("src.mcp.middleware.permissions.logger") as mock_logger,
        ):
            mock_client.return_value.__aenter__.return_value.get.return_value = mock_response
            result = await middleware._fetch_workos_email(claims)

            assert result is None
            mock_logger.debug.assert_called_with(
                "PermissionsMiddleware - User has no email in WorkOS"
            )

    @pytest.mark.asyncio
    async def test_workos_email_extraction_http_exception(self, middleware):
        """Test WorkOS email extraction when HTTP request fails."""
        claims = {"sub": "workos_user_123"}

        with (
            patch("src.mcp.middleware.permissions.get_config_value", return_value="test_api_key"),
            patch("httpx.AsyncClient") as mock_client,
            patch("src.mcp.middleware.permissions.logger") as mock_logger,
        ):
            mock_client.return_value.__aenter__.return_value.get.side_effect = Exception(
                "Network error"
            )
            result = await middleware._fetch_workos_email(claims)

            assert result is None
            mock_logger.warning.assert_called_with(
                "PermissionsMiddleware - Error calling WorkOS user API: Network error"
            )


class TestEmailExtractionPriority:
    """Test email extraction priority order."""

    @pytest.mark.asyncio
    async def test_jwt_email_used_when_available(self, middleware, mock_context):
        """Test that JWT email is used when available."""
        with patch.object(
            middleware, "_extract_jwt_email", return_value="jwt@example.com"
        ) as mock_jwt:
            result = await middleware._get_principal_email(mock_context)

            assert result == "jwt@example.com"
            mock_jwt.assert_called_once()

    @pytest.mark.asyncio
    async def test_no_email_from_any_source(self, middleware, mock_context):
        """Test behavior when no email is available from any source."""
        with (
            patch.object(middleware, "_extract_jwt_email", return_value=None),
            patch("src.mcp.middleware.permissions.logger") as mock_logger,
        ):
            result = await middleware._get_principal_email(mock_context)

            assert result is None
            mock_logger.debug.assert_called_with(
                "PermissionsMiddleware - No email found from any authentication source"
            )


class TestIntegrationScenarios:
    """Integration test scenarios for common authentication flows."""

    @pytest.mark.asyncio
    async def test_complete_slackbot_jwt_flow(
        self, middleware, middleware_context, mock_call_next, mock_context, monkeypatch
    ):
        """Test complete flow with Slack bot JWT."""
        payload = {"email": "slackbot@company.com", "tenant_id": "tn_slack"}
        token = create_jwt_token(payload)
        request = DummyRequest(token)

        monkeypatch.setattr("src.mcp.middleware.permissions.get_http_request", lambda: request)

        with patch("src.mcp.middleware.permissions.make_email_permission_token") as mock_make_token:
            mock_make_token.return_value = "e:slackbot@company.com"

            result = await middleware.on_call_tool(middleware_context, mock_call_next)

            assert result == "next_result"
            mock_make_token.assert_called_once_with("slackbot@company.com")
            # Should set both token and audience
            assert mock_context.set_state.call_count == 2
            mock_context.set_state.assert_any_call(
                "permission_principal_token", "e:slackbot@company.com"
            )
            mock_context.set_state.assert_any_call("permission_audience", None)

    @pytest.mark.asyncio
    async def test_complete_workos_flow(
        self, middleware, middleware_context, mock_call_next, mock_context, monkeypatch
    ):
        """Test complete flow with WorkOS user lookup."""
        payload = {"sub": "workos_user_456", "tenant_id": "tn_workos"}
        token = create_jwt_token(payload)
        request = DummyRequest(token)

        monkeypatch.setattr("src.mcp.middleware.permissions.get_http_request", lambda: request)

        # Mock WorkOS API response
        mock_response = Mock(spec=Response)
        mock_response.status_code = 200
        mock_response.json.return_value = {"email": "user@workos.com"}

        with (
            patch("src.mcp.middleware.permissions.get_config_value", return_value="workos_key"),
            patch("httpx.AsyncClient") as mock_client,
            patch("src.mcp.middleware.permissions.make_email_permission_token") as mock_make_token,
        ):
            mock_client.return_value.__aenter__.return_value.get.return_value = mock_response
            mock_make_token.return_value = "e:user@workos.com"

            result = await middleware.on_call_tool(middleware_context, mock_call_next)

            assert result == "next_result"
            mock_make_token.assert_called_once_with("user@workos.com")
            # Should set both token and audience
            assert mock_context.set_state.call_count == 2
            mock_context.set_state.assert_any_call(
                "permission_principal_token", "e:user@workos.com"
            )
            mock_context.set_state.assert_any_call("permission_audience", None)

    @pytest.mark.asyncio
    async def test_service_api_key_flow(
        self, middleware, middleware_context, mock_call_next, mock_context, monkeypatch
    ):
        """Test flow with service API key (no email available)."""
        # JWT with no email or sub claim
        payload = {"service": "internal", "tenant_id": "tn_service"}
        token = create_jwt_token(payload)
        request = DummyRequest(token)

        # No Gather auth context
        mock_context.get_state.return_value = None
        monkeypatch.setattr("src.mcp.middleware.permissions.get_http_request", lambda: request)

        with patch("src.mcp.middleware.permissions.logger") as mock_logger:
            result = await middleware.on_call_tool(middleware_context, mock_call_next)

            assert result == "next_result"
            mock_logger.debug.assert_any_call("PermissionsMiddleware - No principal email found")
            # Should still set permission_audience even without email
            mock_context.set_state.assert_called_once_with("permission_audience", None)
