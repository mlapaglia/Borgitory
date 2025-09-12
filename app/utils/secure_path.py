"""
Secure path utilities to prevent directory traversal attacks.

This module provides secure wrappers around common file system operations
that validate paths to ensure they stay within expected boundaries.
"""

import logging
import os
import re
import uuid
from typing import List, Dict

logger = logging.getLogger(__name__)


class PathSecurityError(Exception):
    """Raised when a path operation violates security constraints."""

    pass


def validate_path_within_base(
    path: str, base_dir: str, allow_equal: bool = True
) -> str:
    """
    Validate that a path is within the specified base directory.

    Args:
        path: The path to validate
        base_dir: The base directory that the path must be within
        allow_equal: Whether to allow path to equal base_dir

    Returns:
        The normalized path if valid

    Raises:
        PathSecurityError: If the path is outside the base directory
    """
    try:
        normalized_path = os.path.normpath(os.path.abspath(path))
        normalized_base = os.path.normpath(os.path.abspath(base_dir))

        if allow_equal and normalized_path == normalized_base:
            return normalized_path

        # Check if path is within base directory (including direct children)
        # Account for both subdirectories and direct children of base directory
        is_subdirectory = normalized_path.startswith(normalized_base + os.sep)
        is_direct_child = (
            normalized_base == os.path.dirname(normalized_path) and 
            normalized_path != normalized_base
        )
        
        if not (is_subdirectory or is_direct_child):
            raise PathSecurityError(
                f"Path '{path}' is outside allowed base directory '{base_dir}'"
            )

        return normalized_path
    except Exception as e:
        if isinstance(e, PathSecurityError):
            raise
        raise PathSecurityError(f"Invalid path '{path}': {str(e)}")


def sanitize_filename(filename: str, max_length: int = 100) -> str:
    """
    Sanitize a filename to remove dangerous characters.

    Args:
        filename: The filename to sanitize
        max_length: Maximum allowed length

    Returns:
        A safe filename
    """
    if not filename:
        return "unnamed"

    safe_name = re.sub(r"[^a-zA-Z0-9\-_.]", "_", filename)

    safe_name = re.sub(r"\.{2,}", ".", safe_name)

    safe_name = safe_name.strip(". ")

    if not safe_name:
        safe_name = "unnamed"

    # Truncate if too long
    if len(safe_name) > max_length:
        name_part, ext_part = os.path.splitext(safe_name)
        max_name_length = max_length - len(ext_part)
        safe_name = name_part[:max_name_length] + ext_part

    return safe_name


def create_secure_filename(
    base_name: str, original_filename: str = "", add_uuid: bool = True
) -> str:
    """
    Create a secure filename by combining a base name with an optional original filename.

    Args:
        base_name: Base name to use (will be sanitized)
        original_filename: Original filename to extract extension from
        add_uuid: Whether to add a UUID for uniqueness

    Returns:
        A secure filename
    """
    safe_base = sanitize_filename(base_name, max_length=50)

    ext = ""
    if original_filename and "." in original_filename:
        ext = original_filename.rsplit(".", 1)[-1]
        safe_ext = re.sub(r"[^a-zA-Z0-9]", "", ext)[:10]
        if safe_ext:
            ext = f".{safe_ext}"
        else:
            ext = ""

    # Add UUID for uniqueness if requested
    if add_uuid:
        unique_id = str(uuid.uuid4())[:8]
        filename = f"{safe_base}_{unique_id}{ext}"
    else:
        filename = f"{safe_base}{ext}"

    return filename


def secure_path_join(base_dir: str, *path_parts: str) -> str:
    """
    Securely join path components and validate the result is within base_dir.

    Args:
        base_dir: The base directory
        path_parts: Path components to join

    Returns:
        The secure joined path

    Raises:
        PathSecurityError: If the resulting path would be outside base_dir
    """

    safe_parts = []
    for part in path_parts:
        if part:
            safe_part = re.sub(r"\.\.+[/\\]?", "", str(part))
            safe_part = safe_part.strip("/\\")
            if safe_part:
                safe_parts.append(safe_part)

    if not safe_parts:
        return validate_path_within_base(base_dir, base_dir)

    joined_path = os.path.join(base_dir, *safe_parts)

    return validate_path_within_base(joined_path, base_dir)


def secure_exists(path: str, allowed_base_dirs: List[str]) -> bool:
    """
    Securely check if a path exists, validating it's within allowed directories.

    Args:
        path: The path to check
        allowed_base_dirs: List of allowed base directories

    Returns:
        True if path exists and is within allowed directories
    """
    try:
        for base_dir in allowed_base_dirs:
            try:
                validated_path = validate_path_within_base(path, base_dir)
                return os.path.exists(validated_path)
            except PathSecurityError:
                continue

        logger.warning(f"Path '{path}' not within any allowed base directories")
        return False
    except Exception as e:
        logger.error(f"Error checking path existence: {e}")
        return False


def secure_isdir(path: str, allowed_base_dirs: List[str]) -> bool:
    """
    Securely check if a path is a directory, validating it's within allowed directories.

    Args:
        path: The path to check
        allowed_base_dirs: List of allowed base directories

    Returns:
        True if path is a directory and is within allowed directories
    """
    try:
        for base_dir in allowed_base_dirs:
            try:
                validated_path = validate_path_within_base(path, base_dir)
                return os.path.isdir(validated_path)
            except PathSecurityError:
                continue

        logger.warning(f"Path '{path}' not within any allowed base directories")
        return False
    except Exception as e:
        logger.error(f"Error checking if path is directory: {e}")
        return False


def secure_listdir(path: str, allowed_base_dirs: List[str]) -> List[str]:
    """
    Securely list directory contents, validating the path is within allowed directories.

    Args:
        path: The directory path to list
        allowed_base_dirs: List of allowed base directories

    Returns:
        List of directory contents, or empty list if path is invalid/inaccessible
    """
    try:
        for base_dir in allowed_base_dirs:
            try:
                validated_path = validate_path_within_base(path, base_dir)
                return os.listdir(validated_path)
            except PathSecurityError:
                continue

        logger.warning(f"Path '{path}' not within any allowed base directories")
        return []
    except (PermissionError, OSError) as e:
        logger.warning(f"Cannot access directory '{path}': {e}")
        return []
    except Exception as e:
        logger.error(f"Error listing directory: {e}")
        return []


def secure_remove_file(file_path: str, allowed_base_dirs: List[str]) -> bool:
    """
    Securely remove a file, validating it's within allowed directories.

    Args:
        file_path: Path to the file to remove
        allowed_base_dirs: List of allowed base directories

    Returns:
        True if file was removed or didn't exist, False if operation failed
    """
    try:
        for base_dir in allowed_base_dirs:
            try:
                validated_path = validate_path_within_base(file_path, base_dir)
                if os.path.exists(validated_path):
                    os.remove(validated_path)
                    logger.info(f"Successfully removed file: {validated_path}")
                return True
            except PathSecurityError:
                continue

        logger.warning(f"File '{file_path}' not within any allowed base directories")
        return False
    except (PermissionError, OSError) as e:
        logger.error(f"Failed to remove file '{file_path}': {e}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error removing file '{file_path}': {e}")
        return False


def get_directory_listing(
    path: str, allowed_base_dirs: List[str], include_files: bool = False
) -> List[Dict[str, str]]:
    """
    Get a secure directory listing with additional metadata.

    Args:
        path: Directory path to list
        allowed_base_dirs: List of allowed base directories
        include_files: Whether to include files (default: directories only)

    Returns:
        List of dictionaries with 'name' and 'path' keys
    """
    items = []

    try:
        validated_path = None
        for base_dir in allowed_base_dirs:
            try:
                validated_path = validate_path_within_base(path, base_dir)
                break
            except PathSecurityError:
                continue

        if not validated_path:
            logger.warning(f"Path '{path}' not within any allowed base directories")
            return items

        if not os.path.isdir(validated_path):
            return items

        for item_name in os.listdir(validated_path):
            item_path = os.path.join(validated_path, item_name)

            if os.path.isdir(item_path):
                items.append({"name": item_name, "path": item_path})
            elif include_files and os.path.isfile(item_path):
                items.append({"name": item_name, "path": item_path})

        # Sort alphabetically
        items.sort(key=lambda x: x["name"].lower())

    except (PermissionError, OSError) as e:
        logger.warning(f"Cannot access directory '{path}': {e}")
    except Exception as e:
        logger.error(f"Error getting directory listing for '{path}': {e}")

    return items
