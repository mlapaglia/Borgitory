"""
Borg service protocol interface.

Defines the contract for Borg backup operations.
"""

from typing import Protocol, Optional, TYPE_CHECKING
from starlette.responses import StreamingResponse

from borgitory.models.repository_dtos import RepositoryOperationResult

if TYPE_CHECKING:
    from borgitory.models.database import Repository
    from borgitory.models.borg_info import (
        BorgArchiveListResponse,
        RepositoryScanResponse,
    )


class BorgService(Protocol):
    """Protocol for Borg backup services"""

    async def initialize_repository(
        self, repository: "Repository"
    ) -> RepositoryOperationResult:
        """
        Initialize a new Borg repository.

        Args:
            repository: Repository object

        Returns:
            Result dictionary with success status and message
        """
        ...

    async def create_backup(
        self,
        repository: "Repository",
        source_path: str,
        compression: str = "zstd",
        dry_run: bool = False,
        cloud_sync_config_id: Optional[int] = None,
    ) -> str:
        """
        Create a backup and return job_id for tracking.
        Args:
            repository: Repository object
            source_path: Path to backup
            compression: Compression algorithm
            dry_run: Whether to perform dry run
            cloud_sync_config_id: Optional cloud sync config
        Returns:
            Job ID for tracking backup progress
        """
        ...

    async def list_archives(
        self, repository: "Repository"
    ) -> "BorgArchiveListResponse":
        """
        List all archives in a repository.

        Args:
            repository: Repository object

        Returns:
            Structured archive list response with strongly typed archive data
        """
        ...

    async def extract_file_stream(
        self, repository: "Repository", archive_name: str, file_path: str
    ) -> StreamingResponse:
        """
        Extract a single file from an archive and stream it.
        Args:
            repository: Repository object
            archive_name: Name of the archive
            file_path: Path to the file within the archive
        Returns:
            StreamingResponse with file content
        """
        ...

    async def verify_repository_access(
        self, repo_path: str, passphrase: str, keyfile_path: str = ""
    ) -> bool:
        """
        Verify we can access a repository with given credentials.
        Args:
            repo_path: Path to repository
            passphrase: Repository passphrase
            keyfile_path: Path to keyfile if needed
        Returns:
            True if access successful, False otherwise
        """
        ...

    async def scan_for_repositories(
        self,
    ) -> "RepositoryScanResponse":
        """
        Scan for Borg repositories.

        Returns:
            Structured response containing discovered repositories with metadata
        """
        ...
