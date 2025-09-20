"""
Borg service protocol interface.

Defines the contract for Borg backup operations.
"""

from typing import Protocol, Dict, List, Optional, Union
from starlette.responses import StreamingResponse


class BorgService(Protocol):
    """Protocol for Borg backup services"""

    async def initialize_repository(
        self, repository: object
    ) -> Dict[str, Union[str, int, float, bool, None]]:
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
        repository: object,
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
        self, repository: object
    ) -> List[Dict[str, Union[str, int, float, bool, None]]]:
        """
        List all archives in a repository.

        Args:
            repository: Repository object

        Returns:
            List of archive information dictionaries
        """
        ...

    async def get_repo_info(
        self, repository: object
    ) -> Dict[str, Union[str, int, float, bool, None]]:
        """
        Get repository information.

        Args:
            repository: Repository object

        Returns:
            Repository information dictionary
        """
        ...

    async def list_archive_contents(
        self, repository: object, archive_name: str
    ) -> List[Dict[str, Union[str, int, float, bool, None]]]:
        """
        List contents of a specific archive.

        Args:
            repository: Repository object
            archive_name: Name of the archive

        Returns:
            List of archive contents
        """
        ...

    async def extract_file_stream(
        self, repository: object, archive_name: str, file_path: str
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
    ) -> List[Dict[str, Union[str, int, float, bool, None]]]:
        """
        Scan for Borg repositories.

        Returns:
            List of discovered repositories
        """
        ...
