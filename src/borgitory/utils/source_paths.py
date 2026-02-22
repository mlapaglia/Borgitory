"""Utilities for handling multiple source paths stored as JSON array strings."""

import json
import logging
from typing import List

logger = logging.getLogger(__name__)


def parse_source_paths(source_path: str) -> List[str]:
    """Parse a source_path value into a list of absolute paths.

    Handles both legacy single-path strings and JSON array strings.
    Non-absolute paths are filtered out with a warning.
    """
    if not source_path or not source_path.strip():
        return []

    stripped = source_path.strip()
    if stripped.startswith("["):
        try:
            parsed = json.loads(stripped)
            if isinstance(parsed, list):
                raw = [p for p in parsed if isinstance(p, str) and p.strip()]
                return _filter_absolute(raw)
            return _filter_absolute([stripped])
        except (json.JSONDecodeError, ValueError):
            return _filter_absolute([stripped])

    return _filter_absolute([stripped])


def _filter_absolute(paths: List[str]) -> List[str]:
    """Return only absolute paths, logging a warning for any that are skipped."""
    result = []
    for p in paths:
        if p.startswith("/"):
            result.append(p)
        else:
            logger.warning("Skipping non-absolute source path: %s", p)
    return result


def serialize_source_paths(paths: List[str]) -> str:
    """Convert a list of paths to a JSON array string for storage."""
    cleaned = [p.strip() for p in paths if p and p.strip()]
    if not cleaned:
        return "[]"
    return json.dumps(cleaned)
