import asyncio
import json
import logging
import re
from contextlib import asynccontextmanager
from borgitory.models.job_results import JobStatusEnum
from borgitory.services.archives.archive_models import ArchiveEntry
from typing import TYPE_CHECKING, AsyncGenerator, List, Optional

if TYPE_CHECKING:
    from borgitory.models.database import Repository
from borgitory.models.borg_info import (
    BorgArchiveListResponse,
    RepositoryInitializationResult,
)
from borgitory.protocols import (
    CommandRunnerProtocol,
    ProcessExecutorProtocol,
    JobManagerProtocol,
)
from borgitory.protocols.file_protocols import FileServiceProtocol
from borgitory.protocols.command_executor_protocol import CommandExecutorProtocol
from borgitory.protocols.repository_protocols import ArchiveServiceProtocol
from borgitory.utils.security import build_secure_borg_command

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
        file_service: FileServiceProtocol,
    ) -> None:
        """
        Initialize BorgService with mandatory dependency injection.

        Args:
            job_executor: Job executor for running Borg processes
            command_runner: Command runner for executing system commands
            job_manager: Job manager for handling job lifecycle
            archive_service: Archive service for managing archive operations
            command_executor: Command executor for cross-platform command execution
        """
        self.job_executor = job_executor
        self.command_runner = command_runner
        self.job_manager = job_manager
        self.archive_service = archive_service
        self.command_executor = command_executor
        self.file_service = file_service
        self.progress_pattern = re.compile(
            r"(?P<original_size>\d+)\s+(?P<compressed_size>\d+)\s+(?P<deduplicated_size>\d+)\s+"
            r"(?P<nfiles>\d+)\s+(?P<path>.*)"
        )

    def _get_job_manager(self) -> JobManagerProtocol:
        """Get job manager instance - guaranteed to be available via DI"""
        return self.job_manager

    async def initialize_repository(
        self, repository: "Repository"
    ) -> RepositoryInitializationResult:
        """Initialize a new Borg repository"""
        logger.info(f"Initializing Borg repository at {repository.path}")

        try:
            async with self.create_borg_command(
                base_command="borg init",
                repository=repository,
                additional_args=["--encryption=" + repository.encryption_type.value],
                environment_overrides=_build_repository_env_overrides(repository),
            ) as (command, env, _):
                result = await self.command_runner.run_command(command, env, timeout=60)

                if result.success:
                    return RepositoryInitializationResult.success_result(
                        "Repository initialized successfully",
                        repository_path=repository.path,
                    )
                else:
                    error_msg = (
                        result.stderr.strip()
                        or result.stdout.strip()
                        or "Unknown error"
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
            async with self.create_borg_command(
                base_command="borg list",
                repository=repository,
                additional_args=["--json"],
                environment_overrides=_build_repository_env_overrides(repository),
            ) as (command, env, _):
                result = await self.command_runner.run_command(command, env, timeout=30)

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
            async with self.create_borg_command(
                base_command="borg info",
                repository=repository,
                additional_args=["--json"],
            ) as (command, env, _):
                job_manager = self._get_job_manager()
                job_id = await job_manager.start_borg_command(command, env=env)

                # Wait for completion
                max_wait = 30
                wait_time = 0.0

                while wait_time < max_wait:
                    status = job_manager.get_job_status(job_id)

                    if not status:
                        return False

                    if (
                        status.status == JobStatusEnum.COMPLETED
                        or status.status == JobStatusEnum.FAILED
                    ):
                        success = status.return_code == 0
                        # Clean up job
                        self._get_job_manager().cleanup_job(job_id)
                        return bool(success)

                    await asyncio.sleep(0.5)
                    wait_time += 0.5

                return False

        except Exception as e:
            logger.error(f"Failed to verify repository access: {e}")
            return False

    async def create_keyfile_in_repository(self, repository: "Repository", keyfile_content: str) -> str:
        """Create a keyfile in the repository directory and return its path."""
        keyfile_path = f"{repository.path}/keyfile.key"
        await self.file_service.write_file(keyfile_path, keyfile_content.encode('utf-8'))
        logger.debug(f"Created keyfile at {keyfile_path}")
        return keyfile_path

    async def cleanup_keyfile(self, keyfile_path: str) -> None:
        """Remove the keyfile after use."""
        try:
            await self.file_service.remove_file(keyfile_path)
            logger.debug(f"Cleaned up keyfile at {keyfile_path}")
        except Exception as e:
            logger.warning(f"Failed to cleanup keyfile at {keyfile_path}: {e}")

    @asynccontextmanager
    async def create_borg_command(
        self,
        repository: "Repository",
        base_command: str,
        additional_args: Optional[list[str]] = None,
        environment_overrides: Optional[dict[str, str]] = None,
        cleanup_keyfile: bool = True,
    ) -> AsyncGenerator[tuple[list[str], dict[str, str], Optional[str]], str]:
        """
        Execute a borg command with keyfile handling as an async context manager.
        Creates keyfile in repository directory if needed and automatically cleans it up afterwards.
        
        Usage:
            async with borg_service.execute_borg_command_with_keyfile(repo, "borg list") as (command, env):
                # Execute the command
                result = await command_executor.run_command(command, env)
        
        Yields:
            tuple: (command, environment) - ready to execute
        """
        keyfile_path = None
        env_overrides = environment_overrides.copy() if environment_overrides else {}
        
        try:
            keyfile_content = repository.get_keyfile_content()
            if keyfile_content:
                keyfile_path = await self.create_keyfile_in_repository(repository, keyfile_content)
                env_overrides["BORG_KEY_FILE"] = keyfile_path

            command, env = build_secure_borg_command(
                base_command=base_command,
                repository_path=repository.path,
                passphrase=repository.get_passphrase(),
                additional_args=additional_args or [],
                environment_overrides=env_overrides,
            )
            
            yield command, env, keyfile_path
            
        finally:
            if keyfile_path and cleanup_keyfile:
                await self.cleanup_keyfile(keyfile_path)
