import asyncio
import json
import logging
import re
from borgitory.models.job_results import JobStatusEnum
from borgitory.services.archives.archive_models import ArchiveEntry
from typing import List

from borgitory.models.database import Repository
from borgitory.models.borg_info import (
    BorgArchiveListResponse,
    BorgDefaultDirectories,
    RepositoryInitializationResult,
)
from borgitory.protocols import (
    CommandRunnerProtocol,
    ProcessExecutorProtocol,
    JobManagerProtocol,
)
from borgitory.protocols.command_executor_protocol import CommandExecutorProtocol
from borgitory.protocols.path_protocols import PathServiceInterface
from borgitory.protocols.repository_protocols import ArchiveServiceProtocol
from borgitory.utils.security import create_borg_command

logger = logging.getLogger(__name__)


def _build_repository_env_overrides(repository: "Repository") -> dict[str, str]:
    """Build environment overrides for a repository, including cache directory."""
    env_overrides = {}
    if repository.cache_dir:
        env_overrides["BORG_CACHE_DIR"] = repository.cache_dir
    return env_overrides


class BorgService:
    def __init__(
        self,
        job_executor: ProcessExecutorProtocol,
        command_runner: CommandRunnerProtocol,
        job_manager: JobManagerProtocol,
        archive_service: ArchiveServiceProtocol,
        command_executor: CommandExecutorProtocol,
        path_service: PathServiceInterface,
    ) -> None:
        """
        Initialize BorgService with mandatory dependency injection.

        Args:
            job_executor: Job executor for running Borg processes
            command_runner: Command runner for executing system commands
            job_manager: Job manager for handling job lifecycle
            archive_service: Archive service for managing archive operations
            command_executor: Command executor for cross-platform command execution
            path_service: Path service for secure path operations
        """
        self.job_executor = job_executor
        self.command_runner = command_runner
        self.job_manager = job_manager
        self.archive_service = archive_service
        self.command_executor = command_executor
        self.path_service = path_service
        self.progress_pattern = re.compile(
            r"(?P<original_size>\d+)\s+(?P<compressed_size>\d+)\s+(?P<deduplicated_size>\d+)\s+"
            r"(?P<nfiles>\d+)\s+(?P<path>.*)"
        )

    async def initialize_repository(
        self, repository: "Repository"
    ) -> RepositoryInitializationResult:
        """Initialize a new Borg repository"""
        logger.info(f"Initializing Borg repository at {repository.path}")

        try:
            borg_command = create_borg_command(
                base_command="borg init",
                repository_path=repository.path,
                passphrase=repository.get_passphrase(),
                additional_args=["--encryption=" + repository.encryption_type.value],
                environment_overrides=_build_repository_env_overrides(repository),
            )

            result = await self.command_runner.run_command(
                borg_command.command, borg_command.environment, timeout=60
            )

            if result.success:
                return RepositoryInitializationResult.success_result(
                    "Repository initialized successfully",
                    repository_path=repository.path,
                )
            else:
                error_msg = (
                    result.stderr.strip() or result.stdout.strip() or "Unknown error"
                )
                decoded_error = (
                    error_msg.decode("utf-8", errors="replace")
                    if isinstance(error_msg, bytes)
                    else error_msg
                )
                return RepositoryInitializationResult.failure_result(
                    f"Initialization failed: {decoded_error}"
                )

        except Exception as e:
            logger.error(f"Failed to initialize repository: {e}")
            return RepositoryInitializationResult.failure_result(str(e))

    async def list_archives(self, repository: "Repository") -> BorgArchiveListResponse:
        """List all archives in a repository"""
        try:
            borg_command = create_borg_command(
                base_command="borg list",
                repository_path=repository.path,
                passphrase=repository.get_passphrase(),
                additional_args=["--json"],
                environment_overrides=_build_repository_env_overrides(repository),
            )

            result = await self.command_runner.run_command(
                borg_command.command, borg_command.environment, timeout=30
            )

            if result.success and result.return_code == 0:
                try:
                    data = json.loads(result.stdout)
                    return BorgArchiveListResponse.from_borg_json(data)
                except json.JSONDecodeError as je:
                    logger.error(f"JSON decode error: {je}")
                    logger.error(f"Raw output: {result.stdout[:500]}...")
                    return BorgArchiveListResponse(archives=[])
            else:
                raise Exception(
                    f"Borg list failed with code {result.return_code}: {result.stderr}"
                )

        except Exception as e:
            raise Exception(f"Failed to list archives: {str(e)}")

    async def list_archive_directory_contents(
        self, repository: "Repository", archive_name: str, path: str = ""
    ) -> List[ArchiveEntry]:
        """List contents of a specific directory within an archive"""
        entries = await self.archive_service.list_archive_directory_contents(
            repository, archive_name, path
        )

        return entries

    async def verify_repository_access(
        self,
        repository: "Repository",
    ) -> bool:
        """Verify we can access a repository with given credentials"""
        try:
            result = create_borg_command(
                base_command="borg info",
                repository_path=repository.path,
                passphrase=repository.get_passphrase(),
                additional_args=["--json"],
            )

            job_id = await self.job_manager.start_borg_command(
                result.command, env=result.environment
            )

            max_wait = 30
            wait_time = 0.0

            while wait_time < max_wait:
                status = self.job_manager.get_job_status(job_id)

                if not status:
                    return False

                if (
                    status.status == JobStatusEnum.COMPLETED
                    or status.status == JobStatusEnum.FAILED
                ):
                    success = status.return_code == 0

                    self.job_manager.cleanup_job(job_id)
                    return bool(success)

                await asyncio.sleep(0.5)
                wait_time += 0.5

            return False

        except Exception as e:
            logger.error(f"Failed to verify repository access: {e}")
            return False

    async def get_default_directories(self) -> BorgDefaultDirectories:
        """
        Determine Borg's default directories based on environment variable resolution.

        Uses command executor to query environment variables from the actual execution
        environment (e.g., WSL when running on Windows but executing in Linux).

        Follows Borg's environment variable precedence rules:
        - BORG_BASE_DIR defaults to $HOME or ~$USER or ~
        - BORG_CACHE_DIR defaults to $BORG_BASE_DIR/.cache/borg (or $XDG_CACHE_HOME/borg if XDG is set)
        - BORG_CONFIG_DIR defaults to $BORG_BASE_DIR/.config/borg (or $XDG_CONFIG_HOME/borg if XDG is set)
        - BORG_SECURITY_DIR defaults to $BORG_CONFIG_DIR/security
        - BORG_KEYS_DIR defaults to $BORG_CONFIG_DIR/keys
        """

        async def get_env_var(var_name: str) -> str:
            """Get environment variable from execution environment."""
            result = await self.command_executor.execute_command(
                ["echo", f"${var_name}"]
            )

            return result.stdout.strip() if result.success and result.stdout else ""

        borg_base_dir_explicit = await get_env_var("BORG_BASE_DIR")

        if borg_base_dir_explicit:
            base_dir = borg_base_dir_explicit
        else:
            home = await get_env_var("HOME")
            if not home:
                user = await get_env_var("USER")
                if user:
                    result = await self.command_executor.execute_command(
                        ["cd", "~", "&&", "pwd"]
                    )
                    home = result.stdout.strip() if result.success else ""
            base_dir = home

        xdg_cache_home = await get_env_var("XDG_CACHE_HOME")
        xdg_config_home = await get_env_var("XDG_CONFIG_HOME")

        if not borg_base_dir_explicit and xdg_cache_home:
            cache_dir = self.path_service.secure_join(xdg_cache_home, "borg")
        else:
            cache_dir = self.path_service.secure_join(base_dir, ".cache", "borg")

        if not borg_base_dir_explicit and xdg_config_home:
            config_dir = self.path_service.secure_join(xdg_config_home, "borg")
        else:
            config_dir = self.path_service.secure_join(base_dir, ".config", "borg")

        security_dir = self.path_service.secure_join(config_dir, "security")
        keys_dir = self.path_service.secure_join(config_dir, "keys")

        temp_result = await self.command_executor.execute_command(
            ["echo", "${TMPDIR:-/tmp}"]
        )
        temp_dir = temp_result.stdout.strip() if temp_result.success else "/tmp"

        return BorgDefaultDirectories(
            base_dir=base_dir,
            cache_dir=cache_dir,
            config_dir=config_dir,
            security_dir=security_dir,
            keys_dir=keys_dir,
            temp_dir=temp_dir,
        )
