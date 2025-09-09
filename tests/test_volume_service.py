"""
Tests for VolumeService - Service to discover and manage mounted volumes
"""

import asyncio
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from app.services.volume_service import VolumeService


@pytest.fixture
def volume_service():
    return VolumeService()


class TestVolumeService:
    """Test the VolumeService class"""

    @pytest.mark.asyncio
    async def test_get_mounted_volumes_success(self, volume_service):
        """Test successful retrieval of mounted volumes"""
        mock_process = MagicMock()
        mock_process.returncode = 0
        mock_process.communicate = AsyncMock(
            return_value=(
                b"/data/backup\n/backup/volumes\n/storage/files\n",
                b""
            )
        )

        with patch('asyncio.create_subprocess_shell', return_value=mock_process), \
             patch('os.path.exists') as mock_exists, \
             patch('os.path.isdir') as mock_isdir:
            
            # Mock os.path behavior - use paths that won't be filtered out by system paths
            def exists_side_effect(path):
                return path in ["/repos", "/data/backup", "/backup/volumes", "/storage/files"]
            
            def isdir_side_effect(path):
                return path in ["/repos", "/data/backup", "/backup/volumes", "/storage/files"]
            
            mock_exists.side_effect = exists_side_effect
            mock_isdir.side_effect = isdir_side_effect

            volumes = await volume_service.get_mounted_volumes()

            assert "/repos" in volumes
            assert "/data/backup" in volumes
            assert "/backup/volumes" in volumes
            assert "/storage/files" in volumes
            assert len(volumes) >= 4

    @pytest.mark.asyncio
    async def test_get_mounted_volumes_command_failure(self, volume_service):
        """Test handling of command execution failure"""
        mock_process = MagicMock()
        mock_process.returncode = 1
        mock_process.communicate = AsyncMock(
            return_value=(b"", b"command failed")
        )

        with patch('asyncio.create_subprocess_shell', return_value=mock_process), \
             patch('os.path.exists', return_value=True), \
             patch('os.path.isdir', return_value=True):

            volumes = await volume_service.get_mounted_volumes()

            assert "/repos" in volumes
            assert len(volumes) == 1

    @pytest.mark.asyncio
    async def test_get_mounted_volumes_no_repos_fallback(self, volume_service):
        """Test fallback when /repos doesn't exist"""
        mock_process = MagicMock()
        mock_process.returncode = 1
        mock_process.communicate = AsyncMock(
            return_value=(b"", b"command failed")
        )

        with patch('asyncio.create_subprocess_shell', return_value=mock_process), \
             patch('os.path.exists', return_value=False):

            volumes = await volume_service.get_mounted_volumes()

            assert volumes == []

    @pytest.mark.asyncio
    async def test_get_mounted_volumes_filters_system_paths(self, volume_service):
        """Test that system paths are properly filtered out"""
        mock_process = MagicMock()
        mock_process.returncode = 0
        mock_process.communicate = AsyncMock(
            return_value=(
                b"/\n/home\n/var\n/tmp\n/mnt/backup\n/custom/data\n",
                b""
            )
        )

        with patch('asyncio.create_subprocess_shell', return_value=mock_process), \
             patch('os.path.exists') as mock_exists, \
             patch('os.path.isdir') as mock_isdir:
            
            def exists_side_effect(path):
                return path in ["/repos", "/", "/home", "/var", "/tmp", "/mnt/backup", "/custom/data"]
            
            def isdir_side_effect(path):
                return path in ["/repos", "/", "/home", "/var", "/tmp", "/mnt/backup", "/custom/data"]
            
            mock_exists.side_effect = exists_side_effect
            mock_isdir.side_effect = isdir_side_effect

            volumes = await volume_service.get_mounted_volumes()

            # System paths should be filtered out
            assert "/" not in volumes
            assert "/home" not in volumes
            assert "/var" not in volumes
            assert "/tmp" not in volumes
            # /mnt is a system path, so /mnt/backup gets filtered out
            assert "/mnt/backup" not in volumes
            
            # Valid volumes should be included
            assert "/repos" in volumes
            assert "/custom/data" in volumes

    @pytest.mark.asyncio
    async def test_get_mounted_volumes_filters_nonexistent_paths(self, volume_service):
        """Test that non-existent paths are filtered out"""
        mock_process = MagicMock()
        mock_process.returncode = 0
        mock_process.communicate = AsyncMock(
            return_value=(
                b"/backup/exists\n/backup/nonexistent\n/custom/data\n",
                b""
            )
        )

        with patch('asyncio.create_subprocess_shell', return_value=mock_process), \
             patch('os.path.exists') as mock_exists, \
             patch('os.path.isdir') as mock_isdir:
            
            def exists_side_effect(path):
                # Only some paths exist, note that /mnt paths get filtered out anyway
                return path in ["/repos", "/backup/exists", "/custom/data"]
            
            def isdir_side_effect(path):
                # Only some paths are directories
                return path in ["/repos", "/backup/exists", "/custom/data"]
            
            mock_exists.side_effect = exists_side_effect
            mock_isdir.side_effect = isdir_side_effect

            volumes = await volume_service.get_mounted_volumes()

            assert "/repos" in volumes
            assert "/backup/exists" in volumes
            assert "/custom/data" in volumes
            assert "/backup/nonexistent" not in volumes

    @pytest.mark.asyncio
    async def test_get_mounted_volumes_removes_duplicates(self, volume_service):
        """Test that duplicate volumes are removed while preserving order"""
        mock_process = MagicMock()
        mock_process.returncode = 0
        mock_process.communicate = AsyncMock(
            return_value=(
                b"/backup/data\n/custom/data\n/backup/data\n",
                b""
            )
        )

        with patch('asyncio.create_subprocess_shell', return_value=mock_process), \
             patch('os.path.exists') as mock_exists, \
             patch('os.path.isdir') as mock_isdir:
            
            def exists_side_effect(path):
                return path in ["/repos", "/backup/data", "/custom/data"]
            
            def isdir_side_effect(path):
                return path in ["/repos", "/backup/data", "/custom/data"]
            
            mock_exists.side_effect = exists_side_effect
            mock_isdir.side_effect = isdir_side_effect

            volumes = await volume_service.get_mounted_volumes()

            # Should contain each volume only once
            assert volumes.count("/backup/data") == 1
            assert volumes.count("/custom/data") == 1
            assert "/repos" in volumes

    @pytest.mark.asyncio
    async def test_get_mounted_volumes_exception_handling(self, volume_service):
        """Test exception handling in get_mounted_volumes"""
        with patch('asyncio.create_subprocess_shell', side_effect=Exception("Command failed")), \
             patch('os.path.exists', return_value=True):

            volumes = await volume_service.get_mounted_volumes()

            # Should fallback to /repos when command fails
            assert "/repos" in volumes

    @pytest.mark.asyncio
    async def test_get_mounted_volumes_empty_output(self, volume_service):
        """Test handling of empty command output"""
        mock_process = MagicMock()
        mock_process.returncode = 0
        mock_process.communicate = AsyncMock(
            return_value=(b"", b"")
        )

        with patch('asyncio.create_subprocess_shell', return_value=mock_process), \
             patch('os.path.exists', return_value=True), \
             patch('os.path.isdir', return_value=True):

            volumes = await volume_service.get_mounted_volumes()

            # Should still include /repos even with empty command output
            assert "/repos" in volumes

    @pytest.mark.asyncio
    async def test_get_volume_info_success(self, volume_service):
        """Test successful get_volume_info"""
        with patch.object(volume_service, 'get_mounted_volumes', return_value=["/repos", "/mnt/backup"]):
            info = await volume_service.get_volume_info()

            assert info["mounted_volumes"] == ["/repos", "/mnt/backup"]
            assert info["total_mounted_volumes"] == 2
            assert info["accessible"] is True
            assert "error" not in info

    @pytest.mark.asyncio
    async def test_get_volume_info_exception_handling(self, volume_service):
        """Test exception handling in get_volume_info"""
        with patch.object(volume_service, 'get_mounted_volumes', side_effect=Exception("Test error")):
            info = await volume_service.get_volume_info()

            assert info["error"] == "Test error"
            assert info["mounted_volumes"] == []
            assert info["total_mounted_volumes"] == 0
            assert info["accessible"] is False

    @pytest.mark.asyncio
    async def test_get_mounted_volumes_filters_system_subdirs(self, volume_service):
        """Test that subdirectories of system paths are filtered out"""
        mock_process = MagicMock()
        mock_process.returncode = 0
        mock_process.communicate = AsyncMock(
            return_value=(
                b"/home/user\n/var/log\n/usr/local\n/backup/data\n",
                b""
            )
        )

        with patch('asyncio.create_subprocess_shell', return_value=mock_process), \
             patch('os.path.exists') as mock_exists, \
             patch('os.path.isdir') as mock_isdir:
            
            def exists_side_effect(path):
                return path in ["/repos", "/home/user", "/var/log", "/usr/local", "/backup/data"]
            
            def isdir_side_effect(path):
                return path in ["/repos", "/home/user", "/var/log", "/usr/local", "/backup/data"]
            
            mock_exists.side_effect = exists_side_effect
            mock_isdir.side_effect = isdir_side_effect

            volumes = await volume_service.get_mounted_volumes()

            # System subdirectories should be filtered out
            assert "/home/user" not in volumes
            assert "/var/log" not in volumes  
            assert "/usr/local" not in volumes
            
            # Valid volumes should be included
            assert "/repos" in volumes
            assert "/backup/data" in volumes