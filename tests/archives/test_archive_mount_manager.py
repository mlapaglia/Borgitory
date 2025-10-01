"""
Tests for ArchiveMountManager - Behavioral tests focused on service functionality
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch
from pathlib import Path
from datetime import timedelta

from borgitory.services.archives.archive_mount_manager import (
    ArchiveMountManager,
    MountInfo,
)
from borgitory.protocols.command_executor_protocol import CommandExecutorProtocol
from borgitory.models.database import Repository


@pytest.fixture
def mock_command_executor() -> Mock:
    """Create mock command executor."""
    mock = Mock(spec=CommandExecutorProtocol)
    mock.create_subprocess = AsyncMock()
    mock.execute_command = AsyncMock()
    mock.get_platform_name = Mock(return_value="linux")

    # Configure default successful command execution
    mock_result = Mock()
    mock_result.success = True
    mock_result.return_code = 0
    mock_result.stdout = ""
    mock_result.stderr = ""
    mock.execute_command.return_value = mock_result

    return mock


@pytest.fixture
def mock_job_executor() -> Mock:
    """Create mock job executor."""
    return Mock()


@pytest.fixture
def mock_path_config() -> Mock:
    """Create mock path configuration service."""
    mock = Mock()
    mock.is_windows.return_value = False
    mock.get_base_temp_dir.return_value = "/tmp"
    return mock


@pytest.fixture
def archive_mount_manager(
    mock_job_executor: Mock, mock_command_executor: Mock, mock_path_config: Mock
) -> ArchiveMountManager:
    """Create ArchiveMountManager with mock dependencies."""
    # Configure mock path config for the fixture
    mock_path_config.is_windows.return_value = False
    mock_path_config.get_base_temp_dir.return_value = "/tmp"

    return ArchiveMountManager(
        job_executor=mock_job_executor,
        command_executor=mock_command_executor,
        path_config=mock_path_config,
        mount_timeout=timedelta(seconds=30),
        mounting_timeout=timedelta(seconds=10),
    )


@pytest.fixture
def mock_repository() -> Mock:
    """Create mock repository."""
    repo = Mock(spec=Repository)
    repo.name = "test-repo"
    repo.path = "/test/repo/path"
    repo.get_passphrase.return_value = "test-passphrase"
    repo.get_keyfile_content.return_value = None
    return repo


class TestArchiveMountManagerBasics:
    """Test basic ArchiveMountManager functionality."""

    def test_initialization(
        self,
        mock_job_executor: Mock,
        mock_command_executor: Mock,
        mock_path_config: Mock,
    ) -> None:
        """Test ArchiveMountManager initializes correctly."""
        # Configure mock path config to return the expected base directory
        mock_path_config.is_windows.return_value = False
        mock_path_config.get_base_temp_dir.return_value = "/tmp"

        manager = ArchiveMountManager(
            job_executor=mock_job_executor,
            command_executor=mock_command_executor,
            path_config=mock_path_config,
        )
        assert manager.command_executor is mock_command_executor
        assert manager.job_executor is mock_job_executor
        assert str(manager.base_mount_dir).replace("\\", "/") == "/tmp/borgitory-mounts"

    def test_get_mount_key(
        self, archive_mount_manager: ArchiveMountManager, mock_repository: Mock
    ) -> None:
        """Test mount key generation."""
        key = archive_mount_manager._get_mount_key(mock_repository, "test-archive")
        assert key == "/test/repo/path::test-archive"

    def test_get_mount_point(
        self, archive_mount_manager: ArchiveMountManager, mock_repository: Mock
    ) -> None:
        """Test mount point generation."""
        mount_point = archive_mount_manager._get_mount_point(
            mock_repository, "test-archive"
        )
        # The actual implementation uses underscore separator and sanitizes names
        expected = Path("/tmp/borgitory-mounts/test-repo_test-archive")
        # Convert both to strings and normalize path separators for comparison
        assert str(mount_point).replace("\\", "/") == str(expected).replace("\\", "/")


class TestArchiveMountManagerMounting:
    """Test archive mounting functionality."""

    @pytest.mark.asyncio
    async def test_mount_archive_calls_executor(
        self,
        archive_mount_manager: ArchiveMountManager,
        mock_command_executor: Mock,
        mock_repository: Mock,
    ) -> None:
        """Test that mount_archive calls the command executor with correct parameters."""
        # Mock subprocess for mounting
        mock_process = Mock()
        mock_process.pid = 12345
        mock_process.returncode = None  # Process is still running
        mock_command_executor.create_subprocess.return_value = mock_process

        # Mock the mount ready check to return True immediately
        with patch.object(
            archive_mount_manager, "_verify_mount_ready", return_value=True
        ):
            with patch(
                "borgitory.services.archives.archive_mount_manager.secure_borg_command"
            ) as mock_secure:
                mock_secure.return_value.__aenter__.return_value = (
                    [
                        "borg",
                        "mount",
                        "/test/repo/path::test-archive",
                        "/tmp/borgitory-mounts/test-repo_test-archive",
                        "-f",
                    ],
                    {"BORG_PASSPHRASE": "test-passphrase"},
                    None,
                )

                result = await archive_mount_manager.mount_archive(
                    mock_repository, "test-archive"
                )

                # Verify the command executor was called
                mock_command_executor.create_subprocess.assert_called_once()
                call_args = mock_command_executor.create_subprocess.call_args

                # Verify the command contains expected elements
                expected_command = [
                    "borg",
                    "mount",
                    "/test/repo/path::test-archive",
                    "/tmp/borgitory-mounts/test-repo_test-archive",
                    "-f",
                ]
                assert call_args[1]["command"] == expected_command
                assert "BORG_PASSPHRASE" in call_args[1]["env"]

                # Verify we got a mount point back
                expected_mount_point = Path(
                    "/tmp/borgitory-mounts/test-repo_test-archive"
                )
                assert str(result).replace("\\", "/") == str(
                    expected_mount_point
                ).replace("\\", "/")

    @pytest.mark.asyncio
    async def test_mount_archive_already_mounted(
        self,
        archive_mount_manager: ArchiveMountManager,
        mock_repository: Mock,
    ) -> None:
        """Test mounting an already mounted archive."""
        # Add a mount to the active mounts
        mount_key = archive_mount_manager._get_mount_key(
            mock_repository, "test-archive"
        )
        mount_point = archive_mount_manager._get_mount_point(
            mock_repository, "test-archive"
        )

        from borgitory.utils.datetime_utils import now_utc

        archive_mount_manager.active_mounts[mount_key] = MountInfo(
            repository_path=mock_repository.path,
            archive_name="test-archive",
            mount_point=mount_point,
            mounted_at=now_utc(),
            last_accessed=now_utc(),
        )

        result = await archive_mount_manager.mount_archive(
            mock_repository, "test-archive"
        )
        assert result == mount_point

    @pytest.mark.asyncio
    async def test_mount_archive_failure(
        self,
        archive_mount_manager: ArchiveMountManager,
        mock_command_executor: Mock,
        mock_repository: Mock,
    ) -> None:
        """Test mount failure handling."""
        # Mock subprocess that fails
        mock_process = Mock()
        mock_process.pid = 12345
        mock_process.returncode = 1  # Failed process
        mock_process.stderr = Mock()
        mock_process.stderr.read = AsyncMock(
            return_value=b"Mount failed: permission denied"
        )
        mock_process.stdout = Mock()
        mock_process.stdout.read = AsyncMock(return_value=b"")
        mock_command_executor.create_subprocess.return_value = mock_process

        # Mock the mount ready check to return False
        with patch.object(
            archive_mount_manager, "_verify_mount_ready", return_value=False
        ):
            with patch(
                "borgitory.services.archives.archive_mount_manager.secure_borg_command"
            ) as mock_secure:
                mock_secure.return_value.__aenter__.return_value = (
                    [
                        "borg",
                        "mount",
                        "/test/repo/path::test-archive",
                        "/tmp/borgitory-mounts/test-repo_test-archive",
                        "-f",
                    ],
                    {"BORG_PASSPHRASE": "test-passphrase"},
                    None,
                )

                with pytest.raises(Exception, match="Mount failed"):
                    await archive_mount_manager.mount_archive(
                        mock_repository, "test-archive"
                    )


class TestArchiveMountManagerUtilities:
    """Test utility methods."""

    def test_get_mount_stats(self, archive_mount_manager: ArchiveMountManager) -> None:
        """Test getting mount statistics."""
        stats = archive_mount_manager.get_mount_stats()
        assert "active_mounts" in stats
        assert "mounts" in stats
        assert stats["active_mounts"] == 0
        assert len(stats["mounts"]) == 0

    @pytest.mark.asyncio
    async def test_unmount_all(
        self, archive_mount_manager: ArchiveMountManager
    ) -> None:
        """Test unmounting all archives."""
        # Add some mock mounts
        from borgitory.utils.datetime_utils import now_utc

        mock_process1 = Mock()
        mock_process1.terminate = Mock()
        mock_process1.wait = AsyncMock(return_value=0)
        mock_process1.returncode = None  # Process is still running

        mock_process2 = Mock()
        mock_process2.terminate = Mock()
        mock_process2.wait = AsyncMock(return_value=0)
        mock_process2.returncode = None  # Process is still running

        archive_mount_manager.active_mounts["repo1::archive1"] = MountInfo(
            repository_path="/repo1",
            archive_name="archive1",
            mount_point=Path("/tmp/mount1"),
            mounted_at=now_utc(),
            last_accessed=now_utc(),
            process=mock_process1,
        )

        archive_mount_manager.active_mounts["repo2::archive2"] = MountInfo(
            repository_path="/repo2",
            archive_name="archive2",
            mount_point=Path("/tmp/mount2"),
            mounted_at=now_utc(),
            last_accessed=now_utc(),
            process=mock_process2,
        )

        with patch(
            "borgitory.services.archives.archive_mount_manager.cleanup_temp_keyfile"
        ):
            await archive_mount_manager.unmount_all()

            assert len(archive_mount_manager.active_mounts) == 0
            mock_process1.terminate.assert_called_once()
            mock_process2.terminate.assert_called_once()


class TestArchiveMountManagerErrorHandling:
    """Test error handling scenarios."""

    @pytest.mark.asyncio
    async def test_mount_exception_handling(
        self,
        archive_mount_manager: ArchiveMountManager,
        mock_command_executor: Mock,
        mock_repository: Mock,
    ) -> None:
        """Test that mount operations handle exceptions gracefully."""
        # Mock command executor to raise an exception
        mock_command_executor.create_subprocess.side_effect = Exception("Process error")

        with patch(
            "borgitory.services.archives.archive_mount_manager.secure_borg_command"
        ) as mock_secure:
            mock_secure.return_value.__aenter__.return_value = (
                [
                    "borg",
                    "mount",
                    "/test/repo/path::test-archive",
                    "/tmp/borgitory-mounts/test-repo_test-archive",
                    "-f",
                ],
                {"BORG_PASSPHRASE": "test-passphrase"},
                None,
            )

            with pytest.raises(Exception, match="Process error"):
                await archive_mount_manager.mount_archive(
                    mock_repository, "test-archive"
                )
