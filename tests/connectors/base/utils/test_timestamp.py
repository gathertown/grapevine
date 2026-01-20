from datetime import UTC, datetime

import pytest

from connectors.base.utils import convert_timestamp_to_iso, parse_iso_timestamp


class TestParseIsoTimestamp:
    def test_standard_iso_format(self):
        result = parse_iso_timestamp("2024-01-15T10:30:00+00:00")
        assert result == datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC)

    def test_z_suffix(self):
        result = parse_iso_timestamp("2024-01-15T10:30:00Z")
        assert result == datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC)

    def test_with_milliseconds_z_suffix(self):
        result = parse_iso_timestamp("2024-01-15T10:30:00.123Z")
        assert result == datetime(2024, 1, 15, 10, 30, 0, 123000, tzinfo=UTC)

    def test_with_offset(self):
        result = parse_iso_timestamp("2024-01-15T10:30:00-05:00")
        assert result.hour == 10
        utcoffset = result.utcoffset()
        assert utcoffset is not None
        assert utcoffset.total_seconds() == -5 * 3600

    def test_invalid_format_raises(self):
        with pytest.raises(ValueError):
            parse_iso_timestamp("not-a-timestamp")


class TestConvertTimestampToIso:
    def test_none_returns_none(self):
        assert convert_timestamp_to_iso(None) is None

    def test_iso_string_passthrough(self):
        iso_str = "2024-01-15T10:30:00+00:00"
        assert convert_timestamp_to_iso(iso_str) == iso_str

    def test_date_string_passthrough(self):
        date_str = "2024-01-15"
        assert convert_timestamp_to_iso(date_str) == date_str

    def test_datetime_with_space_converted_to_iso(self):
        # Pipedrive format: "YYYY-MM-DD HH:MM:SS"
        result = convert_timestamp_to_iso("2024-01-15 10:30:00")
        assert result == "2024-01-15T10:30:00"

    def test_unix_epoch_int(self):
        # 1705315800 = 2024-01-15T10:30:00+00:00
        result = convert_timestamp_to_iso(1705315800)
        assert result is not None
        assert "2024-01-15" in result
        assert "T" in result

    def test_unix_epoch_float(self):
        result = convert_timestamp_to_iso(1705315800.5)
        assert result is not None
        assert "2024-01-15" in result

    def test_unix_epoch_string(self):
        result = convert_timestamp_to_iso("1705315800")
        assert result is not None
        assert "2024-01-15" in result

    def test_non_numeric_string_passthrough(self):
        result = convert_timestamp_to_iso("some random string")
        assert result == "some random string"

    def test_other_types_converted_to_string(self):
        result = convert_timestamp_to_iso(["not", "a", "timestamp"])
        assert result == "['not', 'a', 'timestamp']"

    def test_empty_string(self):
        # Empty string doesn't contain T or -, and can't be parsed as int
        result = convert_timestamp_to_iso("")
        assert result == ""

    def test_zero_epoch(self):
        # Unix epoch 0 = 1970-01-01T00:00:00+00:00
        result = convert_timestamp_to_iso(0)
        assert result is not None
        assert "1970-01-01" in result
