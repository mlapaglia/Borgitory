"""
Comprehensive tests for ArchiveMountManager - FUSE-based archive browsing system
"""

import asyncio
import pytest
from unittest.mock import Mock, AsyncMock, patch
from pathlib import Path
from datetime import datetime, timedelta
import tempfile
import os

from app.services.archive_mount_manager import ArchiveMountManager, MountInfo, get_archive_mount_manager
from app.models.database import Repository
from app.services.job_executor import JobExecutor


class TestArchiveMountManager:
    """Test ArchiveMountManager core functionality."""
    
    def setup_method(self):
        """Set up test fixtures."""
        # Create a temporary directory for testing
        self.test_mount_dir = tempfile.mkdtemp()
        
        # Mock job executor
        self.mock_job_executor = Mock(spec=JobExecutor)
        
        # Create ArchiveMountManager with dependency injection
        self.manager = ArchiveMountManager(
            base_mount_dir=self.test_mount_dir,
            job_executor=self.mock_job_executor,
            cleanup_interval=60,  # 1 minute for testing
            mount_timeout=300     # 5 minutes for testing
        )
        
        # Mock repository
        self.mock_repository = Mock(spec=Repository)
        self.mock_repository.id = 1
        self.mock_repository.name = "test-repo"
        self.mock_repository.path = "/path/to/repo"
        self.mock_repository.get_passphrase.return_value = "test_passphrase"
    
    def teardown_method(self):
        """Clean up test fixtures."""
        # Clean up temporary directory
        import shutil
        try:
            shutil.rmtree(self.test_mount_dir)
        except (OSError, PermissionError):
            pass

    def test_initialization_with_defaults(self):
        """Test ArchiveMountManager initialization with defaults."""
        manager = ArchiveMountManager()
        assert manager.base_mount_dir.exists()
        assert manager.cleanup_interval == 300
        assert manager.mount_timeout == 1800
        assert isinstance(manager.job_executor, JobExecutor)
        assert len(manager.active_mounts) == 0

    def test_initialization_with_custom_params(self):
        """Test ArchiveMountManager initialization with custom parameters."""
        custom_job_executor = Mock(spec=JobExecutor)
        
        # Use a temporary directory to avoid permission issues
        with tempfile.TemporaryDirectory() as temp_dir:
            custom_dir = os.path.join(temp_dir, "custom_mount_dir")
            manager = ArchiveMountManager(
                base_mount_dir=custom_dir,
                job_executor=custom_job_executor,
                cleanup_interval=120,
                mount_timeout=600
            )
            # Use Path comparison to handle cross-platform differences
            assert manager.base_mount_dir == Path(custom_dir)
            assert manager.cleanup_interval == 120
            assert manager.mount_timeout == 600
            assert manager.job_executor is custom_job_executor

    def test_initialization_cross_platform_paths(self):
        """Test that path handling works across platforms."""
        # Test that explicit path setting always works regardless of OS
        with tempfile.TemporaryDirectory() as temp_dir:
            custom_mount_path = os.path.join(temp_dir, "custom_mounts")
            manager = ArchiveMountManager(base_mount_dir=custom_mount_path)
            assert str(manager.base_mount_dir) == custom_mount_path
            assert manager.base_mount_dir.exists()
        
        # Test default behavior on current platform
        manager_default = ArchiveMountManager()
        assert manager_default.base_mount_dir.exists()
        
        # Test that the path construction logic handles different scenarios correctly
        # by testing the logic directly without platform mocking that causes Path issues
        original_temp = os.environ.get('TEMP')
        
        try:
            # Test Windows logic by setting environment
            os.environ['TEMP'] = '/tmp/test'
            temp_manager = ArchiveMountManager()
            # Should have created some path
            assert temp_manager.base_mount_dir is not None
            assert "borgitory_mounts" in str(temp_manager.base_mount_dir)
            
        finally:
            # Restore original environment
            if original_temp:
                os.environ['TEMP'] = original_temp
            elif 'TEMP' in os.environ:
                del os.environ['TEMP']

    def test_get_mount_key(self):
        """Test mount key generation."""
        key = self.manager._get_mount_key(self.mock_repository, "test-archive")
        expected = "/path/to/repo::test-archive"
        assert key == expected

    def test_get_mount_point(self):
        """Test mount point path generation."""
        mount_point = self.manager._get_mount_point(self.mock_repository, "test-archive")
        expected = self.manager.base_mount_dir / "test-repo_test-archive"
        assert mount_point == expected

    def test_get_mount_point_sanitization(self):
        """Test mount point path sanitization for special characters."""
        self.mock_repository.name = "test/repo with spaces"
        mount_point = self.manager._get_mount_point(self.mock_repository, "archive/with spaces")
        expected = self.manager.base_mount_dir / "test_repo_with_spaces_archive_with_spaces"
        assert mount_point == expected

    @pytest.mark.asyncio
    async def test_mount_archive_success(self):
        """Test successful archive mounting."""
        mock_process = Mock()
        mock_process.wait = AsyncMock(return_value=0)
        mock_process.stderr.read = AsyncMock(return_value=b"")
        
        with patch('asyncio.create_subprocess_exec', return_value=mock_process), \
             patch('app.utils.security.build_secure_borg_command', return_value=(["borg", "mount"], {})), \
             patch.object(self.manager, '_is_mounted', return_value=True), \
             patch('asyncio.sleep'):
            
            mount_point = await self.manager.mount_archive(self.mock_repository, "test-archive")
            
            expected_mount_point = self.manager.base_mount_dir / "test-repo_test-archive"
            assert mount_point == expected_mount_point
            
            # Check that mount info was stored
            mount_key = self.manager._get_mount_key(self.mock_repository, "test-archive")
            assert mount_key in self.manager.active_mounts
            
            mount_info = self.manager.active_mounts[mount_key]
            assert mount_info.repository_path == "/path/to/repo"
            assert mount_info.archive_name == "test-archive"
            assert mount_info.mount_point == expected_mount_point
            assert mount_info.job_executor_process is mock_process

    @pytest.mark.asyncio
    async def test_mount_archive_already_mounted(self):
        """Test mounting an already mounted archive."""
        # Pre-populate active mounts
        mount_key = self.manager._get_mount_key(self.mock_repository, "test-archive")
        mount_point = self.manager._get_mount_point(self.mock_repository, "test-archive")
        
        existing_mount_info = MountInfo(
            repository_path="/path/to/repo",
            archive_name="test-archive",
            mount_point=mount_point,
            mounted_at=datetime.now() - timedelta(minutes=10),
            last_accessed=datetime.now() - timedelta(minutes=5)
        )
        self.manager.active_mounts[mount_key] = existing_mount_info
        
        result = await self.manager.mount_archive(self.mock_repository, "test-archive")
        
        assert result == mount_point
        # Check that last_accessed was updated (allow for small time differences)
        updated_info = self.manager.active_mounts[mount_key]
        assert updated_info.last_accessed >= existing_mount_info.last_accessed

    @pytest.mark.asyncio
    async def test_mount_archive_failure(self):
        """Test archive mounting failure."""
        mock_process = Mock()
        mock_process.wait = AsyncMock(return_value=1)
        mock_process.stderr.read = AsyncMock(return_value=b"Archive not found")
        
        with patch('asyncio.create_subprocess_exec', return_value=mock_process), \
             patch('app.utils.security.build_secure_borg_command', return_value=(["borg", "mount"], {})), \
             patch.object(self.manager, '_is_mounted', return_value=False), \
             patch.object(self.manager, '_unmount_path'), \
             patch('asyncio.sleep'):
            
            with pytest.raises(Exception) as exc_info:
                await self.manager.mount_archive(self.mock_repository, "test-archive")
            
            assert "Mount failed: Archive not found" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_mount_archive_timeout(self):
        """Test archive mounting timeout."""
        mock_process = Mock()
        mock_process.wait = AsyncMock(side_effect=asyncio.TimeoutError())
        mock_process.terminate = Mock()
        
        with patch('asyncio.create_subprocess_exec', return_value=mock_process), \
             patch('app.utils.security.build_secure_borg_command', return_value=(["borg", "mount"], {})), \
             patch.object(self.manager, '_is_mounted', return_value=False), \
             patch.object(self.manager, '_unmount_path'), \
             patch('asyncio.sleep'):
            
            with pytest.raises(Exception) as exc_info:
                await self.manager.mount_archive(self.mock_repository, "test-archive")
            
            assert "Mount process timed out" in str(exc_info.value)
            mock_process.terminate.assert_called_once()

    def test_is_mounted_success(self):
        """Test successful mount check."""
        # Create a temporary directory with some files
        test_dir = Path(self.test_mount_dir) / "test_mount"
        test_dir.mkdir(exist_ok=True)
        (test_dir / "test_file.txt").touch()
        
        assert self.manager._is_mounted(test_dir) is True

    def test_is_mounted_failure(self):
        """Test mount check failure."""
        non_existent_dir = Path(self.test_mount_dir) / "non_existent"
        assert self.manager._is_mounted(non_existent_dir) is False

    @pytest.mark.asyncio
    async def test_unmount_archive_success(self):
        """Test successful archive unmounting."""
        # Setup mounted archive
        mount_key = self.manager._get_mount_key(self.mock_repository, "test-archive")
        mount_point = self.manager._get_mount_point(self.mock_repository, "test-archive")
        
        mock_process = Mock()
        mock_process.terminate = Mock()
        mock_process.wait = AsyncMock(return_value=0)
        mock_process.returncode = 0
        
        mount_info = MountInfo(
            repository_path="/path/to/repo",
            archive_name="test-archive",
            mount_point=mount_point,
            mounted_at=datetime.now(),
            last_accessed=datetime.now(),
            job_executor_process=mock_process
        )
        self.manager.active_mounts[mount_key] = mount_info
        
        with patch.object(self.manager, '_unmount_path', return_value=True):
            result = await self.manager.unmount_archive(self.mock_repository, "test-archive")
            
            assert result is True
            assert mount_key not in self.manager.active_mounts
            mock_process.terminate.assert_called_once()

    @pytest.mark.asyncio
    async def test_unmount_archive_not_mounted(self):
        """Test unmounting an archive that's not mounted."""
        result = await self.manager.unmount_archive(self.mock_repository, "test-archive")
        assert result is False

    @pytest.mark.asyncio
    async def test_unmount_path_success(self):
        """Test successful path unmounting."""
        test_mount_point = Path(self.test_mount_dir) / "test_mount"
        test_mount_point.mkdir(exist_ok=True)
        
        mock_process = Mock()
        mock_process.wait = AsyncMock(return_value=0)
        mock_process.returncode = 0
        
        with patch('asyncio.create_subprocess_exec', return_value=mock_process):
            result = await self.manager._unmount_path(test_mount_point)
            assert result is True

    @pytest.mark.asyncio
    async def test_unmount_path_failure(self):
        """Test path unmounting failure."""
        test_mount_point = Path(self.test_mount_dir) / "test_mount"
        test_mount_point.mkdir(exist_ok=True)
        
        mock_process = Mock()
        mock_process.wait = AsyncMock(return_value=1)
        mock_process.returncode = 1
        mock_process.stderr.read = AsyncMock(return_value=b"Device busy")
        
        with patch('asyncio.create_subprocess_exec', return_value=mock_process):
            result = await self.manager._unmount_path(test_mount_point)
            assert result is False

    def test_list_directory_not_mounted(self):
        """Test listing directory when archive is not mounted."""
        with pytest.raises(Exception) as exc_info:
            self.manager.list_directory(self.mock_repository, "test-archive", "")
        
        assert "Archive test-archive is not mounted" in str(exc_info.value)

    def test_list_directory_success(self):
        """Test successful directory listing."""
        # Setup mounted archive
        mount_key = self.manager._get_mount_key(self.mock_repository, "test-archive")
        test_mount_point = Path(self.test_mount_dir) / "test_mount"
        test_mount_point.mkdir(exist_ok=True)
        
        # Create test files and directories
        (test_mount_point / "file1.txt").touch()
        (test_mount_point / "file2.txt").touch()
        test_subdir = test_mount_point / "subdir"
        test_subdir.mkdir()
        
        mount_info = MountInfo(
            repository_path="/path/to/repo",
            archive_name="test-archive",
            mount_point=test_mount_point,
            mounted_at=datetime.now(),
            last_accessed=datetime.now() - timedelta(minutes=5)
        )
        self.manager.active_mounts[mount_key] = mount_info
        
        contents = self.manager.list_directory(self.mock_repository, "test-archive", "")
        
        # Should have 3 entries: 2 files and 1 directory
        assert len(contents) == 3
        
        # Check sorting (directories first, then files, both alphabetically)
        names = [item["name"] for item in contents]
        assert names == ["subdir", "file1.txt", "file2.txt"]
        
        # Check directory entry
        subdir_entry = next(item for item in contents if item["name"] == "subdir")
        assert subdir_entry["is_directory"] is True
        assert subdir_entry["type"] == "d"
        
        # Check file entry
        file_entry = next(item for item in contents if item["name"] == "file1.txt")
        assert file_entry["is_directory"] is False
        assert file_entry["type"] == "f"
        assert file_entry["size"] == 0  # Empty file

    def test_list_directory_with_path(self):
        """Test directory listing with specific path."""
        # Setup mounted archive with subdirectory
        mount_key = self.manager._get_mount_key(self.mock_repository, "test-archive")
        test_mount_point = Path(self.test_mount_dir) / "test_mount"
        test_mount_point.mkdir(exist_ok=True)
        
        test_subdir = test_mount_point / "data"
        test_subdir.mkdir()
        (test_subdir / "nested_file.txt").touch()
        
        mount_info = MountInfo(
            repository_path="/path/to/repo",
            archive_name="test-archive",
            mount_point=test_mount_point,
            mounted_at=datetime.now(),
            last_accessed=datetime.now()
        )
        self.manager.active_mounts[mount_key] = mount_info
        
        contents = self.manager.list_directory(self.mock_repository, "test-archive", "data")
        
        assert len(contents) == 1
        assert contents[0]["name"] == "nested_file.txt"
        # Handle cross-platform path separators
        expected_path = str(Path("data") / "nested_file.txt")
        assert contents[0]["path"] == expected_path

    def test_list_directory_path_not_exists(self):
        """Test listing non-existent directory."""
        mount_key = self.manager._get_mount_key(self.mock_repository, "test-archive")
        test_mount_point = Path(self.test_mount_dir) / "test_mount"
        test_mount_point.mkdir(exist_ok=True)
        
        mount_info = MountInfo(
            repository_path="/path/to/repo",
            archive_name="test-archive",
            mount_point=test_mount_point,
            mounted_at=datetime.now(),
            last_accessed=datetime.now()
        )
        self.manager.active_mounts[mount_key] = mount_info
        
        with pytest.raises(Exception) as exc_info:
            self.manager.list_directory(self.mock_repository, "test-archive", "nonexistent")
        
        assert "Path does not exist: nonexistent" in str(exc_info.value)

    def test_list_directory_path_not_directory(self):
        """Test listing a file path instead of directory."""
        mount_key = self.manager._get_mount_key(self.mock_repository, "test-archive")
        test_mount_point = Path(self.test_mount_dir) / "test_mount"
        test_mount_point.mkdir(exist_ok=True)
        (test_mount_point / "file.txt").touch()
        
        mount_info = MountInfo(
            repository_path="/path/to/repo",
            archive_name="test-archive",
            mount_point=test_mount_point,
            mounted_at=datetime.now(),
            last_accessed=datetime.now()
        )
        self.manager.active_mounts[mount_key] = mount_info
        
        with pytest.raises(Exception) as exc_info:
            self.manager.list_directory(self.mock_repository, "test-archive", "file.txt")
        
        assert "Path is not a directory: file.txt" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_cleanup_old_mounts(self):
        """Test cleanup of old unused mounts."""
        # Setup old mount
        mount_key = self.manager._get_mount_key(self.mock_repository, "test-archive")
        mount_point = self.manager._get_mount_point(self.mock_repository, "test-archive")
        
        mock_process = Mock()
        mock_process.terminate = Mock()
        mock_process.wait = AsyncMock(return_value=0)
        
        old_mount_info = MountInfo(
            repository_path="/path/to/repo",
            archive_name="test-archive",
            mount_point=mount_point,
            mounted_at=datetime.now() - timedelta(hours=2),
            last_accessed=datetime.now() - timedelta(hours=1),  # Older than mount_timeout
            job_executor_process=mock_process
        )
        self.manager.active_mounts[mount_key] = old_mount_info
        
        with patch.object(self.manager, '_unmount_path', return_value=True):
            await self.manager.cleanup_old_mounts()
            
            assert mount_key not in self.manager.active_mounts
            mock_process.terminate.assert_called_once()

    @pytest.mark.asyncio
    async def test_cleanup_old_mounts_recent_access(self):
        """Test that recently accessed mounts are not cleaned up."""
        # Setup recent mount
        mount_key = self.manager._get_mount_key(self.mock_repository, "test-archive")
        mount_point = self.manager._get_mount_point(self.mock_repository, "test-archive")
        
        recent_mount_info = MountInfo(
            repository_path="/path/to/repo",
            archive_name="test-archive",
            mount_point=mount_point,
            mounted_at=datetime.now() - timedelta(minutes=10),
            last_accessed=datetime.now() - timedelta(minutes=1)  # Recent access
        )
        self.manager.active_mounts[mount_key] = recent_mount_info
        
        await self.manager.cleanup_old_mounts()
        
        # Should still be mounted
        assert mount_key in self.manager.active_mounts

    @pytest.mark.asyncio
    async def test_unmount_all(self):
        """Test unmounting all active mounts."""
        # Setup multiple mounts
        for i in range(3):
            mount_key = f"/repo{i}::archive{i}"
            mount_point = self.manager.base_mount_dir / f"mount{i}"
            
            mock_process = Mock()
            mock_process.terminate = Mock()
            mock_process.wait = AsyncMock(return_value=0)
            
            mount_info = MountInfo(
                repository_path=f"/repo{i}",
                archive_name=f"archive{i}",
                mount_point=mount_point,
                mounted_at=datetime.now(),
                last_accessed=datetime.now(),
                job_executor_process=mock_process
            )
            self.manager.active_mounts[mount_key] = mount_info
        
        with patch.object(self.manager, '_unmount_path', return_value=True):
            await self.manager.unmount_all()
            
            assert len(self.manager.active_mounts) == 0

    def test_get_mount_stats(self):
        """Test getting mount statistics."""
        # Setup mount
        mount_key = self.manager._get_mount_key(self.mock_repository, "test-archive")
        mount_point = self.manager._get_mount_point(self.mock_repository, "test-archive")
        
        mount_info = MountInfo(
            repository_path="/path/to/repo",
            archive_name="test-archive",
            mount_point=mount_point,
            mounted_at=datetime.now(),
            last_accessed=datetime.now()
        )
        self.manager.active_mounts[mount_key] = mount_info
        
        stats = self.manager.get_mount_stats()
        
        assert stats["active_mounts"] == 1
        assert len(stats["mounts"]) == 1
        
        mount_stat = stats["mounts"][0]
        assert mount_stat["archive"] == "test-archive"
        assert mount_stat["mount_point"] == str(mount_point)
        assert "mounted_at" in mount_stat
        assert "last_accessed" in mount_stat


class TestGetArchiveMountManagerGlobal:
    """Test the global get_archive_mount_manager function."""
    
    def teardown_method(self):
        """Reset global state."""
        # Reset global instance
        import app.services.archive_mount_manager
        app.services.archive_mount_manager._mount_manager = None

    def test_get_archive_mount_manager_default(self):
        """Test getting default global instance."""
        manager = get_archive_mount_manager()
        assert isinstance(manager, ArchiveMountManager)
        
        # Should return same instance on subsequent calls
        manager2 = get_archive_mount_manager()
        assert manager is manager2

    def test_get_archive_mount_manager_with_params(self):
        """Test getting global instance with custom parameters."""
        custom_job_executor = Mock(spec=JobExecutor)
        
        # Use a temporary directory to avoid permission issues
        with tempfile.TemporaryDirectory() as temp_dir:
            custom_dir = os.path.join(temp_dir, "custom_dir")
            manager = get_archive_mount_manager(
                base_mount_dir=custom_dir,
                job_executor=custom_job_executor,
                cleanup_interval=120,
                mount_timeout=600
            )
            
            assert isinstance(manager, ArchiveMountManager)
            assert manager.base_mount_dir == Path(custom_dir)
            assert manager.job_executor is custom_job_executor
            assert manager.cleanup_interval == 120
            assert manager.mount_timeout == 600


class TestMountInfoDataclass:
    """Test the MountInfo dataclass."""
    
    def test_mount_info_creation(self):
        """Test MountInfo dataclass creation."""
        now = datetime.now()
        mount_point = Path("/test/mount")
        
        mount_info = MountInfo(
            repository_path="/repo",
            archive_name="archive",
            mount_point=mount_point,
            mounted_at=now,
            last_accessed=now
        )
        
        assert mount_info.repository_path == "/repo"
        assert mount_info.archive_name == "archive"
        assert mount_info.mount_point == mount_point
        assert mount_info.mounted_at == now
        assert mount_info.last_accessed == now
        assert mount_info.job_executor_process is None

    def test_mount_info_with_process(self):
        """Test MountInfo with process."""
        mock_process = Mock()
        now = datetime.now()
        
        mount_info = MountInfo(
            repository_path="/repo",
            archive_name="archive",
            mount_point=Path("/test/mount"),
            mounted_at=now,
            last_accessed=now,
            job_executor_process=mock_process
        )
        
        assert mount_info.job_executor_process is mock_process


class TestArchiveMountManagerIntegration:
    """Integration tests for ArchiveMountManager."""
    
    def setup_method(self):
        """Set up integration test fixtures."""
        self.test_mount_dir = tempfile.mkdtemp()
        self.mock_job_executor = Mock(spec=JobExecutor)
        
    def teardown_method(self):
        """Clean up integration test fixtures."""
        import shutil
        try:
            shutil.rmtree(self.test_mount_dir)
        except (OSError, PermissionError):
            pass

    def test_dependency_injection_pattern(self):
        """Test that dependency injection works properly."""
        custom_job_executor = Mock(spec=JobExecutor)
        
        manager = ArchiveMountManager(
            base_mount_dir=self.test_mount_dir,
            job_executor=custom_job_executor
        )
        
        assert manager.job_executor is custom_job_executor
        assert str(manager.base_mount_dir) == self.test_mount_dir

    @pytest.mark.asyncio
    async def test_mount_unmount_lifecycle(self):
        """Test complete mount/unmount lifecycle."""
        manager = ArchiveMountManager(
            base_mount_dir=self.test_mount_dir,
            job_executor=self.mock_job_executor
        )
        
        mock_repository = Mock(spec=Repository)
        mock_repository.name = "test-repo"
        mock_repository.path = "/path/to/repo"
        mock_repository.get_passphrase.return_value = "test_pass"
        
        # Test that initially no mounts exist
        stats = manager.get_mount_stats()
        assert stats["active_mounts"] == 0
        
        # Mock successful mount
        mock_process = Mock()
        mock_process.wait = AsyncMock(return_value=0)
        mock_process.stderr.read = AsyncMock(return_value=b"")
        
        with patch('asyncio.create_subprocess_exec', return_value=mock_process), \
             patch('app.utils.security.build_secure_borg_command', return_value=(["borg", "mount"], {})), \
             patch.object(manager, '_is_mounted', return_value=True), \
             patch('asyncio.sleep'):
            
            # Mount archive
            mount_point = await manager.mount_archive(mock_repository, "test-archive")
            
            # Verify mount was created
            stats = manager.get_mount_stats()
            assert stats["active_mounts"] == 1
            assert mount_point.exists()
            
            # Test unmount
            with patch.object(manager, '_unmount_path', return_value=True):
                result = await manager.unmount_archive(mock_repository, "test-archive")
                assert result is True
                
                # Verify mount was removed
                stats = manager.get_mount_stats()
                assert stats["active_mounts"] == 0

    def test_error_handling_robustness(self):
        """Test error handling in various scenarios."""
        # Use a path that will be created but may have permission issues
        with tempfile.TemporaryDirectory() as temp_dir:
            restricted_path = os.path.join(temp_dir, "restricted_path")
            
            # Create the manager with a path that exists but might have restrictions
            manager = ArchiveMountManager(
                base_mount_dir=restricted_path,
                job_executor=self.mock_job_executor
            )
            
            # Manager should still be created
            assert isinstance(manager, ArchiveMountManager)
            
            mock_repository = Mock(spec=Repository)
            mock_repository.name = "test-repo"
            mock_repository.path = "/path/to/repo"
            
            # Test listing directory on non-mounted archive
            with pytest.raises(Exception) as exc_info:
                manager.list_directory(mock_repository, "test-archive", "")
            assert "not mounted" in str(exc_info.value)