import re
import secrets
import tempfile
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import List, Dict, Optional, AsyncGenerator, Tuple
import logging

logger = logging.getLogger(__name__)


def sanitize_path(path: str) -> str:
    """
    Sanitize a path to prevent directory traversal and injection attacks.

    Args:
        path: The path to sanitize

    Returns:
        Sanitized path string

    Raises:
        ValueError: If path contains dangerous patterns
    """
    if not path or not isinstance(path, str):
        raise ValueError("Path must be a non-empty string")

    # Remove any null bytes
    path = path.replace("\x00", "")

    # Check for dangerous patterns
    dangerous_patterns = [
        r"\.\./",  # Directory traversal
        r"\.\.\\",  # Windows directory traversal
        r"[;<>|&`$]",  # Command injection characters
        r"\$\(",  # Command substitution
        r"`",  # Backticks
        r"\n|\r",  # Newlines
    ]

    for pattern in dangerous_patterns:
        if re.search(pattern, path):
            raise ValueError(f"Path contains dangerous pattern: {pattern}")

    # Normalize the path
    normalized = str(Path(path).resolve())

    return normalized


def sanitize_passphrase(passphrase: str) -> str:
    """
    Validate and sanitize a passphrase for safe use in commands.

    Args:
        passphrase: The passphrase to sanitize

    Returns:
        Sanitized passphrase

    Raises:
        ValueError: If passphrase contains dangerous characters
    """
    if not passphrase or not isinstance(passphrase, str):
        raise ValueError("Passphrase must be a non-empty string")

    # Check for dangerous shell characters
    dangerous_chars = ["'", '"', "`", "$", "\\", "\n", "\r", ";", "&", "|", "<", ">"]

    for char in dangerous_chars:
        if char in passphrase:
            raise ValueError(f"Passphrase contains dangerous character: {char}")

    return passphrase


def build_secure_borg_command(
    base_command: str,
    repository_path: str,
    passphrase: str,
    additional_args: Optional[List[str]] = None,
    environment_overrides: Optional[Dict[str, str]] = None,
) -> tuple[List[str], Dict[str, str]]:
    """
    Build a secure Borg command with proper escaping and validation.

    Args:
        base_command: The base borg command (e.g., "borg create")
        repository_path: Path to the repository (can be empty if included in additional_args)
        passphrase: Repository passphrase
        additional_args: Additional command arguments
        environment_overrides: Additional environment variables

    Returns:
        Tuple of (command_list, environment_dict)
    """
    # Sanitize inputs
    safe_repo_path = sanitize_path(repository_path) if repository_path else ""
    safe_passphrase = sanitize_passphrase(passphrase)

    # Build environment variables
    environment = {
        "BORG_PASSPHRASE": safe_passphrase,
        "BORG_RELOCATED_REPO_ACCESS_IS_OK": "yes",
        "BORG_UNKNOWN_UNENCRYPTED_REPO_ACCESS_IS_OK": "yes",
    }

    if environment_overrides:
        for key, value in environment_overrides.items():
            if not re.match(r"^[A-Z_][A-Z0-9_]*$", key):
                raise ValueError(f"Invalid environment variable name: {key}")
            environment[key] = str(value)

    # Build command as list (no shell interpretation)
    command_parts = base_command.split()

    if additional_args:
        for i, arg in enumerate(additional_args):
            if not isinstance(arg, str):
                raise ValueError("All arguments must be strings")

            # Special handling for Borg pattern arguments
            is_pattern_arg = (
                i > 0 and additional_args[i - 1] == "--pattern"
            ) or arg == "--pattern"

            if is_pattern_arg:
                # For pattern arguments, allow regex metacharacters but block shell injection
                # Only check for actual shell injection characters, not regex characters
                if re.search(r"[;<>&`\n\r]", arg):
                    raise ValueError(f"Argument contains dangerous characters: {arg}")
                # Also block command substitution patterns
                if "$(" in arg or "${" in arg:
                    raise ValueError(f"Argument contains dangerous characters: {arg}")
            else:
                # For regular arguments, use stricter validation
                if re.search(r"[;<>|&`$\n\r]", arg):
                    raise ValueError(f"Argument contains dangerous characters: {arg}")

            command_parts.append(arg)

    # Add repository path as final argument (only if provided)
    if safe_repo_path:
        command_parts.append(safe_repo_path)

    logger.info(f"Built secure command: {' '.join(command_parts[:3])} [REDACTED_ARGS]")

    return command_parts, environment


def validate_archive_name(name: str) -> str:
    """
    Validate and sanitize an archive name.

    Args:
        name: Archive name to validate

    Returns:
        Validated archive name

    Raises:
        ValueError: If name is invalid
    """
    if not name or not isinstance(name, str):
        raise ValueError("Archive name must be a non-empty string")

    if len(name) > 200:
        raise ValueError("Archive name too long (max 200 characters)")

    return name


def validate_compression(compression: str) -> str:
    """
    Validate compression algorithm.

    Args:
        compression: Compression algorithm

    Returns:
        Validated compression string

    Raises:
        ValueError: If compression is invalid
    """
    valid_compressions = {
        "none",
        "lz4",
        "zlib",
        "lzma",
        "zstd",
        "lz4,1",
        "lz4,9",
        "zlib,1",
        "zlib,9",
        "lzma,0",
        "lzma,9",
        "zstd,1",
        "zstd,22",
    }

    if compression not in valid_compressions:
        raise ValueError(
            f"Invalid compression: {compression}. Valid options: {valid_compressions}"
        )

    return compression


def get_or_generate_secret_key(data_dir: str) -> str:
    """
    Get existing secret key or generate a new one and save it.

    Args:
        data_dir: Directory where the secret key file should be stored

    Returns:
        The secret key string

    Raises:
        Exception: If unable to create data directory or write secret key file
    """

    data_path = Path(data_dir)
    data_path.mkdir(parents=True, exist_ok=True)

    secret_file = data_path / "secret_key"

    if secret_file.exists():
        try:
            return secret_file.read_text().strip()
        except Exception as e:
            raise Exception(f"Failed to read secret key from {secret_file}: {e}")

    secret_key = secrets.token_urlsafe(32)

    try:
        secret_file.write_text(secret_key)
        return secret_key
    except Exception as e:
        raise Exception(f"Failed to save secret key to {secret_file}: {e}")


def _create_temp_keyfile(keyfile_content: str) -> str:
    """Create a temporary keyfile from content and return its path."""
    # Create a temporary file
    temp_fd, temp_path = tempfile.mkstemp(suffix=".key", prefix="borg_temp_")

    try:
        # Write the keyfile content
        with os.fdopen(temp_fd, "w", encoding="utf-8") as f:
            f.write(keyfile_content)

        # Make sure only owner can read the keyfile
        os.chmod(temp_path, 0o600)

        logger.debug(f"Created temporary keyfile at {temp_path}")
        return temp_path
    except Exception:
        # Clean up on error
        try:
            os.unlink(temp_path)
        except OSError:
            pass
        raise


def build_secure_borg_command_with_keyfile(
    base_command: str,
    repository_path: str,
    passphrase: str,
    keyfile_content: Optional[str] = None,
    additional_args: Optional[List[str]] = None,
    environment_overrides: Optional[Dict[str, str]] = None,
) -> Tuple[List[str], Dict[str, str], Optional[str]]:
    """
    Build a secure Borg command with keyfile handling, returning temp keyfile path for manual cleanup.

    Args:
        base_command: The base borg command (e.g., "borg create")
        repository_path: Path to the repository (can be empty if included in additional_args)
        passphrase: Repository passphrase
        keyfile_content: If provided, creates a temporary keyfile and sets BORG_KEY_FILE
        additional_args: Additional command arguments
        environment_overrides: Additional environment variables

    Returns:
        Tuple of (command_list, environment_dict, temp_keyfile_path_for_cleanup)
    """
    temp_keyfile_path = None

    # Handle keyfile creation
    if keyfile_content:
        temp_keyfile_path = _create_temp_keyfile(keyfile_content)
        if not environment_overrides:
            environment_overrides = {}
        environment_overrides["BORG_KEY_FILE"] = temp_keyfile_path

    # Build the command using existing function
    command, env = build_secure_borg_command(
        base_command=base_command,
        repository_path=repository_path,
        passphrase=passphrase,
        additional_args=additional_args,
        environment_overrides=environment_overrides,
    )

    return command, env, temp_keyfile_path


@asynccontextmanager
async def secure_borg_command(
    base_command: str,
    repository_path: str,
    passphrase: str,
    keyfile_content: Optional[str] = None,
    additional_args: Optional[List[str]] = None,
    environment_overrides: Optional[Dict[str, str]] = None,
    cleanup_keyfile: bool = True,
) -> AsyncGenerator[Tuple[List[str], Dict[str, str], Optional[str]], None]:
    """
    Context manager that builds a secure Borg command with optional keyfile cleanup.

    Args:
        base_command: The base borg command (e.g., "borg create")
        repository_path: Path to the repository (can be empty if included in additional_args)
        passphrase: Repository passphrase
        keyfile_content: If provided, creates a temporary keyfile and sets BORG_KEY_FILE
        additional_args: Additional command arguments
        environment_overrides: Additional environment variables
        cleanup_keyfile: If False, keyfile won't be cleaned up automatically (caller must clean up)

    Yields:
        Tuple of (command_list, environment_dict, temp_keyfile_path_for_manual_cleanup)

    Usage:
        # Automatic cleanup (default):
        async with secure_borg_command(...) as (command, env, _):
            result = await command_runner.run_command(command, env)

        # Manual cleanup for long-running jobs:
        async with secure_borg_command(..., cleanup_keyfile=False) as (command, env, temp_keyfile_path):
            job_id = await job_manager.start_job(command, env)
            # Job manager is responsible for cleanup_temp_keyfile(temp_keyfile_path)
    """
    command, env, temp_keyfile_path = build_secure_borg_command_with_keyfile(
        base_command=base_command,
        repository_path=repository_path,
        passphrase=passphrase,
        keyfile_content=keyfile_content,
        additional_args=additional_args,
        environment_overrides=environment_overrides,
    )

    try:
        yield command, env, temp_keyfile_path
    finally:
        # Automatic cleanup (unless disabled)
        if cleanup_keyfile and temp_keyfile_path:
            try:
                os.unlink(temp_keyfile_path)
                logger.debug(f"Cleaned up temporary keyfile: {temp_keyfile_path}")
            except OSError as e:
                logger.warning(
                    f"Failed to clean up temporary keyfile {temp_keyfile_path}: {e}"
                )


def cleanup_temp_keyfile(temp_keyfile_path: Optional[str]) -> None:
    """Helper function to clean up a temporary keyfile."""
    if temp_keyfile_path:
        try:
            os.unlink(temp_keyfile_path)
            logger.debug(f"Cleaned up temporary keyfile: {temp_keyfile_path}")
        except OSError as e:
            logger.warning(
                f"Failed to clean up temporary keyfile {temp_keyfile_path}: {e}"
            )
