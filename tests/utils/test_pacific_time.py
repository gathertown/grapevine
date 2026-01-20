"""Tests for Pacific Time utilities."""

from datetime import date

import pytest

from src.utils.pacific_time import (
    format_pacific_time,
    get_message_pacific_document_id,
    get_pacific_day_boundaries,
    get_pacific_day_boundaries_timestamps,
    is_timestamp_in_pacific_day,
    timestamp_to_pacific_date,
)


class TestPacificTimeUtilities:
    """Test Pacific Time conversion utilities."""

    def test_timestamp_to_pacific_date(self):
        """Test converting Unix timestamp to Pacific date."""
        # Test winter time (PST)
        # January 15, 2024 12:00:00 UTC = January 15, 2024 04:00:00 PST
        winter_ts = 1705320000.0
        result = timestamp_to_pacific_date(winter_ts)
        assert result == date(2024, 1, 15)

        # Test summer time (PDT)
        # July 15, 2024 12:00:00 UTC = July 15, 2024 05:00:00 PDT
        summer_ts = 1721044800.0
        result = timestamp_to_pacific_date(summer_ts)
        assert result == date(2024, 7, 15)

        # Test timestamp as string
        result = timestamp_to_pacific_date("1705320000.123456")
        assert result == date(2024, 1, 15)

    def test_timestamp_to_pacific_date_edge_cases(self):
        """Test edge cases for timestamp conversion."""
        # Test midnight UTC crossing date boundary
        # January 16, 2024 02:00:00 UTC = January 15, 2024 18:00:00 PST (previous day)
        midnight_edge_ts = 1705370400.0
        result = timestamp_to_pacific_date(midnight_edge_ts)
        assert result == date(2024, 1, 15)  # Should be previous day in PT

        # Test invalid timestamp
        with pytest.raises(ValueError):
            timestamp_to_pacific_date("invalid")

    def test_get_pacific_day_boundaries(self):
        """Test getting Pacific day boundaries in UTC."""
        # Test winter day (PST)
        start_dt, end_dt = get_pacific_day_boundaries("2024-01-15")

        # January 15, 2024 00:00:00 PST = January 15, 2024 08:00:00 UTC
        assert start_dt.hour == 8
        assert start_dt.minute == 0
        assert start_dt.second == 0
        assert start_dt.date() == date(2024, 1, 15)

        # January 15, 2024 23:59:59 PST = January 16, 2024 07:59:59 UTC
        assert end_dt.hour == 7
        assert end_dt.minute == 59
        assert end_dt.second == 59
        assert end_dt.date() == date(2024, 1, 16)

        # Test summer day (PDT)
        start_dt, end_dt = get_pacific_day_boundaries("2024-07-15")

        # July 15, 2024 00:00:00 PDT = July 15, 2024 07:00:00 UTC
        assert start_dt.hour == 7
        assert start_dt.minute == 0
        assert start_dt.second == 0
        assert start_dt.date() == date(2024, 7, 15)

    def test_get_pacific_day_boundaries_timestamps(self):
        """Test getting Pacific day boundaries as timestamps."""
        start_ts, end_ts = get_pacific_day_boundaries_timestamps("2024-01-15")

        assert isinstance(start_ts, float)
        assert isinstance(end_ts, float)
        assert end_ts > start_ts

        # Should be approximately 24 hours apart
        diff_hours = (end_ts - start_ts) / 3600
        assert 23.9 < diff_hours < 24.1  # Allow for microsecond precision

    def test_get_pacific_day_boundaries_invalid_date(self):
        """Test error handling for invalid dates."""
        with pytest.raises(ValueError, match="Invalid date format"):
            get_pacific_day_boundaries("invalid-date")

        with pytest.raises(ValueError, match="Invalid date format"):
            get_pacific_day_boundaries("2024-13-45")  # Invalid month/day

    def test_is_timestamp_in_pacific_day(self):
        """Test checking if timestamp falls within Pacific day."""
        # Test timestamp that should be in the day
        # January 15, 2024 15:00:00 PST = January 15, 2024 23:00:00 UTC
        ts_in_day = 1705359600.0
        assert is_timestamp_in_pacific_day(ts_in_day, "2024-01-15") == True

        # Test timestamp that should NOT be in the day (next day)
        # January 16, 2024 01:00:00 PST = January 16, 2024 09:00:00 UTC
        ts_next_day = 1705402800.0
        assert is_timestamp_in_pacific_day(ts_next_day, "2024-01-15") == False

        # Test with string timestamp
        assert is_timestamp_in_pacific_day("1705359600.0", "2024-01-15") == True

        # Test invalid timestamp
        assert is_timestamp_in_pacific_day("invalid", "2024-01-15") == False

    def test_format_pacific_time(self):
        """Test formatting timestamp as Pacific time string."""
        # Test winter time (PST)
        winter_ts = 1705320000.0  # January 15, 2024 12:00:00 UTC
        result = format_pacific_time(winter_ts)
        assert "2024-01-15" in result
        assert "04:00:00" in result
        assert "PST" in result

        # Test summer time (PDT)
        summer_ts = 1721044800.0  # July 15, 2024 12:00:00 UTC
        result = format_pacific_time(summer_ts)
        assert "2024-07-15" in result
        assert "05:00:00" in result
        assert "PDT" in result

        # Test with string timestamp
        result = format_pacific_time("1705320000.123")
        assert "2024-01-15" in result
        assert "PST" in result

    def test_format_pacific_time_invalid(self):
        """Test error handling for invalid timestamps in formatting."""
        with pytest.raises(ValueError):
            format_pacific_time("invalid")

    def test_get_message_pacific_document_id(self):
        """Test generating document IDs based on Pacific time."""
        channel_id = "C12345678"

        # Test winter timestamp
        winter_ts = 1705320000.0  # January 15, 2024 04:00:00 PST
        doc_id = get_message_pacific_document_id(channel_id, winter_ts)
        assert doc_id == "C12345678_2024-01-15"

        # Test summer timestamp
        summer_ts = 1721044800.0  # July 15, 2024 05:00:00 PDT
        doc_id = get_message_pacific_document_id(channel_id, summer_ts)
        assert doc_id == "C12345678_2024-07-15"

        # Test with string timestamp
        doc_id = get_message_pacific_document_id(channel_id, "1705320000.123")
        assert doc_id == "C12345678_2024-01-15"

        # Test cross-day boundary case
        # UTC timestamp that should map to previous PT day
        boundary_ts = 1705370400.0  # January 16, 2024 02:00:00 UTC = January 15, 2024 18:00:00 PST
        doc_id = get_message_pacific_document_id(channel_id, boundary_ts)
        assert doc_id == "C12345678_2024-01-15"  # Should be previous day

    def test_get_message_pacific_document_id_invalid(self):
        """Test error handling for invalid timestamps in document ID generation."""
        with pytest.raises(ValueError):
            get_message_pacific_document_id("C12345678", "invalid")

    def test_dst_transition_spring(self):
        """Test Pacific Time handling during spring DST transition."""
        # Spring DST transition 2024: March 10, 2024 at 2:00 AM PST -> 3:00 AM PDT
        # Test day before transition
        before_dst = get_pacific_day_boundaries("2024-03-09")
        start_before, end_before = before_dst

        # Test day of transition
        transition_day = get_pacific_day_boundaries("2024-03-10")
        start_transition, end_transition = transition_day

        # Day should still be valid and boundaries should work
        assert start_transition < end_transition

        # Test day after transition
        after_dst = get_pacific_day_boundaries("2024-03-11")
        start_after, end_after = after_dst
        assert start_after < end_after

    def test_dst_transition_fall(self):
        """Test Pacific Time handling during fall DST transition."""
        # Fall DST transition 2024: November 3, 2024 at 2:00 AM PDT -> 1:00 AM PST
        # Test day before transition
        before_dst = get_pacific_day_boundaries("2024-11-02")
        start_before, end_before = before_dst

        # Test day of transition
        transition_day = get_pacific_day_boundaries("2024-11-03")
        start_transition, end_transition = transition_day

        # Day should still be valid and boundaries should work
        assert start_transition < end_transition

        # Test day after transition
        after_dst = get_pacific_day_boundaries("2024-11-04")
        start_after, end_after = after_dst
        assert start_after < end_after
