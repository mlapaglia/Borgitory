"""
Secure path utilities to prevent directory traversal attacks.

This module provides secure wrappers around common file system operations
that validate paths to ensure they stay within the /mnt directory only.
All user data must be mounted under /mnt for security.
"""

import logging
import os
import re
import uuid
from pathlib import Path
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)


def _pre_validate_user_input(user_path: str, allowed_prefixes: List[str]) -> bool:
    """
    Pre-validate user input before Path operations to prevent security issues.

    Args:
        user_path: The user-provided path to validate
        allowed_prefixes: List of allowed absolute path prefixes (e.g., ["/mnt", "/app/data"])

    Returns:
        True if input is safe to process, False otherwise
    """
    # Check if input is a proper non-empty string without null bytes
    if not isinstance(user_path, str) or user_path.strip() == "" or "\x00" in user_path:
        logger.warning(
            f"Path validation failed for '{user_path}': empty or invalid path string"
        )
        return False

    # Only permit absolute paths if they start with allowed prefixes
    # Check both OS-specific absolute paths and Unix-style paths (for Docker containers)
    is_absolute = os.path.isabs(user_path) or user_path.startswith("/")
    if is_absolute:
        # For Unix-style paths, check with forward slash
        unix_match = any(
            user_path.startswith(prefix + "/") or user_path == prefix
            for prefix in allowed_prefixes
        )
        # For Windows-style paths, convert allowed prefixes to Windows format and check
        windows_match = False
        if os.name == "nt" and os.path.isabs(user_path):
            # Convert Unix prefixes to Windows format for local development
            windows_prefixes = []
            for prefix in allowed_prefixes:
                if prefix == "/mnt":
                    windows_prefixes.append("C:\\mnt")
                elif prefix == "/app/data":
                    windows_prefixes.append("C:\\app\\app\\data")
            windows_match = any(
                user_path.startswith(prefix + "\\")
                or user_path.startswith(prefix + "/")
                or user_path == prefix
                for prefix in windows_prefixes
            )

        if not (unix_match or windows_match):
            logger.warning(
                f"Path validation failed for '{user_path}': absolute path not under allowed roots"
            )
            return False

    return True


class PathSecurityError(Exception):
    """Raised when a path operation violates security constraints."""

    pass


def validate_secure_path(user_path: str, allow_app_data: bool = True) -> Optional[Path]:
    """
    Validate that a path is under allowed directories. Simple and secure.

    Allowed paths:
    - /mnt/* - For user repos, backup sources, keyfiles, etc.
    - /app/data/* - For application database, secret key, etc. (if allow_app_data=True)

    This function uses pathlib.Path.resolve() to handle symlinks, relative paths,
    and normalization automatically, preventing path traversal attacks.

    Args:
        user_path: The user-provided path to validate
        allow_app_data: Whether to allow /app/data paths (default: True)

    Returns:
        Resolved Path object if valid and under allowed directories, None otherwise
    """
    try:
        allowed_prefixes = ["/mnt"]
        if allow_app_data:
            allowed_prefixes.append("/app/data")

        if not _pre_validate_user_input(user_path, allowed_prefixes):
            return None

        for allowed_root_str in allowed_prefixes:
            allowed_root_real = os.path.realpath(allowed_root_str)

            # Compose the target path
            target_path = (
                user_path
                if os.path.isabs(user_path)
                else os.path.join(allowed_root_str, user_path)
            )
            # Canonicalize target path
            target_realpath = os.path.realpath(os.path.normpath(target_path))

            # Hardened containment check: must be strictly inside allowed_root_real
            normalized_root = os.path.join(allowed_root_real, "")
            if target_realpath == allowed_root_real or target_realpath.startswith(
                normalized_root
            ):
                # Disallow symlinks that point outside, ensure target_realpath is inside root
                # Additional defense: verify relpath does not start with ../
                rel_path = os.path.relpath(target_realpath, allowed_root_real)
                if not rel_path.startswith(".."):
                    logger.debug(f"Validated path: {user_path} -> {target_realpath}")
                    return Path(target_realpath)
                else:
                    logger.warning(
                        f"Path traversal attempt detected for '{user_path}' resolved as '{target_realpath}' relative '{rel_path}'"
                    )
                    return None
        allowed_paths = ["/mnt"] + (["/app/data"] if allow_app_data else [])
        logger.warning(
            f"Path validation failed for '{user_path}': not under allowed paths {allowed_paths}"
        )
        return None
    except (OSError,) as e:
        logger.warning(f"Path validation failed for '{user_path}': {e}")
        return None


def validate_mnt_path(user_path: str) -> Optional[Path]:
    """
    Validate that a path is under /mnt/ only - for user repos/backup sources.
    Use this for user-facing operations to prevent repos in /app/data.
    """
    return validate_secure_path(user_path, allow_app_data=False)


def validate_user_repository_path(user_path: str) -> Optional[Path]:
    """
    Validate paths for user repositories and backup sources - /mnt only.
    This prevents users from putting repositories in /app/data.
    """
    return validate_mnt_path(user_path)


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
        base_dir: Starting path (must be under /mnt or /app/data)
        path_parts: Path components to join

    Returns:
        The secure joined path

    Raises:
        PathSecurityError: If the resulting path would not be under allowed directories
    """
    # Validate base directory is under allowed directories
    validated_base = validate_secure_path(base_dir, allow_app_data=True)
    if validated_base is None:
        raise PathSecurityError(
            f"Base directory '{base_dir}' must be under /mnt or /app/data"
        )

    # Clean and join path parts
    safe_parts = []
    for part in path_parts:
        if part:
            # Remove dangerous path traversal sequences
            safe_part = re.sub(r"\.\.+[/\\]?", "", str(part))
            safe_part = safe_part.strip("/\\")
            if safe_part:
                safe_parts.append(safe_part)

    if not safe_parts:
        return str(validated_base)

    # Join with the validated base
    joined_path = validated_base / Path(*safe_parts)

    # Validate the final result is still under allowed directories
    final_validated = validate_secure_path(str(joined_path), allow_app_data=True)
    if final_validated is None:
        raise PathSecurityError(
            f"Joined path '{joined_path}' would be outside allowed directories"
        )

    return str(final_validated)


def secure_exists(path: str) -> bool:
    """
    Securely check if a path exists, validating it's under allowed directories.

    Args:
        path: The path to check

    Returns:
        True if path exists and is under /mnt or /app/data
    """
    validated_path = validate_secure_path(path, allow_app_data=True)
    if validated_path is None:
        return False

    try:
        return validated_path.exists()
    except (PermissionError, OSError) as e:
        logger.warning(f"Cannot access path '{path}': {e}")
        return False


def secure_isdir(path: str) -> bool:
    """
    Securely check if a path is a directory, validating it's under allowed directories.

    Args:
        path: The path to check

    Returns:
        True if path is a directory and is under /mnt or /app/data
    """
    validated_path = validate_secure_path(path, allow_app_data=True)
    if validated_path is None:
        return False

    try:
        return validated_path.is_dir()
    except (PermissionError, OSError) as e:
        logger.warning(f"Cannot access path '{path}': {e}")
        return False


def secure_remove_file(file_path: str) -> bool:
    """
    Securely remove a file, validating it's under allowed directories.

    Args:
        file_path: Path to the file to remove

    Returns:
        True if file was removed or didn't exist, False if operation failed
    """
    validated_path = validate_secure_path(file_path, allow_app_data=True)
    if validated_path is None:
        logger.warning(f"File '{file_path}' not under allowed directories")
        return False

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
) -> List[Dict[str, str]]:
    """
    Get a secure directory listing with additional metadata.

    Args:
        path: Directory path to list
        include_files: Whether to include files (default: directories only)

    Returns:
        List of dictionaries with 'name' and 'path' keys
    """
    validated_path = validate_secure_path(path, allow_app_data=True)
    if validated_path is None:
        logger.warning(f"Path '{path}' not under allowed directories")
        return []

    if not validated_path.is_dir():
        return []

    items = []
    try:
        for item in validated_path.iterdir():
            if item.is_dir():
                items.append({"name": item.name, "path": str(item)})
            elif include_files and item.is_file():
                items.append({"name": item.name, "path": str(item)})

        # Sort alphabetically
        items.sort(key=lambda x: x["name"].lower())

    except (PermissionError, OSError) as e:
        logger.warning(f"Cannot access directory '{path}': {e}")

    return items


# User-facing functions that only allow /mnt (for repositories/backup sources)
def user_secure_exists(path: str) -> bool:
    """Check if path exists - /mnt only (for user repos/backup sources)."""
    validated_path = validate_mnt_path(path)
    if validated_path is None:
        return False

    try:
        return validated_path.exists()
    except (PermissionError, OSError) as e:
        logger.warning(f"Cannot access path '{path}': {e}")
        return False


def user_secure_isdir(path: str) -> bool:
    """Check if path is directory - /mnt only (for user repos/backup sources)."""
    validated_path = validate_mnt_path(path)
    # Additional defense: require that validated_path is inside /mnt
    mnt_real = os.path.realpath("/mnt")
    if validated_path is None or not str(validated_path).startswith(mnt_real):
        logger.warning(f"Directory check blocked: Path '{path}' not contained in /mnt")
        return False
    try:
        return validated_path.is_dir()
    except (PermissionError, OSError) as e:
        logger.warning(f"Cannot access path '{path}': {e}")
        return False


def user_get_directory_listing(
    path: str, include_files: bool = False
) -> List[Dict[str, str]]:
    """Get directory listing - /mnt only (for user repos/backup sources)."""
    validated_path = validate_mnt_path(path)
    if validated_path is None:
        logger.warning(f"Path '{path}' not under /mnt directory")
        return []

    if not validated_path.is_dir():
        return []

    items = []
    try:
        for item in validated_path.iterdir():
            if item.is_dir():
                items.append({"name": item.name, "path": str(item)})
            elif include_files and item.is_file():
                items.append({"name": item.name, "path": str(item)})

        # Sort alphabetically
        items.sort(key=lambda x: x["name"].lower())

    except (PermissionError, OSError) as e:
        logger.warning(f"Cannot access directory '{path}': {e}")

    return items
