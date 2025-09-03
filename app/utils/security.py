import re
import shlex
from pathlib import Path
from typing import List, Dict, Any
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
    path = path.replace('\x00', '')
    
    # Check for dangerous patterns
    dangerous_patterns = [
        r'\.\./',  # Directory traversal
        r'\.\.\\',  # Windows directory traversal
        r'[;<>|&`$]',  # Command injection characters
        r'\$\(',  # Command substitution
        r'`',  # Backticks
        r'\n|\r',  # Newlines
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
    additional_args: List[str] = None,
    environment_overrides: Dict[str, str] = None
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
        "BORG_UNKNOWN_UNENCRYPTED_REPO_ACCESS_IS_OK": "yes"
    }
    
    if environment_overrides:
        for key, value in environment_overrides.items():
            if not re.match(r'^[A-Z_][A-Z0-9_]*$', key):
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
                i > 0 and additional_args[i-1] == "--pattern"
            ) or arg == "--pattern"
            
            if is_pattern_arg:
                # For pattern arguments, allow regex metacharacters but block shell injection
                # Only check for actual shell injection characters, not regex characters
                if re.search(r'[;<>&`\n\r]', arg):
                    raise ValueError(f"Argument contains dangerous characters: {arg}")
                # Also block command substitution patterns
                if '$(' in arg or '${' in arg:
                    raise ValueError(f"Argument contains dangerous characters: {arg}")
            else:
                # For regular arguments, use stricter validation
                if re.search(r'[;<>|&`$\n\r]', arg):
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
    
    # Archive names should only contain safe characters
    if not re.match(r'^[a-zA-Z0-9._-]+$', name):
        raise ValueError("Archive name contains invalid characters. Only alphanumeric, dots, hyphens, and underscores allowed")
    
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
        'none', 'lz4', 'zlib', 'lzma', 'zstd',
        'lz4,1', 'lz4,9', 'zlib,1', 'zlib,9',
        'lzma,0', 'lzma,9', 'zstd,1', 'zstd,22'
    }
    
    if compression not in valid_compressions:
        raise ValueError(f"Invalid compression: {compression}. Valid options: {valid_compressions}")
    
    return compression