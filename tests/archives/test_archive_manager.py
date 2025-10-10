"""
Tests for ArchiveManager
"""

import pytest
from unittest.mock import AsyncMock, MagicMock
from borgitory.services.archives.archive_manager import ArchiveManager
from borgitory.services.archives.archive_models import ArchiveEntry
from borgitory.models.database import Repository


class TestArchiveManager:
    """Test cases for ArchiveManager"""

    @pytest.fixture
    def mock_job_executor(self) -> AsyncMock:
        """Mock job executor"""
        return AsyncMock()

    @pytest.fixture
    def mock_command_executor(self) -> AsyncMock:
        """Mock command executor"""
        mock = AsyncMock()
        mock.create_subprocess = AsyncMock()
        return mock

    @pytest.fixture
    def mock_repository(self) -> MagicMock:
        """Mock repository"""
        repo = MagicMock(spec=Repository)
        repo.path = "/test/repo"
        repo.name = "test_repo"
        repo.get_passphrase.return_value = "test_passphrase"
        repo.get_keyfile_content.return_value = None
        return repo

    @pytest.fixture
    def manager(
        self, mock_job_executor: AsyncMock, mock_command_executor: AsyncMock
    ) -> ArchiveManager:
        """Create ArchiveManager instance"""
        return ArchiveManager(
            job_executor=mock_job_executor,
            command_executor=mock_command_executor,
        )

    def test_init_with_dependencies(
        self, mock_job_executor: AsyncMock, mock_command_executor: AsyncMock
    ) -> None:
        """Test initialization with dependencies"""
        manager = ArchiveManager(
            job_executor=mock_job_executor,
            command_executor=mock_command_executor,
        )

        assert manager.job_executor == mock_job_executor
        assert manager.command_executor == mock_command_executor

    async def test_parse_borg_list_output(self, manager: ArchiveManager) -> None:
        """Test parsing borg list JSON output"""
        json_output = """{"type": "d", "mode": "drwxr-xr-x", "uid": 1000, "gid": 1000, "user": "user", "group": "user", "size": 0, "mtime": "2023-01-01T00:00:00Z", "path": "test_dir"}
{"type": "-", "mode": "-rw-r--r--", "uid": 1000, "gid": 1000, "user": "user", "group": "user", "size": 1024, "mtime": "2023-01-01T00:00:00Z", "path": "test_file.txt"}"""

        items = manager._parse_borg_list_output(json_output)

        assert len(items) == 2

        # Check directory entry
        dir_entry = items[0]
        assert dir_entry.path == "test_dir"
        assert dir_entry.name == "test_dir"
        assert dir_entry.type == "d"
        assert dir_entry.isdir is True
        assert dir_entry.size == 0

        # Check file entry
        file_entry = items[1]
        assert file_entry.path == "test_file.txt"
        assert file_entry.name == "test_file.txt"
        assert file_entry.type == "f"
        assert file_entry.isdir is False
        assert file_entry.size == 1024

    def test_filter_directory_contents_root(self, manager: ArchiveManager) -> None:
        """Test filtering directory contents for root directory"""
        entries = [
            ArchiveEntry(
                path="file1.txt", name="file1.txt", type="f", size=100, isdir=False
            ),
            ArchiveEntry(
                path="dir1/file2.txt", name="file2.txt", type="f", size=200, isdir=False
            ),
            ArchiveEntry(
                path="dir1/subdir/file3.txt",
                name="file3.txt",
                type="f",
                size=300,
                isdir=False,
            ),
            ArchiveEntry(
                path="dir2/file4.txt", name="file4.txt", type="f", size=400, isdir=False
            ),
        ]

        result = manager._filter_directory_contents(entries, "")

        assert len(result) == 3  # file1.txt, dir1, dir2

        # Check that we have the right items
        names = [item.name for item in result]
        assert "file1.txt" in names
        assert "dir1" in names
        assert "dir2" in names

        # Check that dir1 is marked as directory
        dir1 = next(item for item in result if item.name == "dir1")
        assert dir1.isdir is True
        assert dir1.type == "d"

    def test_filter_directory_contents_subdirectory(
        self, manager: ArchiveManager
    ) -> None:
        """Test filtering directory contents for subdirectory"""
        entries = [
            ArchiveEntry(
                path="dir1/file1.txt", name="file1.txt", type="f", size=100, isdir=False
            ),
            ArchiveEntry(
                path="dir1/file2.txt", name="file2.txt", type="f", size=200, isdir=False
            ),
            ArchiveEntry(
                path="dir1/subdir/file3.txt",
                name="file3.txt",
                type="f",
                size=300,
                isdir=False,
            ),
            ArchiveEntry(
                path="dir2/file4.txt", name="file4.txt", type="f", size=400, isdir=False
            ),
        ]

        result = manager._filter_directory_contents(entries, "dir1")

        assert len(result) == 3  # file1.txt, file2.txt, subdir

        # Check that we have the right items
        names = [item.name for item in result]
        assert "file1.txt" in names
        assert "file2.txt" in names
        assert "subdir" in names

        # Check that subdir is marked as directory
        subdir = next(item for item in result if item.name == "subdir")
        assert subdir.isdir is True
        assert subdir.type == "d"

    def test_filter_directory_contents_sorting(self, manager: ArchiveManager) -> None:
        """Test that filtered results are sorted correctly (directories first)"""
        entries = [
            ArchiveEntry(
                path="file1.txt", name="file1.txt", type="f", size=100, isdir=False
            ),
            ArchiveEntry(
                path="dir1/file2.txt", name="file2.txt", type="f", size=200, isdir=False
            ),
            ArchiveEntry(
                path="dir2/file3.txt", name="file3.txt", type="f", size=300, isdir=False
            ),
        ]

        result = manager._filter_directory_contents(entries, "")

        # Should be sorted: directories first, then files, both alphabetically
        assert result[0].name == "dir1"  # directory
        assert result[1].name == "dir2"  # directory
        assert result[2].name == "file1.txt"  # file
