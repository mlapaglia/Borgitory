"""
Path prefix utilities for handling /mnt/ path normalization
"""

from typing import Tuple


def normalize_path_with_mnt_prefix(input_value: str) -> str:
    """
    Normalize a user input path to ensure it has the /mnt/ prefix.

    Args:
        input_value: User input path (can be empty, relative, or absolute)

    Returns:
        Normalized path with /mnt/ prefix

    Examples:
        normalize_path_with_mnt_prefix("") -> "/mnt/"
        normalize_path_with_mnt_prefix("data") -> "/mnt/data"
        normalize_path_with_mnt_prefix("/data") -> "/mnt/data"
        normalize_path_with_mnt_prefix("/mnt/data") -> "/mnt/data"
    """
    if not input_value:
        return "/mnt/"

    if input_value.startswith("/mnt/"):
        return input_value

    if input_value.startswith("/"):
        return "/mnt" + input_value

    return "/mnt/" + input_value


def parse_path_for_autocomplete(normalized_path: str) -> Tuple[str, str]:
    """
    Parse a normalized path to extract the directory path and search term for autocomplete.

    Args:
        normalized_path: A path that has been normalized with /mnt/ prefix

    Returns:
        Tuple of (directory_path, search_term)

    Examples:
        parse_path_for_autocomplete("/mnt/data") -> ("/mnt/", "data")
        parse_path_for_autocomplete("/mnt/data/") -> ("/mnt/data", "")
        parse_path_for_autocomplete("/mnt/data/search") -> ("/mnt/data", "search")
    """
    if not normalized_path or not normalized_path.startswith("/"):
        return "/mnt/", ""

    # Handle trailing slash case first
    if normalized_path.endswith("/") and len(normalized_path) > 1:
        # Path ends with slash, so no search term
        dir_path = normalized_path.rstrip("/")
        # Special case: if dir_path becomes "/mnt", keep it as "/mnt/"
        if dir_path == "/mnt":
            dir_path = "/mnt/"
        return dir_path, ""

    last_slash_index = normalized_path.rfind("/")

    if last_slash_index == 0:
        # Input like "/s" - search in root directory
        return "/", normalized_path[1:]
    elif last_slash_index > 0:
        # Input like "/mnt/data/search" - search in "/mnt/data"
        dir_path = normalized_path[:last_slash_index]
        search_term = normalized_path[last_slash_index + 1 :]

        # Special case: if dir_path is just "/mnt", make it "/mnt/"
        if dir_path == "/mnt":
            dir_path = "/mnt/"

        return dir_path, search_term
    else:
        return "/mnt/", normalized_path


def remove_mnt_prefix_for_display(path: str) -> str:
    """
    Remove /mnt/ prefix from a path for display purposes.

    Args:
        path: Full path that may have /mnt/ prefix

    Returns:
        Path with /mnt/ prefix removed, or original path if no prefix

    Examples:
        remove_mnt_prefix_for_display("/mnt/data/folder") -> "data/folder"
        remove_mnt_prefix_for_display("/mnt/") -> ""
        remove_mnt_prefix_for_display("/data/folder") -> "/data/folder"
    """
    if path.startswith("/mnt/"):
        return path[5:]
    return path
