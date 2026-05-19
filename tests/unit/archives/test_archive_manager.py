"""
Tests for ArchiveManager
"""

import pytest
from unittest.mock import AsyncMock, MagicMock
from borgitory.config.command_runner_config import CommandRunnerConfig
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
    def mock_command_runner_config(self) -> MagicMock:
        """Mock command runner config"""
        config = MagicMock(spec=["timeout"])
        config.timeout = 60
        return config

    @pytest.fixture
    def manager(
        self,
        mock_job_executor: AsyncMock,
        mock_command_executor: AsyncMock,
        mock_command_runner_config: MagicMock,
    ) -> ArchiveManager:
        """Create ArchiveManager instance"""
        return ArchiveManager(
            job_executor=mock_job_executor,
            command_executor=mock_command_executor,
            command_runner_config=mock_command_runner_config,
        )

    def test_init_with_dependencies(
        self,
        mock_job_executor: AsyncMock,
        mock_command_executor: AsyncMock,
        mock_command_runner_config: MagicMock,
    ) -> None:
        """Test initialization with dependencies"""
        manager = ArchiveManager(
            job_executor=mock_job_executor,
            command_executor=mock_command_executor,
            command_runner_config=mock_command_runner_config,
        )

        assert manager.job_executor == mock_job_executor
        assert manager.command_executor == mock_command_executor
        assert manager.command_runner_config == mock_command_runner_config

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


class TestExtractFileStreamCommand:
    """
    Tests that confirm the bugs reported in issue #227:
    1. Repository path is appended twice to the borg extract command.
    2. A leading slash is prepended to the archive file path, causing a no-match.
    """

    @pytest.fixture
    def mock_repository(self) -> MagicMock:
        repo = MagicMock(spec=Repository)
        repo.path = "/repos/Linux_Server_Backups"
        repo.name = "Linux Server Backups"
        repo.get_passphrase.return_value = None
        repo.get_keyfile_content.return_value = None
        return repo

    @pytest.fixture
    def manager(self) -> ArchiveManager:
        mock_process = MagicMock()
        mock_process.stdout = AsyncMock()
        mock_process.stdout.read = AsyncMock(return_value=b"")
        mock_process.stderr = AsyncMock()
        mock_process.stderr.read = AsyncMock(return_value=b"")
        mock_process.wait = AsyncMock(return_value=0)
        mock_process.returncode = 0

        mock_command_executor = AsyncMock()
        mock_command_executor.create_subprocess = AsyncMock(return_value=mock_process)

        return ArchiveManager(
            job_executor=AsyncMock(),
            command_executor=mock_command_executor,
            command_runner_config=CommandRunnerConfig(timeout=60),
        )

    @pytest.mark.asyncio
    async def test_extract_command_does_not_append_repo_path_twice(
        self, manager: ArchiveManager, mock_repository: MagicMock
    ) -> None:
        """
        Regression test for issue #227.

        The repo path must not appear as a trailing argument after the
        REPO::ARCHIVE spec, because borg interprets it as an include pattern
        that never matches any archive entry.
        """
        archive_name = "test-archive-2026-01-01"
        file_path = "mnt/backup_snapshots/rootsnapshot/srv/nextcloud/.env.app"

        response = await manager.extract_file_stream(
            mock_repository, archive_name, file_path
        )

        # Consume the stream so the subprocess call is made
        async def _consume() -> None:
            async for _ in response.body_iterator:
                pass

        await _consume()

        call_args = manager.command_executor.create_subprocess.call_args
        command = call_args.kwargs.get("command") or call_args.args[0]

        repo_archive_spec = f"{mock_repository.path}::{archive_name}"

        # The REPO::ARCHIVE spec must appear exactly once
        assert command.count(repo_archive_spec) == 1, (
            f"REPO::ARCHIVE spec appeared {command.count(repo_archive_spec)} times in command: {command}"
        )

        # The bare repo path must NOT appear as a standalone trailing argument
        assert (
            mock_repository.path not in command[command.index(repo_archive_spec) + 1 :]
        ), (
            f"Repository path '{mock_repository.path}' was appended again after "
            f"the REPO::ARCHIVE spec in command: {command}"
        )

    @pytest.mark.asyncio
    async def test_extract_command_does_not_prepend_slash_to_file_path(
        self, manager: ArchiveManager, mock_repository: MagicMock
    ) -> None:
        """
        Regression test for issue #227.

        Borg archives store paths without a leading slash.  Prepending '/'
        causes borg to report 'Include pattern never matched' for the file.
        """
        archive_name = "test-archive-2026-01-01"
        file_path = "mnt/backup_snapshots/rootsnapshot/srv/nextcloud/.env.app"

        response = await manager.extract_file_stream(
            mock_repository, archive_name, file_path
        )

        async def _consume() -> None:
            async for _ in response.body_iterator:
                pass

        await _consume()

        call_args = manager.command_executor.create_subprocess.call_args
        command = call_args.kwargs.get("command") or call_args.args[0]

        # The file path argument must not have a leading slash added to it
        assert "/" + file_path not in command, (
            f"File path was given a spurious leading slash in command: {command}"
        )
        assert file_path in command, (
            f"File path '{file_path}' not found in command: {command}"
        )
