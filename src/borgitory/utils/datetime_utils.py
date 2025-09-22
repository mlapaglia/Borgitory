"""
Datetime utilities for consistent timezone handling across the application.
"""

from datetime import datetime, UTC, timezone, timedelta
from typing import Optional, Union
import os


def parse_datetime_string(dt_string: str) -> Optional[datetime]:
    """
    Parse datetime string with consistent UTC timezone handling.

    Handles common formats:
    - ISO format with 'Z' suffix (converts to UTC)
    - ISO format with timezone offset
    - ISO format without timezone (assumes UTC)

    Args:
        dt_string: String representation of datetime

    Returns:
        Parsed datetime object with timezone info, or None if parsing fails
    """
    if not dt_string or not isinstance(dt_string, str):
        return None

    dt_string = dt_string.strip()

    try:
        # Handle 'Z' suffix (UTC indicator)
        if dt_string.endswith("Z"):
            return datetime.fromisoformat(dt_string.replace("Z", "+00:00"))

        # Try parsing as-is (may have timezone offset)
        return datetime.fromisoformat(dt_string)

    except (ValueError, TypeError):
        # If all parsing attempts fail
        return None


def get_server_timezone() -> timezone:
    """
    Get the server's configured timezone.

    Can be overridden with BORGITORY_TIMEZONE environment variable.
    Defaults to UTC for consistency.

    Returns:
        Timezone object
    """
    tz_name = os.getenv("BORGITORY_TIMEZONE")

    if tz_name:
        try:
            # Handle common timezone formats
            if tz_name.upper() == "UTC":
                return UTC
            elif tz_name.startswith(("+", "-")):
                # Handle offset format like +05:30 or -08:00
                sign = 1 if tz_name[0] == "+" else -1
                hours, minutes = map(int, tz_name[1:].split(":"))
                offset = timedelta(hours=sign * hours, minutes=sign * minutes)
                return timezone(offset)
        except (ValueError, AttributeError):
            pass

    # Default to UTC for consistency
    return UTC


def format_datetime_for_display(
    dt: datetime,
    format_str: str = "%Y-%m-%d %H:%M:%S",
    target_timezone: Optional[timezone] = None,
    browser_tz_offset_minutes: Optional[int] = None,
) -> str:
    """
    Format datetime for display, handling timezone conversion.

    Args:
        dt: Datetime object to format
        format_str: Format string for strftime
        target_timezone: Target timezone for display (defaults to server timezone)
        browser_tz_offset_minutes: Browser timezone offset in minutes (takes precedence over target_timezone)

    Returns:
        Formatted datetime string in target timezone
    """
    if not dt:
        return "N/A"

    # If browser timezone offset is provided, use it instead of target_timezone
    if browser_tz_offset_minutes is not None:
        target_timezone = parse_timezone_offset(browser_tz_offset_minutes)
    elif target_timezone is None:
        target_timezone = get_server_timezone()

    # Ensure datetime is UTC-aware
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)

    # Convert to target timezone
    local_dt = dt.astimezone(target_timezone)

    return local_dt.strftime(format_str)


def now_utc() -> datetime:
    """
    Get current datetime in UTC timezone.

    Returns:
        Current datetime with UTC timezone
    """
    return datetime.now(UTC)


def parse_timezone_offset(tz_offset_minutes: Union[int, None]) -> timezone:
    """
    Parse timezone offset in minutes to timezone object.

    Args:
        tz_offset_minutes: Timezone offset in minutes (e.g., -240 for EDT), or None

    Returns:
        Timezone object (UTC if input is None)
    """
    if tz_offset_minutes is None:
        return UTC

    try:
        # Ensure we have a valid integer
        offset_int = int(tz_offset_minutes)
    except (ValueError, TypeError):
        return UTC

    # Convert minutes to hours and minutes
    hours = abs(offset_int) // 60
    minutes = abs(offset_int) % 60

    # Create timedelta (negative offset means behind UTC)
    sign = -1 if offset_int > 0 else 1  # JavaScript getTimezoneOffset() is inverted
    offset = timedelta(hours=sign * hours, minutes=sign * minutes)

    return timezone(offset)


def ensure_utc(dt: Union[datetime, str, None]) -> Optional[datetime]:
    """
    Ensure datetime object is in UTC timezone.

    Args:
        dt: Datetime object, string, or None

    Returns:
        UTC datetime object or None
    """
    if dt is None:
        return None

    if isinstance(dt, str):
        dt = parse_datetime_string(dt)
        if dt is None:
            return None

    if not isinstance(dt, datetime):
        return None

    # If datetime is naive, assume it's already UTC
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)

    # Convert to UTC if it has timezone info
    return dt.astimezone(UTC)
