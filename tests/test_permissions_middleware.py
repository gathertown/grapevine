"""Tests for PermissionsMiddleware permission_audience extraction and enforcement."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastmcp.server.context import Context

from src.mcp.middleware.permissions import PermissionsMiddleware


class TestPermissionsMiddleware:
    """Test PermissionsMiddleware permission_audience extraction."""

    @pytest.fixture
    def middleware(self):
        """Create a PermissionsMiddleware instance."""
        return PermissionsMiddleware()

    @pytest.fixture
    def mock_context(self):
        """Create a mock FastMCP context."""
        context = MagicMock(spec=Context)
        context.set_state = MagicMock()
        context.get_state = MagicMock(return_value=None)
        return context

    @pytest.fixture
    def mock_middleware_context(self, mock_context):
        """Create a mock middleware context."""
        middleware_context = MagicMock()
        middleware_context.fastmcp_context = mock_context
        return middleware_context

    @pytest.fixture
    def mock_call_next(self):
        """Create a mock call_next function."""
        return AsyncMock(return_value={"result": "success"})

    @pytest.mark.asyncio
    async def test_extract_permission_audience_from_jwt(
        self, middleware, mock_middleware_context, mock_call_next
    ):
        """Test that permission_audience is extracted from JWT claims."""
        # Mock JWT with permission_audience
        mock_jwt_token = "mock.jwt.token"
        mock_claims = {
            "email": "test@example.com",
            "permission_audience": "tenant",
        }

        with (
            patch.object(middleware, "_extract_jwt_claims", return_value=mock_claims),
            patch.object(middleware, "_get_principal_email", return_value="test@example.com"),
            patch("src.mcp.middleware.permissions.get_http_request") as mock_get_request,
            patch("src.mcp.middleware.permissions.is_api_key_authentication", return_value=False),
        ):
            mock_user = MagicMock()
            mock_access_token = MagicMock()
            mock_access_token.token = mock_jwt_token
            mock_user.access_token = mock_access_token
            mock_request = MagicMock()
            mock_request.user = mock_user
            mock_get_request.return_value = mock_request

            await middleware.on_call_tool(mock_middleware_context, mock_call_next)

            # Verify permission_audience was set in context
            mock_middleware_context.fastmcp_context.set_state.assert_any_call(
                "permission_audience", "tenant"
            )

    @pytest.mark.asyncio
    async def test_slack_bot_jwt_with_private_audience(
        self, middleware, mock_middleware_context, mock_call_next
    ):
        """Test that Slack bot JWT with private audience is processed correctly."""
        mock_claims = {
            "email": "user@example.com",
            "permission_audience": "private",
        }

        with (
            patch.object(middleware, "_extract_jwt_claims", return_value=mock_claims),
            patch.object(middleware, "_get_principal_email", return_value="user@example.com"),
            patch("src.mcp.middleware.permissions.get_http_request") as mock_get_request,
            patch("src.mcp.middleware.permissions.is_api_key_authentication", return_value=False),
        ):
            mock_user = MagicMock()
            mock_access_token = MagicMock()
            mock_access_token.token = "mock.jwt.token"
            mock_user.access_token = mock_access_token
            mock_request = MagicMock()
            mock_request.user = mock_user
            mock_get_request.return_value = mock_request

            await middleware.on_call_tool(mock_middleware_context, mock_call_next)

            # Verify permission_audience was set to "private"
            mock_middleware_context.fastmcp_context.set_state.assert_any_call(
                "permission_audience", "private"
            )

    @pytest.mark.asyncio
    async def test_no_permission_audience_defaults_to_none(
        self, middleware, mock_middleware_context, mock_call_next
    ):
        """Test that missing permission_audience in JWT defaults to None."""
        mock_claims = {
            "email": "test@example.com",
            # No permission_audience field
        }

        with (
            patch.object(middleware, "_extract_jwt_claims", return_value=mock_claims),
            patch.object(middleware, "_get_principal_email", return_value="test@example.com"),
            patch("src.mcp.middleware.permissions.get_http_request") as mock_get_request,
            patch("src.mcp.middleware.permissions.is_api_key_authentication", return_value=False),
        ):
            mock_user = MagicMock()
            mock_access_token = MagicMock()
            mock_access_token.token = "mock.jwt.token"
            mock_user.access_token = mock_access_token
            mock_request = MagicMock()
            mock_request.user = mock_user
            mock_get_request.return_value = mock_request

            await middleware.on_call_tool(mock_middleware_context, mock_call_next)

            # Verify permission_audience was set to None (no default)
            mock_middleware_context.fastmcp_context.set_state.assert_any_call(
                "permission_audience", None
            )

    @pytest.mark.asyncio
    async def test_api_key_authentication_sets_tenant_audience(
        self, middleware, mock_middleware_context, mock_call_next
    ):
        """Test that API key authentication sets permission_audience to 'tenant' and no principal token."""
        with (
            patch("src.mcp.middleware.permissions.get_http_request") as mock_get_request,
            patch("src.mcp.middleware.permissions.is_api_key_authentication", return_value=True),
        ):
            mock_user = MagicMock()
            mock_access_token = MagicMock()
            mock_access_token.token = "gv_tenant123_abcd1234"
            mock_access_token.client_id = "api-key:tenant123"
            mock_user.access_token = mock_access_token
            mock_request = MagicMock()
            mock_request.user = mock_user
            mock_get_request.return_value = mock_request

            await middleware.on_call_tool(mock_middleware_context, mock_call_next)

            # Verify API key authentication sets tenant-scoped permissions
            mock_middleware_context.fastmcp_context.set_state.assert_any_call(
                "permission_audience", "tenant"
            )
            mock_middleware_context.fastmcp_context.set_state.assert_any_call(
                "permission_principal_token", None
            )

    @pytest.mark.asyncio
    async def test_extract_jwt_audience(self, middleware):
        """Test _extract_jwt_audience correctly extracts audience from JWT."""
        # Test with permission_audience present
        with patch.object(
            middleware,
            "_extract_jwt_claims",
            return_value={"permission_audience": "tenant"},
        ):
            audience = middleware._extract_jwt_audience()
            assert audience == "tenant"

        # Test with no permission_audience
        with patch.object(
            middleware, "_extract_jwt_claims", return_value={"email": "test@example.com"}
        ):
            audience = middleware._extract_jwt_audience()
            assert audience is None

        # Test with no claims
        with patch.object(middleware, "_extract_jwt_claims", return_value=None):
            audience = middleware._extract_jwt_audience()
            assert audience is None
