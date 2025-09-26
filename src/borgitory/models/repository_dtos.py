"""
Data Transfer Objects for Repository operations.
Clean data structures for business logic layer.
"""

from typing import Optional, List
from dataclasses import dataclass
from fastapi import UploadFile
from borgitory.custom_types import ConfigDict


@dataclass
class CreateRepositoryRequest:
    """Request data for creating a new repository."""

    name: str
    path: str
    passphrase: str
    user_id: int


@dataclass
class ImportRepositoryRequest:
    """Request data for importing an existing repository."""

    name: str
    path: str
    passphrase: str
    keyfile: Optional[UploadFile] = None
    encryption_type: Optional[str] = None  # Manual encryption type override
    keyfile_content: Optional[str] = None  # Keyfile content as text
    user_id: Optional[int] = None


@dataclass
class RepositoryValidationError:
    """Validation error details."""

    field: str
    message: str


@dataclass
class RepositoryOperationResult:
    """Result of a repository operation."""

    success: bool
    repository_id: Optional[int] = None
    repository_name: Optional[str] = None
    message: Optional[str] = None
    error_message: Optional[str] = None
    validation_errors: Optional[List[RepositoryValidationError]] = None
    borg_error: Optional[str] = None

    @property
    def is_validation_error(self) -> bool:
        """Check if this is a validation error."""
        return self.validation_errors is not None and len(self.validation_errors) > 0

    @property
    def is_borg_error(self) -> bool:
        """Check if this is a Borg-specific error."""
        return self.borg_error is not None


@dataclass
class ArchiveInfo:
    """Information about a repository archive."""

    name: str
    time: str
    formatted_time: Optional[str] = None
    size_info: Optional[str] = None
    stats: Optional[ConfigDict] = None


@dataclass
class ArchiveListingResult:
    """Result of listing repository archives."""

    success: bool
    repository_id: int
    repository_name: str
    archives: List[ArchiveInfo]
    recent_archives: List[ArchiveInfo]
    error_message: Optional[str] = None

    @property
    def archive_count(self) -> int:
        """Get total number of archives."""
        return len(self.archives)


@dataclass
class DirectoryItem:
    """Item in a directory listing."""

    name: str
    type: str  # 'directory' or 'file'
    path: str
    size: Optional[int] = None
    modified: Optional[str] = None


@dataclass
class DirectoryListingRequest:
    """Request for directory listing."""

    path: str
    include_files: bool = False
    max_items: int = 1000


@dataclass
class DirectoryListingResult:
    """Result of directory listing operation."""

    success: bool
    path: str
    directories: List[str]
    error_message: Optional[str] = None


@dataclass
class ArchiveContentsRequest:
    """Request for archive contents."""

    repository_id: int
    archive_name: str
    path: str = ""


@dataclass
class ArchiveContentsResult:
    """Result of archive contents listing."""

    success: bool
    repository_id: int
    archive_name: str
    path: str
    items: List[DirectoryItem]
    breadcrumb_parts: List[str]
    error_message: Optional[str] = None


@dataclass
class RepositoryScanRequest:
    """Request for repository scanning."""

    include_existing: bool = True


@dataclass
class ScannedRepository:
    """Information about a scanned repository."""

    name: str
    path: str
    encryption_mode: str
    requires_keyfile: bool
    preview: str
    is_existing: bool = False


@dataclass
class RepositoryScanResult:
    """Result of repository scanning operation."""

    success: bool
    repositories: List[ScannedRepository]
    error_message: Optional[str] = None

    @property
    def repository_count(self) -> int:
        """Get total number of repositories found."""
        return len(self.repositories)


@dataclass
class RepositoryInfoRequest:
    """Request for repository information."""

    repository_id: int


@dataclass
class RepositoryInfoResult:
    """Result of repository info operation."""

    success: bool
    repository_id: int
    info: Optional[ConfigDict] = None
    error_message: Optional[str] = None


@dataclass
class DeleteRepositoryRequest:
    """Request for repository deletion."""

    repository_id: int
    delete_borg_repo: bool = False
    user_id: Optional[int] = None


@dataclass
class DeleteRepositoryResult:
    """Result of repository deletion."""

    success: bool
    repository_name: str
    deleted_schedules: int = 0
    message: Optional[str] = None
    error_message: Optional[str] = None
    conflict_jobs: Optional[List[str]] = None  # Job types that are blocking deletion

    @property
    def has_conflicts(self) -> bool:
        """Check if deletion was blocked by active jobs."""
        return self.conflict_jobs is not None and len(self.conflict_jobs) > 0
