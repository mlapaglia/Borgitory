"""
Repository Business Logic Service.
Handles all repository-related business operations independent of HTTP concerns.
"""

import asyncio
import logging
import os
from typing import Dict, List, Protocol, TypedDict, Union, Any
from sqlalchemy.orm import Session

from borgitory.models.database import Repository, Job, Schedule
from borgitory.models.repository_dtos import (
    CreateRepositoryRequest,
    ImportRepositoryRequest,
    RepositoryOperationResult,
    RepositoryValidationError,
    ArchiveInfo,
    ArchiveListingResult,
    DirectoryListingRequest,
    DirectoryListingResult,
    ArchiveContentsRequest,
    ArchiveContentsResult,
    DirectoryItem,
    RepositoryScanRequest,
    RepositoryScanResult,
    ScannedRepository,
    DeleteRepositoryRequest,
    DeleteRepositoryResult,
)
from borgitory.services.borg_service import BorgService
from borgitory.services.scheduling.scheduler_service import SchedulerService
from borgitory.services.volumes.volume_service import VolumeService
from borgitory.utils.datetime_utils import (
    format_datetime_for_display,
    parse_datetime_string,
)
from borgitory.utils.secure_path import (
    create_secure_filename,
    secure_path_join,
    secure_remove_file,
    PathSecurityError,
    user_secure_exists,
    user_secure_isdir,
    user_get_directory_listing,
)
from borgitory.utils.security import secure_borg_command

logger = logging.getLogger(__name__)


class KeyfileProtocol(Protocol):
    """Protocol for keyfile objects (e.g., FastAPI UploadFile)."""

    filename: str | None

    async def read(self) -> bytes:
        """Read the file content."""
        ...


class KeyfileSuccessResult(TypedDict):
    """Result when keyfile save succeeds."""

    success: bool
    path: str


class KeyfileErrorResult(TypedDict):
    """Result when keyfile save fails."""

    success: bool
    error: str


KeyfileSaveResult = Union[KeyfileSuccessResult, KeyfileErrorResult]


class RepositoryService:
    """Service for repository business logic operations."""

    def __init__(
        self,
        borg_service: BorgService,
        scheduler_service: SchedulerService,
        volume_service: VolumeService,
    ) -> None:
        self.borg_service = borg_service
        self.scheduler_service = scheduler_service
        self.volume_service = volume_service

    async def create_repository(
        self, request: CreateRepositoryRequest, db: Session
    ) -> RepositoryOperationResult:
        """Create a new Borg repository."""
        try:
            # Validate repository doesn't already exist
            validation_errors = await self._validate_repository_creation(request, db)
            if validation_errors:
                return RepositoryOperationResult(
                    success=False, validation_errors=validation_errors
                )

            db_repo = Repository()
            db_repo.name = request.name
            db_repo.path = request.path
            db_repo.set_passphrase(request.passphrase)

            # Initialize repository with Borg
            init_result = await self.borg_service.initialize_repository(db_repo)
            if not init_result.success:
                borg_error = init_result.message
                error_message = self._parse_borg_initialization_error(borg_error)

                logger.error(
                    f"Repository initialization failed for '{request.name}': {borg_error}"
                )
                return RepositoryOperationResult(
                    success=False,
                    error_message=error_message,
                    borg_error=borg_error,
                )

            # Save to database
            db.add(db_repo)
            db.commit()
            db.refresh(db_repo)

            logger.info(
                f"Successfully created and initialized repository '{request.name}'"
            )

            return RepositoryOperationResult(
                success=True,
                repository_id=db_repo.id,
                repository_name=db_repo.name,
                message=f"Repository '{request.name}' created successfully",
            )

        except Exception as e:
            db.rollback()
            error_message = f"Failed to create repository: {str(e)}"
            logger.error(error_message)
            return RepositoryOperationResult(success=False, error_message=error_message)

    async def import_repository(
        self, request: ImportRepositoryRequest, db: Session
    ) -> RepositoryOperationResult:
        """Import an existing Borg repository."""
        try:
            # Validate repository doesn't already exist
            validation_errors = await self._validate_repository_import(request, db)
            if validation_errors:
                return RepositoryOperationResult(
                    success=False, validation_errors=validation_errors
                )

            # Handle keyfile if provided
            keyfile_path: str | None = None
            if request.keyfile and request.keyfile.filename:
                keyfile_result = await self._save_keyfile(request.name, request.keyfile)
                if not keyfile_result["success"]:
                    # Type narrowing: if success is False, it's a KeyfileErrorResult
                    error_msg = keyfile_result.get("error")
                    return RepositoryOperationResult(
                        success=False,
                        error_message=str(error_msg)
                        if error_msg
                        else "Unknown keyfile error",
                    )
                # Type narrowing: if success is True, it's a KeyfileSuccessResult
                path_value = keyfile_result.get("path")
                keyfile_path = str(path_value) if path_value else None

            db_repo = Repository()
            db_repo.name = request.name
            db_repo.path = request.path
            db_repo.set_passphrase(request.passphrase)

            # Set encryption type if provided
            if request.encryption_type:
                db_repo.encryption_type = request.encryption_type

            # Set keyfile content if provided
            if request.keyfile_content:
                db_repo.set_keyfile_content(request.keyfile_content)

            db.add(db_repo)
            db.commit()
            db.refresh(db_repo)

            verification_successful = await self.borg_service.verify_repository_access(
                repo_path=request.path,
                passphrase=request.passphrase,
                keyfile_path=str(keyfile_path) if keyfile_path else "",
                keyfile_content=request.keyfile_content or "",
            )

            if not verification_successful:
                if keyfile_path:
                    secure_remove_file(keyfile_path)
                db.delete(db_repo)
                db.commit()

                return RepositoryOperationResult(
                    success=False,
                    error_message="Failed to verify repository access. Please check the path, passphrase, and keyfile (if required).",
                )

            try:
                archives_response = await self.borg_service.list_archives(db_repo)
                logger.info(
                    f"Successfully imported repository '{request.name}' with {len(archives_response.archives)} archives"
                )
            except Exception:
                logger.info(
                    f"Successfully imported repository '{request.name}' (could not count archives)"
                )

            return RepositoryOperationResult(
                success=True,
                repository_id=db_repo.id,
                repository_name=db_repo.name,
                message=f"Repository '{request.name}' imported successfully",
            )

        except Exception as e:
            db.rollback()
            error_message = f"Failed to import repository: {str(e)}"
            logger.error(error_message)
            return RepositoryOperationResult(success=False, error_message=error_message)

    async def scan_repositories(
        self, request: RepositoryScanRequest
    ) -> RepositoryScanResult:
        """Scan for existing repositories."""
        try:
            scan_response = await self.borg_service.scan_for_repositories()

            scanned_repos = []
            for borg_repo in scan_response.repositories:
                scanned_repo = ScannedRepository(
                    name="",  # Borg doesn't provide name, will be set by user
                    path=borg_repo.path,
                    encryption_mode=borg_repo.encryption_mode,
                    requires_keyfile=borg_repo.requires_keyfile,
                    preview=borg_repo.config_preview,
                    is_existing=False,  # These are newly discovered repos
                )
                scanned_repos.append(scanned_repo)

            return RepositoryScanResult(
                success=True,
                repositories=scanned_repos,
            )

        except Exception as e:
            logger.error(f"Error scanning for repositories: {e}")
            return RepositoryScanResult(
                success=False,
                repositories=[],
                error_message=f"Failed to scan repositories: {str(e)}",
            )

    async def list_archives(
        self, repository_id: int, db: Session
    ) -> ArchiveListingResult:
        """List archives in a repository."""
        try:
            repository = (
                db.query(Repository).filter(Repository.id == repository_id).first()
            )
            if not repository:
                return ArchiveListingResult(
                    success=False,
                    repository_id=repository_id,
                    repository_name="Unknown",
                    archives=[],
                    recent_archives=[],
                    error_message="Repository not found",
                )

            archives_response = await self.borg_service.list_archives(repository)

            archive_infos = []
            for archive in archives_response.archives:
                archive_info = ArchiveInfo(
                    name=archive.name,
                    time=archive.start,  # Use start time as primary timestamp
                    stats={"original_size": archive.original_size}
                    if archive.original_size
                    else None,
                )

                if archive_info.time:
                    dt = parse_datetime_string(archive_info.time)
                    if dt:
                        archive_info.formatted_time = format_datetime_for_display(dt)
                    else:
                        archive_info.formatted_time = archive_info.time

                if archive_info.stats and "original_size" in archive_info.stats:
                    size_value = archive_info.stats["original_size"]
                    if isinstance(size_value, (int, float)) and size_value is not None:
                        size_bytes = float(size_value)
                        for unit in ["B", "KB", "MB", "GB", "TB"]:
                            if size_bytes < 1024.0:
                                archive_info.size_info = f"{size_bytes:.1f} {unit}"
                                break
                            size_bytes /= 1024.0

                archive_infos.append(archive_info)

            recent_archives = []
            if archive_infos:
                recent_list = (
                    archive_infos[-10:] if len(archive_infos) > 10 else archive_infos
                )
                recent_archives = list(reversed(recent_list))

            return ArchiveListingResult(
                success=True,
                repository_id=repository.id,
                repository_name=repository.name,
                archives=archive_infos,
                recent_archives=recent_archives,
            )

        except Exception as e:
            logger.error(f"Error listing archives for repository {repository_id}: {e}")
            return ArchiveListingResult(
                success=False,
                repository_id=repository_id,
                repository_name="Unknown",
                archives=[],
                recent_archives=[],
                error_message=f"Error loading archives: {str(e)}",
            )

    async def get_directories(
        self, request: DirectoryListingRequest
    ) -> DirectoryListingResult:
        """List directories at the given path."""
        try:
            if not user_secure_exists(request.path):
                return DirectoryListingResult(
                    success=True, path=request.path, directories=[]
                )

            if not user_secure_isdir(request.path):
                return DirectoryListingResult(
                    success=True, path=request.path, directories=[]
                )

            directory_data = user_get_directory_listing(
                request.path, include_files=request.include_files
            )

            if request.max_items > 0:
                directory_data = directory_data[: request.max_items]

            # Extract just the names for the result
            directories = [item["name"] for item in directory_data]

            return DirectoryListingResult(
                success=True, path=request.path, directories=directories
            )

        except PathSecurityError as e:
            logger.warning(f"Path security violation: {e}")
            return DirectoryListingResult(
                success=True, path=request.path, directories=[]
            )
        except Exception as e:
            logger.error(f"Error listing directories at {request.path}: {e}")
            return DirectoryListingResult(
                success=False,
                path=request.path,
                directories=[],
                error_message=f"Failed to list directories: {str(e)}",
            )

    async def get_archive_contents(
        self, request: ArchiveContentsRequest, db: Session
    ) -> ArchiveContentsResult:
        """Get contents of an archive at specified path."""
        try:
            repository = (
                db.query(Repository)
                .filter(Repository.id == request.repository_id)
                .first()
            )
            if not repository:
                return ArchiveContentsResult(
                    success=False,
                    repository_id=request.repository_id,
                    archive_name=request.archive_name,
                    path=request.path,
                    items=[],
                    breadcrumb_parts=[],
                    error_message="Repository not found",
                )

            contents = await self.borg_service.list_archive_directory_contents(
                repository, request.archive_name, request.path
            )

            items = []
            for item in contents:
                directory_item = DirectoryItem(
                    name=item.name,
                    type=item.type,
                    path=item.path,
                    size=item.size,
                    modified=item.mtime,
                )
                items.append(directory_item)

            breadcrumb_parts = request.path.split("/") if request.path else []

            return ArchiveContentsResult(
                success=True,
                repository_id=request.repository_id,
                archive_name=request.archive_name,
                path=request.path,
                items=items,
                breadcrumb_parts=breadcrumb_parts,
            )

        except Exception as e:
            logger.error(
                f"Error getting archive contents for {request.repository_id}/{request.archive_name}: {e}"
            )
            return ArchiveContentsResult(
                success=False,
                repository_id=request.repository_id,
                archive_name=request.archive_name,
                path=request.path,
                items=[],
                breadcrumb_parts=[],
                error_message=f"Error loading directory contents: {str(e)}",
            )

    async def delete_repository(
        self, request: DeleteRepositoryRequest, db: Session
    ) -> DeleteRepositoryResult:
        """Delete a repository and its associated data."""
        try:
            repository = (
                db.query(Repository)
                .filter(Repository.id == request.repository_id)
                .first()
            )
            if not repository:
                return DeleteRepositoryResult(
                    success=False,
                    repository_name="Unknown",
                    error_message="Repository not found",
                )

            repo_name = repository.name

            active_jobs = (
                db.query(Job)
                .filter(
                    Job.repository_id == request.repository_id,
                    Job.status.in_(["running", "pending", "queued"]),
                )
                .all()
            )

            if active_jobs:
                active_job_types = [job.type for job in active_jobs]
                return DeleteRepositoryResult(
                    success=False,
                    repository_name=repo_name,
                    conflict_jobs=active_job_types,
                    error_message=f"Cannot delete repository '{repo_name}' - {len(active_jobs)} active job(s) running: {', '.join(active_job_types)}. Please wait for jobs to complete or cancel them first.",
                )

            schedules_to_delete = (
                db.query(Schedule)
                .filter(Schedule.repository_id == request.repository_id)
                .all()
            )

            deleted_schedules = 0
            for schedule in schedules_to_delete:
                try:
                    await self.scheduler_service.remove_schedule(schedule.id)
                    deleted_schedules += 1
                    logger.info(f"Removed scheduled job for schedule ID {schedule.id}")
                except Exception as e:
                    logger.warning(
                        f"Could not remove scheduled job for schedule ID {schedule.id}: {e}"
                    )

            db.delete(repository)
            db.commit()

            logger.info(f"Successfully deleted repository '{repo_name}'")

            return DeleteRepositoryResult(
                success=True,
                repository_name=repo_name,
                deleted_schedules=deleted_schedules,
                message=f"Repository '{repo_name}' deleted successfully",
            )

        except Exception as e:
            db.rollback()
            error_message = f"Failed to delete repository: {str(e)}"
            logger.error(error_message)
            return DeleteRepositoryResult(
                success=False,
                repository_name="Unknown",
                error_message=error_message,
            )

    async def _validate_repository_creation(
        self, request: CreateRepositoryRequest, db: Session
    ) -> List[RepositoryValidationError]:
        """Validate repository creation request."""
        errors = []

        existing_name = (
            db.query(Repository).filter(Repository.name == request.name).first()
        )
        if existing_name:
            errors.append(
                RepositoryValidationError(
                    field="name", message="Repository with this name already exists"
                )
            )

        existing_path = (
            db.query(Repository).filter(Repository.path == request.path).first()
        )
        if existing_path:
            errors.append(
                RepositoryValidationError(
                    field="path",
                    message=f"Repository with path '{request.path}' already exists with name '{existing_path.name}'",
                )
            )

        return errors

    async def _validate_repository_import(
        self, request: ImportRepositoryRequest, db: Session
    ) -> List[RepositoryValidationError]:
        """Validate repository import request."""
        errors = []

        existing_name = (
            db.query(Repository).filter(Repository.name == request.name).first()
        )
        if existing_name:
            errors.append(
                RepositoryValidationError(
                    field="name", message="Repository with this name already exists"
                )
            )

        existing_path = (
            db.query(Repository).filter(Repository.path == request.path).first()
        )
        if existing_path:
            errors.append(
                RepositoryValidationError(
                    field="path",
                    message=f"Repository with path '{request.path}' already exists with name '{existing_path.name}'",
                )
            )

        return errors

    def _parse_borg_initialization_error(self, borg_error: str) -> str:
        """Parse Borg initialization error into user-friendly message."""
        if "Read-only file system" in borg_error:
            return "Cannot create repository: The target directory is read-only. Please choose a writable location."
        elif "Permission denied" in borg_error:
            return "Cannot create repository: Permission denied. Please check directory permissions."
        elif "already exists" in borg_error.lower():
            return "A repository already exists at this location."
        else:
            return f"Failed to initialize repository: {borg_error}"

    async def _save_keyfile(
        self, repository_name: str, keyfile: KeyfileProtocol
    ) -> KeyfileSaveResult:
        """Save uploaded keyfile securely."""
        try:
            keyfiles_dir = "/app/data/keyfiles"
            os.makedirs(keyfiles_dir, exist_ok=True)

            safe_filename = create_secure_filename(
                repository_name, keyfile.filename or "keyfile", add_uuid=True
            )
            keyfile_path = secure_path_join(keyfiles_dir, safe_filename)

            with open(keyfile_path, "wb") as f:
                content = await keyfile.read()
                f.write(content)

            logger.info(
                f"Saved keyfile for repository '{repository_name}' at {keyfile_path}"
            )

            return {"success": True, "path": keyfile_path}

        except (PathSecurityError, OSError) as e:
            error_message = f"Failed to save keyfile: {str(e)}"
            logger.error(error_message)
            return {"success": False, "error": error_message}

    async def check_repository_lock_status(
        self, repository: Repository
    ) -> Dict[str, Any]:
        """Check if a repository is currently locked by attempting a quick borg list operation."""
        try:
            async with secure_borg_command(
                base_command="borg list",
                repository_path=repository.path,
                passphrase=repository.get_passphrase(),
                keyfile_content=repository.get_keyfile_content(),
                additional_args=["--short"],
            ) as (command, env, _):
                process = await asyncio.create_subprocess_exec(
                    *command,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    env=env,
                )

                try:
                    stdout, stderr = await asyncio.wait_for(
                        process.communicate(), timeout=10
                    )

                    if process.returncode == 0:
                        return {
                            "locked": False,
                            "accessible": True,
                            "message": "Repository is accessible",
                        }
                    else:
                        stderr_text = stderr.decode() if stderr else ""
                        if (
                            "Failed to create/acquire the lock" in stderr_text
                            or "LockTimeout" in stderr_text
                        ):
                            return {
                                "locked": True,
                                "accessible": False,
                                "message": "Repository is locked by another process",
                                "error": stderr_text,
                            }
                        else:
                            return {
                                "locked": False,
                                "accessible": False,
                                "message": f"Repository access failed: {stderr_text}",
                                "error": stderr_text,
                            }

                except asyncio.TimeoutError:
                    process.kill()
                    await process.wait()
                    return {
                        "locked": True,
                        "accessible": False,
                        "message": "Repository check timed out (possibly locked)",
                    }

        except Exception as e:
            logger.error(f"Error checking repository lock status: {e}")
            return {
                "locked": False,
                "accessible": False,
                "message": f"Error checking repository: {str(e)}",
                "error": str(e),
            }

    async def break_repository_lock(self, repository: Repository) -> Dict[str, Any]:
        """Break a repository lock using borg break-lock command."""
        try:
            logger.info(f"Attempting to break lock on repository: {repository.name}")

            async with secure_borg_command(
                base_command="borg break-lock",
                repository_path=repository.path,
                passphrase=repository.get_passphrase(),
                keyfile_content=repository.get_keyfile_content(),
                additional_args=[],
            ) as (command, env, _):
                process = await asyncio.create_subprocess_exec(
                    *command,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    env=env,
                )

                try:
                    stdout, stderr = await asyncio.wait_for(
                        process.communicate(), timeout=30
                    )

                    if process.returncode == 0:
                        logger.info(
                            f"Successfully broke lock on repository: {repository.name}"
                        )
                        return {
                            "success": True,
                            "message": "Repository lock successfully removed",
                        }
                    else:
                        stderr_text = stderr.decode() if stderr else "No error details"
                        logger.warning(
                            f"Break-lock returned {process.returncode} for {repository.name}: {stderr_text}"
                        )
                        return {
                            "success": False,
                            "message": f"Failed to break lock: {stderr_text}",
                            "error": stderr_text,
                        }

                except asyncio.TimeoutError:
                    logger.warning(
                        f"Break-lock timed out for repository: {repository.name}"
                    )
                    process.kill()
                    await process.wait()
                    return {
                        "success": False,
                        "message": "Break-lock operation timed out",
                    }

        except Exception as e:
            logger.error(f"Error breaking lock for repository {repository.name}: {e}")
            return {
                "success": False,
                "message": f"Error breaking lock: {str(e)}",
                "error": str(e),
            }

    async def get_repository_info(self, repository: Repository) -> Dict[str, Any]:
        """Get detailed repository information using borg info and borg config commands."""
        try:
            # Get repository info
            info_result = await self._get_borg_info(repository)
            if not info_result["success"]:
                return info_result

            # Get repository config
            config_result = await self._get_borg_config(repository)

            # Combine results
            result = info_result.copy()
            result["config"] = config_result.get("config", {})
            result["config_error"] = (
                config_result.get("error_message")
                if not config_result.get("success")
                else None
            )

            return result

        except Exception as e:
            logger.error(f"Error getting repository info for {repository.name}: {e}")
            return {
                "success": False,
                "error": True,
                "error_message": f"Error getting repository info: {str(e)}",
            }

    async def _get_borg_info(self, repository: Repository) -> Dict[str, Any]:
        """Get repository information using borg info command."""
        try:
            async with secure_borg_command(
                base_command="borg info",
                repository_path=repository.path,
                passphrase=repository.get_passphrase(),
                keyfile_content=repository.get_keyfile_content(),
                additional_args=["--json"],
            ) as (command, env, _):
                process = await asyncio.create_subprocess_exec(
                    *command,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    env=env,
                )

                try:
                    stdout, stderr = await asyncio.wait_for(
                        process.communicate(), timeout=30
                    )

                    if process.returncode == 0:
                        import json

                        info_data = json.loads(stdout.decode())

                        # Extract relevant information
                        result = {
                            "success": True,
                            "repository_id": info_data.get("repository", {}).get("id"),
                            "location": info_data.get("repository", {}).get("location"),
                            "encryption": info_data.get("encryption"),
                            "cache": info_data.get("cache"),
                            "security_dir": info_data.get("security_dir"),
                        }

                        # Add archive statistics if available
                        archives = info_data.get("archives", [])
                        if archives:
                            result["archives_count"] = len(archives)

                            # Calculate totals
                            total_original = sum(
                                archive.get("stats", {}).get("original_size", 0)
                                for archive in archives
                            )
                            total_compressed = sum(
                                archive.get("stats", {}).get("compressed_size", 0)
                                for archive in archives
                            )
                            total_deduplicated = sum(
                                archive.get("stats", {}).get("deduplicated_size", 0)
                                for archive in archives
                            )

                            # Format sizes
                            result["original_size"] = self._format_bytes(total_original)
                            result["compressed_size"] = self._format_bytes(
                                total_compressed
                            )
                            result["deduplicated_size"] = self._format_bytes(
                                total_deduplicated
                            )

                            # Get last modified from most recent archive
                            if archives:
                                latest_archive = max(
                                    archives, key=lambda a: a.get("start", "")
                                )
                                result["last_modified"] = latest_archive.get(
                                    "start", "Unknown"
                                )

                        return result
                    else:
                        stderr_text = stderr.decode() if stderr else "Unknown error"
                        return {
                            "success": False,
                            "error": True,
                            "error_message": f"Failed to get repository info: {stderr_text}",
                        }

                except asyncio.TimeoutError:
                    process.kill()
                    await process.wait()
                    return {
                        "success": False,
                        "error": True,
                        "error_message": "Repository info command timed out",
                    }

        except Exception as e:
            logger.error(f"Error getting borg info for {repository.name}: {e}")
            return {
                "success": False,
                "error": True,
                "error_message": f"Error getting borg info: {str(e)}",
            }

    async def _get_borg_config(self, repository: Repository) -> Dict[str, Any]:
        """Get repository configuration using borg config --list command."""
        try:
            async with secure_borg_command(
                base_command="borg config",
                repository_path=repository.path,
                passphrase=repository.get_passphrase(),
                keyfile_content=repository.get_keyfile_content(),
                additional_args=["--list"],
            ) as (command, env, _):
                process = await asyncio.create_subprocess_exec(
                    *command,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    env=env,
                )

                try:
                    stdout, stderr = await asyncio.wait_for(
                        process.communicate(), timeout=30
                    )

                    if process.returncode == 0:
                        config_output = stdout.decode().strip()
                        config_dict = {}

                        # Parse the config output (format: key = value)
                        for line in config_output.split("\n"):
                            line = line.strip()
                            if line and "=" in line:
                                key, value = line.split("=", 1)
                                config_dict[key.strip()] = value.strip()

                        return {"success": True, "config": config_dict}
                    else:
                        stderr_text = stderr.decode() if stderr else "Unknown error"
                        return {
                            "success": False,
                            "error_message": f"Failed to get repository config: {stderr_text}",
                        }

                except asyncio.TimeoutError:
                    process.kill()
                    await process.wait()
                    return {
                        "success": False,
                        "error_message": "Repository config command timed out",
                    }

        except Exception as e:
            logger.error(f"Error getting borg config for {repository.name}: {e}")
            return {
                "success": False,
                "error_message": f"Error getting borg config: {str(e)}",
            }

    async def export_repository_key(self, repository: Repository) -> Dict[str, Any]:
        """Export repository key using borg key export command."""
        try:
            async with secure_borg_command(
                base_command="borg key export",
                repository_path=repository.path,
                passphrase=repository.get_passphrase(),
                keyfile_content=repository.get_keyfile_content(),
                additional_args=[],
            ) as (command, env, _):
                process = await asyncio.create_subprocess_exec(
                    *command,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    env=env,
                )

                try:
                    stdout, stderr = await asyncio.wait_for(
                        process.communicate(), timeout=30
                    )

                    if process.returncode == 0:
                        key_data = stdout.decode().strip()
                        return {
                            "success": True,
                            "key_data": key_data,
                            "filename": f"{repository.name}_key.txt",
                        }
                    else:
                        stderr_text = stderr.decode() if stderr else "Unknown error"
                        return {
                            "success": False,
                            "error_message": f"Failed to export repository key: {stderr_text}",
                        }

                except asyncio.TimeoutError:
                    process.kill()
                    await process.wait()
                    return {
                        "success": False,
                        "error_message": "Key export command timed out",
                    }

        except Exception as e:
            logger.error(f"Error exporting key for repository {repository.name}: {e}")
            return {
                "success": False,
                "error_message": f"Error exporting repository key: {str(e)}",
            }

    def _format_bytes(self, bytes_value: int) -> str:
        """Format bytes into human readable format."""
        if bytes_value == 0:
            return "0 B"

        # Convert to float for division
        value = float(bytes_value)
        for unit in ["B", "KB", "MB", "GB", "TB"]:
            if value < 1024.0:
                return f"{value:.1f} {unit}"
            value /= 1024.0
        return f"{value:.1f} PB"
