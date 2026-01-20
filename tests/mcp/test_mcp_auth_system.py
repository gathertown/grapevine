"""Tests for the MCP authentication system without Gather auth."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastmcp.server.auth.auth import AccessToken

from src.mcp.auth import APIKeyAuthProvider
from src.mcp.auth.multi_provider import MultiAuthProvider
from src.mcp.mcp_instance import _build_auth_provider


class TestMultiAuthProvider:
    """Test the MultiAuthProvider functionality."""

    def test_empty_providers(self):
        """Test MultiAuthProvider with no providers."""
        provider = MultiAuthProvider(primary_routes_provider=None, verifiers=[])
        assert provider.get_routes() == []

    @pytest.mark.asyncio
    async def test_single_provider_success(self):
        """Test MultiAuthProvider with one provider that succeeds."""
        mock_provider = MagicMock()
        mock_token = AccessToken(
            token="test-token",
            client_id="test-client",
            scopes=["test"],
            expires_at=None,
        )
        mock_provider.verify_token = AsyncMock(return_value=mock_token)

        provider = MultiAuthProvider(primary_routes_provider=None, verifiers=[mock_provider])

        result = await provider.verify_token("test-token")
        assert result == mock_token
        mock_provider.verify_token.assert_called_once_with("test-token")

    @pytest.mark.asyncio
    async def test_multiple_providers_first_succeeds(self):
        """Test MultiAuthProvider tries providers in order, returns first success."""
        mock_provider1 = MagicMock()
        mock_provider2 = MagicMock()
        mock_token = AccessToken(
            token="test-token",
            client_id="test-client",
            scopes=["test"],
            expires_at=None,
        )

        mock_provider1.verify_token = AsyncMock(return_value=mock_token)
        mock_provider2.verify_token = AsyncMock()  # Should not be called

        provider = MultiAuthProvider(
            primary_routes_provider=None, verifiers=[mock_provider1, mock_provider2]
        )

        result = await provider.verify_token("test-token")
        assert result == mock_token
        mock_provider1.verify_token.assert_called_once_with("test-token")
        mock_provider2.verify_token.assert_not_called()


class TestAPIKeyAuthProvider:
    """Test the APIKeyAuthProvider functionality."""

    def test_provider_creation(self):
        """Test APIKeyAuthProvider can be created."""
        provider = APIKeyAuthProvider()
        assert provider is not None

    @pytest.mark.asyncio
    async def test_verify_valid_api_key(self):
        """Test verification of a valid API key."""
        valid_api_key = "gv_tenant123_abcd1234ef567890abcdef1234567890"
        expected_tenant_id = "tenant123"

        with patch(
            "src.mcp.auth.api_key_provider.verify_api_key",
            AsyncMock(return_value=expected_tenant_id),
        ) as mock_verify:
            provider = APIKeyAuthProvider()
            access_token = await provider.verify_token(valid_api_key)

            assert access_token is not None
            assert access_token.token == valid_api_key
            assert access_token.client_id == f"api-key:{expected_tenant_id}"
            assert access_token.scopes == ["api-key"]
            assert access_token.expires_at is None  # API keys don't expire

            mock_verify.assert_called_once_with(valid_api_key)

    @pytest.mark.asyncio
    async def test_verify_invalid_api_key(self):
        """Test verification fails for invalid API key."""
        invalid_api_key = "invalid-key"

        with patch(
            "src.mcp.auth.api_key_provider.verify_api_key", AsyncMock(return_value=None)
        ) as mock_verify:
            provider = APIKeyAuthProvider()
            result = await provider.verify_token(invalid_api_key)

            assert result is None
            mock_verify.assert_called_once_with(invalid_api_key)

    @pytest.mark.asyncio
    async def test_verify_api_key_exception(self):
        """Test verification handles exceptions gracefully."""
        api_key = "gv_tenant123_abcd1234ef567890abcdef1234567890"

        with patch(
            "src.mcp.auth.api_key_provider.verify_api_key",
            AsyncMock(side_effect=Exception("DB error")),
        ) as mock_verify:
            provider = APIKeyAuthProvider()
            result = await provider.verify_token(api_key)

            assert result is None
            mock_verify.assert_called_once_with(api_key)

    @pytest.mark.asyncio
    async def test_verify_empty_token(self):
        """Test verification fails for empty token."""
        with patch(
            "src.mcp.auth.api_key_provider.verify_api_key", AsyncMock(return_value=None)
        ) as mock_verify:
            provider = APIKeyAuthProvider()
            result = await provider.verify_token("")

            assert result is None
            mock_verify.assert_called_once_with("")


class TestMCPAuthProviderIntegration:
    """Test the MCP auth provider integration and configuration."""

    @pytest.mark.asyncio
    async def test_build_auth_provider_with_minimal_config(self):
        """Test _build_auth_provider with only API key provider (minimal config)."""
        with (
            patch("src.mcp.mcp_instance.get_authkit_domain", return_value=None),
            patch("src.mcp.mcp_instance.get_internal_jwt_jwks_uri", return_value=None),
            patch("src.mcp.mcp_instance.get_internal_jwt_public_key", return_value=None),
        ):
            provider = _build_auth_provider()
            assert provider is not None
            assert isinstance(provider, APIKeyAuthProvider)

    @pytest.mark.asyncio
    async def test_build_auth_provider_with_authkit(self):
        """Test _build_auth_provider creates MultiAuthProvider with AuthKit + API key."""
        with (
            patch("src.mcp.mcp_instance.get_authkit_domain", return_value="https://auth.example"),
            patch("src.mcp.mcp_instance.get_internal_jwt_jwks_uri", return_value=None),
            patch("src.mcp.mcp_instance.get_internal_jwt_public_key", return_value=None),
        ):
            provider = _build_auth_provider()
            assert provider is not None
            assert isinstance(provider, MultiAuthProvider)

    @pytest.mark.asyncio
    async def test_build_auth_provider_with_internal_jwt(self):
        """Test _build_auth_provider creates MultiAuthProvider with internal JWT + API key."""
        with (
            patch("src.mcp.mcp_instance.get_authkit_domain", return_value=None),
            patch("src.mcp.mcp_instance.get_internal_jwt_jwks_uri", return_value="https://jwks"),
            patch("src.mcp.mcp_instance.get_internal_jwt_public_key", return_value=None),
        ):
            provider = _build_auth_provider()
            assert provider is not None
            assert isinstance(provider, MultiAuthProvider)
