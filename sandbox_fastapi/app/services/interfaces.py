"""
Clean service interfaces following 2024 best practices.

These interfaces define clear contracts with single responsibilities,
making testing and dependency injection much cleaner.
"""

from typing import Protocol, Optional, List, Dict, Any
from abc import ABC, abstractmethod
from sqlalchemy.orm import Session

from app.models.repository import Repository
from app.models.schemas import RepositoryImport, RepositoryResponse, ImportResult


class SecurityValidator(Protocol):
    """Interface for security validation operations."""
    
    def validate_repository_name(self, name: str) -> str:
        """Validate and sanitize repository name."""
        ...
    
    def validate_passphrase(self, passphrase: str) -> str:
        """Validate passphrase for security."""
        ...
    
    def validate_path(self, path: str) -> str:
        """Validate and sanitize file path."""
        ...
    
    def build_secure_borg_env(
        self, 
        passphrase: str,
        keyfile_path: Optional[str] = None,
        additional_env: Optional[Dict[str, str]] = None
    ) -> Dict[str, str]:
        """Build secure environment variables for Borg commands."""
        ...


class CommandExecutor(Protocol):
    """Interface for command execution - simple and testable."""
    
    async def run_command(
        self, 
        command: List[str], 
        env: Optional[dict] = None, 
        timeout: int = 30
    ) -> 'CommandResult':
        """Execute a command and return result."""
        ...


class FileSystemService(Protocol):
    """Interface for file system operations."""
    
    def exists(self, path: str) -> bool:
        """Check if path exists."""
        ...
    
    def is_dir(self, path: str) -> bool:
        """Check if path is a directory."""
        ...
        
    def list_directories(self, path: str, include_files: bool = False) -> List[Dict[str, Any]]:
        """List directory contents."""
        ...
    
    def get_basename(self, path: str) -> str:
        """Get the basename of a path."""
        ...
    
    def delete_file(self, path: str) -> bool:
        """Delete a file. Returns True if successful."""
        ...


class BorgVerificationService(Protocol):
    """Interface for Borg repository verification operations."""
    
    async def verify_repository_access(
        self,
        repo_path: str,
        passphrase: str,
        keyfile_content: Optional[bytes] = None
    ) -> bool:
        """Verify access to a Borg repository."""
        ...


class RepositoryDataService(Protocol):
    """Interface for repository data operations (Repository pattern)."""
    
    def find_by_name(self, db: Session, name: str) -> Optional[Repository]:
        """Find repository by name."""
        ...
    
    def find_by_path(self, db: Session, path: str) -> Optional[Repository]:
        """Find repository by path."""
        ...
    
    def save(self, db: Session, repository: Repository) -> Repository:
        """Save repository to database."""
        ...
    
    def delete(self, db: Session, repository: Repository) -> bool:
        """Delete repository from database."""
        ...


class RepositoryImportService(Protocol):
    """Interface for repository import business logic."""
    
    async def import_repository(
        self,
        import_data: RepositoryImport,
        db: Session
    ) -> ImportResult:
        """Import a repository with full business logic."""
        ...


class JobExecutionService(Protocol):
    """Interface for job execution operations."""
    
    async def execute_backup_task(
        self,
        job_id: int,
        repository: 'Repository',
        source_path: str,
        compression: str = "zstd",
        dry_run: bool = False
    ) -> None:
        """Execute backup task in background following FastAPI BackgroundTasks pattern."""
        ...


class NotificationService(Protocol):
    """Interface for notification operations."""
    
    async def send_backup_notification(
        self,
        notification_config: 'NotificationConfig',
        repository_name: str,
        backup_success: bool,
        job_details: str = ""
    ) -> bool:
        """Send backup completion notification."""
        ...
    
    async def test_notification_config(
        self,
        notification_config: 'NotificationConfig'
    ) -> bool:
        """Test notification configuration."""
        ...


class TaskExecutionService(Protocol):
    """Interface for individual task execution."""
    
    async def execute_backup_task(
        self,
        job_id: int,
        repository: 'Repository',
        source_path: str,
        compression: 'CompressionType',
        dry_run: bool = False
    ) -> bool:
        """Execute backup task."""
        ...
    
    async def execute_notification_task(
        self,
        job_id: int,
        task_id: int,
        notification_config: 'NotificationConfig',
        backup_result: bool
    ) -> bool:
        """Execute notification task."""
        ...


class JobWorkflowService(Protocol):
    """Interface for multi-task job orchestration."""
    
    async def create_workflow_job(
        self,
        repository_id: int,
        tasks: List['TaskDefinition'],
        db: Session
    ) -> int:
        """Create multi-task workflow job."""
        ...
    
    async def execute_workflow(
        self,
        job_id: int
    ) -> None:
        """Execute all tasks in workflow sequentially."""
        ...


class JobManagementService(Protocol):
    """Interface for job management operations."""
    
    async def create_backup_job(
        self,
        backup_request: 'BackupRequest',
        db: Session
    ) -> 'BackupResult':
        """Create backup job following FastAPI BackgroundTasks best practices."""
        ...
    
    def get_job_status(self, job_id: int, db: Session) -> Optional['JobResponse']:
        """Get job status and details."""
        ...
    
    def list_jobs(
        self,
        db: Session,
        skip: int = 0,
        limit: int = 100,
        status_filter: Optional[str] = None
    ) -> List['JobResponse']:
        """List jobs with filtering and pagination."""
        ...


# Result classes
class CommandResult:
    """Result of command execution."""
    def __init__(self, return_code: int, stdout: bytes, stderr: bytes):
        self.return_code = return_code
        self.stdout = stdout
        self.stderr = stderr
        
    @property
    def success(self) -> bool:
        return self.return_code == 0


# Exception classes
class RepositoryError(Exception):
    """Base exception for repository operations."""
    pass


class RepositoryValidationError(RepositoryError):
    """Raised when repository validation fails."""
    pass


class RepositoryVerificationError(RepositoryError):
    """Raised when repository verification fails."""
    pass