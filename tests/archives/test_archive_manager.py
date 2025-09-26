"""
Tests for ArchiveManager - Handles Borg archive operations and content management
"""

import pytest
import json
from unittest.mock import Mock, AsyncMock, patch
from types import SimpleNamespace

from borgitory.services.archives.archive_manager import ArchiveManager, ArchiveEntry
from borgitory.models.database import Repository
from borgitory.services.jobs.job_executor import JobExecutor


@pytest.fixture
def mock_job_executor() -> Mock:
    """Mock JobExecutor."""
    mock = Mock(spec=JobExecutor)
    mock.start_process = AsyncMock()
    mock.monitor_process_output = AsyncMock()
    return mock


@pytest.fixture
def archive_manager(
    mock_job_executor: Mock,
) -> ArchiveManager:
    """ArchiveManager instance with mocked dependencies."""
    mock_mount_manager = Mock()
    mock_mount_manager.mount_archive = AsyncMock()
    mock_mount_manager.list_directory = Mock(return_value=[])
    return ArchiveManager(
        job_executor=mock_job_executor,
        mount_manager=mock_mount_manager,
    )


@pytest.fixture
def test_repository() -> Repository:
    """Test repository object."""
    repo = Repository()
    repo.name = "test-repo"
    repo.path = "/tmp/test-repo"
    repo.set_passphrase("test-passphrase")
    return repo


@pytest.fixture
def mock_process_result() -> SimpleNamespace:
    """Mock process result."""
    result = SimpleNamespace()
    result.return_code = 0
    result.stdout = b'{"path": "test.txt", "type": "f", "size": 1024, "mtime": "2023-01-01T00:00:00"}\n'
    result.stderr = b""
    return result


class TestArchiveManager:
    """Test class for ArchiveManager."""

    def test_init_with_dependencies(self) -> None:
        """Test ArchiveManager initialization with provided dependencies."""
        mock_executor = Mock(spec=JobExecutor)
        mock_mount_manager = Mock()

        manager = ArchiveManager(
            job_executor=mock_executor,
            mount_manager=mock_mount_manager,
        )

        assert manager.job_executor is mock_executor
        assert manager.mount_manager is mock_mount_manager

    def test_init_with_defaults(self) -> None:
        """Test ArchiveManager initialization with default dependencies."""

        mock_mount_manager = Mock()
        manager = ArchiveManager(
            job_executor=JobExecutor(),
            mount_manager=mock_mount_manager,
        )

        assert isinstance(manager.job_executor, JobExecutor)
        assert manager.mount_manager is mock_mount_manager

    @pytest.mark.asyncio
    async def test_list_archive_directory_contents_success(
        self, archive_manager, test_repository
    ) -> None:
        """Test listing directory contents using FUSE mount."""
        # Configure the mount manager that's already injected in the fixture
        archive_manager.mount_manager.list_directory.return_value = [
            ArchiveEntry(
                name="file1.txt",
                type="f",
                size=100,
                isdir=False,
                path="file1.txt",
            ),
            ArchiveEntry(name="subdir", type="d", size=0, isdir=True, path="subdir"),
        ]

        result = await archive_manager.list_archive_directory_contents(
            test_repository, "test-archive", "/data"
        )

        assert len(result) == 2
        assert result[0].name == "file1.txt"
        assert result[1].name == "subdir"

        # Verify the mount manager was called correctly
        archive_manager.mount_manager.mount_archive.assert_called_once_with(
            test_repository, "test-archive"
        )
        archive_manager.mount_manager.list_directory.assert_called_once_with(
            test_repository, "test-archive", "/data"
        )

    def test_filter_directory_contents_root(
        self, archive_manager: ArchiveManager
    ) -> None:
        """Test filtering directory contents for root path."""
        all_entries = [
            ArchiveEntry(
                path="file1.txt", type="f", size=100, name="file1.txt", isdir=False
            ),
            ArchiveEntry(
                path="dir1/file2.txt", type="f", size=200, name="file2.txt", isdir=False
            ),
            ArchiveEntry(
                path="dir1/subdir/file3.txt",
                type="f",
                size=300,
                name="file3.txt",
                isdir=False,
            ),
            ArchiveEntry(
                path="dir2/file4.txt", type="f", size=400, name="file4.txt", isdir=False
            ),
        ]

        result = archive_manager._filter_directory_contents(all_entries, "")

        # Should return immediate children at root level
        assert len(result) == 3
        names = [item.name for item in result]
        assert "file1.txt" in names
        assert "dir1" in names
        assert "dir2" in names

        # Check directory detection
        dir1_item = next(item for item in result if item.name == "dir1")
        assert dir1_item.type == "d"
        assert dir1_item.isdir is True

    def test_filter_directory_contents_subdirectory(
        self, archive_manager: ArchiveManager
    ) -> None:
        """Test filtering directory contents for subdirectory path."""
        all_entries = [
            ArchiveEntry(
                path="dir1/file1.txt", type="f", size=100, name="file1.txt", isdir=False
            ),
            ArchiveEntry(
                path="dir1/file2.txt", type="f", size=200, name="file2.txt", isdir=False
            ),
            ArchiveEntry(
                path="dir1/subdir/file3.txt",
                type="f",
                size=300,
                name="file3.txt",
                isdir=False,
            ),
            ArchiveEntry(
                path="dir2/file4.txt", type="f", size=400, name="file4.txt", isdir=False
            ),
        ]

        result = archive_manager._filter_directory_contents(all_entries, "dir1")

        # Should return immediate children of dir1
        assert len(result) == 3
        names = [item.name for item in result]
        assert "file1.txt" in names
        assert "file2.txt" in names
        assert "subdir" in names

    def test_filter_directory_contents_sorting(
        self, archive_manager: ArchiveManager
    ) -> None:
        """Test that results are sorted correctly (directories first, then alphabetically)."""
        all_entries = [
            ArchiveEntry(
                path="zebra.txt", type="f", size=100, name="zebra.txt", isdir=False
            ),
            ArchiveEntry(
                path="bdir/file.txt", type="f", size=200, name="file.txt", isdir=False
            ),
            ArchiveEntry(
                path="adir/file.txt", type="f", size=300, name="file.txt", isdir=False
            ),
            ArchiveEntry(
                path="alpha.txt", type="f", size=400, name="alpha.txt", isdir=False
            ),
        ]

        result = archive_manager._filter_directory_contents(all_entries, "")

        # Should be: directories first (adir, bdir), then files (alpha.txt, zebra.txt)
        names = [item.name for item in result]
        assert names == ["adir", "bdir", "alpha.txt", "zebra.txt"]

    @pytest.mark.asyncio
    async def test_extract_file_stream_success(
        self, archive_manager, test_repository
    ) -> None:
        """Test successful file extraction streaming."""
        with patch("asyncio.create_subprocess_exec") as mock_subprocess:
            # Mock process
            mock_process = Mock()
            mock_process.stdout.read = AsyncMock(
                side_effect=[b"chunk1", b"chunk2", b""]
            )
            mock_process.wait = AsyncMock(return_value=0)
            mock_subprocess.return_value = mock_process

            chunks = []
            async for chunk in archive_manager.extract_file_stream(
                test_repository, "test-archive", "test.txt"
            ):
                chunks.append(chunk)

            assert chunks == [b"chunk1", b"chunk2"]
            mock_subprocess.assert_called_once()

    @pytest.mark.asyncio
    async def test_extract_file_stream_error(
        self, archive_manager, test_repository
    ) -> None:
        """Test file extraction with Borg error."""
        with patch("asyncio.create_subprocess_exec") as mock_subprocess:
            mock_process = Mock()
            mock_process.stdout.read = AsyncMock(return_value=b"")
            mock_process.wait = AsyncMock(return_value=1)
            mock_process.stderr.read = AsyncMock(return_value=b"File not found")
            mock_subprocess.return_value = mock_process

            with pytest.raises(Exception) as exc_info:
                chunks = []
                async for chunk in archive_manager.extract_file_stream(
                    test_repository, "test-archive", "nonexistent.txt"
                ):
                    chunks.append(chunk)

            assert "Borg extract failed with code 1" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_extract_file_stream_process_cleanup(
        self, archive_manager, test_repository
    ) -> None:
        """Test process cleanup on exception during streaming."""
        with patch("asyncio.create_subprocess_exec") as mock_subprocess:
            mock_process = Mock()
            mock_process.stdout.read = AsyncMock(side_effect=Exception("Read error"))
            mock_process.returncode = None
            mock_process.terminate = Mock()
            mock_process.kill = Mock()
            mock_process.wait = AsyncMock()
            mock_subprocess.return_value = mock_process

            with pytest.raises(Exception):
                async for chunk in archive_manager.extract_file_stream(
                    test_repository, "test-archive", "test.txt"
                ):
                    pass

            mock_process.terminate.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_archive_metadata_success(
        self, archive_manager, test_repository, mock_job_executor
    ) -> None:
        """Test successful archive metadata retrieval."""
        # Setup mock result
        repo_info = {
            "archives": [
                {"name": "archive1", "size": 1000, "stats": {"nfiles": 10}},
                {"name": "test-archive", "size": 2000, "stats": {"nfiles": 20}},
                {"name": "archive2", "size": 3000, "stats": {"nfiles": 30}},
            ]
        }

        result = SimpleNamespace()
        result.return_code = 0
        result.stdout = json.dumps(repo_info).encode("utf-8")
        result.stderr = b""

        mock_process = Mock()
        mock_job_executor.start_process.return_value = mock_process
        mock_job_executor.monitor_process_output.return_value = result

        metadata = await archive_manager.get_archive_metadata(
            test_repository, "test-archive"
        )

        assert metadata is not None
        assert metadata["name"] == "test-archive"
        assert metadata["size"] == 2000
        assert metadata["stats"]["nfiles"] == 20

    @pytest.mark.asyncio
    async def test_get_archive_metadata_not_found(
        self, archive_manager, test_repository, mock_job_executor
    ) -> None:
        """Test archive metadata when archive is not found."""
        # Setup mock result with different archives
        repo_info = {"archives": [{"name": "other-archive", "size": 1000}]}

        result = SimpleNamespace()
        result.return_code = 0
        result.stdout = json.dumps(repo_info).encode("utf-8")
        result.stderr = b""

        mock_process = Mock()
        mock_job_executor.start_process.return_value = mock_process
        mock_job_executor.monitor_process_output.return_value = result

        metadata = await archive_manager.get_archive_metadata(
            test_repository, "nonexistent-archive"
        )

        assert metadata is None

    @pytest.mark.asyncio
    async def test_get_archive_metadata_borg_error(
        self, archive_manager, test_repository, mock_job_executor
    ) -> None:
        """Test archive metadata retrieval with Borg error."""
        result = SimpleNamespace()
        result.return_code = 1
        result.stdout = b""
        result.stderr = b"Repository access denied"

        mock_process = Mock()
        mock_job_executor.start_process.return_value = mock_process
        mock_job_executor.monitor_process_output.return_value = result

        metadata = await archive_manager.get_archive_metadata(
            test_repository, "test-archive"
        )

        assert metadata is None

    def test_calculate_directory_size_root(
        self, archive_manager: ArchiveManager
    ) -> None:
        """Test calculating total size for root directory."""
        entries = [
            ArchiveEntry(
                path="file1.txt", type="f", size=100, name="file1.txt", isdir=False
            ),
            ArchiveEntry(
                path="file2.txt", type="f", size=200, name="file2.txt", isdir=False
            ),
            ArchiveEntry(path="dir1", type="d", size=0, name="dir1", isdir=True),
            ArchiveEntry(
                path="dir1/file3.txt", type="f", size=300, name="file3.txt", isdir=False
            ),
        ]

        total_size = archive_manager.calculate_directory_size(entries, "")

        # Should sum all files (ignore directories)
        assert total_size == 600

    def test_calculate_directory_size_subdirectory(
        self, archive_manager: ArchiveManager
    ) -> None:
        """Test calculating size for specific subdirectory."""
        entries = [
            ArchiveEntry(
                path="file1.txt", type="f", size=100, name="file1.txt", isdir=False
            ),
            ArchiveEntry(
                path="dir1/file2.txt", type="f", size=200, name="file2.txt", isdir=False
            ),
            ArchiveEntry(
                path="dir1/file3.txt", type="f", size=300, name="file3.txt", isdir=False
            ),
            ArchiveEntry(
                path="dir2/file4.txt", type="f", size=400, name="file4.txt", isdir=False
            ),
        ]

        total_size = archive_manager.calculate_directory_size(entries, "dir1")

        # Should sum only files in dir1
        assert total_size == 500

    def test_find_entries_by_pattern_case_sensitive(
        self, archive_manager: ArchiveManager
    ) -> None:
        """Test finding entries by pattern (case sensitive)."""
        entries = [
            ArchiveEntry(
                path="Test.txt", type="f", size=100, name="Test.txt", isdir=False
            ),
            ArchiveEntry(
                path="test.log", type="f", size=100, name="test.log", isdir=False
            ),
            ArchiveEntry(
                path="data/Test.cfg", type="f", size=100, name="Test.cfg", isdir=False
            ),
        ]

        matches = archive_manager.find_entries_by_pattern(
            entries, "Test", case_sensitive=True
        )

        assert len(matches) == 2
        names = [entry.name for entry in matches]
        assert "Test.txt" in names
        assert "Test.cfg" in names

    def test_find_entries_by_pattern_case_insensitive(
        self, archive_manager: ArchiveManager
    ) -> None:
        """Test finding entries by pattern (case insensitive)."""
        entries = [
            ArchiveEntry(
                path="Test.txt", type="f", size=100, name="Test.txt", isdir=False
            ),
            ArchiveEntry(
                path="test.log", type="f", size=100, name="test.log", isdir=False
            ),
            ArchiveEntry(
                path="data/config.cfg",
                type="f",
                size=100,
                name="borgitory.config.cfg",
                isdir=False,
            ),
        ]

        matches = archive_manager.find_entries_by_pattern(
            entries, "test", case_sensitive=False
        )

        assert len(matches) == 2
        names = [entry.name for entry in matches]
        assert "Test.txt" in names
        assert "test.log" in names

    def test_find_entries_by_pattern_regex(
        self, archive_manager: ArchiveManager
    ) -> None:
        """Test finding entries using regex pattern."""
        entries = [
            ArchiveEntry(
                path="file1.txt", type="f", size=100, name="file1.txt", isdir=False
            ),
            ArchiveEntry(
                path="file2.log", type="f", size=100, name="file2.log", isdir=False
            ),
            ArchiveEntry(
                path="backup.tar.gz",
                type="f",
                size=100,
                name="backup.tar.gz",
                isdir=False,
            ),
        ]

        matches = archive_manager.find_entries_by_pattern(entries, r"\.txt$")

        assert len(matches) == 1
        assert matches[0].name == "file1.txt"

    def test_find_entries_by_pattern_invalid_regex(
        self, archive_manager: ArchiveManager
    ) -> None:
        """Test finding entries with invalid regex (fallback to literal)."""
        entries = [
            ArchiveEntry(
                path="test[.txt", type="f", size=100, name="test[.txt", isdir=False
            ),
            ArchiveEntry(
                path="normal.txt", type="f", size=100, name="normal.txt", isdir=False
            ),
        ]

        # This should treat the pattern as literal string
        matches = archive_manager.find_entries_by_pattern(entries, "[")

        assert len(matches) == 1
        assert matches[0].name == "test[.txt"

    def test_get_file_type_summary(self, archive_manager: ArchiveManager) -> None:
        """Test generating file type summary."""
        entries = [
            ArchiveEntry(
                path="doc1.txt", type="f", size=100, name="doc1.txt", isdir=False
            ),
            ArchiveEntry(
                path="doc2.txt", type="f", size=100, name="doc2.txt", isdir=False
            ),
            ArchiveEntry(
                path="image.jpg", type="f", size=100, name="image.jpg", isdir=False
            ),
            ArchiveEntry(path="folder1", type="d", size=0, name="folder1", isdir=True),
            ArchiveEntry(path="folder2", type="d", size=0, name="folder2", isdir=True),
            ArchiveEntry(
                path="script", type="f", size=100, name="script", isdir=False
            ),  # no extension
        ]

        summary = archive_manager.get_file_type_summary(entries)

        # Should be sorted by count descending
        expected_order = [".txt", "directory", ".jpg", "no extension"]
        assert list(summary.keys()) == expected_order
        assert summary[".txt"] == 2
        assert summary["directory"] == 2
        assert summary[".jpg"] == 1
        assert summary["no extension"] == 1

    def test_validate_archive_path_valid(self, archive_manager: ArchiveManager) -> None:
        """Test validation of valid archive name and path."""
        with patch(
            "borgitory.services.archives.archive_manager.validate_archive_name"
        ) as mock_validate_archive:
            with patch(
                "borgitory.services.archives.archive_manager.sanitize_path"
            ) as mock_sanitize_path:
                mock_validate_archive.return_value = None  # No exception means valid
                mock_sanitize_path.return_value = "/safe/path"

                errors = archive_manager.validate_archive_path(
                    "valid-archive", "/safe/path"
                )

                assert len(errors) == 0
                mock_validate_archive.assert_called_once_with("valid-archive")
                mock_sanitize_path.assert_called_once_with("/safe/path")

    def test_validate_archive_path_invalid(
        self, archive_manager: ArchiveManager
    ) -> None:
        """Test validation with invalid archive name and path."""
        with patch(
            "borgitory.services.archives.archive_manager.validate_archive_name"
        ) as mock_validate_archive:
            with patch(
                "borgitory.services.archives.archive_manager.sanitize_path"
            ) as mock_sanitize_path:
                mock_validate_archive.side_effect = Exception("Invalid archive name")
                mock_sanitize_path.side_effect = Exception("Unsafe path")

                errors = archive_manager.validate_archive_path(
                    "../evil", "../../etc/passwd"
                )

                assert len(errors) == 2
                assert "archive_name" in errors
                assert "file_path" in errors
                assert "Invalid archive name" in errors["archive_name"]
                assert "Unsafe path" in errors["file_path"]
