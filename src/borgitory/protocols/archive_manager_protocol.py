"""
Archive Manager Protocol - Defines the interface for archive management operations
"""

from typing import List, Protocol, TYPE_CHECKING

if TYPE_CHECKING:
    from borgitory.models.database import Repository
    from borgitory.services.archives.archive_models import ArchiveEntry
    from starlette.responses import StreamingResponse


class ArchiveManagerProtocol(Protocol):
    """
    Protocol defining the interface for archive management operations.

    This allows for different implementations:
    - FUSE-based mounting (current implementation)
    - Direct borg list commands (new implementation)
    - Future implementations (e.g., cached, streaming, etc.)
    """

    async def list_archive_directory_contents(
        self, repository: "Repository", archive_name: str, path: str = ""
    ) -> List["ArchiveEntry"]:
        """
        List contents of a specific directory within an archive.

        Args:
            repository: The repository containing the archive
            archive_name: Name of the archive to browse
            path: Directory path within the archive (empty string for root)

        Returns:
            List of ArchiveEntry objects representing files and directories

        Raises:
            Exception: If the archive cannot be accessed or path doesn't exist
        """
        ...

    async def extract_file_stream(
        self, repository: "Repository", archive_name: str, file_path: str
    ) -> "StreamingResponse":
        """
        Extract a single file from an archive and stream it as a StreamingResponse.

        Args:
            repository: The repository containing the archive
            archive_name: Name of the archive containing the file
            file_path: Path to the file within the archive

        Returns:
            StreamingResponse: HTTP streaming response with the file content

        Raises:
            Exception: If the file cannot be extracted or doesn't exist
        """
        ...
