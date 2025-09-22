"""
Repository Business Logic Service.
Handles all repository-related business operations independent of HTTP concerns.
"""

import logging
import os
from typing import List, Dict, Any
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
    RepositoryInfoRequest,
    RepositoryInfoResult,
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

logger = logging.getLogger(__name__)


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
            if not init_result["success"]:
                borg_error = init_result["message"]
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
            keyfile_path = None
            if request.keyfile and request.keyfile.filename:
                keyfile_result = await self._save_keyfile(request.name, request.keyfile)
                if not keyfile_result["success"]:
                    return RepositoryOperationResult(
                        success=False, error_message=keyfile_result["error"]
                    )
                keyfile_path = keyfile_result["path"]

            db_repo = Repository()
            db_repo.name = request.name
            db_repo.path = request.path
            db_repo.set_passphrase(request.passphrase)

            db.add(db_repo)
            db.commit()
            db.refresh(db_repo)

            verification_successful = await self.borg_service.verify_repository_access(
                repo_path=request.path,
                passphrase=request.passphrase,
                keyfile_path=str(keyfile_path) if keyfile_path else "",
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
                archives = await self.borg_service.list_archives(db_repo)
                logger.info(
                    f"Successfully imported repository '{request.name}' with {len(archives)} archives"
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
            available_repos = await self.borg_service.scan_for_repositories()

            scanned_repos = []
            for repo in available_repos:
                scanned_repo = ScannedRepository(
                    name=repo.get("name", ""),
                    path=repo.get("path", ""),
                    encryption_mode=repo.get("encryption_mode", "unknown"),
                    requires_keyfile=repo.get("requires_keyfile", False),
                    preview=repo.get("preview", "Repository detected"),
                    is_existing=repo.get("is_existing", False),
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

            archives = await self.borg_service.list_archives(repository)

            archive_infos = []
            for archive in archives:
                archive_info = ArchiveInfo(
                    name=archive.get("name", "Unknown"),
                    time=archive.get("time", ""),
                    stats=archive.get("stats"),
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
                    name=item.get("name", ""),
                    type=item.get("type", "file"),
                    path=item.get("path", ""),
                    size=item.get("size"),
                    modified=item.get("modified"),
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

    async def get_repository_info(
        self, request: RepositoryInfoRequest, db: Session
    ) -> RepositoryInfoResult:
        """Get repository information."""
        try:
            repository = (
                db.query(Repository)
                .filter(Repository.id == request.repository_id)
                .first()
            )
            if not repository:
                return RepositoryInfoResult(
                    success=False,
                    repository_id=request.repository_id,
                    error_message="Repository not found",
                )

            info = await self.borg_service.get_repo_info(repository)

            return RepositoryInfoResult(
                success=True, repository_id=request.repository_id, info=info
            )

        except Exception as e:
            logger.error(
                f"Error getting repository info for {request.repository_id}: {e}"
            )
            return RepositoryInfoResult(
                success=False,
                repository_id=request.repository_id,
                error_message=str(e),
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

    async def _save_keyfile(self, repository_name: str, keyfile: Any) -> Dict[str, Any]:
        """Save uploaded keyfile securely."""
        try:
            keyfiles_dir = "/app/data/keyfiles"
            os.makedirs(keyfiles_dir, exist_ok=True)

            safe_filename = create_secure_filename(
                repository_name, keyfile.filename, add_uuid=True
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
