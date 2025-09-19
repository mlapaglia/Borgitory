"""
Protocol interfaces for storage and volume services.
"""

from typing import Protocol, List, Dict, Any


class VolumeInfo:
    """Information about a mounted volume."""

    def __init__(self, path: str, mount_point: str, filesystem: str):
        self.path = path
        self.mount_point = mount_point
        self.filesystem = filesystem


class VolumeServiceProtocol(Protocol):
    """Protocol for volume management services."""

    async def get_mounted_volumes(self) -> List[str]:
        """Get list of mounted volume paths."""
        ...

    async def get_volume_info(self) -> Dict[str, Any]:
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

    def get_connection_info(self) -> Dict[str, Any]:
        """Get connection information for display."""
        ...
