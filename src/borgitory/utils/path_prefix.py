"""
Path prefix utilities for handling path normalization
"""

from typing import Tuple


def parse_path_for_autocomplete(normalized_path: str) -> Tuple[str, str]:
    """
    Parse a normalized path to extract the directory path and search term for autocomplete.

    Args:
        normalized_path: A path that has been normalized

    Returns:
        Tuple of (directory_path, search_term)

    Examples:
        parse_path_for_autocomplete("/data") -> ("/", "data")
        parse_path_for_autocomplete("/data/") -> ("/data", "")
        parse_path_for_autocomplete("/data/search") -> ("/data", "search")
    """
    if normalized_path.endswith("/") and len(normalized_path) > 1:
        dir_path = normalized_path.rstrip("/")
        return dir_path, ""

    last_slash_index = normalized_path.rfind("/")

    if last_slash_index == 0:
        # Input like "/s" - search in root directory
        return "/", normalized_path[1:]
    else:
        dir_path = normalized_path[:last_slash_index]
        search_term = normalized_path[last_slash_index + 1 :]

        return dir_path, search_term
