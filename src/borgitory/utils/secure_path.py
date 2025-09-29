"""
Secure path utilities to prevent directory traversal attacks.

This module provides secure wrappers around common file system operations.
"""

import logging
import os
import re
import uuid
import configparser
from pathlib import Path
from typing import List
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class DirectoryInfo:
    """Information about a directory entry."""

    name: str
    path: str
    is_borg_repo: bool = False
    is_borg_cache: bool = False

    @property
    def path_with_separator(self) -> str:
        """Get path with Unix-style trailing separator (WSL-first approach)."""
        if not self.path:
            return self.path

        # Check if path already ends with Unix separator
        if self.path.endswith("/"):
            return self.path

        # Always add Unix-style separator for WSL-first approach
        return self.path + "/"


def _is_borg_repository(directory_path: str) -> bool:
    """Check if a directory is a Borg repository by looking for a config file."""
    try:
        config_path = os.path.join(directory_path, "config")

        if not os.path.exists(config_path) or not os.path.isfile(config_path):
            return False

        # Try to read the config file and check for [repository] section
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                config_content = f.read()

            config = configparser.ConfigParser()
            config.read_string(config_content)

            return config.has_section("repository")

        except (configparser.Error, UnicodeDecodeError, PermissionError):
            return False

    except Exception:
        return False


def _is_borg_cache(directory_path: str) -> bool:
    """Check if a directory is a Borg cache by looking for a config file with [cache] section."""
    try:
        config_path = os.path.join(directory_path, "config")

        if not os.path.exists(config_path) or not os.path.isfile(config_path):
            return False

        # Try to read the config file and check for [cache] section
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                config_content = f.read()

            config = configparser.ConfigParser()
            config.read_string(config_content)

            return config.has_section("cache")

        except (configparser.Error, UnicodeDecodeError, PermissionError):
            return False

    except Exception:
        return False


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
    Securely join path components and validate the result is under allowed directories.

    Args:
        base_dir: Starting path
        path_parts: Path components to join

    Returns:
        The secure joined path
    """
    validated_base = Path(base_dir)

    # Clean and join path parts
    safe_parts = []
    for part in path_parts:
        if part:
            # Remove dangerous path traversal sequences (Unix-style only)
            safe_part = re.sub(r"\.\.+/?", "", str(part))
            safe_part = safe_part.strip("/")
            if safe_part:
                safe_parts.append(safe_part)

    if not safe_parts:
        return str(validated_base)

    # Join with the validated base
    joined_path = validated_base / Path(*safe_parts)

    # Validate the final result is still under allowed directories
    final_validated = Path(str(joined_path))

    return str(final_validated)


def secure_exists(path: str) -> bool:
    """
    Securely check if a path exists.

    Args:
        path: The path to check

    Returns:
        True if path exists
    """
    validated_path = Path(path)
    if validated_path is None:
        return False

    try:
        return validated_path.exists()
    except (PermissionError, OSError) as e:
        logger.warning(f"Cannot access path '{path}': {e}")
        return False


def secure_isdir(path: str) -> bool:
    """
    Securely check if a path is a directory.

    Args:
        path: The path to check

    Returns:
        True if path is a directory
    """
    validated_path = Path(path)
    if validated_path is None:
        return False

    try:
        return validated_path.is_dir()
    except (PermissionError, OSError) as e:
        logger.warning(f"Cannot access path '{path}': {e}")
        return False


def secure_remove_file(file_path: str) -> bool:
    """
    Securely remove a file.

    Args:
        file_path: Path to the file to remove

    Returns:
        True if file was removed or didn't exist, False if operation failed
    """
    validated_path = Path(file_path)

    try:
        if validated_path.exists():
            validated_path.unlink()
            logger.info(f"Successfully removed file: {validated_path}")
        return True
    except (PermissionError, OSError) as e:
        logger.error(f"Failed to remove file '{file_path}': {e}")
        return False


def get_directory_listing(
    path: str,
    include_files: bool = False,
) -> List[DirectoryInfo]:
    """
    Get a secure directory listing with additional metadata.

    Args:
        path: Directory path to list
        include_files: Whether to include files (default: directories only)

    Returns:
        List of DirectoryInfo objects
    """
    validated_path = Path(path)

    if not validated_path.is_dir():
        return []

    items = []
    try:
        for item in validated_path.iterdir():
            if item.is_dir():
                is_borg_repo = _is_borg_repository(str(item))
                is_borg_cache = _is_borg_cache(str(item))
                items.append(
                    DirectoryInfo(
                        name=item.name,
                        path=str(item),
                        is_borg_repo=is_borg_repo,
                        is_borg_cache=is_borg_cache,
                    )
                )
            elif include_files and item.is_file():
                items.append(
                    DirectoryInfo(
                        name=item.name,
                        path=str(item),
                        is_borg_repo=False,
                        is_borg_cache=False,
                    )
                )

        # Sort alphabetically
        items.sort(key=lambda x: x.name.lower())

    except (PermissionError, OSError) as e:
        logger.warning(f"Cannot access directory '{path}': {e}")

    return items
