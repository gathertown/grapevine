"""Tests for SnowflakeService."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, Mock, patch

import pytest

from src.warehouses.models import QueryType, WarehouseSource
from src.warehouses.snowflake_service import SnowflakeOAuthToken, SnowflakeService


class TestSnowflakeOAuthToken:
    """Test cases for SnowflakeOAuthToken class."""

    def test_is_expired_true(self):
        """Test token expiry detection when expired."""
        expires_at = (datetime.now(UTC) - timedelta(minutes=5)).isoformat()
        token = SnowflakeOAuthToken(
            access_token="token",
            refresh_token="refresh",
            access_token_expires_at=expires_at,
            username="user@example.com",
        )
        assert token.is_expired() is True

    def test_is_expired_false(self):
        """Test token expiry detection when not expired."""
        expires_at = (datetime.now(UTC) + timedelta(minutes=5)).isoformat()
        token = SnowflakeOAuthToken(
            access_token="token",
            refresh_token="refresh",
            access_token_expires_at=expires_at,
            username="user@example.com",
        )
        assert token.is_expired() is False

    def test_to_dict(self):
        """Test converting token to dictionary."""
        token = SnowflakeOAuthToken(
            access_token="access123",
            refresh_token="refresh123",
            access_token_expires_at="2025-01-01T00:00:00Z",
            username="user@example.com",
        )
        result = token.to_dict()

        assert result["access_token"] == "access123"
        assert result["refresh_token"] == "refresh123"
        assert result["access_token_expires_at"] == "2025-01-01T00:00:00Z"
        assert result["username"] == "user@example.com"

    def test_from_dict(self):
        """Test creating token from dictionary."""
        data = {
            "access_token": "access123",
            "refresh_token": "refresh123",
            "access_token_expires_at": "2025-01-01T00:00:00Z",
            "username": "user@example.com",
        }
        token = SnowflakeOAuthToken.from_dict(data)

        assert token.access_token == "access123"
        assert token.refresh_token == "refresh123"
        assert token.access_token_expires_at == "2025-01-01T00:00:00Z"
        assert token.username == "user@example.com"

    def test_refresh_token_expiry_in_dict(self):
        """Test refresh token expiry is included in dictionary."""
        refresh_expires_at = (datetime.now(UTC) + timedelta(days=90)).isoformat()
        token = SnowflakeOAuthToken(
            access_token="access123",
            refresh_token="refresh123",
            access_token_expires_at="2025-01-01T00:00:00Z",
            refresh_token_expires_at=refresh_expires_at,
            username="user@example.com",
        )
        result = token.to_dict()

        assert result["refresh_token_expires_at"] == refresh_expires_at

    def test_refresh_token_expiry_from_dict(self):
        """Test creating token with refresh token expiry from dictionary."""
        refresh_expires_at = (datetime.now(UTC) + timedelta(days=90)).isoformat()
        data = {
            "access_token": "access123",
            "refresh_token": "refresh123",
            "access_token_expires_at": "2025-01-01T00:00:00Z",
            "refresh_token_expires_at": refresh_expires_at,
            "username": "user@example.com",
        }
        token = SnowflakeOAuthToken.from_dict(data)

        assert token.refresh_token_expires_at == refresh_expires_at

    def test_is_refresh_token_expiring_soon_true(self):
        """Test refresh token expiring soon detection when expiring within threshold."""
        # Token expires in 5 days
        expires_at = (datetime.now(UTC) + timedelta(days=5)).isoformat()
        token = SnowflakeOAuthToken(
            access_token="token",
            refresh_token="refresh",
            access_token_expires_at="2025-01-01T00:00:00Z",
            refresh_token_expires_at=expires_at,
        )
        # Check with 7 day threshold
        assert token.is_refresh_token_expiring_soon(days_threshold=7) is True

    def test_is_refresh_token_expiring_soon_false(self):
        """Test refresh token expiring soon detection when not expiring within threshold."""
        # Token expires in 30 days
        expires_at = (datetime.now(UTC) + timedelta(days=30)).isoformat()
        token = SnowflakeOAuthToken(
            access_token="token",
            refresh_token="refresh",
            access_token_expires_at="2025-01-01T00:00:00Z",
            refresh_token_expires_at=expires_at,
        )
        # Check with 7 day threshold
        assert token.is_refresh_token_expiring_soon(days_threshold=7) is False

    def test_is_refresh_token_expired_true(self):
        """Test refresh token expiry detection when expired."""
        # Token expired 5 days ago
        expires_at = (datetime.now(UTC) - timedelta(days=5)).isoformat()
        token = SnowflakeOAuthToken(
            access_token="token",
            refresh_token="refresh",
            access_token_expires_at="2025-01-01T00:00:00Z",
            refresh_token_expires_at=expires_at,
        )
        assert token.is_refresh_token_expired() is True

    def test_is_refresh_token_expired_false(self):
        """Test refresh token expiry detection when not expired."""
        # Token expires in 30 days
        expires_at = (datetime.now(UTC) + timedelta(days=30)).isoformat()
        token = SnowflakeOAuthToken(
            access_token="token",
            refresh_token="refresh",
            access_token_expires_at="2025-01-01T00:00:00Z",
            refresh_token_expires_at=expires_at,
        )
        assert token.is_refresh_token_expired() is False

    def test_is_refresh_token_expired_none(self):
        """Test refresh token expiry detection when expiry not set."""
        token = SnowflakeOAuthToken(
            access_token="token",
            refresh_token="refresh",
            access_token_expires_at="2025-01-01T00:00:00Z",
            refresh_token_expires_at=None,
        )
        assert token.is_refresh_token_expired() is False


class TestSnowflakeService:
    """Test cases for SnowflakeService class."""

    @pytest.fixture
    def service(self):
        """Create SnowflakeService instance."""
        return SnowflakeService()

    @pytest.fixture
    def mock_token(self):
        """Create mock OAuth token."""
        expires_at = (datetime.now(UTC) + timedelta(minutes=5)).isoformat()
        return SnowflakeOAuthToken(
            access_token="test_access_token",
            refresh_token="test_refresh_token",
            access_token_expires_at=expires_at,
            username="test@example.com",
        )

    @pytest.mark.asyncio
    async def test_get_oauth_token_from_ssm_success(self, service):
        """Test getting OAuth token from SSM."""
        token_data = {
            "access_token": "access123",
            "refresh_token": "refresh123",
            "access_token_expires_at": "2025-01-01T00:00:00Z",
        }
        import json

        token_json = json.dumps(token_data)

        with patch.object(service.ssm_client, "get_parameter", return_value=token_json):
            token = await service._get_oauth_token_from_ssm("tenant123")

            assert token is not None
            assert token.access_token == "access123"
            assert token.username is None

    @pytest.mark.asyncio
    async def test_get_oauth_token_from_ssm_not_found(self, service):
        """Test getting OAuth token when not in SSM."""
        with patch.object(service.ssm_client, "get_parameter", return_value=None):
            token = await service._get_oauth_token_from_ssm("tenant123")
            assert token is None

    @pytest.mark.asyncio
    async def test_save_oauth_token_to_ssm(self, service, mock_token):
        """Test saving OAuth token to SSM."""
        with patch.object(service.ssm_client, "put_parameter") as mock_put:
            await service._save_oauth_token_to_ssm("tenant123", mock_token)

            mock_put.assert_called_once()
            call_args = mock_put.call_args
            assert call_args[0][0] == "/tenant123/api-key/SNOWFLAKE_OAUTH_TOKEN_PAYLOAD"
            assert "test_access_token" in call_args[0][1]

    @pytest.mark.skip(
        reason="Complex async context manager mocking - better suited for integration tests"
    )
    @pytest.mark.asyncio
    async def test_get_snowflake_config(self, service):
        """Test getting Snowflake configuration from Control DB."""
        pass  # Integration test recommended

    @pytest.mark.asyncio
    async def test_refresh_access_token_success(self, service):
        """Test refreshing access token."""
        mock_response = Mock()
        mock_response.is_success = True
        mock_response.json.return_value = {
            "access_token": "new_access_token",
            "refresh_token": "new_refresh_token",
            "expires_in": 600,
            "username": "user@example.com",
        }

        with patch.object(service.http_client, "post", return_value=mock_response):
            result = await service._refresh_access_token(
                refresh_token="old_refresh",
                account_identifier="myorg-account123",
                client_id="client123",
                client_secret="secret123",
            )

            assert result["access_token"] == "new_access_token"
            assert result["username"] == "user@example.com"

    @pytest.mark.asyncio
    async def test_refresh_access_token_invalid_grant(self, service):
        """Test refresh token with invalid_grant error."""
        mock_response = Mock()
        mock_response.is_success = False
        mock_response.status_code = 400
        mock_response.text = '{"error": "invalid_grant"}'
        mock_response.json.return_value = {"error": "invalid_grant"}

        with (
            patch.object(service.http_client, "post", return_value=mock_response),
            pytest.raises(ValueError, match="refresh token is invalid or expired"),
        ):
            await service._refresh_access_token(
                refresh_token="old_refresh",
                account_identifier="myorg-account123",
                client_id="client123",
                client_secret="secret123",
            )

    @pytest.mark.asyncio
    async def test_get_valid_oauth_token_not_expired(self, service, mock_token):
        """Test getting valid OAuth token when not expired."""
        with (
            patch.object(service, "_get_oauth_token_from_ssm", return_value=mock_token) as mock_get,
            patch.object(
                service,
                "_get_snowflake_config",
                return_value={"account_identifier": "myorg-account123"},
            ),
        ):
            token, account_id = await service.get_valid_oauth_token("tenant123")

            assert token.access_token == "test_access_token"
            assert account_id == "myorg-account123"
            # Should not refresh since token not expired
            mock_get.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_valid_oauth_token_expired(self, service):
        """Test getting valid OAuth token when expired triggers refresh."""
        # Create expired token
        expires_at = (datetime.now(UTC) - timedelta(minutes=5)).isoformat()
        expired_token = SnowflakeOAuthToken(
            access_token="old_access",
            refresh_token="refresh_token",
            access_token_expires_at=expires_at,
        )

        with (
            patch.object(service, "_get_oauth_token_from_ssm", return_value=expired_token),
            patch.object(
                service,
                "_get_snowflake_config",
                return_value={
                    "account_identifier": "myorg-account123",
                    "client_id": "client123",
                    "client_secret": "secret123",
                    "token_endpoint": None,
                },
            ),
            patch.object(
                service,
                "_refresh_access_token",
                return_value={
                    "access_token": "new_access",
                    "refresh_token": "new_refresh",
                    "expires_in": 600,
                },
            ) as mock_refresh,
            patch.object(service, "_save_oauth_token_to_ssm") as mock_save,
        ):
            token, account_id = await service.get_valid_oauth_token("tenant123")

            assert token.access_token == "new_access"
            mock_refresh.assert_called_once()
            mock_save.assert_called_once()

    @pytest.mark.asyncio
    async def test_refresh_token_expiry_updated_with_new_refresh_token(self, service):
        """Test that refresh token expiry is updated when new refresh token is returned."""
        # Create expired access token with old refresh token expiry
        old_refresh_expires_at = (datetime.now(UTC) + timedelta(days=30)).isoformat()
        expired_token = SnowflakeOAuthToken(
            access_token="old_access",
            refresh_token="old_refresh",
            access_token_expires_at=(datetime.now(UTC) - timedelta(minutes=5)).isoformat(),
            refresh_token_expires_at=old_refresh_expires_at,
        )

        with (
            patch.object(service, "_get_oauth_token_from_ssm", return_value=expired_token),
            patch.object(
                service,
                "_get_snowflake_config",
                return_value={
                    "account_identifier": "myorg-account123",
                    "client_id": "client123",
                    "client_secret": "secret123",
                    "token_endpoint": None,
                },
            ),
            patch.object(
                service,
                "_refresh_access_token",
                return_value={
                    "access_token": "new_access",
                    "refresh_token": "new_refresh",  # New refresh token returned
                    "expires_in": 600,
                },
            ),
            patch.object(service, "_save_oauth_token_to_ssm") as mock_save,
        ):
            token, _ = await service.get_valid_oauth_token("tenant123")

            # Verify new tokens
            assert token.access_token == "new_access"
            assert token.refresh_token == "new_refresh"

            # Verify refresh token expiry was updated to ~90 days from now
            assert token.refresh_token_expires_at is not None
            assert token.refresh_token_expires_at != old_refresh_expires_at

            # Parse the new expiry and verify it's approximately 90 days from now
            new_expiry = datetime.fromisoformat(
                token.refresh_token_expires_at.replace("Z", "+00:00")
            )
            expected_expiry = datetime.now(UTC) + timedelta(days=90)
            time_diff = abs((new_expiry - expected_expiry).total_seconds())
            assert time_diff < 60, "Refresh token expiry should be ~90 days from now"

            # Verify the token was saved
            mock_save.assert_called_once()
            saved_token = mock_save.call_args[0][1]
            assert saved_token.refresh_token_expires_at == token.refresh_token_expires_at

    @pytest.mark.asyncio
    async def test_refresh_token_expiry_preserved_without_new_refresh_token(self, service):
        """Test that refresh token expiry is preserved when no new refresh token returned."""
        # Create expired access token with existing refresh token expiry
        existing_refresh_expires_at = (datetime.now(UTC) + timedelta(days=30)).isoformat()
        expired_token = SnowflakeOAuthToken(
            access_token="old_access",
            refresh_token="refresh_token",
            access_token_expires_at=(datetime.now(UTC) - timedelta(minutes=5)).isoformat(),
            refresh_token_expires_at=existing_refresh_expires_at,
        )

        with (
            patch.object(service, "_get_oauth_token_from_ssm", return_value=expired_token),
            patch.object(
                service,
                "_get_snowflake_config",
                return_value={
                    "account_identifier": "myorg-account123",
                    "client_id": "client123",
                    "client_secret": "secret123",
                    "token_endpoint": None,
                },
            ),
            patch.object(
                service,
                "_refresh_access_token",
                return_value={
                    "access_token": "new_access",
                    # No refresh_token in response - Snowflake keeps the old one
                    "expires_in": 600,
                },
            ),
            patch.object(service, "_save_oauth_token_to_ssm") as mock_save,
        ):
            token, _ = await service.get_valid_oauth_token("tenant123")

            # Verify access token was refreshed
            assert token.access_token == "new_access"

            # Verify refresh token and expiry were preserved
            assert token.refresh_token == "refresh_token"
            assert token.refresh_token_expires_at == existing_refresh_expires_at

            # Verify the token was saved with preserved expiry
            mock_save.assert_called_once()
            saved_token = mock_save.call_args[0][1]
            assert saved_token.refresh_token_expires_at == existing_refresh_expires_at

    @pytest.mark.skip(
        reason="Complex async context manager mocking - better suited for integration tests"
    )
    @pytest.mark.asyncio
    async def test_get_semantic_models(self, service):
        """Test getting semantic models from tenant DB."""
        pass  # Integration test recommended

    @pytest.mark.asyncio
    async def test_log_query(self, service):
        """Test logging query to tenant database."""
        mock_conn = AsyncMock()

        with patch(
            "src.warehouses.snowflake_service.tenant_db_manager.acquire_connection"
        ) as mock_acquire:
            mock_acquire.return_value.__aenter__.return_value = mock_conn

            await service.log_query(
                tenant_id="tenant123",
                user_id=None,
                source=WarehouseSource.SNOWFLAKE,
                query_type=QueryType.NATURAL_LANGUAGE,
                question="What are sales?",
                generated_sql="SELECT * FROM sales",
                execution_time_ms=150,
                row_count=10,
                success=True,
            )

            mock_conn.execute.assert_called_once()
            call_args = mock_conn.execute.call_args
            assert "INSERT INTO warehouse_query_log" in call_args[0][0]
            assert call_args[0][2] is None
            assert call_args[0][3] == "snowflake"
            assert call_args[0][4] == "natural_language"

    @pytest.mark.asyncio
    async def test_close(self, service):
        """Test closing HTTP client."""
        with patch.object(service.http_client, "aclose") as mock_close:
            await service.close()
            mock_close.assert_called_once()
