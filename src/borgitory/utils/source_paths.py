"""Utilities for handling multiple source paths stored as JSON array strings."""

import json
from typing import List


def parse_source_paths(source_path: str) -> List[str]:
    """Parse a source_path value into a list of paths.

    Handles both legacy single-path strings and JSON array strings.
    """
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


def serialize_source_paths(paths: List[str]) -> str:
    """Convert a list of paths to a JSON array string for storage."""
    cleaned = [p.strip() for p in paths if p and p.strip()]
    if not cleaned:
        return "[]"
    return json.dumps(cleaned)
