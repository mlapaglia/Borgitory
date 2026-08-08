"""Utilities for handling multiple source paths stored as JSON array strings."""

import json
import logging
from typing import List

logger = logging.getLogger(__name__)


def parse_source_paths(source_paths: str) -> List[str]:
    """Parse a source_paths JSON array string into a list of path strings.

    Returns only non-empty strings. Invalid JSON returns an empty list.
    """
    if not source_paths or not source_paths.strip():
        return []

    try:
        parsed = json.loads(source_paths)
        if isinstance(parsed, list):
            return [p for p in parsed if isinstance(p, str) and p.strip()]
        return []
    except json.JSONDecodeError, ValueError:
        return []


def serialize_source_paths(paths: List[str]) -> str:
    """Convert a list of paths to a JSON array string for storage."""
    cleaned = [p.strip() for p in paths if p and p.strip()]
    return json.dumps(cleaned) if cleaned else "[]"
