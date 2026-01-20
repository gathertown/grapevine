"""
Tests for usage tracker functionality.
"""

from datetime import UTC, datetime
from unittest.mock import patch

import pytest

from src.utils.usage_tracker import (
    UsageTracker,
    get_usage_tracker,
)


class TestUsageTracker:
    """Test cases for UsageTracker class."""

    def test_init(self):
        """Test UsageTracker initialization."""
        tracker = UsageTracker()
        assert tracker is not None

    def test_record_usage_valid(self):
        """Test recording valid usage."""
        tracker = UsageTracker()

        # Should not raise any exceptions
        tracker.record_usage(
            tenant_id="test-tenant", metric_type="requests", metric_value=1, source_type="ask_agent"
        )

    def test_record_usage_with_details(self):
        """Test recording usage with source details."""
        tracker = UsageTracker()

        source_details = {"model": "gpt-4", "endpoint": "/api/ask"}

        tracker.record_usage(
            tenant_id="test-tenant",
            metric_type="input_tokens",
            metric_value=150,
            source_type="ask_agent",
            source_details=source_details,
        )

    def test_record_usage_invalid_metric_type(self):
        """Test recording usage with invalid metric type."""
        tracker = UsageTracker()

        with pytest.raises(ValueError, match="Invalid metric_type"):
            tracker.record_usage(
                tenant_id="test-tenant",
                metric_type="invalid_metric",
                metric_value=1,
                source_type="ask_agent",
            )

    def test_record_usage_invalid_source_type(self):
        """Test recording usage with invalid source type."""
        tracker = UsageTracker()

        with pytest.raises(ValueError, match="Invalid source_type"):
            tracker.record_usage(
                tenant_id="test-tenant",
                metric_type="requests",
                metric_value=1,
                source_type="invalid_source",
            )

    def test_record_usage_negative_value(self):
        """Test recording usage with negative value."""
        tracker = UsageTracker()

        with pytest.raises(ValueError, match="metric_value must be non-negative"):
            tracker.record_usage(
                tenant_id="test-tenant",
                metric_type="requests",
                metric_value=-1,
                source_type="ask_agent",
            )

    def test_record_usage_empty_tenant_id(self):
        """Test recording usage with empty tenant ID."""
        tracker = UsageTracker()

        with pytest.raises(ValueError, match="tenant_id is required"):
            tracker.record_usage(
                tenant_id="", metric_type="requests", metric_value=1, source_type="ask_agent"
            )

    @pytest.mark.asyncio
    async def test_get_monthly_usage(self):
        """Test getting monthly usage (currently returns 0)."""
        tracker = UsageTracker()

        usage = await tracker.get_monthly_usage("test-tenant", "requests")
        assert usage == 0

    @pytest.mark.asyncio
    async def test_get_monthly_usage_invalid_metric(self):
        """Test getting monthly usage with invalid metric type."""
        tracker = UsageTracker()

        with pytest.raises(ValueError, match="Invalid metric_type"):
            await tracker.get_monthly_usage("test-tenant", "invalid_metric")


class TestGetUsageTracker:
    """Test cases for get_usage_tracker singleton."""

    def test_singleton_behavior(self):
        """Test that get_usage_tracker returns the same instance."""
        tracker1 = get_usage_tracker()
        tracker2 = get_usage_tracker()

        assert tracker1 is tracker2
        assert isinstance(tracker1, UsageTracker)


class TestBillingPeriodCalculation:
    """Test cases for _calculate_current_billing_period method."""

    @patch("src.utils.usage_tracker.datetime")
    def test_same_month_before_anchor_day(self, mock_datetime):
        """Test billing period when current date is before anchor day in same month."""
        tracker = UsageTracker()

        # Anchor on 15th, current date on 10th - should return previous month's period
        anchor = datetime(2024, 3, 15, 10, 0, 0, tzinfo=UTC)
        mock_datetime.now.return_value = datetime(2024, 3, 10, 12, 0, 0, tzinfo=UTC)

        result = tracker._calculate_current_billing_period(anchor)
        expected = datetime(2024, 2, 15, 10, 0, 0, tzinfo=UTC)
        assert result == expected

    @patch("src.utils.usage_tracker.datetime")
    def test_same_month_after_anchor_day(self, mock_datetime):
        """Test billing period when current date is after anchor day in same month."""
        tracker = UsageTracker()

        # Anchor on 15th, current date on 20th - should return current month's period
        anchor = datetime(2024, 3, 15, 10, 0, 0, tzinfo=UTC)
        mock_datetime.now.return_value = datetime(2024, 3, 20, 12, 0, 0, tzinfo=UTC)

        result = tracker._calculate_current_billing_period(anchor)
        expected = datetime(2024, 3, 15, 10, 0, 0, tzinfo=UTC)
        assert result == expected

    @patch("src.utils.usage_tracker.datetime")
    def test_year_boundary_crossing(self, mock_datetime):
        """Test billing period calculation across year boundaries."""
        tracker = UsageTracker()

        # Anchor in December, current in February next year
        anchor = datetime(2023, 12, 15, 10, 0, 0, tzinfo=UTC)
        mock_datetime.now.return_value = datetime(2024, 2, 20, 12, 0, 0, tzinfo=UTC)

        result = tracker._calculate_current_billing_period(anchor)
        expected = datetime(2024, 2, 15, 10, 0, 0, tzinfo=UTC)
        assert result == expected
