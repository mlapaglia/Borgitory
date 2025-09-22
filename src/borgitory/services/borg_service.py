import asyncio
import json
import logging
import re
import os
from datetime import datetime
from borgitory.utils.datetime_utils import now_utc
from typing import Any, AsyncGenerator, Dict, List, Optional, cast

from starlette.responses import StreamingResponse

from borgitory.models.database import Repository, Job
from borgitory.services.jobs.job_executor import JobExecutor
from borgitory.services.simple_command_runner import SimpleCommandRunner
from borgitory.protocols import (
    CommandRunnerProtocol,
    VolumeServiceProtocol,
    JobManagerProtocol,
)
from borgitory.utils.db_session import get_db_session
from borgitory.utils.security import (
    build_secure_borg_command,
    validate_archive_name,
    validate_compression,
    sanitize_path,
)

logger = logging.getLogger(__name__)


class BorgService:
    def __init__(
        self,
        job_executor: Optional[JobExecutor] = None,
        command_runner: Optional[CommandRunnerProtocol] = None,
        job_manager: Optional[JobManagerProtocol] = None,
        volume_service: Optional[VolumeServiceProtocol] = None,
    ) -> None:
        self.job_executor = job_executor or JobExecutor()
        self.command_runner = command_runner or SimpleCommandRunner()
        self.job_manager = job_manager
        self.volume_service = volume_service
        self.progress_pattern = re.compile(
            r"(?P<original_size>\d+)\s+(?P<compressed_size>\d+)\s+(?P<deduplicated_size>\d+)\s+"
            r"(?P<nfiles>\d+)\s+(?P<path>.*)"
        )

    def _get_job_manager(self) -> JobManagerProtocol:
        """Get job manager instance - must be injected via DI"""
        if self.job_manager is None:
            raise RuntimeError(
                "JobManager not provided - must be injected via dependency injection"
            )
        return self.job_manager

    def _parse_borg_config(self, repo_path: str) -> Dict[str, Any]:
        """Parse a Borg repository config file to determine encryption mode"""
        config_path = os.path.join(repo_path, "config")

        try:
            if not os.path.exists(config_path):
                return {
                    "mode": "unknown",
                    "requires_keyfile": False,
                    "preview": "Config file not found",
                }

            with open(config_path, "r", encoding="utf-8") as f:
                config_content = f.read()

            # Parse the config file (it's an INI-like format)
            import configparser

            config = configparser.ConfigParser()
            config.read_string(config_content)

            # Debug: log the actual config content to understand structure
            logger.info(f"Parsing Borg config at {config_path}")
            logger.info(f"Sections found: {config.sections()}")

            # Check if this looks like a Borg repository
            if not config.has_section("repository"):
                return {
                    "mode": "invalid",
                    "requires_keyfile": False,
                    "preview": "Not a valid Borg repository (no [repository] section)",
                }

            # Log all options in repository section
            if config.has_section("repository"):
                repo_options = dict(config.items("repository"))
                logger.info(f"Repository section options: {repo_options}")

            # The key insight: Borg stores encryption info differently
            # Check for a key file in the repository directory
            key_files = []
            try:
                for item in os.listdir(repo_path):
                    if item.startswith("key.") or "key" in item.lower():
                        key_files.append(item)
            except (OSError, ValueError):
                pass

            # Method 1: Check for repokey data in config
            encryption_mode = "unknown"
            requires_keyfile = False
            preview = "Repository detected"

            # Look for key-related sections
            key_sections = [s for s in config.sections() if "key" in s.lower()]
            logger.info(f"Key-related sections: {key_sections}")

            # Check repository section for encryption hints
            repo_section = dict(config.items("repository"))

            # Check for encryption by looking for the 'key' field in repository section
            if "key" in repo_section:
                # Repository has a key field - this means it's encrypted
                key_value = repo_section["key"]

                if (
                    key_value and len(key_value) > 50
                ):  # Key data is present and substantial
                    # This is repokey mode - key is embedded in the repository
                    encryption_mode = "repokey"
                    requires_keyfile = False
                    preview = "Encrypted repository (repokey mode) - key embedded in repository"
                else:
                    # Key field exists but might be empty/reference - possibly keyfile mode
                    if key_files:
                        encryption_mode = "keyfile"
                        requires_keyfile = True
                        preview = f"Encrypted repository (keyfile mode) - found key files: {', '.join(key_files)}"
                    else:
                        encryption_mode = "encrypted"
                        requires_keyfile = False
                        preview = (
                            "Encrypted repository (key field present but unclear mode)"
                        )
            elif key_files:
                # No key in config but key files found - definitely keyfile mode
                encryption_mode = "keyfile"
                requires_keyfile = True
                preview = f"Encrypted repository (keyfile mode) - found key files: {', '.join(key_files)}"
            else:
                # No key field and no key files - check for other encryption indicators
                all_content_lower = config_content.lower()
                if any(
                    word in all_content_lower
                    for word in ["encrypt", "cipher", "algorithm", "blake2", "aes"]
                ):
                    encryption_mode = "encrypted"
                    requires_keyfile = False
                    preview = (
                        "Encrypted repository (encryption detected but mode unclear)"
                    )
                else:
                    # Likely unencrypted (very rare for Borg)
                    encryption_mode = "none"
                    requires_keyfile = False
                    preview = "Unencrypted repository (no encryption detected)"

            return {
                "mode": encryption_mode,
                "requires_keyfile": requires_keyfile,
                "preview": preview,
            }

        except Exception as e:
            logger.error(f"Error parsing Borg config at {config_path}: {e}")
            return {
                "mode": "error",
                "requires_keyfile": False,
                "preview": f"Error reading config: {str(e)}",
            }

    async def initialize_repository(self, repository: Repository) -> Dict[str, Any]:
        """Initialize a new Borg repository"""
        logger.info(f"Initializing Borg repository at {repository.path}")

        try:
            command, env = build_secure_borg_command(
                base_command="borg init",
                repository_path=repository.path,
                passphrase=repository.get_passphrase(),
                additional_args=["--encryption=repokey"],
            )
        except Exception as e:
            logger.error(f"Failed to build secure command: {e}")
            return {
                "success": False,
                "message": f"Security validation failed: {str(e)}",
            }

        try:
            # Execute the command directly and wait for result
            result = await self.command_runner.run_command(command, env, timeout=60)

            if result.success:
                return {
                    "success": True,
                    "message": "Repository initialized successfully",
                }
            else:
                # Check if it's just because repo already exists
                if "already exists" in result.stderr.lower():
                    logger.info("Repository already exists, which is fine")
                    return {
                        "success": True,
                        "message": "Repository already exists",
                    }

                # Return the actual error from borg
                error_msg = (
                    result.stderr.strip() or result.stdout.strip() or "Unknown error"
                )
                return {
                    "success": False,
                    "message": f"Initialization failed: {error_msg.decode('utf-8', errors='replace') if isinstance(error_msg, bytes) else error_msg}",
                }

        except Exception as e:
            logger.error(f"Failed to initialize repository: {e}")
            return {"success": False, "message": str(e)}

    async def create_backup(
        self,
        repository: Repository,
        source_path: str,
        compression: str = "zstd",
        dry_run: bool = False,
        cloud_sync_config_id: Optional[int] = None,
    ) -> str:
        """Create a backup and return job_id for tracking"""
        logger.info(
            f"Creating backup for repository: {repository.name} at {repository.path}"
        )

        try:
            validate_compression(compression)
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
                repository_path="",  # Path is included in additional_args
                passphrase=repository.get_passphrase(),
                additional_args=additional_args,
            )
        except Exception as e:
            raise Exception(f"Security validation failed: {str(e)}")

        try:
            job_id = await self._get_job_manager().start_borg_command(
                command, env=env, is_backup=True
            )

            # Create job record in database
            from borgitory.utils.db_session import get_db_session

            with get_db_session() as db:
                job = Job()
                job.id = job_id  # Store the JobManager UUID as the primary key
                job.repository_id = repository.id
                job.type = "backup"
                job.status = "queued"  # Will be updated to 'running' when started
                job.started_at = datetime.now()
                job.cloud_sync_config_id = cloud_sync_config_id
                db.add(job)
                db.refresh(job)
                logger.info(f"Created job record {job.id} for backup job {job_id}")

            return job_id

        except Exception as e:
            logger.error(f"Failed to start backup: {e}")
            raise Exception(f"Failed to start backup: {str(e)}")

    async def list_archives(self, repository: Repository) -> List[Dict[str, Any]]:
        """List all archives in a repository"""
        try:
            command, env = build_secure_borg_command(
                base_command="borg list",
                repository_path=repository.path,
                passphrase=repository.get_passphrase(),
                additional_args=["--json"],
            )
        except Exception as e:
            raise Exception(f"Security validation failed: {str(e)}")

        try:
            # Start the borg list command
            job_manager = self._get_job_manager()
            job_id = await job_manager.start_borg_command(command, env=env)

            # Create database job record for tracking
            with get_db_session() as db:
                db_job = Job()
                db_job.id = job_id  # Store the JobManager UUID as the primary key
                db_job.repository_id = repository.id
                db_job.type = "list"
                db_job.status = "running"
                db_job.started_at = now_utc()
                db.add(db_job)
                db.commit()  # Commit the job record
                logger.info(f"Created database record for list archives job {job_id}")

            # Wait for completion (list is usually quick)
            max_wait = 30  # 30 seconds max
            wait_time = 0.0
            final_status = None

            while wait_time < max_wait:
                status = job_manager.get_job_status(job_id)
                if not status:
                    final_status = {
                        "status": "failed",
                        "return_code": -1,
                        "error": "Job not found",
                    }
                    break

                if status["completed"] or status["status"] in ["completed", "failed"]:
                    final_status = status
                    break

                await asyncio.sleep(0.5)
                wait_time += 0.5

            # Handle timeout
            if final_status is None:
                final_status = {
                    "status": "failed",
                    "return_code": -1,
                    "error": "List archives timed out",
                }

            # Single database update at the end
            with get_db_session() as db:
                existing_job: Optional[Job] = (
                    db.query(Job).filter(Job.id == job_id).first()
                )
                if existing_job:
                    existing_job.status = (
                        "completed" if final_status["return_code"] == 0 else "failed"
                    )
                    existing_job.finished_at = now_utc()
                    if final_status["return_code"] != 0:
                        existing_job.error = str(
                            final_status.get("error", "Unknown error")
                        )
                    db.commit()

            # Handle the result
            if final_status["return_code"] != 0:
                error_msg = final_status.get("error", "Unknown error")
                raise Exception(f"Borg list failed: {error_msg}")

            # Get and process the output
            output = await self._get_job_manager().get_job_output_stream(job_id)

            # Parse JSON output - look for complete JSON structure
            json_lines = []
            for line in cast(List[Dict[str, str]], output.get("lines", [])):
                line_text = line["text"].strip()
                if line_text:
                    json_lines.append(line_text)

            # Try to parse the complete JSON output
            full_json = "\n".join(json_lines)
            try:
                data = json.loads(full_json)
                if "archives" in data:
                    logger.info(
                        f"Successfully parsed {len(data['archives'])} archives from repository"
                    )
                    return cast(List[Dict[str, Any]], data["archives"])
            except json.JSONDecodeError as je:
                logger.error(f"JSON decode error: {je}")
                logger.error(f"Raw output: {full_json[:500]}...")  # Log first 500 chars

            # Fallback: return empty list if no valid JSON found
            logger.warning(
                "No valid archives JSON found in output, returning empty list"
            )
            return []

        except Exception as e:
            raise Exception(f"Failed to list archives: {str(e)}")

    async def get_repo_info(self, repository: Repository) -> Dict[str, Any]:
        """Get repository information using direct process execution"""
        try:
            command, env = build_secure_borg_command(
                base_command="borg info",
                repository_path=repository.path,
                passphrase=repository.get_passphrase(),
                additional_args=["--json"],
            )
        except Exception as e:
            raise Exception(f"Security validation failed: {str(e)}")

        try:
            # Use JobExecutor directly for simple synchronous operations
            process = await self.job_executor.start_process(command, env)
            result = await self.job_executor.monitor_process_output(process)

            if result.return_code == 0:
                # Parse JSON output from stdout
                output_text = result.stdout.decode("utf-8", errors="replace")
                for line in output_text.split("\n"):
                    line = line.strip()
                    if line.startswith("{"):
                        try:
                            return cast(Dict[str, Any], json.loads(line))
                        except json.JSONDecodeError:
                            continue

                raise Exception("No valid JSON output found")
            else:
                error_text = (
                    result.stderr.decode("utf-8", errors="replace")
                    if result.stderr
                    else "Unknown error"
                )
                raise Exception(
                    f"Borg info failed with code {result.return_code}: {error_text}"
                )

        except Exception as e:
            raise Exception(f"Failed to get repository info: {str(e)}")

    async def list_archive_contents(
        self, repository: Repository, archive_name: str
    ) -> List[Dict[str, Any]]:
        """List contents of a specific archive"""
        try:
            validate_archive_name(archive_name)
            command, env = build_secure_borg_command(
                base_command="borg list",
                repository_path="",  # Path is in archive specification
                passphrase=repository.get_passphrase(),
                additional_args=["--json-lines", f"{repository.path}::{archive_name}"],
            )
        except Exception as e:
            raise Exception(f"Validation failed: {str(e)}")

        try:
            # Use JobExecutor directly for simple synchronous operations
            process = await self.job_executor.start_process(command, env)
            result = await self.job_executor.monitor_process_output(process)

            if result.return_code == 0:
                # Parse JSON lines output from stdout
                output_text = result.stdout.decode("utf-8", errors="replace")
                contents = []

                for line in output_text.split("\n"):
                    line = line.strip()
                    if line.startswith("{"):
                        try:
                            item = json.loads(line)
                            contents.append(item)
                        except json.JSONDecodeError:
                            continue

                return contents
            else:
                error_text = (
                    result.stderr.decode("utf-8", errors="replace")
                    if result.stderr
                    else "Unknown error"
                )
                raise Exception(
                    f"Borg list failed with code {result.return_code}: {error_text}"
                )

        except Exception as e:
            raise Exception(f"Failed to list archive contents: {str(e)}")

    async def list_archive_directory_contents(
        self, repository: Repository, archive_name: str, path: str = ""
    ) -> List[Dict[str, Any]]:
        """List contents of a specific directory within an archive using FUSE mount"""
        # Use the archive manager which now uses FUSE mounting
        if not hasattr(self, "_archive_manager"):
            from borgitory.services.archives.archive_manager import ArchiveManager

            self._archive_manager = ArchiveManager()

        entries = await self._archive_manager.list_archive_directory_contents(
            repository, archive_name, path
        )
        # Convert ArchiveEntry objects to dictionaries
        return [
            entry.__dict__ if hasattr(entry, "__dict__") else dict(entry)
            for entry in entries
        ]

    async def extract_file_stream(
        self, repository: Repository, archive_name: str, file_path: str
    ) -> StreamingResponse:
        """Extract a single file from an archive and stream it to the client"""
        try:
            validate_archive_name(archive_name)

            # Sanitize the file path
            if not file_path or not isinstance(file_path, str):
                raise Exception("File path is required")

            # Build borg extract command with --stdout
            borg_args = ["--stdout", f"{repository.path}::{archive_name}", file_path]

            command, env = build_secure_borg_command(
                base_command="borg extract",
                repository_path="",
                passphrase=repository.get_passphrase(),
                additional_args=borg_args,
            )

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

            filename = os.path.basename(file_path)

            return StreamingResponse(
                generate_stream(),
                media_type="application/octet-stream",
                headers={"Content-Disposition": f'attachment; filename="{filename}"'},
            )

        except Exception as e:
            logger.error(f"Failed to extract file {file_path}: {str(e)}")
            raise Exception(f"Failed to extract file: {str(e)}")

    async def verify_repository_access(
        self, repo_path: str, passphrase: str, keyfile_path: str = ""
    ) -> bool:
        """Verify we can access a repository with given credentials"""
        try:
            # Build environment overrides for keyfile if needed
            env_overrides = {}
            if keyfile_path != "":
                env_overrides["BORG_KEY_FILE"] = keyfile_path

            command, env = build_secure_borg_command(
                base_command="borg info",
                repository_path=repo_path,
                passphrase=passphrase,
                additional_args=["--json"],
                environment_overrides=env_overrides,
            )
        except Exception as e:
            logger.error(f"Security validation failed: {e}")
            return False

        try:
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
                    return bool(success)

                await asyncio.sleep(0.5)
                wait_time += 0.5

            return False

        except Exception as e:
            logger.error(f"Failed to verify repository access: {e}")
            return False

    def _validate_scan_path(self, path: str) -> bool:
        """Validate if a scan path exists and is a directory (abstracted for testing)"""
        try:
            safe_scan_path = sanitize_path(path)
            return os.path.exists(safe_scan_path) and os.path.isdir(safe_scan_path)
        except Exception:
            return False

    def _is_valid_repository_path(self, path: str) -> bool:
        """Check if a path is a valid repository path (abstracted for testing)"""
        return bool(
            path
            and path.startswith("/")  # Must be an absolute path
            and os.path.isdir(path)  # Must be a valid directory
        )

    async def _get_mounted_volumes(self) -> List[str]:
        """Get mounted volumes (abstracted for testing)"""
        if self.volume_service:
            return await self.volume_service.get_mounted_volumes()
        else:
            # Fallback: use direct import (for backward compatibility)
            from borgitory.dependencies import get_volume_service

            volume_service = get_volume_service()
            return await volume_service.get_mounted_volumes()

    async def scan_for_repositories(self) -> List[Dict[str, Any]]:
        """Scan for Borg repositories using SimpleCommandRunner"""
        logger.info("Starting repository scan")

        mounted_volumes = await self._get_mounted_volumes()

        if not mounted_volumes:
            logger.warning("No mounted volumes found, falling back to /mnt")
            scan_paths = ["/mnt"]
        else:
            scan_paths = mounted_volumes

        logger.info(f"Scanning across {len(scan_paths)} mounted volumes: {scan_paths}")

        # Build command to scan multiple paths
        command_parts = ["find"]

        # Add all valid scan paths
        for path in scan_paths:
            if self._validate_scan_path(path):
                command_parts.append(sanitize_path(path))
            else:
                logger.warning(f"Skipping invalid scan path {path}")

        # If no valid paths found, use /mnt as fallback
        if len(command_parts) == 1:  # Only "find" command
            logger.warning("No valid scan paths found, using /mnt as fallback")
            command_parts.append("/mnt")

        # Add find parameters
        command_parts.extend(
            [
                "-mindepth",
                "2",  # Start looking 2 levels deep (scan_path/repo_name/config)
                "-maxdepth",
                "2",  # Don't go deeper than 2 levels
                "-name",
                "config",
                "-type",
                "f",
                "-exec",
                "sh",
                "-c",
                'if head -20 "$1" 2>/dev/null | grep -q "\\[repository\\]"; then echo "$(dirname "$1")"; fi',
                "_",
                "{}",
                ";",
            ]
        )

        try:
            logger.info(f"Executing scan command: {' '.join(command_parts)}")

            # Execute the command directly and wait for result
            result = await self.command_runner.run_command(command_parts, timeout=300)

            if not result.success:
                logger.error(f"Scan failed: {result.error}")
                return []

            # Process the output to find repositories
            repo_paths = []
            for line in result.stdout.splitlines():
                line_text = (
                    line.decode("utf-8", errors="replace").strip()
                    if isinstance(line, bytes)
                    else line.strip()
                )
                if self._is_valid_repository_path(line_text):
                    # Parse the Borg config file to get encryption info
                    encryption_info = self._parse_borg_config(line_text)

                    repo_paths.append(
                        {
                            "path": line_text,
                            "id": f"repo_{hash(line_text)}",
                            "encryption_mode": encryption_info["mode"],
                            "requires_keyfile": encryption_info["requires_keyfile"],
                            "detected": True,
                            "config_preview": encryption_info["preview"],
                        }
                    )

            logger.info(f"Scan completed, found {len(repo_paths)} repositories")
            return repo_paths

        except Exception as e:
            logger.error(f"Failed to scan for repositories: {e}")
            return []
