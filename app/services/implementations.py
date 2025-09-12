"""
Concrete implementations of service interfaces.

These classes implement the business logic defined in interfaces,
providing actual functionality while maintaining clean separation.
"""

import logging
from typing import Optional, Dict, Any, List
from sqlalchemy.orm import Session

from app.models.database import Repository, User
from app.services.interfaces import (
    SecurityValidator, 
    BorgServiceInterface, 
    RepositoryService,
    RepositoryQueryService,
    RepositoryError,
    RepositoryNotFoundError,
    RepositoryValidationError
)
from app.utils.security import (
    validate_repository_name as _validate_repo_name,
    sanitize_passphrase,
)
from app.utils.secure_path import sanitize_filename as _sanitize_filename

logger = logging.getLogger(__name__)


class DefaultRepositoryQueryService:
    """Default implementation of repository query operations."""
    
    def list_repositories(
        self, 
        db: Session, 
        skip: int = 0, 
        limit: int = 100
    ) -> List[Repository]:
        """List repositories with pagination."""
        return db.query(Repository).offset(skip).limit(limit).all()


class DefaultSecurityValidator:
    """Default implementation of security validation."""
    
    def validate_repository_name(self, name: str) -> str:
        """Validate repository name using existing security function."""
        return _validate_repo_name(name)
    
    def sanitize_filename(self, filename: str, max_length: int = 100) -> str:
        """Sanitize filename using existing security function."""
        return _sanitize_filename(filename, max_length)
    
    def validate_passphrase(self, passphrase: str) -> str:
        """Validate passphrase using existing security function."""
        return sanitize_passphrase(passphrase)


class DefaultBorgService:
    """Wrapper for existing BorgService to match interface."""
    
    def __init__(self, borg_service=None):
        # Import here to avoid circular imports
        if borg_service is None:
            from app.dependencies import get_borg_service
            borg_service = get_borg_service()
        self._borg_service = borg_service
    
    async def initialize_repository(self, repository: Repository) -> Dict[str, Any]:
        """Initialize repository using existing BorgService."""
        return await self._borg_service.initialize_repository(repository)
    
    async def verify_repository_access(
        self, 
        repo_path: str, 
        passphrase: str, 
        keyfile_path: Optional[str] = None
    ) -> bool:
        """Verify repository access using existing BorgService."""
        return await self._borg_service.verify_repository_access(
            repo_path, passphrase, keyfile_path
        )
    
    async def list_archives(self, repository: Repository) -> List[Dict]:
        """List archives using existing BorgService."""
        return await self._borg_service.list_archives(repository)


class DefaultRepositoryService:
    """Default implementation of repository business logic."""
    
    def __init__(
        self, 
        security_validator: SecurityValidator,
        borg_service: BorgServiceInterface
    ):
        self.security_validator = security_validator
        self.borg_service = borg_service
    
    async def create_repository(
        self,
        name: str,
        path: str, 
        passphrase: str,
        user: User,
        db: Session,
        is_import: bool = False,
        keyfile_content: Optional[bytes] = None,
        keyfile_filename: Optional[str] = None
    ) -> Repository:
        """Create a new repository with validation and business logic."""
        
        # Validate inputs
        try:
            validated_name = self.security_validator.validate_repository_name(name)
            validated_passphrase = self.security_validator.validate_passphrase(passphrase)
        except ValueError as e:
            raise RepositoryValidationError(f"Validation failed: {str(e)}")
        
        # Check for existing repositories
        existing_name = db.query(Repository).filter(Repository.name == validated_name).first()
        if existing_name:
            raise RepositoryValidationError("Repository with this name already exists")
        
        existing_path = db.query(Repository).filter(Repository.path == path).first()
        if existing_path:
            raise RepositoryValidationError(
                f"Repository with path '{path}' already exists with name '{existing_path.name}'"
            )
        
        # Handle keyfile upload for imports
        keyfile_path = None
        if is_import and keyfile_content and keyfile_filename:
            from app.utils.secure_path import create_secure_filename, secure_path_join
            import os
            
            keyfiles_dir = "/app/app/data/keyfiles"
            os.makedirs(keyfiles_dir, exist_ok=True)
            
            try:
                safe_filename = create_secure_filename(
                    validated_name, keyfile_filename, add_uuid=True
                )
                keyfile_path = secure_path_join(keyfiles_dir, safe_filename)
                
                with open(keyfile_path, "wb") as f:
                    f.write(keyfile_content)
                
                logger.info(f"Saved keyfile for repository '{validated_name}' at {keyfile_path}")
            except Exception as e:
                raise RepositoryError(f"Failed to save keyfile: {str(e)}")

        # Create repository object
        repository = Repository(name=validated_name, path=path)
        repository.set_passphrase(validated_passphrase)
        
        try:
            if is_import:
                # For imports, verify access to existing repository
                success = await self.borg_service.verify_repository_access(
                    path, validated_passphrase, keyfile_path
                )
                if not success:
                    raise RepositoryValidationError(
                        "Failed to verify repository access. Please check the path, passphrase, and keyfile (if required)."
                    )
            else:
                # For new repos, initialize with Borg
                result = await self.borg_service.initialize_repository(repository)
                if not result["success"]:
                    error_msg = result["message"]
                    if "Read-only file system" in error_msg:
                        raise RepositoryError("Cannot create repository: Target directory is read-only")
                    elif "Permission denied" in error_msg:
                        raise RepositoryError("Cannot create repository: Permission denied")
                    elif "already exists" in error_msg.lower():
                        raise RepositoryError("A repository already exists at this location")
                    else:
                        raise RepositoryError(f"Failed to initialize repository: {error_msg}")
            
            # Save to database
            db.add(repository)
            db.commit()
            db.refresh(repository)
            
            logger.info(f"Successfully {'imported' if is_import else 'created'} repository '{validated_name}'")
            return repository
            
        except Exception:
            # Clean up on failure
            if keyfile_path:
                from app.utils.secure_path import secure_remove_file
                secure_remove_file(keyfile_path)
            if repository.id:  # If it was saved to DB
                db.delete(repository)
                db.commit()
            raise
    
    async def update_repository(
        self,
        repo_id: int,
        updates: Dict[str, Any],
        user: User,
        db: Session
    ) -> Repository:
        """Update repository with validation."""
        
        # Get existing repository
        repository = db.query(Repository).filter(Repository.id == repo_id).first()
        if not repository:
            raise RepositoryNotFoundError("Repository not found")
        
        # Validate name if being updated
        if "name" in updates:
            try:
                validated_name = self.security_validator.validate_repository_name(updates["name"])
                updates["name"] = validated_name
            except ValueError as e:
                raise RepositoryValidationError(f"Invalid repository name: {str(e)}")
        
        # Validate passphrase if being updated
        if "passphrase" in updates:
            try:
                validated_passphrase = self.security_validator.validate_passphrase(updates["passphrase"])
                repository.set_passphrase(validated_passphrase)
                updates.pop("passphrase")  # Remove from updates since we handled it
            except ValueError as e:
                raise RepositoryValidationError(f"Invalid passphrase: {str(e)}")
        
        # Apply updates
        for field, value in updates.items():
            if hasattr(repository, field):
                setattr(repository, field, value)
        
        db.commit()
        db.refresh(repository)
        
        logger.info(f"Updated repository {repo_id}")
        return repository
    
    def get_repository(self, repo_id: int, db: Session) -> Optional[Repository]:
        """Get repository by ID."""
        return db.query(Repository).filter(Repository.id == repo_id).first()
    
    async def delete_repository(
        self, 
        repo_id: int, 
        user: User, 
        db: Session,
        scheduler_service=None,
        delete_borg_repo: bool = False
    ) -> bool:
        """Delete repository with proper cleanup."""
        repository = db.query(Repository).filter(Repository.id == repo_id).first()
        if not repository:
            raise RepositoryNotFoundError("Repository not found")
        
        # Check for active jobs
        from app.models.database import Job
        active_jobs = (
            db.query(Job)
            .filter(
                Job.repository_id == repo_id,
                Job.status.in_(["running", "pending", "queued"]),
            )
            .all()
        )
        
        if active_jobs:
            active_job_types = [job.type for job in active_jobs]
            raise RepositoryValidationError(
                f"Cannot delete repository '{repository.name}' - {len(active_jobs)} active job(s) running: {', '.join(active_job_types)}. Please wait for jobs to complete or cancel them first."
            )
        
        # Clean up schedules if scheduler service provided
        if scheduler_service:
            from app.models.database import Schedule
            schedules_to_delete = (
                db.query(Schedule).filter(Schedule.repository_id == repo_id).all()
            )
            
            for schedule in schedules_to_delete:
                try:
                    await scheduler_service.remove_schedule(schedule.id)
                    logger.info(f"Removed scheduled job for schedule ID {schedule.id}")
                except Exception as e:
                    logger.warning(
                        f"Could not remove scheduled job for schedule ID {schedule.id}: {e}"
                    )
        
        # Delete the repository
        db.delete(repository)
        db.commit()
        
        logger.info(f"Deleted repository {repo_id}: {repository.name}")
        return True


# Factory functions for easy dependency injection
def get_default_security_validator() -> SecurityValidator:
    """Get default security validator implementation."""
    return DefaultSecurityValidator()


def get_default_borg_service() -> BorgServiceInterface:
    """Get default Borg service implementation."""
    return DefaultBorgService()


def get_default_repository_service() -> RepositoryService:
    """Get default repository service with default dependencies."""
    security_validator = get_default_security_validator()
    borg_service = get_default_borg_service()
    return DefaultRepositoryService(security_validator, borg_service)