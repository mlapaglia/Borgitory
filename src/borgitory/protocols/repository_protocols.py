"""
Protocol interfaces for repository and backup services.
"""

from typing import Protocol, Dict, List, Optional, AsyncGenerator, TYPE_CHECKING
from datetime import datetime

from borgitory.models.borg_info import (
    BorgArchiveListResponse,
    RepositoryScanResponse,
    RepositoryInitializationResult,
)

if TYPE_CHECKING:
    from borgitory.models.database import Repository
    from borgitory.services.archives.archive_manager import ArchiveEntry


class RepositoryInfo:
    """Information about a repository."""

    def __init__(self, path: str, name: str, encrypted: bool = False):
        self.path = path
        self.name = name
        self.encrypted = encrypted


class ArchiveInfo:
    """Information about an archive."""

    def __init__(self, name: str, created: datetime, size: int = 0):
        self.name = name
        self.created = created
        self.size = size


class BackupServiceProtocol(Protocol):
    """Protocol for backup operations (BorgService)."""

    async def initialize_repository(
        self,
        repository: "Repository",  # Repository model
    ) -> RepositoryInitializationResult:
        """Initialize a new repository."""
        ...

    async def create_backup(
        self,
        repository: "Repository",  # Repository model
        source_path: str,
        compression: str = "zstd",
        dry_run: bool = False,
        cloud_sync_config_id: Optional[int] = None,
    ) -> str:
        """Create a backup and return job_id."""
        ...

    async def list_archives(
        self,
        repository: "Repository",  # Repository model
    ) -> "BorgArchiveListResponse":
        """List all archives in a repository."""
        ...

    async def verify_repository_access(
        self, repo_path: str, passphrase: str, keyfile_path: str = ""
    ) -> bool:
        """Verify repository can be accessed."""
        ...

    async def scan_for_repositories(
        self,
    ) -> "RepositoryScanResponse":
        """Scan for Borg repositories."""
        ...


class ArchiveServiceProtocol(Protocol):
    """Protocol for archive content operations (ArchiveManager)."""

    async def list_archive_directory_contents(
        self,
        repository: "Repository",  # Repository model
        archive_name: str,
        path: str = "",
    ) -> List["ArchiveEntry"]:
        """List contents of a directory within an archive."""
        ...

    def extract_file_stream(
        self,
        repository: "Repository",  # Repository model
        archive_name: str,
        file_path: str,
    ) -> AsyncGenerator[bytes, None]:
        """Stream file content from an archive."""
        ...


class RepositoryServiceProtocol(Protocol):
    """Protocol for repository management operations."""

    async def create_repository(
        self,
        name: str,
        path: str,
        passphrase: Optional[str] = None,
    ) -> Dict[str, object]:
        """Create a new repository."""
        ...

    async def delete_repository(
        self,
        repository_id: int,
    ) -> Dict[str, object]:
        """Delete a repository."""
        ...

    async def scan_repositories(self) -> List[Dict[str, object]]:
        """Scan for repositories on mounted volumes."""
        ...

    def get_repository_stats(
        self,
        repository_id: int,
    ) -> Dict[str, object]:
        """Get repository statistics."""
        ...

    def get_all_repositories(self) -> List[object]:
        """Get all repositories from database."""
        ...

    def get_repository_by_id(self, repository_id: int) -> Optional[object]:
        """Get repository by ID."""
        ...

    async def update_repository(
        self,
        repository_id: int,
        updates: Dict[str, object],
    ) -> Optional[object]:
        """Update repository."""
        ...
