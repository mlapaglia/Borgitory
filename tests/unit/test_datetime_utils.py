"""
Tests for datetime_utils - Timezone handling utilities
"""

import os
from datetime import datetime, timezone, timedelta, UTC
from unittest.mock import patch

from borgitory.utils.datetime_utils import (
    parse_datetime_string,
    get_server_timezone,
    format_datetime_for_display,
    parse_timezone_offset,
    now_utc,
    ensure_utc,
)


class TestParseDatetimeString:
    """Test datetime string parsing"""

    def test_parse_datetime_with_z_suffix(self) -> None:
        """Test parsing ISO datetime with Z suffix"""
        dt_string = "2023-01-15T14:30:45Z"
        result = parse_datetime_string(dt_string)

        assert result is not None
        assert result.year == 2023
        assert result.month == 1
        assert result.day == 15
        assert result.hour == 14
        assert result.minute == 30
        assert result.second == 45
        assert result.tzinfo == timezone.utc

    def test_parse_datetime_with_timezone_offset(self) -> None:
        """Test parsing ISO datetime with timezone offset"""
        dt_string = "2023-01-15T14:30:45+05:30"
        result = parse_datetime_string(dt_string)

        assert result is not None
        assert result.year == 2023
        assert result.month == 1
        assert result.day == 15
        assert result.hour == 14
        assert result.minute == 30
        assert result.second == 45
        # Check timezone offset
        assert result.tzinfo == timezone(timedelta(hours=5, minutes=30))

    def test_parse_datetime_with_negative_offset(self) -> None:
        """Test parsing ISO datetime with negative timezone offset"""
        dt_string = "2023-01-15T14:30:45-08:00"
        result = parse_datetime_string(dt_string)

        assert result is not None
        assert result.tzinfo == timezone(timedelta(hours=-8))

    def test_parse_datetime_without_timezone(self) -> None:
        """Test parsing ISO datetime without timezone info"""
        dt_string = "2023-01-15T14:30:45"
        result = parse_datetime_string(dt_string)

        assert result is not None
        assert result.year == 2023
        assert result.month == 1
        assert result.day == 15
        assert result.hour == 14
        assert result.minute == 30
        assert result.second == 45
        # Should be timezone-naive
        assert result.tzinfo is None

    def test_parse_datetime_with_microseconds(self) -> None:
        """Test parsing datetime with microseconds"""
        dt_string = "2023-01-15T14:30:45.123456Z"
        result = parse_datetime_string(dt_string)

        assert result is not None
        assert result.microsecond == 123456
        assert result.tzinfo == timezone.utc

    def test_parse_datetime_empty_string(self) -> None:
        """Test parsing empty string"""
        assert parse_datetime_string("") is None
        assert parse_datetime_string("   ") is None

    def test_parse_datetime_none_input(self) -> None:
        """Test parsing None input"""
        assert parse_datetime_string(None) is None

    def test_parse_datetime_non_string_input(self) -> None:
        """Test parsing non-string input"""
        assert parse_datetime_string(123) is None
        assert parse_datetime_string([]) is None

    def test_parse_datetime_invalid_format(self) -> None:
        """Test parsing invalid datetime format"""
        assert parse_datetime_string("not-a-date") is None
        assert parse_datetime_string("2023-13-45T25:70:70Z") is None
        assert parse_datetime_string("2023/01/15 14:30:45") is None

    def test_parse_datetime_strips_whitespace(self) -> None:
        """Test that whitespace is stripped from input"""
        dt_string = "  2023-01-15T14:30:45Z  "
        result = parse_datetime_string(dt_string)

        assert result is not None
        assert result.year == 2023


class TestGetServerTimezone:
    """Test server timezone configuration"""

    def test_get_server_timezone_default_utc(self) -> None:
        """Test default timezone is UTC"""
        with patch.dict(os.environ, {}, clear=True):
            tz = get_server_timezone()
            assert tz == UTC

    def test_get_server_timezone_utc_env_var(self) -> None:
        """Test UTC timezone from environment variable"""
        with patch.dict(os.environ, {"BORGITORY_TIMEZONE": "UTC"}):
            tz = get_server_timezone()
            assert tz == UTC

    def test_get_server_timezone_utc_lowercase(self) -> None:
        """Test UTC timezone case insensitive"""
        with patch.dict(os.environ, {"BORGITORY_TIMEZONE": "utc"}):
            tz = get_server_timezone()
            assert tz == UTC

    def test_get_server_timezone_positive_offset(self) -> None:
        """Test positive timezone offset"""
        with patch.dict(os.environ, {"BORGITORY_TIMEZONE": "+05:30"}):
            tz = get_server_timezone()
            expected = timezone(timedelta(hours=5, minutes=30))
            assert tz == expected

    def test_get_server_timezone_negative_offset(self) -> None:
        """Test negative timezone offset"""
        with patch.dict(os.environ, {"BORGITORY_TIMEZONE": "-08:00"}):
            tz = get_server_timezone()
            expected = timezone(timedelta(hours=-8))
            assert tz == expected

    def test_get_server_timezone_invalid_format(self) -> None:
        """Test invalid timezone format falls back to UTC"""
        with patch.dict(os.environ, {"BORGITORY_TIMEZONE": "invalid"}):
            tz = get_server_timezone()
            assert tz == UTC

    def test_get_server_timezone_invalid_offset(self) -> None:
        """Test invalid offset format falls back to UTC"""
        with patch.dict(os.environ, {"BORGITORY_TIMEZONE": "+25:70"}):
            tz = get_server_timezone()
            assert tz == UTC


class TestFormatDatetimeForDisplay:
    """Test datetime formatting for display"""

    def test_format_datetime_default_format(self) -> None:
        """Test default datetime formatting"""
        dt = datetime(2023, 1, 15, 14, 30, 45, tzinfo=UTC)
        result = format_datetime_for_display(dt)
        assert result == "2023-01-15 14:30:45"

    def test_format_datetime_custom_format(self) -> None:
        """Test custom datetime formatting"""
        dt = datetime(2023, 1, 15, 14, 30, 45, tzinfo=UTC)
        result = format_datetime_for_display(dt, "%Y/%m/%d %H:%M")
        assert result == "2023/01/15 14:30"

    def test_format_datetime_none_input(self) -> None:
        """Test formatting None datetime"""
        result = format_datetime_for_display(None)
        assert result == "N/A"

    def test_format_datetime_empty_input(self) -> None:
        """Test formatting empty datetime"""
        result = format_datetime_for_display("")
        assert result == "N/A"

    def test_format_datetime_naive_to_utc(self) -> None:
        """Test naive datetime is treated as UTC"""
        dt = datetime(2023, 1, 15, 14, 30, 45)  # Naive datetime
        result = format_datetime_for_display(dt)
        assert result == "2023-01-15 14:30:45"

    def test_format_datetime_timezone_conversion(self) -> None:
        """Test timezone conversion"""
        dt = datetime(2023, 1, 15, 14, 30, 45, tzinfo=UTC)
        target_tz = timezone(timedelta(hours=5, minutes=30))
        result = format_datetime_for_display(dt, target_timezone=target_tz)
        assert (
            result == "2023-01-15 19:60:45" or result == "2023-01-15 20:00:45"
        )  # 14:30 UTC + 5:30

    def test_format_datetime_server_timezone(self) -> None:
        """Test using server timezone"""
        dt = datetime(2023, 1, 15, 14, 30, 45, tzinfo=UTC)
        with patch.dict(os.environ, {"BORGITORY_TIMEZONE": "+02:00"}):
            result = format_datetime_for_display(dt)
            assert result == "2023-01-15 16:30:45"  # 14:30 UTC + 2:00


class TestNowUtc:
    """Test UTC now function"""

    def test_now_utc_returns_utc_datetime(self) -> None:
        """Test now_utc returns UTC datetime"""
        result = now_utc()
        assert isinstance(result, datetime)
        assert result.tzinfo == UTC

    def test_now_utc_is_recent(self) -> None:
        """Test now_utc returns recent time"""
        before = datetime.now(UTC)
        result = now_utc()
        after = datetime.now(UTC)

        assert before <= result <= after


class TestEnsureUtc:
    """Test UTC conversion utility"""

    def test_ensure_utc_none_input(self) -> None:
        """Test ensure_utc with None input"""
        assert ensure_utc(None) is None

    def test_ensure_utc_string_input(self) -> None:
        """Test ensure_utc with string input"""
        dt_string = "2023-01-15T14:30:45Z"
        result = ensure_utc(dt_string)

        assert result is not None
        assert result.tzinfo == UTC
        assert result.year == 2023

    def test_ensure_utc_invalid_string(self) -> None:
        """Test ensure_utc with invalid string"""
        assert ensure_utc("not-a-date") is None

    def test_ensure_utc_naive_datetime(self) -> None:
        """Test ensure_utc with naive datetime"""
        dt = datetime(2023, 1, 15, 14, 30, 45)
        result = ensure_utc(dt)

        assert result is not None
        assert result.tzinfo == UTC
        assert result.year == 2023
        assert result.hour == 14

    def test_ensure_utc_aware_datetime_utc(self) -> None:
        """Test ensure_utc with UTC datetime"""
        dt = datetime(2023, 1, 15, 14, 30, 45, tzinfo=UTC)
        result = ensure_utc(dt)

        assert result is not None
        assert result.tzinfo == UTC
        assert result == dt

    def test_ensure_utc_aware_datetime_other_timezone(self) -> None:
        """Test ensure_utc with non-UTC timezone"""
        est = timezone(timedelta(hours=-5))
        dt = datetime(2023, 1, 15, 14, 30, 45, tzinfo=est)
        result = ensure_utc(dt)

        assert result is not None
        assert result.tzinfo == UTC
        # Should be converted to UTC (14:30 EST = 19:30 UTC)
        assert result.hour == 19

    def test_ensure_utc_non_datetime_object(self) -> None:
        """Test ensure_utc with non-datetime object"""
        assert ensure_utc(123) is None
        assert ensure_utc([]) is None
        assert ensure_utc({}) is None


class TestIntegration:
    """Integration tests for datetime utilities"""

    def test_parse_and_format_roundtrip(self) -> None:
        """Test parsing and formatting roundtrip"""
        original = "2023-01-15T14:30:45Z"
        parsed = parse_datetime_string(original)
        formatted = format_datetime_for_display(parsed, "%Y-%m-%dT%H:%M:%SZ")

        assert formatted == "2023-01-15T14:30:45Z"

    def test_now_utc_and_format(self) -> None:
        """Test getting current time and formatting"""
        current = now_utc()
        formatted = format_datetime_for_display(current)

        # Should be in the expected format
        assert len(formatted) == 19  # YYYY-MM-DD HH:MM:SS
        assert formatted[4] == "-"
        assert formatted[7] == "-"
        assert formatted[10] == " "
        assert formatted[13] == ":"
        assert formatted[16] == ":"

    def test_ensure_utc_and_format(self) -> None:
        """Test ensuring UTC and formatting"""
        dt_string = "2023-01-15T14:30:45+05:00"
        ensured = ensure_utc(dt_string)
        formatted = format_datetime_for_display(ensured)

        # Should be converted to UTC and formatted
        assert formatted == "2023-01-15 09:30:45"  # 14:30+05:00 = 09:30 UTC


class TestBrowserTimezone:
    """Test browser timezone functionality"""

    def test_parse_timezone_offset_edt(self) -> None:
        """Test parsing EDT timezone offset (240 minutes)"""
        tz = parse_timezone_offset(240)  # EDT is UTC-4, JS returns +240
        expected_offset = timedelta(hours=-4)
        assert tz.utcoffset(None) == expected_offset

    def test_parse_timezone_offset_utc(self) -> None:
        """Test parsing UTC timezone offset (0 minutes)"""
        tz = parse_timezone_offset(0)
        expected_offset = timedelta(0)
        assert tz.utcoffset(None) == expected_offset

    def test_parse_timezone_offset_ahead_utc(self) -> None:
        """Test parsing timezone ahead of UTC (negative JS offset)"""
        tz = parse_timezone_offset(-120)  # UTC+2, JS returns -120
        expected_offset = timedelta(hours=2)
        assert tz.utcoffset(None) == expected_offset

    def test_format_datetime_for_display_with_browser_offset_edt(self) -> None:
        """Test formatting datetime with EDT browser timezone offset"""
        dt = datetime(2025, 9, 22, 17, 53, tzinfo=UTC)
        result = format_datetime_for_display(
            dt, "%Y-%m-%d %H:%M", browser_tz_offset_minutes=240
        )  # EDT
        assert result == "2025-09-22 13:53"  # 17:53 UTC - 4 hours = 13:53 EDT

    def test_format_datetime_for_display_with_browser_offset_utc(self) -> None:
        """Test formatting datetime with UTC browser timezone offset"""
        dt = datetime(2025, 9, 22, 17, 53, tzinfo=UTC)
        result = format_datetime_for_display(
            dt, "%Y-%m-%d %H:%M", browser_tz_offset_minutes=0
        )  # UTC
        assert result == "2025-09-22 17:53"  # No change

    def test_format_datetime_for_display_with_browser_offset_cet(self) -> None:
        """Test formatting datetime with CET browser timezone offset"""
        dt = datetime(2025, 9, 22, 17, 53, tzinfo=UTC)
        result = format_datetime_for_display(
            dt, "%Y-%m-%d %H:%M", browser_tz_offset_minutes=-60
        )  # CET
        assert result == "2025-09-22 18:53"  # 17:53 UTC + 1 hour = 18:53 CET

    def test_format_datetime_for_display_with_browser_offset_none_input(self) -> None:
        """Test formatting None datetime with browser timezone offset"""
        result = format_datetime_for_display(
            None, "%Y-%m-%d %H:%M", browser_tz_offset_minutes=240
        )
        assert result == "N/A"

    def test_format_datetime_for_display_browser_offset_precedence(self) -> None:
        """Test that browser timezone offset takes precedence over target_timezone"""
        dt = datetime(2025, 9, 22, 17, 53, tzinfo=UTC)
        cet_tz = timezone(timedelta(hours=1))
        # Browser offset should override target_timezone
        result = format_datetime_for_display(
            dt,
            "%Y-%m-%d %H:%M",
            target_timezone=cet_tz,  # Would give 18:53
            browser_tz_offset_minutes=240,  # Should give 13:53 (EDT)
        )
        assert result == "2025-09-22 13:53"  # Browser offset wins

    def test_parse_timezone_offset_none_input(self) -> None:
        """Test parsing None timezone offset returns UTC"""
        tz = parse_timezone_offset(None)
        assert tz == UTC

    def test_parse_timezone_offset_invalid_input(self) -> None:
        """Test parsing invalid timezone offset returns UTC"""
        tz = parse_timezone_offset("invalid")  # type: ignore
        assert tz == UTC
