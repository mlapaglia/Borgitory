"""
BorgCommandBuilder - Handles Borg command construction and validation
"""

import logging
from borgitory.utils.datetime_utils import now_utc
from typing import Dict, List, Optional, Tuple

from borgitory.models.database import Repository
from borgitory.utils.security import (
    build_secure_borg_command,
    validate_archive_name,
    validate_compression,
    sanitize_path,
)
from borgitory.constants.retention import RetentionFieldHandler

logger = logging.getLogger(__name__)


class BorgCommandBuilder:
    """
    Handles construction and validation of Borg commands.

    Responsibilities:
    - Build secure Borg commands with proper argument validation
    - Generate archive names and validate parameters
    - Construct commands for different Borg operations
    - Apply security and validation rules consistently
    """

    def __init__(self) -> None:
        pass

    def build_backup_command(
        self,
        repository: Repository,
        source_path: str,
        compression: str = "zstd",
        dry_run: bool = False,
        archive_name: Optional[str] = None,
    ) -> Tuple[List[str], Dict[str, str]]:
        """Build a secure backup command with validation"""
        try:
            validate_compression(compression)

            if archive_name is None:
                archive_name = f"backup-{now_utc().strftime('%Y-%m-%d_%H-%M-%S')}"

            validate_archive_name(archive_name)
        except Exception as e:
            raise Exception(f"Validation failed: {str(e)}")

        # Build additional arguments
        additional_args = []

        if dry_run:
            additional_args.append("--dry-run")

        additional_args.extend(
            [
                "--compression",
                compression,
                "--stats",
                "--progress",
                "--json",  # Enable JSON output for progress parsing
                f"{repository.path}::{archive_name}",
                source_path,
            ]
        )

        try:
            command, env = build_secure_borg_command(
                base_command="borg create",
                repository_path=repository.path,
                passphrase=repository.get_passphrase(),
                additional_args=additional_args,
            )
            return command, env
        except Exception as e:
            raise Exception(f"Security validation failed: {str(e)}")

    def build_list_archives_command(
        self, repository: Repository
    ) -> Tuple[List[str], Dict[str, str]]:
        """Build command to list all archives in a repository"""
        try:
            command, env = build_secure_borg_command(
                base_command="borg list",
                repository_path=repository.path,
                passphrase=repository.get_passphrase(),
                additional_args=["--json"],
            )
            return command, env
        except Exception as e:
            raise Exception(f"Security validation failed: {str(e)}")

    def build_repo_info_command(
        self, repository: Repository
    ) -> Tuple[List[str], Dict[str, str]]:
        """Build command to get repository information"""
        try:
            command, env = build_secure_borg_command(
                base_command="borg info",
                repository_path=repository.path,
                passphrase=repository.get_passphrase(),
                additional_args=["--json"],
            )
            return command, env
        except Exception as e:
            raise Exception(f"Security validation failed: {str(e)}")

    def build_list_archive_contents_command(
        self,
        repository: Repository,
        archive_name: str,
        directory_path: Optional[str] = None,
    ) -> Tuple[List[str], Dict[str, str]]:
        """Build command to list contents of a specific archive"""
        try:
            validate_archive_name(archive_name)
        except Exception as e:
            raise Exception(f"Archive name validation failed: {str(e)}")

        additional_args = ["--json-lines"]

        # Build the archive specification
        archive_spec = f"{repository.path}::{archive_name}"

        # If directory path is specified, add it
        if directory_path:
            try:
                sanitized_path = sanitize_path(directory_path)
                archive_spec += f"::{sanitized_path}"
            except Exception as e:
                raise Exception(f"Path validation failed: {str(e)}")

        additional_args.append(archive_spec)

        try:
            command, env = build_secure_borg_command(
                base_command="borg list",
                repository_path=repository.path,
                passphrase=repository.get_passphrase(),
                additional_args=additional_args,
            )
            return command, env
        except Exception as e:
            raise Exception(f"Security validation failed: {str(e)}")

    def build_extract_command(
        self,
        repository: Repository,
        archive_name: str,
        file_path: str,
        extract_to_stdout: bool = True,
    ) -> Tuple[List[str], Dict[str, str]]:
        """Build command to extract a specific file from an archive"""
        try:
            validate_archive_name(archive_name)
            sanitized_file_path = sanitize_path(file_path)
        except Exception as e:
            raise Exception(f"Validation failed: {str(e)}")

        additional_args = []

        if extract_to_stdout:
            additional_args.append("--stdout")

        # Build the archive and file specification
        archive_spec = f"{repository.path}::{archive_name}"
        additional_args.extend([archive_spec, sanitized_file_path])

        try:
            command, env = build_secure_borg_command(
                base_command="borg extract",
                repository_path=repository.path,
                passphrase=repository.get_passphrase(),
                additional_args=additional_args,
            )
            return command, env
        except Exception as e:
            raise Exception(f"Security validation failed: {str(e)}")

    def build_initialize_repository_command(
        self, repository: Repository, encryption_mode: str = "repokey-blake2"
    ) -> Tuple[List[str], Dict[str, str]]:
        """Build command to initialize a new Borg repository"""
        additional_args = ["--encryption", encryption_mode, repository.path]

        try:
            command, env = build_secure_borg_command(
                base_command="borg init",
                repository_path=repository.path,
                passphrase=repository.get_passphrase(),
                additional_args=additional_args,
            )
            return command, env
        except Exception as e:
            raise Exception(f"Security validation failed: {str(e)}")

    def build_prune_command(
        self,
        repository: Repository,
        keep_within: Optional[str] = None,
        keep_secondly: Optional[int] = None,
        keep_minutely: Optional[int] = None,
        keep_hourly: Optional[int] = None,
        keep_daily: Optional[int] = None,
        keep_weekly: Optional[int] = None,
        keep_monthly: Optional[int] = None,
        keep_yearly: Optional[int] = None,
        dry_run: bool = False,
        show_list: bool = True,
        show_stats: bool = True,
        save_space: bool = False,
        force_prune: bool = False,
    ) -> Tuple[List[str], Dict[str, str]]:
        """Build command to prune old archives from a repository"""
        additional_args = []

        retention_args = RetentionFieldHandler.build_borg_args_explicit(
            keep_within=keep_within,
            keep_secondly=keep_secondly,
            keep_minutely=keep_minutely,
            keep_hourly=keep_hourly,
            keep_daily=keep_daily,
            keep_weekly=keep_weekly,
            keep_monthly=keep_monthly,
            keep_yearly=keep_yearly,
            include_keep_within=True,
        )
        additional_args.extend(retention_args)

        # Add options
        if dry_run:
            additional_args.append("--dry-run")
        if show_list:
            additional_args.append("--list")
        if show_stats:
            additional_args.append("--stats")
        if save_space:
            additional_args.append("--save-space")
        if force_prune:
            additional_args.append("--force")

        # Add repository path
        additional_args.append(repository.path)

        try:
            command, env = build_secure_borg_command(
                base_command="borg prune",
                repository_path=repository.path,
                passphrase=repository.get_passphrase(),
                additional_args=additional_args,
            )
            return command, env
        except Exception as e:
            raise Exception(f"Security validation failed: {str(e)}")

    def build_check_command(
        self,
        repository: Repository,
        check_type: str = "repository",
        verify_data: bool = False,
        repair_mode: bool = False,
        save_space: bool = False,
        max_duration: Optional[int] = None,
        archive_prefix: Optional[str] = None,
        archive_glob: Optional[str] = None,
        first_n_archives: Optional[int] = None,
        last_n_archives: Optional[int] = None,
    ) -> Tuple[List[str], Dict[str, str]]:
        """Build command to check repository integrity"""
        additional_args = []

        if check_type == "repository_only":
            additional_args.append("--repository-only")
        elif check_type == "archives_only":
            additional_args.append("--archives-only")
        elif check_type == "full":
            pass
        else:
            additional_args.append("--repository-only")

        if verify_data:
            additional_args.append("--verify-data")
        if repair_mode:
            additional_args.append("--repair")
        if save_space:
            additional_args.append("--save-space")

        if max_duration:
            additional_args.extend(["--max-duration", str(max_duration)])

        if archive_prefix:
            additional_args.extend(["--glob-archives", f"{archive_prefix}*"])
        elif archive_glob:
            additional_args.extend(["--glob-archives", archive_glob])

        if first_n_archives:
            additional_args.extend(["--first", str(first_n_archives)])
        elif last_n_archives:
            additional_args.extend(["--last", str(last_n_archives)])

        additional_args.append(repository.path)

        try:
            command, env = build_secure_borg_command(
                base_command="borg check",
                repository_path=repository.path,
                passphrase=repository.get_passphrase(),
                additional_args=additional_args,
            )
            return command, env
        except Exception as e:
            raise Exception(f"Security validation failed: {str(e)}")

    def generate_archive_name(self, prefix: str = "backup") -> str:
        """Generate a timestamped archive name"""
        timestamp = now_utc().strftime("%Y-%m-%d_%H-%M-%S")
        archive_name = f"{prefix}-{timestamp}"

        try:
            validate_archive_name(archive_name)
            return archive_name
        except Exception as e:
            # Fallback to basic name if validation fails
            logger.warning(f"Generated archive name validation failed: {e}")
            return f"backup-{now_utc().strftime('%Y%m%d_%H%M%S')}"

    def validate_command_parameters(
        self,
        repository: Repository,
        archive_name: Optional[str] = None,
        source_path: Optional[str] = None,
        compression: Optional[str] = None,
    ) -> Dict[str, str]:
        """Validate all command parameters and return any validation errors"""
        errors = {}

        # Validate repository
        if not repository or not repository.path:
            errors["repository"] = "Repository path is required"

        # Validate archive name if provided
        if archive_name:
            try:
                validate_archive_name(archive_name)
            except Exception as e:
                errors["archive_name"] = str(e)

        # Validate source path if provided
        if source_path:
            try:
                sanitize_path(source_path)
            except Exception as e:
                errors["source_path"] = str(e)

        # Validate compression if provided
        if compression:
            try:
                validate_compression(compression)
            except Exception as e:
                errors["compression"] = str(e)

        return errors
