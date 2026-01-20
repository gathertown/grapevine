"""Tests for gatekeeper utility functions."""

import json
import urllib.parse
from unittest.mock import AsyncMock, patch

import pytest

from src.ingest.gatekeeper.utils import extract_tenant_from_slack_request


class TestExtractTenantFromSlackRequest:
    """Test the extract_tenant_from_slack_request function."""

    @pytest.mark.asyncio
    async def test_legacy_host_header_success(self):
        """Test successful tenant extraction from Host header (legacy per-tenant app)."""
        headers = {"Host": "tenant123.ingest.localhost"}
        body_str = json.dumps({"team": {"id": "T123456"}})

        with patch("src.ingest.gatekeeper.utils.get_base_domain", return_value="localhost"):
            result = await extract_tenant_from_slack_request(body_str, headers)

        assert result.tenant_id == "tenant123"
        assert result.error is None

    @pytest.mark.asyncio
    async def test_legacy_host_header_case_insensitive(self):
        """Test Host header extraction is case-insensitive."""
        headers = {"host": "tenant456.ingest.localhost"}  # lowercase "host"
        body_str = json.dumps({"team": {"id": "T123456"}})

        with patch("src.ingest.gatekeeper.utils.get_base_domain", return_value="localhost"):
            result = await extract_tenant_from_slack_request(body_str, headers)

        assert result.tenant_id == "tenant456"
        assert result.error is None

    @pytest.mark.asyncio
    async def test_slack_subdomain_skips_to_centralized_oauth(self):
        """Test that 'slack' subdomain skips Host header and uses centralized OAuth."""
        headers = {"Host": "slack.ingest.localhost"}
        body_str = json.dumps({"team": {"id": "T123456"}})

        with (
            patch("src.ingest.gatekeeper.utils.get_base_domain", return_value="localhost"),
            patch(
                "src.ingest.gatekeeper.utils.resolve_tenant_by_slack_team_id",
                new_callable=AsyncMock,
                return_value="resolved-tenant-123",
            ) as mock_resolve,
        ):
            result = await extract_tenant_from_slack_request(body_str, headers)

        assert result.tenant_id == "resolved-tenant-123"
        assert result.error is None
        mock_resolve.assert_called_once_with("T123456")

    @pytest.mark.asyncio
    async def test_centralized_oauth_with_team_id(self):
        """Test centralized OAuth with team_id in payload."""
        headers = {"Host": "invalid-host"}  # Invalid host to trigger fallback
        body_str = json.dumps({"team": {"id": "T987654"}})

        with (
            patch("src.ingest.gatekeeper.utils.get_base_domain", return_value="localhost"),
            patch(
                "src.ingest.gatekeeper.utils.resolve_tenant_by_slack_team_id",
                new_callable=AsyncMock,
                return_value="tenant-from-team-id",
            ) as mock_resolve,
        ):
            result = await extract_tenant_from_slack_request(body_str, headers)

        assert result.tenant_id == "tenant-from-team-id"
        assert result.error is None
        mock_resolve.assert_called_once_with("T987654")

    @pytest.mark.asyncio
    async def test_centralized_oauth_with_top_level_team_id(self):
        """Test centralized OAuth with team_id at top level of payload."""
        headers = {"Host": "invalid-host"}
        body_str = json.dumps({"team_id": "T555555"})

        with (
            patch("src.ingest.gatekeeper.utils.get_base_domain", return_value="localhost"),
            patch(
                "src.ingest.gatekeeper.utils.resolve_tenant_by_slack_team_id",
                new_callable=AsyncMock,
                return_value="tenant-555",
            ) as mock_resolve,
        ):
            result = await extract_tenant_from_slack_request(body_str, headers)

        assert result.tenant_id == "tenant-555"
        assert result.error is None
        mock_resolve.assert_called_once_with("T555555")

    @pytest.mark.asyncio
    async def test_centralized_oauth_form_encoded_payload(self):
        """Test centralized OAuth with form-encoded payload."""
        headers = {"Host": "slack.ingest.localhost"}
        payload_data = {"team": {"id": "T999999"}}
        body_str = f"payload={urllib.parse.quote(json.dumps(payload_data))}"

        with (
            patch("src.ingest.gatekeeper.utils.get_base_domain", return_value="localhost"),
            patch(
                "src.ingest.gatekeeper.utils.resolve_tenant_by_slack_team_id",
                new_callable=AsyncMock,
                return_value="form-encoded-tenant",
            ) as mock_resolve,
        ):
            result = await extract_tenant_from_slack_request(body_str, headers)

        assert result.tenant_id == "form-encoded-tenant"
        assert result.error is None
        mock_resolve.assert_called_once_with("T999999")

    @pytest.mark.asyncio
    async def test_centralized_oauth_team_id_not_found(self):
        """Test centralized OAuth when team_id doesn't resolve to a tenant."""
        headers = {"Host": "slack.ingest.localhost"}
        body_str = json.dumps({"team": {"id": "T000000"}})

        with (
            patch("src.ingest.gatekeeper.utils.get_base_domain", return_value="localhost"),
            patch(
                "src.ingest.gatekeeper.utils.resolve_tenant_by_slack_team_id",
                new_callable=AsyncMock,
                return_value=None,
            ) as mock_resolve,
        ):
            result = await extract_tenant_from_slack_request(body_str, headers)

        assert result.tenant_id is None
        assert result.error == "No tenant found for Slack team_id T000000"
        mock_resolve.assert_called_once_with("T000000")

    @pytest.mark.asyncio
    async def test_centralized_oauth_no_team_id_in_payload(self):
        """Test centralized OAuth when payload doesn't contain team_id."""
        headers = {"Host": "slack.ingest.localhost"}
        body_str = json.dumps({"type": "event_callback", "event": {}})

        with patch("src.ingest.gatekeeper.utils.get_base_domain", return_value="localhost"):
            result = await extract_tenant_from_slack_request(body_str, headers)

        assert result.tenant_id is None
        assert result.error == "Could not extract team_id from Slack webhook payload"

    @pytest.mark.asyncio
    async def test_invalid_json_payload(self):
        """Test handling of invalid JSON payload."""
        headers = {"Host": "slack.ingest.localhost"}
        body_str = "invalid json {"

        with patch("src.ingest.gatekeeper.utils.get_base_domain", return_value="localhost"):
            result = await extract_tenant_from_slack_request(body_str, headers)

        assert result.tenant_id is None
        assert result.error is not None
        assert "Failed to parse Slack webhook payload" in result.error

    @pytest.mark.asyncio
    async def test_missing_host_header_with_no_team_id(self):
        """Test when both Host header is missing and no team_id in payload."""
        headers: dict[str, str] = {}
        body_str = json.dumps({"type": "event_callback"})

        with patch("src.ingest.gatekeeper.utils.get_base_domain", return_value="localhost"):
            result = await extract_tenant_from_slack_request(body_str, headers)

        assert result.tenant_id is None
        assert result.error == "Could not extract team_id from Slack webhook payload"

    @pytest.mark.asyncio
    async def test_invalid_host_format_fallback_to_team_id(self):
        """Test that invalid host format falls back to team_id resolution."""
        headers = {"Host": "wrong-format"}  # Doesn't match expected pattern
        body_str = json.dumps({"team": {"id": "T111111"}})

        with (
            patch("src.ingest.gatekeeper.utils.get_base_domain", return_value="localhost"),
            patch(
                "src.ingest.gatekeeper.utils.resolve_tenant_by_slack_team_id",
                new_callable=AsyncMock,
                return_value="fallback-tenant",
            ) as mock_resolve,
        ):
            result = await extract_tenant_from_slack_request(body_str, headers)

        assert result.tenant_id == "fallback-tenant"
        assert result.error is None
        mock_resolve.assert_called_once_with("T111111")

    @pytest.mark.asyncio
    async def test_form_encoded_without_payload_key(self):
        """Test form-encoded body that starts with 'payload=' but no payload key."""
        headers = {"Host": "slack.ingest.localhost"}
        # Edge case: starts with "payload=" but when parsed, no actual payload key
        body_str = "payload=notjson"

        with patch("src.ingest.gatekeeper.utils.get_base_domain", return_value="localhost"):
            result = await extract_tenant_from_slack_request(body_str, headers)

        assert result.tenant_id is None
        assert result.error is not None
        assert "Failed to parse Slack webhook payload" in result.error

    @pytest.mark.asyncio
    async def test_tenant_id_with_hyphens_and_underscores(self):
        """Test that tenant IDs with hyphens and underscores are accepted."""
        headers = {"Host": "tenant-123_abc.ingest.localhost"}
        body_str = json.dumps({"team": {"id": "T123456"}})

        with patch("src.ingest.gatekeeper.utils.get_base_domain", return_value="localhost"):
            result = await extract_tenant_from_slack_request(body_str, headers)

        assert result.tenant_id == "tenant-123_abc"
        assert result.error is None

    @pytest.mark.asyncio
    async def test_priority_order_legacy_over_centralized(self):
        """Test that legacy Host header is prioritized over centralized OAuth."""
        headers = {"Host": "legacy-tenant.ingest.localhost"}
        body_str = json.dumps({"team": {"id": "T123456"}})

        with (
            patch("src.ingest.gatekeeper.utils.get_base_domain", return_value="localhost"),
            patch(
                "src.ingest.gatekeeper.utils.resolve_tenant_by_slack_team_id",
                new_callable=AsyncMock,
            ) as mock_resolve,
        ):
            result = await extract_tenant_from_slack_request(body_str, headers)

        # Should use Host header, not call resolve function
        assert result.tenant_id == "legacy-tenant"
        assert result.error is None
        mock_resolve.assert_not_called()
