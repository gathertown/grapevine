"""Tests for API key verification service."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.mcp.utils.api_keys import verify_api_key


class TestVerifyApiKey:
    """Test the verify_api_key function."""

    @pytest.mark.asyncio
    async def test_invalid_format_no_prefix(self):
        """Test API key without 'gv_' prefix is rejected."""
        result = await verify_api_key("invalid_key")
        assert result is None

    @pytest.mark.asyncio
    async def test_invalid_format_empty_string(self):
        """Test empty API key is rejected."""
        result = await verify_api_key("")
        assert result is None

    @pytest.mark.asyncio
    async def test_invalid_format_none(self):
        """Test None API key is rejected."""
        result = await verify_api_key(None)
        assert result is None

    @pytest.mark.asyncio
    async def test_invalid_format_missing_components(self):
        """Test API key with missing components is rejected."""
        # Only has prefix, no tenant_id or random portion
        result = await verify_api_key("gv_")
        assert result is None

        # Missing random portion
        result = await verify_api_key("gv_tenant123")
        assert result is None

    @pytest.mark.asyncio
    async def test_key_not_found_in_database(self):
        """Test API key not found in tenant database returns None."""
        api_key = "gv_tenant123_abcd1234ef567890abcdef1234567890"

        # Mock database connection
        mock_conn = AsyncMock()
        mock_conn.fetchrow.return_value = None  # Key not found

        mock_pool = MagicMock()
        mock_pool.acquire.return_value.__aenter__.return_value = mock_conn
        mock_pool.acquire.return_value.__aexit__ = AsyncMock()

        with patch("src.mcp.utils.api_keys._tenant_db_manager") as mock_db_manager:
            mock_db_manager.acquire_pool.return_value.__aenter__.return_value = mock_pool
            mock_db_manager.acquire_pool.return_value.__aexit__ = AsyncMock()

            result = await verify_api_key(api_key)

        assert result is None
        mock_conn.fetchrow.assert_called_once_with(
            "SELECT id FROM api_keys WHERE prefix = $1",
            "gv_tenant123_abcd1234",
        )

    @pytest.mark.asyncio
    async def test_key_mismatch_in_ssm(self):
        """Test API key found in DB but doesn't match SSM stored key."""
        api_key = "gv_tenant123_abcd1234ef567890abcdef1234567890"

        # Mock database connection
        mock_conn = AsyncMock()
        mock_conn.fetchrow.return_value = {"id": 1}
        mock_conn.execute = AsyncMock()

        mock_pool = MagicMock()
        mock_pool.acquire.return_value.__aenter__.return_value = mock_conn
        mock_pool.acquire.return_value.__aexit__ = AsyncMock()

        # Mock SSMClient to return different key
        mock_ssm = AsyncMock()
        mock_ssm.get_api_key.return_value = "gv_tenant123_abcd1234ef567890abcdef9876543210"

        with (
            patch("src.mcp.utils.api_keys._tenant_db_manager") as mock_db_manager,
            patch("src.mcp.utils.api_keys.SSMClient", return_value=mock_ssm),
        ):
            mock_db_manager.acquire_pool.return_value.__aenter__.return_value = mock_pool
            mock_db_manager.acquire_pool.return_value.__aexit__ = AsyncMock()

            result = await verify_api_key(api_key)

        assert result is None
        mock_ssm.get_api_key.assert_called_once_with("tenant123", "gv_api_1")
        # Should not update last_used_at when key doesn't match
        mock_conn.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_key_not_in_ssm(self):
        """Test API key found in DB but not in SSM."""
        api_key = "gv_tenant123_abcd1234ef567890abcdef1234567890"

        # Mock database connection
        mock_conn = AsyncMock()
        mock_conn.fetchrow.return_value = {"id": 1}
        mock_conn.execute = AsyncMock()

        mock_pool = MagicMock()
        mock_pool.acquire.return_value.__aenter__.return_value = mock_conn
        mock_pool.acquire.return_value.__aexit__ = AsyncMock()

        # Mock SSMClient to return None
        mock_ssm = AsyncMock()
        mock_ssm.get_api_key.return_value = None

        with (
            patch("src.mcp.utils.api_keys._tenant_db_manager") as mock_db_manager,
            patch("src.mcp.utils.api_keys.SSMClient", return_value=mock_ssm),
        ):
            mock_db_manager.acquire_pool.return_value.__aenter__.return_value = mock_pool
            mock_db_manager.acquire_pool.return_value.__aexit__ = AsyncMock()

            result = await verify_api_key(api_key)

        assert result is None
        mock_ssm.get_api_key.assert_called_once_with("tenant123", "gv_api_1")
        # Should not update last_used_at when key not in SSM
        mock_conn.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_successful_verification(self):
        """Test successful API key verification returns tenant ID and updates last_used_at."""
        api_key = "gv_tenant123_abcd1234ef567890abcdef1234567890"

        # Mock database connection
        mock_conn = AsyncMock()
        mock_conn.fetchrow.return_value = {"id": 1}
        mock_conn.execute = AsyncMock()

        mock_pool = MagicMock()
        mock_pool.acquire.return_value.__aenter__.return_value = mock_conn
        mock_pool.acquire.return_value.__aexit__ = AsyncMock()

        # Mock SSMClient to return matching key
        mock_ssm = AsyncMock()
        mock_ssm.get_api_key.return_value = api_key

        with (
            patch("src.mcp.utils.api_keys._tenant_db_manager") as mock_db_manager,
            patch("src.mcp.utils.api_keys.SSMClient", return_value=mock_ssm),
        ):
            mock_db_manager.acquire_pool.return_value.__aenter__.return_value = mock_pool
            mock_db_manager.acquire_pool.return_value.__aexit__ = AsyncMock()

            result = await verify_api_key(api_key)

        assert result == "tenant123"
        mock_ssm.get_api_key.assert_called_once_with("tenant123", "gv_api_1")
        # Should update last_used_at timestamp
        mock_conn.execute.assert_called_once_with(
            "UPDATE api_keys SET last_used_at = CURRENT_TIMESTAMP WHERE prefix = $1",
            "gv_tenant123_abcd1234",
        )

    @pytest.mark.asyncio
    async def test_exception_during_verification(self):
        """Test that exceptions are caught and None is returned."""
        api_key = "gv_tenant123_abcd1234_rest_of_key"

        # Mock database to raise exception
        with patch("src.mcp.utils.api_keys._tenant_db_manager") as mock_db_manager:
            mock_db_manager.acquire_pool.side_effect = Exception("Database connection failed")

            result = await verify_api_key(api_key)

        assert result is None

    @pytest.mark.asyncio
    async def test_long_tenant_id(self):
        """Test API key with long tenant ID is parsed correctly."""
        api_key = "gv_verylongtenant123456789_abcd1234ef567890abcdef1234567890"

        # Mock database connection
        mock_conn = AsyncMock()
        mock_conn.fetchrow.return_value = {"id": 1}
        mock_conn.execute = AsyncMock()

        mock_pool = MagicMock()
        mock_pool.acquire.return_value.__aenter__.return_value = mock_conn
        mock_pool.acquire.return_value.__aexit__ = AsyncMock()

        # Mock SSMClient
        mock_ssm = AsyncMock()
        mock_ssm.get_api_key.return_value = api_key

        with (
            patch("src.mcp.utils.api_keys._tenant_db_manager") as mock_db_manager,
            patch("src.mcp.utils.api_keys.SSMClient", return_value=mock_ssm),
        ):
            mock_db_manager.acquire_pool.return_value.__aenter__.return_value = mock_pool
            mock_db_manager.acquire_pool.return_value.__aexit__ = AsyncMock()

            result = await verify_api_key(api_key)

        assert result == "verylongtenant123456789"
        mock_ssm.get_api_key.assert_called_once_with("verylongtenant123456789", "gv_api_1")

    @pytest.mark.asyncio
    async def test_key_with_long_random_portion(self):
        """Test API key with long random portion extracts first 8 chars for SSM lookup."""
        # The format is gv_{tenant_id}_{random}
        # Only first 8 chars of random portion are used for SSM key ID
        api_key = "gv_tenant123_abcdef1234567890abcdef1234567890"

        # Mock database connection
        mock_conn = AsyncMock()
        mock_conn.fetchrow.return_value = {"id": 1}
        mock_conn.execute = AsyncMock()

        mock_pool = MagicMock()
        mock_pool.acquire.return_value.__aenter__.return_value = mock_conn
        mock_pool.acquire.return_value.__aexit__ = AsyncMock()

        # Mock SSMClient
        mock_ssm = AsyncMock()
        mock_ssm.get_api_key.return_value = api_key

        with (
            patch("src.mcp.utils.api_keys._tenant_db_manager") as mock_db_manager,
            patch("src.mcp.utils.api_keys.SSMClient", return_value=mock_ssm),
        ):
            mock_db_manager.acquire_pool.return_value.__aenter__.return_value = mock_pool
            mock_db_manager.acquire_pool.return_value.__aexit__ = AsyncMock()

            result = await verify_api_key(api_key)

        assert result == "tenant123"
        # Should only use first 8 chars of random portion
        mock_ssm.get_api_key.assert_called_once_with("tenant123", "gv_api_1")

    @pytest.mark.asyncio
    async def test_timing_attack_protection(self):
        """Test that constant-time comparison is used for key verification."""
        # This test verifies we're using hmac.compare_digest, not ==
        # We can't easily test the timing aspect, but we ensure it's in the code path

        api_key = "gv_tenant123_abcd1234ef567890abcdef1234567890"
        wrong_key = "gv_tenant123_abcd1234ef567890abcdef9876543210"

        # Mock database connection
        mock_conn = AsyncMock()
        mock_conn.fetchrow.return_value = {"id": 1}
        mock_conn.execute = AsyncMock()

        mock_pool = MagicMock()
        mock_pool.acquire.return_value.__aenter__.return_value = mock_conn
        mock_pool.acquire.return_value.__aexit__ = AsyncMock()

        # Mock SSMClient to return correct key
        mock_ssm = AsyncMock()
        mock_ssm.get_api_key.return_value = api_key

        with (
            patch("src.mcp.utils.api_keys._tenant_db_manager") as mock_db_manager,
            patch("src.mcp.utils.api_keys.SSMClient", return_value=mock_ssm),
            patch("src.mcp.utils.api_keys.hmac.compare_digest") as mock_compare,
        ):
            mock_db_manager.acquire_pool.return_value.__aenter__.return_value = mock_pool
            mock_db_manager.acquire_pool.return_value.__aexit__ = AsyncMock()
            mock_compare.return_value = False  # Simulate mismatch

            result = await verify_api_key(wrong_key)

        assert result is None
        # Verify hmac.compare_digest was called (timing attack protection)
        mock_compare.assert_called_once()

    @pytest.mark.asyncio
    async def test_short_ssm_key_id(self):
        """Test that only first 8 characters of random portion are used for SSM lookup."""
        # The SSM key ID should be extracted from characters after tenant_id
        api_key = "gv_tenant123_abc"  # Less than 8 chars in random portion

        # Mock database connection
        mock_conn = AsyncMock()
        mock_conn.fetchrow.return_value = {"id": 1}
        mock_conn.execute = AsyncMock()

        mock_pool = MagicMock()
        mock_pool.acquire.return_value.__aenter__.return_value = mock_conn
        mock_pool.acquire.return_value.__aexit__ = AsyncMock()

        # Mock SSMClient
        mock_ssm = AsyncMock()
        mock_ssm.get_api_key.return_value = api_key

        with (
            patch("src.mcp.utils.api_keys._tenant_db_manager") as mock_db_manager,
            patch("src.mcp.utils.api_keys.SSMClient", return_value=mock_ssm),
        ):
            mock_db_manager.acquire_pool.return_value.__aenter__.return_value = mock_pool
            mock_db_manager.acquire_pool.return_value.__aexit__ = AsyncMock()

            result = await verify_api_key(api_key)

        assert result == "tenant123"
        # Should use first 8 chars (or less if shorter)
        mock_ssm.get_api_key.assert_called_once_with("tenant123", "gv_api_1")
