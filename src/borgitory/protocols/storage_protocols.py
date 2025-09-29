"""
Protocol interfaces for storage and volume services.
"""

from typing import Protocol, Dict


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
