"""
Tests for VolumeService - Service to discover directories under /mnt
"""

import pytest
from unittest.mock import patch
from typing import List
from borgitory.services.volumes.volume_service import VolumeService, FileSystemInterface


class MockFileSystem(FileSystemInterface):
    """Mock filesystem for testing"""

    def __init__(self) -> None:
        self.directories = set()
        self.files = set()

    def add_directory(self, path: str) -> None:
        """Add a directory to the mock filesystem"""
        self.directories.add(path)

    def add_file(self, path: str) -> None:
        """Add a file to the mock filesystem"""
        self.files.add(path)

    def exists(self, path: str) -> bool:
        return path in self.directories or path in self.files

    def is_dir(self, path: str) -> bool:
        return path in self.directories

    def listdir(self, path: str) -> List[str]:
        if path not in self.directories:
            raise OSError(f"No such directory: {path}")

        # Find all items that are direct children of this path
        items = []
        for item_path in self.directories | self.files:
            if (
                item_path.startswith(path + "/")
                and "/" not in item_path[len(path) + 1 :]
            ):
                items.append(item_path.split("/")[-1])
        return items

    def join(self, *paths: str) -> str:
        return "/".join(paths)


@pytest.fixture
def mock_filesystem():
    return MockFileSystem()


@pytest.fixture
def volume_service(mock_filesystem):
    return VolumeService(filesystem=mock_filesystem)


class TestVolumeService:
    """Test the VolumeService class"""

    @pytest.mark.asyncio
    async def test_get_mounted_volumes_success(
        self, volume_service, mock_filesystem
    ) -> None:
        """Test successful discovery of volumes under /mnt"""
        # Set up mock filesystem
        mock_filesystem.add_directory("/mnt")
        mock_filesystem.add_directory("/mnt/data")
        mock_filesystem.add_directory("/mnt/repos")
        mock_filesystem.add_directory("/mnt/backups")

        volumes = await volume_service.get_mounted_volumes()

        assert "/mnt/backups" in volumes
        assert "/mnt/data" in volumes
        assert "/mnt/repos" in volumes
        assert len(volumes) == 3

    @pytest.mark.asyncio
    async def test_get_mounted_volumes_no_mnt_directory(
        self, volume_service, mock_filesystem
    ) -> None:
        """Test behavior when /mnt directory doesn't exist"""
        # Don't add /mnt to mock filesystem (it doesn't exist)
        volumes = await volume_service.get_mounted_volumes()
        assert volumes == []

    @pytest.mark.asyncio
    async def test_get_mounted_volumes_empty_mnt_directory(
        self, volume_service, mock_filesystem
    ) -> None:
        """Test behavior when /mnt directory is empty"""
        # Add /mnt directory but no subdirectories
        mock_filesystem.add_directory("/mnt")

        volumes = await volume_service.get_mounted_volumes()
        assert volumes == []

    @pytest.mark.asyncio
    async def test_get_mounted_volumes_filters_files(
        self, volume_service, mock_filesystem
    ) -> None:
        """Test that only directories are included, not files"""
        # Set up mock filesystem with directories and files
        mock_filesystem.add_directory("/mnt")
        mock_filesystem.add_directory("/mnt/data")
        mock_filesystem.add_directory("/mnt/backups")
        mock_filesystem.add_file("/mnt/repos.txt")  # This is a file, not directory

        volumes = await volume_service.get_mounted_volumes()

        assert "/mnt/data" in volumes
        assert "/mnt/backups" in volumes
        assert "/mnt/repos.txt" not in volumes  # File should be excluded
        assert len(volumes) == 2

    @pytest.mark.asyncio
    async def test_get_mounted_volumes_exception_handling(
        self, mock_filesystem
    ) -> None:
        """Test handling of exceptions during directory listing"""

        # Create a filesystem that throws exceptions
        class ExceptionFileSystem(MockFileSystem):
            def exists(self, path: str) -> bool:
                raise OSError("Permission denied")

        exception_filesystem = ExceptionFileSystem()
        volume_service = VolumeService(filesystem=exception_filesystem)

        volumes = await volume_service.get_mounted_volumes()
        assert volumes == []

    @pytest.mark.asyncio
    async def test_get_volume_info_success(self, volume_service) -> None:
        """Test successful volume info retrieval"""
        with patch.object(
            volume_service,
            "get_mounted_volumes",
            return_value=["/mnt/data", "/mnt/repos"],
        ):
            info = await volume_service.get_volume_info()

            assert info["mounted_volumes"] == ["/mnt/data", "/mnt/repos"]
            assert info["total_mounted_volumes"] == 2
            assert info["accessible"] is True

    @pytest.mark.asyncio
    async def test_get_volume_info_exception(self, volume_service) -> None:
        """Test volume info retrieval with exception"""
        with patch.object(
            volume_service, "get_mounted_volumes", side_effect=Exception("Test error")
        ):
            info = await volume_service.get_volume_info()

            assert "error" in info
            assert info["error"] == "Test error"
            assert info["mounted_volumes"] == []
            assert info["total_mounted_volumes"] == 0
            assert info["accessible"] is False

    @pytest.mark.asyncio
    async def test_volumes_sorted_consistently(
        self, volume_service, mock_filesystem
    ) -> None:
        """Test that volumes are returned in sorted order"""
        # Set up mock filesystem with unsorted directories
        mock_filesystem.add_directory("/mnt")
        mock_filesystem.add_directory("/mnt/zzz-volume")
        mock_filesystem.add_directory("/mnt/aaa-volume")
        mock_filesystem.add_directory("/mnt/mmm-volume")

        volumes = await volume_service.get_mounted_volumes()

        # Should be sorted alphabetically
        assert volumes == ["/mnt/aaa-volume", "/mnt/mmm-volume", "/mnt/zzz-volume"]
