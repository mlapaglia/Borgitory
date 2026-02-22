"""Utilities for handling multiple source paths stored as JSON array strings."""

import json
import logging
from typing import List

logger = logging.getLogger(__name__)


def _parse_raw(source_path: str) -> List[str]:
    """Parse a source_path value into a list of path strings without filtering."""
    if not source_path or not source_path.strip():
        return []

    stripped = source_path.strip()
    if stripped.startswith("["):
        try:
            parsed = json.loads(stripped)
            if isinstance(parsed, list):
                return [p for p in parsed if isinstance(p, str) and p.strip()]
            return [stripped]
        except (json.JSONDecodeError, ValueError):
            return [stripped]

    return [stripped]


def parse_source_paths(source_path: str) -> List[str]:
    """Parse a source_path value into a list of absolute paths.

    Handles both legacy single-path strings and JSON array strings.
    Non-absolute paths are filtered out with a warning.
    """
    result = []
    for p in _parse_raw(source_path):
        if p.startswith("/"):
            result.append(p)
        else:
            logger.warning("Skipping non-absolute source path: %s", p)
    return result


def parse_source_paths_raw(source_path: str) -> List[str]:
    """Parse a source_path value into a list of paths without absolute-path filtering.

    Used by validators that need to inspect all paths before deciding how to report errors.
    """
    return _parse_raw(source_path)


def serialize_source_paths(paths: List[str]) -> str:
    """Convert a list of paths to a JSON array string for storage."""
    cleaned = [p.strip() for p in paths if p and p.strip()]
    if not cleaned:
        return "[]"
    return json.dumps(cleaned)
