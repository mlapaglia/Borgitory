import asyncio
import json
import logging
import re
import os
from borgitory.services.archives.archive_manager import ArchiveEntry
from typing import AsyncGenerator, List

from starlette.responses import StreamingResponse

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
from borgitory.protocols.repository_protocols import ArchiveServiceProtocol
from borgitory.utils.security import (
    build_secure_borg_command_with_keyfile,
    secure_borg_command,
    cleanup_temp_keyfile,
    validate_archive_name,
)

logger = logging.getLogger(__name__)


def _build_repository_env_overrides(repository: Repository) -> dict[str, str]:
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
    ) -> None:
        """
        Initialize BorgService with mandatory dependency injection.

        Args:
            job_executor: Job executor for running Borg processes
            command_runner: Command runner for executing system commands
            job_manager: Job manager for handling job lifecycle
            archive_service: Archive service for managing archive operations
        """
        self.job_executor = job_executor
        self.command_runner = command_runner
        self.job_manager = job_manager
        self.archive_service = archive_service
        self.progress_pattern = re.compile(
            r"(?P<original_size>\d+)\s+(?P<compressed_size>\d+)\s+(?P<deduplicated_size>\d+)\s+"
            r"(?P<nfiles>\d+)\s+(?P<path>.*)"
        )

    def _get_job_manager(self) -> JobManagerProtocol:
        """Get job manager instance - guaranteed to be available via DI"""
        return self.job_manager

    async def initialize_repository(
        self, repository: Repository
    ) -> RepositoryInitializationResult:
        """Initialize a new Borg repository"""
        logger.info(f"Initializing Borg repository at {repository.path}")

        try:
            async with secure_borg_command(
                base_command="borg init",
                repository_path=repository.path,
                passphrase=repository.get_passphrase(),
                keyfile_content=repository.get_keyfile_content(),
                additional_args=["--encryption=repokey"],
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

    async def list_archives(self, repository: Repository) -> BorgArchiveListResponse:
        """List all archives in a repository"""
        try:
            async with secure_borg_command(
                base_command="borg list",
                repository_path=repository.path,
                passphrase=repository.get_passphrase(),
                keyfile_content=repository.get_keyfile_content(),
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
        self, repository: Repository, archive_name: str, path: str = ""
    ) -> List[ArchiveEntry]:
        """List contents of a specific directory within an archive using FUSE mount"""
        entries = await self.archive_service.list_archive_directory_contents(
            repository, archive_name, path
        )

        return entries

    async def extract_file_stream(
        self, repository: Repository, archive_name: str, file_path: str
    ) -> StreamingResponse:
        """Extract a single file from an archive and stream it to the client"""
        result = None
        try:
            # Validate inputs
            if not archive_name or not archive_name.strip():
                raise ValueError("Archive name must be a non-empty string")

            if not file_path:
                raise ValueError("File path is required")

            validate_archive_name(archive_name)

            # Build borg extract command with --stdout
            borg_args = ["--stdout", f"{repository.path}::{archive_name}", file_path]

            # Use manual keyfile management for streaming operations
            result = build_secure_borg_command_with_keyfile(
                base_command="borg extract",
                repository_path="",
                passphrase=repository.get_passphrase(),
                keyfile_content=repository.get_keyfile_content(),
                additional_args=borg_args,
            )
            command, env = result.command, result.environment

            logger.info(f"Extracting file {file_path} from archive {archive_name}")

            # Start the borg process
            process = await asyncio.create_subprocess_exec(
                *command,
                env=env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            async def generate_stream() -> AsyncGenerator[bytes, None]:
                """Generator function to stream the file content with automatic backpressure"""
                try:
                    while True:
                        if process.stdout is None:
                            break
                        chunk = await process.stdout.read(
                            65536
                        )  # 64KB chunks for efficiency
                        if not chunk:
                            break

                        yield chunk

                finally:
                    if process.returncode is None:
                        process.terminate()
                        try:
                            await asyncio.wait_for(process.wait(), timeout=5.0)
                        except asyncio.TimeoutError:
                            process.kill()
                            await process.wait()

                    if process.returncode != 0 and process.stderr:
                        stderr = await process.stderr.read()
                        error_msg = (
                            stderr.decode("utf-8") if stderr else "Unknown error"
                        )
                        logger.error(f"Borg extract process failed: {error_msg}")
                        raise Exception(f"Borg extract failed: {error_msg}")

                    # Clean up keyfile after streaming completes
                    result.cleanup_temp_files()

            filename = os.path.basename(file_path)

            return StreamingResponse(
                generate_stream(),
                media_type="application/octet-stream",
                headers={"Content-Disposition": f'attachment; filename="{filename}"'},
            )

        except Exception as e:
            # Clean up keyfile if error occurs before streaming starts
            if result:
                result.cleanup_temp_files()
            logger.error(f"Failed to extract file {file_path}: {str(e)}")
            raise Exception(f"Failed to extract file: {str(e)}")

    async def verify_repository_access(
        self,
        repo_path: str,
        passphrase: str,
        keyfile_path: str = "",
        keyfile_content: str = "",
    ) -> bool:
        """Verify we can access a repository with given credentials"""
        try:
            # Handle keyfile path override if provided
            env_overrides = {}
            if keyfile_path:
                env_overrides["BORG_KEY_FILE"] = keyfile_path

            async with secure_borg_command(
                base_command="borg info",
                repository_path=repo_path,
                passphrase=passphrase,
                keyfile_content=keyfile_content,
                additional_args=["--json"],
                environment_overrides=env_overrides,
                cleanup_keyfile=False,  # Don't cleanup yet - job will handle it
            ) as (command, env, temp_keyfile_path):
                job_manager = self._get_job_manager()
                job_id = await job_manager.start_borg_command(command, env=env)

                # Wait for completion
                max_wait = 30
                wait_time = 0.0

                while wait_time < max_wait:
                    status = job_manager.get_job_status(job_id)

                    if not status:
                        return False

                    if status["completed"] or status["status"] == "failed":
                        success = status["return_code"] == 0
                        # Clean up job
                        self._get_job_manager().cleanup_job(job_id)
                        # Clean up temporary keyfile if created
                        cleanup_temp_keyfile(temp_keyfile_path)
                        return bool(success)

                    await asyncio.sleep(0.5)
                    wait_time += 0.5

                # Cleanup keyfile on timeout
                cleanup_temp_keyfile(temp_keyfile_path)
                return False

        except Exception as e:
            logger.error(f"Failed to verify repository access: {e}")
            return False
