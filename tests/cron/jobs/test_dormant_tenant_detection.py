"""Tests for dormant tenant detection cron job.

This module tests the dormant tenant detection cron job including:
- Dry-run mode behavior
- Detection enabled/disabled logic
- Scan and mark phase
- Auto-delete phase (with and without dry-run)
- Resource discovery in dry-run mode
- Error handling and logging
- DB fetch error handling (fail-safe behavior)
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.cron.jobs.dormant_tenant_detection import (
    _days_since,
    _log_dormant_candidate,
    dormant_tenant_detection,
    is_dry_run_enabled,
)
from src.dormant.deletion import DeletionResult, ResourceDiscoveryResult
from src.dormant.service import (
    DormancyCheckResult,
    TenantInfo,
    _BatchedControlData,
    _TenantDBData,
    scan_for_dormant_tenants,
)


class TestDryRunHelper:
    """Test suite for dry-run helper function."""

    def test_is_dry_run_enabled_default(self):
        """Test that dry-run defaults to enabled."""
        with patch("src.cron.jobs.dormant_tenant_detection.get_config_value", return_value=True):
            assert is_dry_run_enabled() is True

    def test_is_dry_run_enabled_disabled(self):
        """Test that dry-run can be disabled."""
        with patch("src.cron.jobs.dormant_tenant_detection.get_config_value", return_value=False):
            assert is_dry_run_enabled() is False

    def test_is_dry_run_enabled_with_default(self):
        """Test that get_config_value default is used."""
        with patch(
            "src.cron.jobs.dormant_tenant_detection.get_config_value",
            return_value=True,  # Default value
        ):
            assert is_dry_run_enabled() is True


class TestDaysSinceHelper:
    """Test suite for _days_since helper function."""

    def test_days_since_with_datetime(self):
        """Test calculating days since a datetime."""
        dt = datetime.now(UTC) - timedelta(days=5)
        result = _days_since(dt)
        assert result == 5

    def test_days_since_with_none(self):
        """Test that None returns None."""
        assert _days_since(None) is None

    def test_days_since_with_naive_datetime(self):
        """Test that naive datetime gets UTC timezone."""
        dt = datetime.now() - timedelta(days=3)
        result = _days_since(dt)
        # Allow for small timing differences (within 1 day)
        assert result is not None
        assert 2 <= result <= 4


class TestLogDormantCandidate:
    """Test suite for logging dormant candidates."""

    @patch("src.cron.jobs.dormant_tenant_detection.logger")
    def test_log_dormant_candidate(self, mock_logger):
        """Test logging a dormant candidate."""
        candidate = DormancyCheckResult(
            tenant_id="test-tenant-123",
            is_dormant=True,
            reasons=["No connectors", "No documents"],
            has_connectors=False,
            has_slack_bot=False,
            document_count=0,
            usage_count=0,
            days_since_provisioning=10,
            company_name="Test Company",
        )

        _log_dormant_candidate(candidate)

        mock_logger.info.assert_called_once()
        call_args = mock_logger.info.call_args
        assert "test-tenant-123" in call_args[0][0]
        assert call_args[1]["extra"]["tenant_id"] == "test-tenant-123"
        assert call_args[1]["extra"]["company_name"] == "Test Company"
        assert call_args[1]["extra"]["has_connectors"] is False
        assert call_args[1]["extra"]["document_count"] == 0


class TestDormantTenantDetectionJob:
    """Test suite for the main dormant tenant detection cron job."""

    @pytest.mark.asyncio
    async def test_job_disabled(self):
        """Test that job returns early when detection is disabled."""
        with (
            patch(
                "src.cron.jobs.dormant_tenant_detection.is_detection_enabled", return_value=False
            ),
            patch("src.cron.jobs.dormant_tenant_detection.logger") as mock_logger,
        ):
            await dormant_tenant_detection()

            # Should log that detection is disabled (with extra metadata)
            mock_logger.info.assert_called_once()
            call_args = mock_logger.info.call_args
            assert call_args[0][0] == "Dormant tenant detection is disabled"
            assert call_args[1]["extra"]["dormant_detection_enabled"] is False

    @pytest.mark.asyncio
    async def test_dry_run_mode_scan_only(self):
        """Test dry-run mode scans but doesn't mark tenants."""
        mock_scan_result = MagicMock()
        mock_scan_result.total_scanned = 10
        mock_scan_result.dormant_candidates = [
            DormancyCheckResult(
                tenant_id="tenant-1",
                is_dormant=True,
                reasons=["No connectors"],
                has_connectors=False,
                has_slack_bot=False,
                document_count=0,
                usage_count=0,
                days_since_provisioning=8,
            )
        ]
        mock_scan_result.newly_marked = 0
        mock_scan_result.errors = []

        with (
            patch("src.cron.jobs.dormant_tenant_detection.is_detection_enabled", return_value=True),
            patch("src.cron.jobs.dormant_tenant_detection.is_dry_run_enabled", return_value=True),
            patch(
                "src.cron.jobs.dormant_tenant_detection.get_dormant_days_threshold", return_value=7
            ),
            patch("src.cron.jobs.dormant_tenant_detection.get_grace_period_days", return_value=14),
            patch(
                "src.cron.jobs.dormant_tenant_detection.is_auto_delete_enabled", return_value=False
            ),
            patch(
                "src.cron.jobs.dormant_tenant_detection.scan_for_dormant_tenants",
                return_value=mock_scan_result,
            ) as mock_scan,
            patch("src.cron.jobs.dormant_tenant_detection.logger") as mock_logger,
        ):
            await dormant_tenant_detection()

            # Should call scan with mark=False in dry-run mode
            mock_scan.assert_called_once_with(mark=False)

            # Should log dry-run mode message
            log_calls = [call[0][0] for call in mock_logger.info.call_args_list]
            assert any("DRY RUN MODE" in msg for msg in log_calls)

            # Should log summary with would_mark count
            summary_calls = [
                call
                for call in mock_logger.info.call_args_list
                if "completed" in call[0][0].lower()
            ]
            assert len(summary_calls) > 0
            summary_call = summary_calls[-1]  # Get the last "completed" log
            assert summary_call[1]["extra"]["dry_run"] is True
            assert summary_call[1]["extra"]["would_mark"] == 1
            assert summary_call[1]["extra"]["newly_marked"] == 0

    @pytest.mark.asyncio
    async def test_live_mode_marks_tenants(self):
        """Test live mode actually marks dormant tenants."""
        mock_scan_result = MagicMock()
        mock_scan_result.total_scanned = 5
        mock_scan_result.dormant_candidates = [
            DormancyCheckResult(
                tenant_id="tenant-2",
                is_dormant=True,
                reasons=["No connectors"],
                has_connectors=False,
                has_slack_bot=False,
                document_count=0,
                usage_count=0,
                days_since_provisioning=10,
            )
        ]
        mock_scan_result.newly_marked = 1
        mock_scan_result.errors = []

        with (
            patch("src.cron.jobs.dormant_tenant_detection.is_detection_enabled", return_value=True),
            patch("src.cron.jobs.dormant_tenant_detection.is_dry_run_enabled", return_value=False),
            patch(
                "src.cron.jobs.dormant_tenant_detection.get_dormant_days_threshold", return_value=7
            ),
            patch("src.cron.jobs.dormant_tenant_detection.get_grace_period_days", return_value=14),
            patch(
                "src.cron.jobs.dormant_tenant_detection.is_auto_delete_enabled", return_value=False
            ),
            patch(
                "src.cron.jobs.dormant_tenant_detection.scan_for_dormant_tenants",
                return_value=mock_scan_result,
            ) as mock_scan,
            patch("src.cron.jobs.dormant_tenant_detection.logger") as mock_logger,
        ):
            await dormant_tenant_detection()

            # Should call scan with mark=True in live mode
            mock_scan.assert_called_once_with(mark=True)

            # Should NOT log dry-run mode message
            log_calls = [call[0][0] for call in mock_logger.info.call_args_list]
            assert not any("DRY RUN MODE" in msg for msg in log_calls)

            # Should log summary with newly_marked count
            summary_calls = [
                call
                for call in mock_logger.info.call_args_list
                if "completed" in call[0][0].lower()
            ]
            assert len(summary_calls) > 0
            summary_call = summary_calls[-1]  # Get the last "completed" log
            assert summary_call[1]["extra"]["dry_run"] is False
            assert summary_call[1]["extra"]["newly_marked"] == 1
            assert summary_call[1]["extra"].get("would_mark", 0) == 0

    @pytest.mark.asyncio
    async def test_auto_delete_dry_run_mode(self):
        """Test auto-delete in dry-run mode discovers resources but doesn't delete."""
        mock_scan_result = MagicMock()
        mock_scan_result.total_scanned = 0
        mock_scan_result.dormant_candidates = []
        mock_scan_result.newly_marked = 0
        mock_scan_result.errors = []

        expired_tenant = TenantInfo(
            id="expired-tenant-1",
            state="provisioned",
            provisioned_at=datetime.now(UTC) - timedelta(days=30),
            created_at=datetime.now(UTC) - timedelta(days=30),
            workos_org_id="org-123",
            is_dormant=True,
            dormant_detected_at=datetime.now(UTC) - timedelta(days=20),
        )

        mock_discovery = ResourceDiscoveryResult(
            tenant_id="expired-tenant-1",
            database_exists=True,
            database_name="db_expired-tenant-1",
            role_exists=True,
            role_name="expired-tenant-1_app_rw",
            opensearch_indices=["tenant-expired-tenant-1-v1"],
            turbopuffer_namespace_exists=False,
            ssm_parameters=["/expired-tenant-1/credentials/postgresql/db_name"],
            control_db_tenant_exists=True,
            control_db_related_counts={},
        )

        mock_control_pool = MagicMock()

        with (
            patch("src.cron.jobs.dormant_tenant_detection.is_detection_enabled", return_value=True),
            patch("src.cron.jobs.dormant_tenant_detection.is_dry_run_enabled", return_value=True),
            patch(
                "src.cron.jobs.dormant_tenant_detection.get_dormant_days_threshold", return_value=7
            ),
            patch("src.cron.jobs.dormant_tenant_detection.get_grace_period_days", return_value=14),
            patch(
                "src.cron.jobs.dormant_tenant_detection.is_auto_delete_enabled", return_value=True
            ),
            patch(
                "src.cron.jobs.dormant_tenant_detection.scan_for_dormant_tenants",
                return_value=mock_scan_result,
            ),
            patch("src.clients.tenant_db.tenant_db_manager") as mock_mgr,
            patch(
                "src.cron.jobs.dormant_tenant_detection.get_expired_dormant_tenants",
                return_value=[expired_tenant],
            ),
            patch(
                "src.cron.jobs.dormant_tenant_detection.discover_tenant_resources",
                return_value=mock_discovery,
            ) as mock_discover,
            patch(
                "src.cron.jobs.dormant_tenant_detection.hard_delete_tenant",
            ) as mock_delete,
            patch("src.cron.jobs.dormant_tenant_detection.logger") as mock_logger,
        ):
            mock_mgr.get_control_db = AsyncMock(return_value=mock_control_pool)

            await dormant_tenant_detection()

            # Should discover resources but NOT delete
            mock_discover.assert_called_once_with("expired-tenant-1")

            # Should NOT call hard_delete_tenant in dry-run mode
            mock_delete.assert_not_called()

            # Should log dry-run deletion message
            log_calls = [call[0][0] for call in mock_logger.info.call_args_list]
            assert any("DRY RUN: Would delete" in msg for msg in log_calls)

            # Should log resource discovery
            resource_log_calls = [
                call
                for call in mock_logger.info.call_args_list
                if "Resources for tenant" in call[0][0]
            ]
            assert len(resource_log_calls) == 1
            assert resource_log_calls[0][1]["extra"]["database_exists"] is True
            assert resource_log_calls[0][1]["extra"]["opensearch_indices"] == [
                "tenant-expired-tenant-1-v1"
            ]

            # Should log summary with would_delete count
            summary_calls = [
                call
                for call in mock_logger.info.call_args_list
                if "completed" in call[0][0].lower()
            ]
            assert len(summary_calls) > 0
            summary_call = summary_calls[-1]  # Get the last "completed" log
            assert summary_call[1]["extra"]["would_delete"] == 1
            assert summary_call[1]["extra"]["expired_deleted"] == 0

    @pytest.mark.asyncio
    async def test_auto_delete_live_mode(self):
        """Test auto-delete in live mode actually deletes tenants."""
        mock_scan_result = MagicMock()
        mock_scan_result.total_scanned = 0
        mock_scan_result.dormant_candidates = []
        mock_scan_result.newly_marked = 0
        mock_scan_result.errors = []

        expired_tenant = TenantInfo(
            id="expired-tenant-2",
            state="provisioned",
            provisioned_at=datetime.now(UTC) - timedelta(days=30),
            created_at=datetime.now(UTC) - timedelta(days=30),
            workos_org_id="org-456",
            is_dormant=True,
            dormant_detected_at=datetime.now(UTC) - timedelta(days=20),
        )

        mock_deletion_result = DeletionResult(
            tenant_id="expired-tenant-2",
            success=True,
            steps_completed=["PostgreSQL database deleted", "OpenSearch indices deleted"],
            steps_failed=[],
            errors=[],
        )

        mock_control_pool = MagicMock()

        with (
            patch("src.cron.jobs.dormant_tenant_detection.is_detection_enabled", return_value=True),
            patch("src.cron.jobs.dormant_tenant_detection.is_dry_run_enabled", return_value=False),
            patch(
                "src.cron.jobs.dormant_tenant_detection.get_dormant_days_threshold", return_value=7
            ),
            patch("src.cron.jobs.dormant_tenant_detection.get_grace_period_days", return_value=14),
            patch(
                "src.cron.jobs.dormant_tenant_detection.is_auto_delete_enabled", return_value=True
            ),
            patch(
                "src.cron.jobs.dormant_tenant_detection.scan_for_dormant_tenants",
                return_value=mock_scan_result,
            ),
            patch("src.clients.tenant_db.tenant_db_manager") as mock_mgr,
            patch(
                "src.cron.jobs.dormant_tenant_detection.get_expired_dormant_tenants",
                return_value=[expired_tenant],
            ),
            patch(
                "src.cron.jobs.dormant_tenant_detection.hard_delete_tenant",
                return_value=mock_deletion_result,
            ) as mock_delete,
            patch(
                "src.cron.jobs.dormant_tenant_detection.discover_tenant_resources",
            ) as mock_discover,
            patch("src.cron.jobs.dormant_tenant_detection.logger") as mock_logger,
        ):
            mock_mgr.get_control_db = AsyncMock(return_value=mock_control_pool)

            await dormant_tenant_detection()

            # Should actually delete the tenant
            mock_delete.assert_called_once_with("expired-tenant-2")

            # Should NOT discover resources in live mode (only in dry-run)
            mock_discover.assert_not_called()

            # Should log deletion message
            log_calls = [call[0][0] for call in mock_logger.info.call_args_list]
            assert any("Auto-deleting expired dormant tenant" in msg for msg in log_calls)

            # Should log summary with expired_deleted count
            summary_calls = [
                call
                for call in mock_logger.info.call_args_list
                if "completed" in call[0][0].lower()
            ]
            assert len(summary_calls) > 0
            summary_call = summary_calls[-1]  # Get the last "completed" log
            assert summary_call[1]["extra"]["expired_deleted"] == 1
            assert summary_call[1]["extra"].get("would_delete", 0) == 0

    @pytest.mark.asyncio
    async def test_auto_delete_disabled(self):
        """Test that auto-delete phase is skipped when disabled."""
        mock_scan_result = MagicMock()
        mock_scan_result.total_scanned = 5
        mock_scan_result.dormant_candidates = []
        mock_scan_result.newly_marked = 0
        mock_scan_result.errors = []

        with (
            patch("src.cron.jobs.dormant_tenant_detection.is_detection_enabled", return_value=True),
            patch("src.cron.jobs.dormant_tenant_detection.is_dry_run_enabled", return_value=False),
            patch(
                "src.cron.jobs.dormant_tenant_detection.get_dormant_days_threshold", return_value=7
            ),
            patch("src.cron.jobs.dormant_tenant_detection.get_grace_period_days", return_value=14),
            patch(
                "src.cron.jobs.dormant_tenant_detection.is_auto_delete_enabled", return_value=False
            ),
            patch(
                "src.cron.jobs.dormant_tenant_detection.scan_for_dormant_tenants",
                return_value=mock_scan_result,
            ),
            patch(
                "src.cron.jobs.dormant_tenant_detection.get_expired_dormant_tenants",
            ) as mock_get_expired,
            patch("src.cron.jobs.dormant_tenant_detection.logger") as mock_logger,
        ):
            await dormant_tenant_detection()

            # Should NOT fetch expired tenants when auto-delete is disabled
            mock_get_expired.assert_not_called()

            # Should log summary with 0 deleted
            summary_calls = [
                call
                for call in mock_logger.info.call_args_list
                if "completed" in call[0][0].lower()
            ]
            assert len(summary_calls) > 0
            summary_call = summary_calls[-1]  # Get the last "completed" log
            assert summary_call[1]["extra"]["expired_deleted"] == 0

    @pytest.mark.asyncio
    async def test_error_handling_scan_errors(self):
        """Test that scan errors are logged as warnings."""
        mock_scan_result = MagicMock()
        mock_scan_result.total_scanned = 10
        mock_scan_result.dormant_candidates = []
        mock_scan_result.newly_marked = 0
        mock_scan_result.errors = ["Error scanning tenant-1", "Error scanning tenant-2"]

        with (
            patch("src.cron.jobs.dormant_tenant_detection.is_detection_enabled", return_value=True),
            patch("src.cron.jobs.dormant_tenant_detection.is_dry_run_enabled", return_value=False),
            patch(
                "src.cron.jobs.dormant_tenant_detection.get_dormant_days_threshold", return_value=7
            ),
            patch("src.cron.jobs.dormant_tenant_detection.get_grace_period_days", return_value=14),
            patch(
                "src.cron.jobs.dormant_tenant_detection.is_auto_delete_enabled", return_value=False
            ),
            patch(
                "src.cron.jobs.dormant_tenant_detection.scan_for_dormant_tenants",
                return_value=mock_scan_result,
            ),
            patch("src.cron.jobs.dormant_tenant_detection.logger") as mock_logger,
        ):
            await dormant_tenant_detection()

            # Should log scan errors as warning
            warning_calls = list(mock_logger.warning.call_args_list)
            assert len(warning_calls) == 1
            assert "Scan errors encountered" in warning_calls[0][0][0]
            assert warning_calls[0][1]["extra"]["errors"] == mock_scan_result.errors

    @pytest.mark.asyncio
    async def test_error_handling_delete_errors(self):
        """Test that delete errors are logged as warnings."""
        mock_scan_result = MagicMock()
        mock_scan_result.total_scanned = 0
        mock_scan_result.dormant_candidates = []
        mock_scan_result.newly_marked = 0
        mock_scan_result.errors = []

        expired_tenant = TenantInfo(
            id="expired-tenant-3",
            state="provisioned",
            provisioned_at=datetime.now(UTC) - timedelta(days=30),
            created_at=datetime.now(UTC) - timedelta(days=30),
            workos_org_id="org-789",
            is_dormant=True,
            dormant_detected_at=datetime.now(UTC) - timedelta(days=20),
        )

        mock_deletion_result = DeletionResult(
            tenant_id="expired-tenant-3",
            success=False,
            steps_completed=["PostgreSQL database deleted"],
            steps_failed=["OpenSearch indices deletion"],
            errors=["Failed to delete OpenSearch indices"],
        )

        mock_control_pool = MagicMock()

        with (
            patch("src.cron.jobs.dormant_tenant_detection.is_detection_enabled", return_value=True),
            patch("src.cron.jobs.dormant_tenant_detection.is_dry_run_enabled", return_value=False),
            patch(
                "src.cron.jobs.dormant_tenant_detection.get_dormant_days_threshold", return_value=7
            ),
            patch("src.cron.jobs.dormant_tenant_detection.get_grace_period_days", return_value=14),
            patch(
                "src.cron.jobs.dormant_tenant_detection.is_auto_delete_enabled", return_value=True
            ),
            patch(
                "src.cron.jobs.dormant_tenant_detection.scan_for_dormant_tenants",
                return_value=mock_scan_result,
            ),
            patch("src.clients.tenant_db.tenant_db_manager") as mock_mgr,
            patch(
                "src.cron.jobs.dormant_tenant_detection.get_expired_dormant_tenants",
                return_value=[expired_tenant],
            ),
            patch(
                "src.cron.jobs.dormant_tenant_detection.hard_delete_tenant",
                return_value=mock_deletion_result,
            ),
            patch("src.cron.jobs.dormant_tenant_detection.logger") as mock_logger,
        ):
            mock_mgr.get_control_db = AsyncMock(return_value=mock_control_pool)

            await dormant_tenant_detection()

            # Should log delete errors as warning
            warning_calls = list(mock_logger.warning.call_args_list)
            assert len(warning_calls) == 1
            assert "Delete errors encountered" in warning_calls[0][0][0]
            assert len(warning_calls[0][1]["extra"]["errors"]) == 1
            assert "expired-tenant-3" in warning_calls[0][1]["extra"]["errors"][0]

    @pytest.mark.asyncio
    async def test_resource_discovery_error_handling(self):
        """Test that resource discovery errors in dry-run are handled gracefully."""
        mock_scan_result = MagicMock()
        mock_scan_result.total_scanned = 0
        mock_scan_result.dormant_candidates = []
        mock_scan_result.newly_marked = 0
        mock_scan_result.errors = []

        expired_tenant = TenantInfo(
            id="expired-tenant-4",
            state="provisioned",
            provisioned_at=datetime.now(UTC) - timedelta(days=30),
            created_at=datetime.now(UTC) - timedelta(days=30),
            workos_org_id="org-999",
            is_dormant=True,
            dormant_detected_at=datetime.now(UTC) - timedelta(days=20),
        )

        mock_control_pool = MagicMock()

        with (
            patch("src.cron.jobs.dormant_tenant_detection.is_detection_enabled", return_value=True),
            patch("src.cron.jobs.dormant_tenant_detection.is_dry_run_enabled", return_value=True),
            patch(
                "src.cron.jobs.dormant_tenant_detection.get_dormant_days_threshold", return_value=7
            ),
            patch("src.cron.jobs.dormant_tenant_detection.get_grace_period_days", return_value=14),
            patch(
                "src.cron.jobs.dormant_tenant_detection.is_auto_delete_enabled", return_value=True
            ),
            patch(
                "src.cron.jobs.dormant_tenant_detection.scan_for_dormant_tenants",
                return_value=mock_scan_result,
            ),
            patch("src.clients.tenant_db.tenant_db_manager") as mock_mgr,
            patch(
                "src.cron.jobs.dormant_tenant_detection.get_expired_dormant_tenants",
                return_value=[expired_tenant],
            ),
            patch(
                "src.cron.jobs.dormant_tenant_detection.discover_tenant_resources",
                side_effect=Exception("Discovery failed"),
            ),
            patch("src.cron.jobs.dormant_tenant_detection.logger") as mock_logger,
        ):
            mock_mgr.get_control_db = AsyncMock(return_value=mock_control_pool)

            await dormant_tenant_detection()

            # Should log warning about discovery failure
            warning_calls = list(mock_logger.warning.call_args_list)
            assert len(warning_calls) == 1
            assert "Failed to discover resources" in warning_calls[0][0][0]
            assert "expired-tenant-4" in warning_calls[0][0][0]

    @pytest.mark.asyncio
    async def test_multiple_expired_tenants(self):
        """Test handling multiple expired tenants."""
        mock_scan_result = MagicMock()
        mock_scan_result.total_scanned = 0
        mock_scan_result.dormant_candidates = []
        mock_scan_result.newly_marked = 0
        mock_scan_result.errors = []

        expired_tenants = [
            TenantInfo(
                id=f"expired-tenant-{i}",
                state="provisioned",
                provisioned_at=datetime.now(UTC) - timedelta(days=30),
                created_at=datetime.now(UTC) - timedelta(days=30),
                workos_org_id=f"org-{i}",
                is_dormant=True,
                dormant_detected_at=datetime.now(UTC) - timedelta(days=20),
            )
            for i in range(3)
        ]

        mock_deletion_results = [
            DeletionResult(
                tenant_id=f"expired-tenant-{i}",
                success=True,
                steps_completed=["All resources deleted"],
                steps_failed=[],
                errors=[],
            )
            for i in range(3)
        ]

        mock_control_pool = MagicMock()

        with (
            patch("src.cron.jobs.dormant_tenant_detection.is_detection_enabled", return_value=True),
            patch("src.cron.jobs.dormant_tenant_detection.is_dry_run_enabled", return_value=False),
            patch(
                "src.cron.jobs.dormant_tenant_detection.get_dormant_days_threshold", return_value=7
            ),
            patch("src.cron.jobs.dormant_tenant_detection.get_grace_period_days", return_value=14),
            patch(
                "src.cron.jobs.dormant_tenant_detection.is_auto_delete_enabled", return_value=True
            ),
            patch(
                "src.cron.jobs.dormant_tenant_detection.scan_for_dormant_tenants",
                return_value=mock_scan_result,
            ),
            patch("src.clients.tenant_db.tenant_db_manager") as mock_mgr,
            patch(
                "src.cron.jobs.dormant_tenant_detection.get_expired_dormant_tenants",
                return_value=expired_tenants,
            ),
            patch(
                "src.cron.jobs.dormant_tenant_detection.hard_delete_tenant",
                side_effect=mock_deletion_results,
            ) as mock_delete,
            patch("src.cron.jobs.dormant_tenant_detection.logger") as mock_logger,
        ):
            mock_mgr.get_control_db = AsyncMock(return_value=mock_control_pool)

            await dormant_tenant_detection()

            # Should delete all 3 tenants
            assert mock_delete.call_count == 3

            # Should log summary with 3 deleted
            summary_calls = [
                call
                for call in mock_logger.info.call_args_list
                if "completed" in call[0][0].lower()
            ]
            assert len(summary_calls) > 0
            summary_call = summary_calls[-1]  # Get the last "completed" log
            assert summary_call[1]["extra"]["expired_deleted"] == 3


class TestDBFetchErrorHandling:
    """Test suite for DB fetch error handling in dormant tenant detection.

    These tests verify that tenants with database connectivity issues are NOT
    incorrectly marked as dormant. This is a critical fail-safe to prevent
    active tenants from being marked dormant during transient DB issues.
    """

    @pytest.mark.asyncio
    async def test_db_fetch_error_excludes_tenant_from_dormancy(self):
        """Test that tenants with DB fetch errors are excluded from dormancy check.

        When _fetch_tenant_db_data fails for a tenant, that tenant should be
        excluded from dormancy consideration entirely - NOT marked dormant with
        default values (document_count=0, usage_count=0).
        """
        # Create test tenants - none have connectors or slack bot
        test_tenants = [
            TenantInfo(
                id="tenant-healthy",
                state="provisioned",
                provisioned_at=datetime.now(UTC) - timedelta(days=10),
                created_at=datetime.now(UTC) - timedelta(days=10),
                workos_org_id="org-healthy",
                is_dormant=False,
                dormant_detected_at=None,
            ),
            TenantInfo(
                id="tenant-with-db-error",
                state="provisioned",
                provisioned_at=datetime.now(UTC) - timedelta(days=10),
                created_at=datetime.now(UTC) - timedelta(days=10),
                workos_org_id="org-db-error",
                is_dormant=False,
                dormant_detected_at=None,
            ),
        ]

        # Control data: neither tenant has connectors or slack
        mock_control_data = _BatchedControlData(
            tenants_with_connectors=set(),
            tenants_with_slack_bot=set(),
        )

        # DB data for healthy tenant: truly dormant (no docs, no usage)
        healthy_db_data = _TenantDBData(document_count=0, usage_count=0, company_name="Healthy Co")

        # Mock functions to simulate DB error for one tenant
        async def mock_fetch_tenant_db_data(tenant_id: str) -> _TenantDBData:
            if tenant_id == "tenant-with-db-error":
                raise ConnectionError("Database connection failed")
            return healthy_db_data

        mock_control_pool = AsyncMock()

        with (
            patch("src.dormant.service.tenant_db_manager") as mock_manager,
            patch("src.dormant.service.get_all_provisioned_tenants", return_value=test_tenants),
            patch("src.dormant.service._batch_fetch_control_data", return_value=mock_control_data),
            patch(
                "src.dormant.service._fetch_tenant_db_data",
                side_effect=mock_fetch_tenant_db_data,
            ),
            patch("src.dormant.service.get_dormant_days_threshold", return_value=7),
            patch("src.dormant.service.mark_tenant_dormant", return_value=True),
            patch("src.dormant.service.logger"),
        ):
            mock_manager.get_control_db = AsyncMock(return_value=mock_control_pool)

            result = await scan_for_dormant_tenants(mark=False)

            # Only healthy tenant should be in dormant candidates
            # tenant-with-db-error should be EXCLUDED (not marked dormant with defaults)
            assert len(result.dormant_candidates) == 1
            assert result.dormant_candidates[0].tenant_id == "tenant-healthy"

            # Should have one error recorded
            assert len(result.errors) == 1
            assert "tenant-with-db-error" in result.errors[0]
            assert "Database connection failed" in result.errors[0]

    @pytest.mark.asyncio
    async def test_active_tenant_not_marked_dormant_on_db_error(self):
        """Test that an active tenant is NOT incorrectly marked dormant on DB error.

        This is the critical safety test: if a tenant has documents and usage,
        but we can't read them due to a transient DB error, the tenant should
        NOT appear in the dormant candidates list.
        """
        # Active tenant with real documents/usage (but we'll simulate DB error)
        active_tenant = TenantInfo(
            id="active-tenant",
            state="provisioned",
            provisioned_at=datetime.now(UTC) - timedelta(days=30),
            created_at=datetime.now(UTC) - timedelta(days=30),
            workos_org_id="org-active",
            is_dormant=False,
            dormant_detected_at=None,
        )

        # No connectors or slack - would look dormant if we used default values
        mock_control_data = _BatchedControlData(
            tenants_with_connectors=set(),
            tenants_with_slack_bot=set(),
        )

        mock_control_pool = AsyncMock()

        with (
            patch("src.dormant.service.tenant_db_manager") as mock_manager,
            patch("src.dormant.service.get_all_provisioned_tenants", return_value=[active_tenant]),
            patch("src.dormant.service._batch_fetch_control_data", return_value=mock_control_data),
            patch(
                "src.dormant.service._fetch_tenant_db_data",
                side_effect=Exception("Timeout connecting to tenant DB"),
            ),
            patch("src.dormant.service.get_dormant_days_threshold", return_value=7),
            patch("src.dormant.service.logger"),
        ):
            mock_manager.get_control_db = AsyncMock(return_value=mock_control_pool)

            result = await scan_for_dormant_tenants(mark=False)

            # CRITICAL: Active tenant should NOT be in dormant candidates
            # Even though default values (0 docs, 0 usage) would make it appear dormant
            assert len(result.dormant_candidates) == 0

            # Error should be recorded
            assert len(result.errors) == 1
            assert "active-tenant" in result.errors[0]

    @pytest.mark.asyncio
    async def test_partial_db_failures_only_exclude_failed_tenants(self):
        """Test that only tenants with actual DB failures are excluded.

        If some tenants have DB errors, only those should be excluded.
        Tenants with successful DB queries should still be evaluated normally.
        """
        tenants = [
            TenantInfo(
                id=f"tenant-{i}",
                state="provisioned",
                provisioned_at=datetime.now(UTC) - timedelta(days=10),
                created_at=datetime.now(UTC) - timedelta(days=10),
                workos_org_id=f"org-{i}",
                is_dormant=False,
                dormant_detected_at=None,
            )
            for i in range(5)
        ]

        mock_control_data = _BatchedControlData(
            tenants_with_connectors=set(),
            tenants_with_slack_bot=set(),
        )

        # Tenants 1 and 3 have DB errors, others succeed with dormant-looking data
        async def mock_fetch(tenant_id: str) -> _TenantDBData:
            if tenant_id in ("tenant-1", "tenant-3"):
                raise Exception(f"DB error for {tenant_id}")
            return _TenantDBData(document_count=0, usage_count=0, company_name=None)

        mock_control_pool = AsyncMock()

        with (
            patch("src.dormant.service.tenant_db_manager") as mock_manager,
            patch("src.dormant.service.get_all_provisioned_tenants", return_value=tenants),
            patch("src.dormant.service._batch_fetch_control_data", return_value=mock_control_data),
            patch("src.dormant.service._fetch_tenant_db_data", side_effect=mock_fetch),
            patch("src.dormant.service.get_dormant_days_threshold", return_value=7),
            patch("src.dormant.service.logger"),
        ):
            mock_manager.get_control_db = AsyncMock(return_value=mock_control_pool)

            result = await scan_for_dormant_tenants(mark=False)

            # Only 3 tenants (0, 2, 4) should be dormant candidates
            # Tenants 1 and 3 should be excluded due to DB errors
            dormant_ids = {c.tenant_id for c in result.dormant_candidates}
            assert dormant_ids == {"tenant-0", "tenant-2", "tenant-4"}

            # Should have 2 errors
            assert len(result.errors) == 2
            error_text = " ".join(result.errors)
            assert "tenant-1" in error_text
            assert "tenant-3" in error_text
