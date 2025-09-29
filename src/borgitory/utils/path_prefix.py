"""
Path prefix utilities for Unix path handling (WSL-first approach)
"""

from typing import Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from borgitory.protocols.path_protocols import PathServiceInterface


def parse_path_for_autocomplete(
    normalized_path: str, path_service: "PathServiceInterface"
) -> Tuple[str, str]:
    """
    Parse a Unix-style path to extract the directory path and search term for autocomplete.

    With WSL-first approach, all paths are Unix-style (including Windows paths as /mnt/c/...).

    Args:
        normalized_path: A Unix-style path
        path_service: Path service for filesystem operations

    Returns:
        Tuple of (directory_path, search_term)

    Examples:
        parse_path_for_autocomplete("/data") -> ("/", "data")
        parse_path_for_autocomplete("/mnt/c/data") -> ("/mnt/c", "data")
        parse_path_for_autocomplete("/data/") -> ("/data", "")
    """
    if not normalized_path:
        # Always return Unix root for WSL-first approach
        return "/", ""

    # Check if path ends with separator (indicating it's a complete directory)
    if normalized_path.endswith("/") and len(normalized_path) > 1:
        # Remove trailing separator and return as directory with empty search term
        clean_path = normalized_path.rstrip("/")
        return clean_path if clean_path else "/", ""

    # Handle root directory
    if normalized_path == "/":
        return "/", ""

    # Split into parent directory and search term
    last_slash_index = normalized_path.rfind("/")

    if last_slash_index == 0:
        # Path like "/data" - search in root directory
        return "/", normalized_path[1:]
    elif last_slash_index == -1:
        # No slash found - relative path, use current directory
        return ".", normalized_path
    else:
        # Normal case - split at last slash
        dir_path = normalized_path[:last_slash_index]
        search_term = normalized_path[last_slash_index + 1 :]
        return dir_path, search_term


def parse_path_for_autocomplete_legacy(normalized_path: str) -> Tuple[str, str]:
    """
    Legacy version for backwards compatibility - assumes Unix paths.

    DEPRECATED: Use parse_path_for_autocomplete with path_service instead.
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
