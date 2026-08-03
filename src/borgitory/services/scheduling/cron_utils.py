"""Cron expression helpers for APScheduler compatibility."""

from __future__ import annotations

import re

# Unix cron day-of-week: 0 and 7 = Sunday, 1 = Monday, ..., 6 = Saturday.
# APScheduler 3.x uses Monday = 0 ... Sunday = 6, and rejects 7.
# Converting numbers to names avoids the numbering mismatch.
_UNIX_DOW_TO_NAME = {
    "0": "sun",
    "1": "mon",
    "2": "tue",
    "3": "wed",
    "4": "thu",
    "5": "fri",
    "6": "sat",
    "7": "sun",
}

_NUMERIC_DOW_SEGMENT = re.compile(
    r"^(?P<start>\d+)(?:-(?P<end>\d+))?(?:/(?P<step>\d+))?$"
)


def normalize_cron_for_apscheduler(cron_expression: str) -> str:
    """
    Normalize a 5-field Unix crontab expression for APScheduler 3.x.

    Converts numeric day-of-week values to weekday names so that:
    - ``0`` and ``7`` both mean Sunday (Unix cron)
    - weekday numbering matches user/cron expectations rather than
      APScheduler's Monday-based integers
    """
    parts = cron_expression.strip().split()
    if len(parts) != 5:
        return cron_expression.strip()

    parts[4] = _normalize_day_of_week_field(parts[4])
    return " ".join(parts)


def _normalize_day_of_week_field(field: str) -> str:
    if field in ("*", "?"):
        return field

    segments = [_normalize_dow_segment(segment.strip()) for segment in field.split(",")]
    return ",".join(segments)


def _normalize_dow_segment(segment: str) -> str:
    if not segment:
        return segment

    if segment.startswith("*/"):
        return segment

    # Already a weekday name or name range (e.g. sun, mon-fri)
    if re.fullmatch(r"[a-zA-Z]+(?:-[a-zA-Z]+)?", segment):
        return segment.lower()

    match = _NUMERIC_DOW_SEGMENT.fullmatch(segment)
    if not match:
        return segment

    start = int(match.group("start"))
    end = match.group("end")
    step = match.group("step")

    if end is None and step is None:
        return _unix_dow_to_name(start)

    step_value = int(step) if step is not None else 1
    if step_value < 1:
        raise ValueError(f"Invalid day-of-week step in '{segment}'")

    # Single start with step (e.g. 1/2) runs through Sunday (7) inclusive,
    # matching common cron behavior for the 0-7 day-of-week range.
    end_value = int(end) if end is not None else 7

    names: list[str] = []
    for value in range(start, end_value + 1, step_value):
        name = _unix_dow_to_name(value)
        if name not in names:
            names.append(name)

    if not names:
        raise ValueError(f"Invalid day-of-week expression '{segment}'")

    return ",".join(names)


def _unix_dow_to_name(value: int) -> str:
    try:
        return _UNIX_DOW_TO_NAME[str(value)]
    except KeyError as exc:
        raise ValueError(
            f"day-of-week value {value} is out of range (expected 0-7)"
        ) from exc
