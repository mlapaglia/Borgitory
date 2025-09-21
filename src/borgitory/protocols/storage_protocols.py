"""
Protocol interfaces for storage and volume services.
"""

from typing import Protocol, List, Dict, TYPE_CHECKING

if TYPE_CHECKING:
    from borgitory.services.volumes.volume_service import VolumeInfo


class VolumeServiceProtocol(Protocol):
    """Protocol for volume management services."""

    async def get_mounted_volumes(self) -> List[str]:
        """Get list of mounted volume paths."""
        ...

    async def get_volume_info(self) -> "VolumeInfo":
        """Get detailed volume information."""
        ...


class CloudStorageProtocol(Protocol):
    """Protocol for cloud storage operations."""

    async def upload_file(self, local_path: str, remote_path: str) -> bool:
        """Upload a file to cloud storage."""
        ...

    async def download_file(self, remote_path: str, local_path: str) -> bool:
        """Download a file from cloud storage."""
        ...

    async def test_connection(self) -> bool:
        """Test connection to cloud storage."""
        ...

    def get_connection_info(self) -> Dict[str, object]:
        """Get connection information for display."""
        ...
