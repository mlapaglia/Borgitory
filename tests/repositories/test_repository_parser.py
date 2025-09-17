"""
Tests for RepositoryParser - Comprehensive coverage
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch, mock_open

from borgitory.services.repositories.repository_parser import RepositoryParser
from borgitory.models.database import Repository
from borgitory.services.simple_command_runner import SimpleCommandRunner


@pytest.fixture
def mock_command_runner():
    """Mock SimpleCommandRunner."""
    mock = Mock(spec=SimpleCommandRunner)
    mock.run_command = AsyncMock()
    return mock


@pytest.fixture
def repository_parser(mock_command_runner):
    """RepositoryParser instance with mocked dependencies."""
    mock_job_manager = Mock()
    return RepositoryParser(
        command_runner=mock_command_runner, job_manager=mock_job_manager
    )


@pytest.fixture
def test_repository():
    """Test repository object."""
    repository = Repository(
        id=1,
        name="test-repo",
        path="/path/to/repo",
        encrypted_passphrase="encrypted_passphrase",
    )
    repository.get_passphrase = Mock(return_value="test_passphrase")
    return repository


class TestRepositoryParser:
    """Test RepositoryParser functionality."""

    def test_parse_borg_config_file_not_found(self, repository_parser) -> None:
        """Test handling missing config file."""
        with patch("os.path.exists", return_value=False):
            result = repository_parser.parse_borg_config("/fake/path")

        assert result["preview"] == "Config file not found"
        assert result["mode"] == "unknown"
        assert result["requires_keyfile"] is False

    def test_parse_borg_config_valid_repository_with_encryption(
        self, repository_parser
    ) -> None:
        """Test parsing valid Borg repository with encryption."""
        config_content = """[repository]
version = 2
segments_per_dir = 1000
max_segment_size = 524288000
append_only = 0
storage_quota = 0
additional_free_space = 0
id = abc123def456
key = some-key-value
"""
        key_type_content = "blake2-chacha20-poly1305"

        with patch("os.path.exists") as mock_exists, patch(
            "builtins.open", mock_open(read_data=config_content)
        ) as mock_file:

            def exists_side_effect(path):
                if path.endswith("config"):
                    return True
                elif path.endswith("key-type"):
                    return True
                elif path.endswith("security"):
                    return True
                return False

            mock_exists.side_effect = exists_side_effect

            # Mock the key-type file read
            def open_side_effect(path, mode="r", encoding=None):
                if path.endswith("key-type"):
                    return mock_open(read_data=key_type_content).return_value
                else:
                    return mock_open(read_data=config_content).return_value

            mock_file.side_effect = open_side_effect

            result = repository_parser.parse_borg_config("/test/repo")

            assert result["mode"] == "encrypted"
            assert result["requires_keyfile"] is False  # passphrase mode
            assert "Key type: blake2-chacha20-poly1305" in result["preview"]
            assert "Version: 2" in result["preview"]

    def test_parse_borg_config_keyfile_encryption(self, repository_parser) -> None:
        """Test parsing repository with keyfile encryption."""
        config_content = """[repository]
version = 2
segments_per_dir = 1000
"""
        key_type_content = "blake2-aes256-ctr-hmac-sha256"

        with patch("os.path.exists") as mock_exists, patch(
            "builtins.open", mock_open()
        ) as mock_file:

            def exists_side_effect(path):
                return path.endswith(("config", "key-type"))

            mock_exists.side_effect = exists_side_effect

            def open_side_effect(path, mode="r", encoding=None):
                if path.endswith("key-type"):
                    return mock_open(read_data=key_type_content).return_value
                else:
                    return mock_open(read_data=config_content).return_value

            mock_file.side_effect = open_side_effect

            result = repository_parser.parse_borg_config("/test/repo")

            assert result["mode"] == "encrypted"
            assert result["requires_keyfile"] is True  # keyfile mode
            assert "Key type: blake2-aes256-ctr-hmac-sha256" in result["preview"]

    def test_parse_borg_config_no_repository_section(self, repository_parser) -> None:
        """Test parsing config without repository section."""
        config_content = """[cache]
version = 1
"""

        with patch("os.path.exists", return_value=True), patch(
            "builtins.open", mock_open(read_data=config_content)
        ):
            result = repository_parser.parse_borg_config("/test/repo")

            assert result["mode"] == "invalid"
            assert "Not a valid Borg repository" in result["preview"]
            assert result["requires_keyfile"] is False

    def test_parse_borg_config_unencrypted_repository(self, repository_parser) -> None:
        """Test parsing unencrypted repository."""
        config_content = """[repository]
version = 2
segments_per_dir = 1000
"""

        with patch("os.path.exists") as mock_exists, patch(
            "builtins.open", mock_open(read_data=config_content)
        ), patch("os.listdir", return_value=[]):

            def exists_side_effect(path):
                if path.endswith("config"):
                    return True
                elif path.endswith("security"):
                    return True
                return False

            mock_exists.side_effect = exists_side_effect

            result = repository_parser.parse_borg_config("/test/repo")

            assert result["mode"] == "unencrypted"
            assert result["requires_keyfile"] is False
            assert "Security files: 0 files" in result["preview"]

    def test_parse_borg_config_unknown_key_type(self, repository_parser) -> None:
        """Test parsing with unknown key type."""
        config_content = """[repository]
version = 2
"""
        key_type_content = "unknown-encryption-type"

        with patch("os.path.exists") as mock_exists, patch(
            "builtins.open", mock_open()
        ) as mock_file:

            def exists_side_effect(path):
                return path.endswith(("config", "key-type"))

            mock_exists.side_effect = exists_side_effect

            def open_side_effect(path, mode="r", encoding=None):
                if path.endswith("key-type"):
                    return mock_open(read_data=key_type_content).return_value
                else:
                    return mock_open(read_data=config_content).return_value

            mock_file.side_effect = open_side_effect

            result = repository_parser.parse_borg_config("/test/repo")

            assert result["mode"] == "encrypted"
            assert result["requires_keyfile"] is False  # defaults to passphrase
            assert "Key type: unknown-encryption-type" in result["preview"]

    def test_parse_borg_config_file_read_error(self, repository_parser) -> None:
        """Test handling file read errors."""
        with patch("os.path.exists", return_value=True), patch(
            "builtins.open", side_effect=IOError("Permission denied")
        ):
            result = repository_parser.parse_borg_config("/test/repo")

            assert result["mode"] == "error"
            assert "Parse error: Permission denied" in result["preview"]
            assert result["requires_keyfile"] is False

    def test_parse_borg_config_invalid_config_format(self, repository_parser) -> None:
        """Test handling invalid config file format."""
        invalid_config = "This is not a valid config file\nJust some random text"

        with patch("os.path.exists", return_value=True), patch(
            "builtins.open", mock_open(read_data=invalid_config)
        ):
            result = repository_parser.parse_borg_config("/test/repo")

            assert result["mode"] == "error"
            assert "Parse error:" in result["preview"]
            assert result["requires_keyfile"] is False

    def test_parse_borg_config_key_type_read_error(self, repository_parser) -> None:
        """Test handling key-type file read error."""
        config_content = """[repository]
version = 2
"""

        with patch("os.path.exists") as mock_exists, patch(
            "builtins.open", mock_open(read_data=config_content)
        ) as mock_file:

            def exists_side_effect(path):
                return path.endswith(("config", "key-type", "security"))

            mock_exists.side_effect = exists_side_effect

            def open_side_effect(path, mode="r", encoding=None):
                if path.endswith("key-type"):
                    raise IOError("Cannot read key-type file")
                else:
                    return mock_open(read_data=config_content).return_value

            mock_file.side_effect = open_side_effect

            with patch("os.listdir", return_value=["file1", "file2"]):
                result = repository_parser.parse_borg_config("/test/repo")

            assert result["mode"] == "encrypted"
            assert (
                "Could not read key-type: Cannot read key-type file"
                in result["preview"]
            )
            assert "Security files: 2 files" in result["preview"]

    def test_parse_borg_config_security_dir_error(self, repository_parser) -> None:
        """Test handling security directory read error."""
        config_content = """[repository]
version = 2
"""

        with patch("os.path.exists") as mock_exists, patch(
            "builtins.open", mock_open(read_data=config_content)
        ), patch("os.listdir", side_effect=OSError("Cannot read directory")):

            def exists_side_effect(path):
                return path.endswith(("config", "security"))

            mock_exists.side_effect = exists_side_effect

            result = repository_parser.parse_borg_config("/test/repo")

            assert result["mode"] == "encrypted"  # fallback to encrypted
            assert (
                "Security directory error: Cannot read directory" in result["preview"]
            )

    @pytest.mark.asyncio
    async def test_start_repository_scan_default_path(self, repository_parser) -> None:
        """Test starting repository scan with default path."""
        # Set up mock job manager
        mock_job_manager = Mock()
        mock_job_manager.start_borg_command = AsyncMock(return_value="job-123")
        repository_parser.job_manager = mock_job_manager

        job_id = await repository_parser.start_repository_scan()

        assert job_id == "job-123"
        mock_job_manager.start_borg_command.assert_called_once()
        # Verify the command includes the default scan path
        call_args = mock_job_manager.start_borg_command.call_args[0][0]
        assert "/mnt" in call_args

    @pytest.mark.asyncio
    async def test_start_repository_scan_custom_path(self, repository_parser) -> None:
        """Test starting repository scan with custom path."""
        # Set up mock job manager
        mock_job_manager = Mock()
        mock_job_manager.start_borg_command = AsyncMock(return_value="job-456")
        repository_parser.job_manager = mock_job_manager

        job_id = await repository_parser.start_repository_scan("/custom/path")

        assert job_id == "job-456"
        mock_job_manager.start_borg_command.assert_called_once()
        call_args = mock_job_manager.start_borg_command.call_args[0][0]
        assert "/custom/path" in call_args

    @pytest.mark.asyncio
    async def test_check_scan_status_job_not_found(self, repository_parser) -> None:
        """Test checking status of non-existent job."""
        mock_job_manager = Mock()
        mock_job_manager.get_job_status.return_value = None
        repository_parser.job_manager = mock_job_manager

        result = await repository_parser.check_scan_status("non-existent-job")

        assert result["exists"] is False
        assert result["completed"] is False
        assert result["status"] == "not_found"
        assert result["error"] == "Job not found"

    @pytest.mark.asyncio
    async def test_check_scan_status_job_running(self, repository_parser) -> None:
        """Test checking status of running job."""
        mock_job_manager = Mock()
        mock_job_manager.get_job_status.return_value = {
            "completed": False,
            "status": "running",
            "output": "Scanning directories...",
            "error": None,
        }
        repository_parser.job_manager = mock_job_manager

        result = await repository_parser.check_scan_status("running-job")

        assert result["exists"] is True
        assert result["completed"] is False
        assert result["status"] == "running"
        assert result["output"] == "Scanning directories..."
        assert result["error"] is None

    @pytest.mark.asyncio
    async def test_check_scan_status_job_completed(self, repository_parser) -> None:
        """Test checking status of completed job."""
        mock_job_manager = Mock()
        mock_job_manager.get_job_status.return_value = {
            "completed": True,
            "status": "completed",
            "output": "/path/repo1\n/path/repo2\n",
            "error": None,
        }
        repository_parser.job_manager = mock_job_manager

        result = await repository_parser.check_scan_status("completed-job")

        assert result["exists"] is True
        assert result["completed"] is True
        assert result["status"] == "completed"
        assert "/path/repo1" in result["output"]

    @pytest.mark.asyncio
    async def test_check_scan_status_job_with_error(self, repository_parser) -> None:
        """Test checking status of job with error."""
        mock_job_manager = Mock()
        mock_job_manager.get_job_status.return_value = {
            "completed": True,
            "status": "failed",
            "output": "Some output before error",
            "error": "Permission denied",
        }
        repository_parser.job_manager = mock_job_manager

        result = await repository_parser.check_scan_status("failed-job")

        assert result["exists"] is True
        assert result["completed"] is True
        assert result["status"] == "failed"
        assert result["error"] == "Permission denied"

    @pytest.mark.asyncio
    async def test_check_scan_status_no_job_manager(self, repository_parser) -> None:
        """Test checking status without job manager."""
        repository_parser.job_manager = None

        result = await repository_parser.check_scan_status("any-job")

        assert result["exists"] is False
        assert result["completed"] is False
        assert result["status"] == "error"
        assert "JobManager not provided" in result["error"]

    @pytest.mark.asyncio
    async def test_check_scan_status_job_manager_error(self, repository_parser) -> None:
        """Test handling job manager errors during status check."""
        mock_job_manager = Mock()
        mock_job_manager.get_job_status.side_effect = Exception("Job manager error")
        repository_parser.job_manager = mock_job_manager

        result = await repository_parser.check_scan_status("any-job")

        assert result["exists"] is False
        assert result["completed"] is False
        assert result["status"] == "error"
        assert "Job manager error" in result["error"]

    @pytest.mark.asyncio
    async def test_get_scan_results_job_not_completed(self, repository_parser) -> None:
        """Test getting results from incomplete job."""
        mock_job_manager = Mock()
        mock_job_manager.get_job_status.return_value = {
            "completed": False,
            "status": "running",
        }
        repository_parser.job_manager = mock_job_manager

        result = await repository_parser.get_scan_results("running-job")

        assert result == []

    @pytest.mark.asyncio
    async def test_get_scan_results_job_completed_no_output(
        self, repository_parser
    ) -> None:
        """Test getting results from completed job with no output."""
        mock_job_manager = Mock()
        mock_job_manager.get_job_status.return_value = {
            "completed": True,
            "status": "completed",
            "output": "",
            "error": None,
        }
        repository_parser.job_manager = mock_job_manager

        result = await repository_parser.get_scan_results("completed-job")

        assert result == []

    @pytest.mark.asyncio
    async def test_get_scan_results_job_completed_with_repositories(
        self, repository_parser
    ) -> None:
        """Test getting results from completed job with repository output."""
        scan_output = "/path/to/repo1\n/path/to/repo2\n/path/to/repo3"

        mock_job_manager = Mock()
        mock_job_manager.get_job_status.return_value = {
            "completed": True,
            "status": "completed",
            "output": scan_output,
            "error": None,
        }
        repository_parser.job_manager = mock_job_manager

        # Mock the parse_borg_config method to return valid repository info
        with patch.object(repository_parser, "parse_borg_config") as mock_parse, patch(
            "os.path.exists", return_value=True
        ), patch("os.path.basename", side_effect=lambda x: x.split("/")[-1]):
            mock_parse.return_value = {
                "mode": "encrypted",
                "requires_keyfile": False,
                "preview": "Encrypted repository",
            }

            result = await repository_parser.get_scan_results("completed-job")

            assert len(result) == 3
            assert result[0]["path"] == "/path/to/repo1"
            assert result[0]["name"] == "repo1"
            assert result[0]["encryption_mode"] == "encrypted"
            assert result[0]["requires_keyfile"] is False

    @pytest.mark.asyncio
    async def test_get_scan_results_job_with_error(self, repository_parser) -> None:
        """Test getting results from job that had errors."""
        mock_job_manager = Mock()
        mock_job_manager.get_job_status.return_value = {
            "completed": True,
            "status": "completed",
            "output": "/path/to/repo1",
            "error": "Some scan error occurred",
        }
        repository_parser.job_manager = mock_job_manager

        with patch.object(repository_parser, "parse_borg_config") as mock_parse, patch(
            "os.path.exists", return_value=True
        ), patch("os.path.basename", return_value="repo1"):
            mock_parse.return_value = {
                "mode": "encrypted",
                "requires_keyfile": False,
                "preview": "Encrypted repository",
            }

            result = await repository_parser.get_scan_results("job-with-error")

            assert len(result) == 1

    @pytest.mark.asyncio
    async def test_get_scan_results_no_job_manager(self, repository_parser) -> None:
        """Test getting results without job manager."""
        repository_parser.job_manager = None

        result = await repository_parser.get_scan_results("any-job")

        assert result == []

    @pytest.mark.asyncio
    async def test_parse_scan_output_empty(self, repository_parser) -> None:
        """Test parsing empty scan output."""
        result = await repository_parser._parse_scan_output("")

        assert result == []

    @pytest.mark.asyncio
    async def test_parse_scan_output_invalid_paths(self, repository_parser) -> None:
        """Test parsing scan output with invalid paths."""
        scan_output = "/nonexistent/path1\n\n/nonexistent/path2"

        with patch("os.path.exists", return_value=False):
            result = await repository_parser._parse_scan_output(scan_output)

        assert result == []

    @pytest.mark.asyncio
    async def test_parse_scan_output_invalid_repositories(
        self, repository_parser
    ) -> None:
        """Test parsing scan output where paths exist but aren't valid Borg repos."""
        scan_output = "/path/to/invalid1\n/path/to/invalid2"

        with patch("os.path.exists", return_value=True), patch.object(
            repository_parser, "parse_borg_config"
        ) as mock_parse:
            mock_parse.return_value = {
                "mode": "invalid",
                "requires_keyfile": False,
                "preview": "Not a Borg repository",
            }

            result = await repository_parser._parse_scan_output(scan_output)

        assert result == []

    @pytest.mark.asyncio
    async def test_parse_scan_output_with_metadata(self, repository_parser) -> None:
        """Test parsing scan output with metadata collection."""
        scan_output = "/path/to/repo1\n/path/to/repo2"

        with patch("os.path.exists", return_value=True), patch(
            "os.path.basename", side_effect=lambda x: x.split("/")[-1]
        ), patch.object(
            repository_parser, "parse_borg_config"
        ) as mock_parse, patch.object(
            repository_parser, "_get_repository_metadata"
        ) as mock_metadata:
            mock_parse.return_value = {
                "mode": "encrypted",
                "requires_keyfile": False,
                "preview": "Encrypted repository",
            }

            mock_metadata.return_value = {
                "size": "1.5G",
                "last_backup": "2023-01-01T00:00:00Z",
            }

            result = await repository_parser._parse_scan_output(scan_output)

            assert len(result) == 2
            assert result[0]["size"] == "1.5G"
            assert result[0]["last_backup"] == "2023-01-01T00:00:00Z"

    @pytest.mark.asyncio
    async def test_parse_scan_output_metadata_error(self, repository_parser) -> None:
        """Test parsing scan output when metadata collection fails."""
        scan_output = "/path/to/repo1"

        with patch("os.path.exists", return_value=True), patch(
            "os.path.basename", return_value="repo1"
        ), patch.object(
            repository_parser, "parse_borg_config"
        ) as mock_parse, patch.object(
            repository_parser, "_get_repository_metadata"
        ) as mock_metadata:
            mock_parse.return_value = {
                "mode": "encrypted",
                "requires_keyfile": False,
                "preview": "Encrypted repository",
            }

            mock_metadata.side_effect = Exception("Metadata error")

            result = await repository_parser._parse_scan_output(scan_output)

            assert len(result) == 1
            assert "Metadata unavailable: Metadata error" in result[0]["preview"]

    @pytest.mark.asyncio
    async def test_parse_scan_output_unnamed_repository(
        self, repository_parser
    ) -> None:
        """Test parsing scan output with repository that has no name."""
        scan_output = "/"  # Root path edge case

        with patch("os.path.exists", return_value=True), patch(
            "os.path.basename", return_value=""
        ), patch.object(repository_parser, "parse_borg_config") as mock_parse:
            mock_parse.return_value = {
                "mode": "encrypted",
                "requires_keyfile": False,
                "preview": "Encrypted repository",
            }

            result = await repository_parser._parse_scan_output(scan_output)

            assert len(result) == 1
            assert result[0]["name"] == "unnamed_repository"


class TestRepositoryParserMetadata:
    """Test metadata collection functionality."""

    @pytest.mark.asyncio
    async def test_get_repository_metadata_size_success(
        self, repository_parser
    ) -> None:
        """Test successful size collection."""
        mock_result = Mock()
        mock_result.return_code = 0
        mock_result.stdout = "1.5G\t/path/to/repo"

        repository_parser.command_runner.run_command = AsyncMock(
            return_value=mock_result
        )

        with patch("os.path.exists", return_value=True):
            metadata = await repository_parser._get_repository_metadata("/path/to/repo")

        assert metadata["size"] == "1.5G"
        repository_parser.command_runner.run_command.assert_called_once_with(
            ["du", "-sh", "/path/to/repo"], timeout=10
        )

    @pytest.mark.asyncio
    async def test_get_repository_metadata_size_command_failure(
        self, repository_parser
    ) -> None:
        """Test size collection when du command fails."""
        mock_result = Mock()
        mock_result.returncode = 1
        mock_result.stdout = ""

        repository_parser.command_runner.run_command = AsyncMock(
            return_value=mock_result
        )

        with patch("os.path.exists", return_value=True):
            metadata = await repository_parser._get_repository_metadata("/path/to/repo")

        assert "size" not in metadata

    @pytest.mark.asyncio
    async def test_get_repository_metadata_size_exception(
        self, repository_parser
    ) -> None:
        """Test size collection when du command raises exception."""
        repository_parser.command_runner.run_command = AsyncMock(
            side_effect=Exception("Command failed")
        )

        with patch("os.path.exists", return_value=True):
            metadata = await repository_parser._get_repository_metadata("/path/to/repo")

        assert "size" not in metadata

    @pytest.mark.asyncio
    async def test_get_repository_metadata_last_backup_success(
        self, repository_parser
    ) -> None:
        """Test successful last backup time collection."""
        test_time = 1640995200.0  # 2022-01-01 00:00:00 UTC

        repository_parser.command_runner.run_command = AsyncMock(
            side_effect=Exception("No du")
        )

        with patch("os.path.exists", return_value=True), patch(
            "os.walk"
        ) as mock_walk, patch("os.path.getmtime", return_value=test_time):
            # Mock os.walk to return some files
            mock_walk.return_value = [
                ("/path/to/repo/data", [], ["file1", "file2"]),
                ("/path/to/repo/data/subdir", [], ["file3"]),
            ]

            metadata = await repository_parser._get_repository_metadata("/path/to/repo")

        assert "last_backup" in metadata
        # Should be ISO format timestamp
        assert metadata["last_backup"] == "2022-01-01T00:00:00+00:00"

    @pytest.mark.asyncio
    async def test_get_repository_metadata_last_backup_no_data_dir(
        self, repository_parser
    ) -> None:
        """Test last backup time when data directory doesn't exist."""
        repository_parser.command_runner.run_command = AsyncMock(
            side_effect=Exception("No du")
        )

        with patch("os.path.exists") as mock_exists:

            def exists_side_effect(path):
                return not path.endswith("/data")  # data dir doesn't exist

            mock_exists.side_effect = exists_side_effect

            metadata = await repository_parser._get_repository_metadata("/path/to/repo")

        assert "last_backup" not in metadata

    @pytest.mark.asyncio
    async def test_get_repository_metadata_last_backup_empty_data_dir(
        self, repository_parser
    ) -> None:
        """Test last backup time when data directory is empty."""
        repository_parser.command_runner.run_command = AsyncMock(
            side_effect=Exception("No du")
        )

        with patch("os.path.exists", return_value=True), patch(
            "os.walk", return_value=[]
        ):
            metadata = await repository_parser._get_repository_metadata("/path/to/repo")

        assert "last_backup" not in metadata

    @pytest.mark.asyncio
    async def test_get_repository_metadata_last_backup_file_access_error(
        self, repository_parser
    ) -> None:
        """Test last backup time when file access fails."""
        repository_parser.command_runner.run_command = AsyncMock(
            side_effect=Exception("No du")
        )

        with patch("os.path.exists", return_value=True), patch(
            "os.walk"
        ) as mock_walk, patch(
            "os.path.getmtime", side_effect=OSError("Permission denied")
        ):
            mock_walk.return_value = [("/path/to/repo/data", [], ["file1"])]

            metadata = await repository_parser._get_repository_metadata("/path/to/repo")

        # Should handle the error gracefully
        assert "last_backup" not in metadata

    @pytest.mark.asyncio
    async def test_get_repository_metadata_last_backup_walk_exception(
        self, repository_parser
    ) -> None:
        """Test last backup time when os.walk raises exception."""
        repository_parser.command_runner.run_command = AsyncMock(
            side_effect=Exception("No du")
        )

        with patch("os.path.exists", return_value=True), patch(
            "os.walk", side_effect=OSError("Cannot walk directory")
        ):
            metadata = await repository_parser._get_repository_metadata("/path/to/repo")

        assert "last_backup" not in metadata

    @pytest.mark.asyncio
    async def test_get_repository_metadata_multiple_files_latest(
        self, repository_parser
    ) -> None:
        """Test last backup time with multiple files, should get latest."""
        old_time = 1640995200.0  # 2022-01-01
        new_time = 1672531200.0  # 2023-01-01

        repository_parser.command_runner.run_command = AsyncMock(
            side_effect=Exception("No du")
        )

        with patch("os.path.exists", return_value=True), patch(
            "os.walk"
        ) as mock_walk, patch("os.path.getmtime") as mock_getmtime:
            mock_walk.return_value = [
                ("/path/to/repo/data", [], ["old_file", "new_file"])
            ]

            def getmtime_side_effect(path):
                if "old_file" in path:
                    return old_time
                elif "new_file" in path:
                    return new_time
                return old_time

            mock_getmtime.side_effect = getmtime_side_effect

            metadata = await repository_parser._get_repository_metadata("/path/to/repo")

        assert "last_backup" in metadata
        # Should be the newer timestamp
        assert metadata["last_backup"] == "2023-01-01T00:00:00+00:00"

    @pytest.mark.asyncio
    async def test_get_repository_metadata_repo_not_exist(
        self, repository_parser
    ) -> None:
        """Test metadata collection when repository path doesn't exist."""
        repository_parser.command_runner.run_command = AsyncMock(
            side_effect=Exception("No du")
        )

        with patch("os.path.exists", return_value=False):
            metadata = await repository_parser._get_repository_metadata(
                "/nonexistent/repo"
            )

        assert metadata == {}


class TestRepositoryParserVerification:
    """Test repository access verification functionality."""

    @pytest.mark.asyncio
    async def test_verify_repository_access_success(
        self, repository_parser, test_repository
    ) -> None:
        """Test successful repository access verification."""
        mock_job_manager = Mock()
        mock_job_manager.start_borg_command = AsyncMock(return_value="verify-job-123")

        # Mock successful verification
        def get_status_side_effect(job_id):
            return {
                "completed": True,
                "status": "completed",
                "output": '{"repository": {"id": "abc123"}}',
                "error": None,
            }

        mock_job_manager.get_job_status = Mock(side_effect=get_status_side_effect)
        repository_parser.job_manager = mock_job_manager

        with patch(
            "borgitory.services.repositories.repository_parser.build_secure_borg_command"
        ) as mock_build_cmd:
            mock_build_cmd.return_value = (
                ["borg", "info", "/repo", "--json"],
                {"BORG_PASSPHRASE": "test"},
            )

            result = await repository_parser.verify_repository_access(test_repository)

        assert result["accessible"] is True
        assert result["error"] is None
        assert result["requires_passphrase"] is False
        assert "repository_info" in result

    @pytest.mark.asyncio
    async def test_verify_repository_access_with_custom_passphrase(
        self, repository_parser, test_repository
    ) -> None:
        """Test repository verification with custom passphrase."""
        mock_job_manager = Mock()
        mock_job_manager.start_borg_command = AsyncMock(return_value="verify-job-123")
        mock_job_manager.get_job_status = Mock(
            return_value={
                "completed": True,
                "status": "completed",
                "output": "{}",
                "error": None,
            }
        )
        repository_parser.job_manager = mock_job_manager

        with patch(
            "borgitory.services.repositories.repository_parser.build_secure_borg_command"
        ) as mock_build_cmd:
            mock_build_cmd.return_value = (
                ["borg", "info", "/repo", "--json"],
                {"BORG_PASSPHRASE": "custom"},
            )

            result = await repository_parser.verify_repository_access(
                test_repository, "custom_passphrase"
            )

        assert result["accessible"] is True
        mock_build_cmd.assert_called_once()
        # Should use custom passphrase, not repository's passphrase
        assert mock_build_cmd.call_args[1]["passphrase"] == "custom_passphrase"

    @pytest.mark.asyncio
    async def test_verify_repository_access_wrong_passphrase(
        self, repository_parser, test_repository
    ) -> None:
        """Test repository verification with wrong passphrase."""
        mock_job_manager = Mock()
        mock_job_manager.start_borg_command = AsyncMock(return_value="verify-job-123")
        mock_job_manager.get_job_status = Mock(
            return_value={
                "completed": True,
                "status": "failed",
                "output": "",
                "error": "PassphraseWrong: passphrase supplied in BORG_PASSPHRASE is wrong",
            }
        )
        repository_parser.job_manager = mock_job_manager

        with patch(
            "borgitory.utils.security.build_secure_borg_command"
        ) as mock_build_cmd:
            mock_build_cmd.return_value = (
                ["borg", "info", "/repo", "--json"],
                {"BORG_PASSPHRASE": "wrong"},
            )

            result = await repository_parser.verify_repository_access(
                test_repository, "wrong_passphrase"
            )

            assert result["accessible"] is False
            assert result["error"] == "Incorrect passphrase"
        assert result["requires_passphrase"] is True

    @pytest.mark.asyncio
    async def test_verify_repository_access_repo_not_exist(
        self, repository_parser, test_repository
    ) -> None:
        """Test repository verification when repository doesn't exist."""
        mock_job_manager = Mock()
        mock_job_manager.start_borg_command = AsyncMock(return_value="verify-job-123")
        mock_job_manager.get_job_status = Mock(
            return_value={
                "completed": True,
                "status": "failed",
                "output": "",
                "error": "Repository /path/to/repo does not exist",
            }
        )
        repository_parser.job_manager = mock_job_manager

        with patch(
            "borgitory.services.repositories.repository_parser.build_secure_borg_command"
        ) as mock_build_cmd:
            mock_build_cmd.return_value = (
                ["borg", "info", "/repo", "--json"],
                {"BORG_PASSPHRASE": "test"},
            )

            result = await repository_parser.verify_repository_access(test_repository)

        assert result["accessible"] is False
        assert "does not exist" in result["error"]
        assert result["requires_passphrase"] is False

    @pytest.mark.asyncio
    async def test_verify_repository_access_general_error(
        self, repository_parser, test_repository
    ) -> None:
        """Test repository verification with general error."""
        mock_job_manager = Mock()
        mock_job_manager.start_borg_command = AsyncMock(return_value="verify-job-123")
        mock_job_manager.get_job_status = Mock(
            return_value={
                "completed": True,
                "status": "failed",
                "output": "",
                "error": "Some other borg error occurred",
            }
        )
        repository_parser.job_manager = mock_job_manager

        with patch(
            "borgitory.services.repositories.repository_parser.build_secure_borg_command"
        ) as mock_build_cmd:
            mock_build_cmd.return_value = (
                ["borg", "info", "/repo", "--json"],
                {"BORG_PASSPHRASE": "test"},
            )

            result = await repository_parser.verify_repository_access(test_repository)

        assert result["accessible"] is False
        assert (
            "Repository access failed: Some other borg error occurred"
            in result["error"]
        )
        assert result["requires_passphrase"] is True

    @pytest.mark.asyncio
    async def test_verify_repository_access_job_not_found(
        self, repository_parser, test_repository
    ) -> None:
        """Test repository verification when job is not found."""
        mock_job_manager = Mock()
        mock_job_manager.start_borg_command = AsyncMock(return_value="verify-job-123")
        mock_job_manager.get_job_status = Mock(return_value=None)  # Job not found
        repository_parser.job_manager = mock_job_manager

        with patch(
            "borgitory.services.repositories.repository_parser.build_secure_borg_command"
        ) as mock_build_cmd:
            mock_build_cmd.return_value = (
                ["borg", "info", "/repo", "--json"],
                {"BORG_PASSPHRASE": "test"},
            )

            result = await repository_parser.verify_repository_access(test_repository)

        assert result["accessible"] is False
        assert result["error"] == "Verification job not found"
        assert result["requires_passphrase"] is True

    @pytest.mark.asyncio
    async def test_verify_repository_access_timeout(
        self, repository_parser, test_repository
    ) -> None:
        """Test repository verification timeout."""
        mock_job_manager = Mock()
        mock_job_manager.start_borg_command = AsyncMock(return_value="verify-job-123")
        # Job never completes
        mock_job_manager.get_job_status = Mock(
            return_value={
                "completed": False,
                "status": "running",
                "output": "",
                "error": None,
            }
        )
        repository_parser.job_manager = mock_job_manager

        with patch(
            "borgitory.utils.security.build_secure_borg_command"
        ) as mock_build_cmd, patch(
            "asyncio.sleep", new_callable=AsyncMock
        ):  # Speed up the test
            mock_build_cmd.return_value = (
                ["borg", "info", "/repo", "--json"],
                {"BORG_PASSPHRASE": "test"},
            )

            result = await repository_parser.verify_repository_access(
                test_repository, "valid_passphrase"
            )

        assert result["accessible"] is False
        assert "timed out" in result["error"]
        assert result["requires_passphrase"] is True

    @pytest.mark.asyncio
    async def test_verify_repository_access_no_job_manager(
        self, repository_parser, test_repository
    ) -> None:
        """Test repository verification without job manager."""
        repository_parser.job_manager = None

        with patch(
            "borgitory.services.repositories.repository_parser.build_secure_borg_command"
        ) as mock_build_cmd:
            mock_build_cmd.return_value = (
                ["borg", "info", "/repo", "--json"],
                {"BORG_PASSPHRASE": "test"},
            )

            result = await repository_parser.verify_repository_access(test_repository)

        assert result["accessible"] is False
        assert "JobManager not provided" in result["error"]
        assert result["requires_passphrase"] is True

    @pytest.mark.asyncio
    async def test_verify_repository_access_security_validation_error(
        self, repository_parser, test_repository
    ) -> None:
        """Test repository verification when security validation fails."""
        with patch(
            "borgitory.services.repositories.repository_parser.build_secure_borg_command"
        ) as mock_build_cmd:
            mock_build_cmd.side_effect = Exception("Security validation failed")

            result = await repository_parser.verify_repository_access(test_repository)

        assert result["accessible"] is False
        assert "Security validation failed" in result["error"]
        assert result["requires_passphrase"] is True

    @pytest.mark.asyncio
    async def test_verify_repository_access_job_start_error(
        self, repository_parser, test_repository
    ) -> None:
        """Test repository verification when job start fails."""
        mock_job_manager = Mock()
        mock_job_manager.start_borg_command = AsyncMock(
            side_effect=Exception("Failed to start job")
        )
        repository_parser.job_manager = mock_job_manager

        with patch(
            "borgitory.services.repositories.repository_parser.build_secure_borg_command"
        ) as mock_build_cmd:
            mock_build_cmd.return_value = (
                ["borg", "info", "/repo", "--json"],
                {"BORG_PASSPHRASE": "test"},
            )

            result = await repository_parser.verify_repository_access(test_repository)

        assert result["accessible"] is False
        assert "Verification error: Failed to start job" in result["error"]
        assert result["requires_passphrase"] is True

    @pytest.mark.asyncio
    async def test_verify_repository_access_invalid_json_output(
        self, repository_parser, test_repository
    ) -> None:
        """Test repository verification with invalid JSON output."""
        mock_job_manager = Mock()
        mock_job_manager.start_borg_command = AsyncMock(return_value="verify-job-123")
        mock_job_manager.get_job_status = Mock(
            return_value={
                "completed": True,
                "status": "completed",
                "output": "Not valid JSON output",
                "error": None,
            }
        )
        repository_parser.job_manager = mock_job_manager

        with patch(
            "borgitory.services.repositories.repository_parser.build_secure_borg_command"
        ) as mock_build_cmd:
            mock_build_cmd.return_value = (
                ["borg", "info", "/repo", "--json"],
                {"BORG_PASSPHRASE": "test"},
            )

            result = await repository_parser.verify_repository_access(test_repository)

        # Should still be successful even if JSON parsing fails
        assert result["accessible"] is True
        assert result["error"] is None
        assert result["repository_info"] == {}  # Empty dict when JSON parsing fails


class TestRepositoryParserLegacyScan:
    """Test legacy scan_for_repositories method."""

    @pytest.mark.asyncio
    async def test_scan_for_repositories_success(self, repository_parser) -> None:
        """Test successful legacy repository scan."""
        scan_output = "/path/to/repo1\n/path/to/repo2"

        mock_job_manager = Mock()
        mock_job_manager.start_borg_command = AsyncMock(return_value="scan-job-123")
        repository_parser.job_manager = mock_job_manager

        # Mock the status check to complete quickly
        status_calls = [
            {"completed": False, "status": "running", "output": "", "error": None},
            {
                "completed": True,
                "status": "completed",
                "output": scan_output,
                "error": None,
            },
        ]
        mock_job_manager.get_job_status = Mock(side_effect=status_calls)

        # Mock the check_scan_status and get_scan_results methods to avoid the async issue
        with patch.object(
            repository_parser, "check_scan_status"
        ) as mock_check_status, patch.object(
            repository_parser, "get_scan_results"
        ) as mock_get_results, patch(
            "asyncio.sleep", new_callable=AsyncMock
        ):  # Speed up the test
            mock_check_status.side_effect = [
                {"completed": False, "status": "running"},
                {"completed": True, "status": "completed"},
            ]

            mock_get_results.return_value = [
                {
                    "path": "/path/to/repo1",
                    "name": "repo1",
                    "encryption_mode": "encrypted",
                },
                {
                    "path": "/path/to/repo2",
                    "name": "repo2",
                    "encryption_mode": "encrypted",
                },
            ]

            result = await repository_parser.scan_for_repositories("/test/path")

        assert len(result) == 2
        assert result[0]["path"] == "/path/to/repo1"
        assert result[1]["path"] == "/path/to/repo2"

    @pytest.mark.asyncio
    async def test_scan_for_repositories_timeout(self, repository_parser) -> None:
        """Test legacy scan timeout."""
        mock_job_manager = Mock()
        mock_job_manager.start_borg_command = AsyncMock(return_value="scan-job-123")
        # Job never completes
        mock_job_manager.get_job_status = Mock(
            return_value={
                "completed": False,
                "status": "running",
                "output": "Partial output",
                "error": None,
            }
        )
        repository_parser.job_manager = mock_job_manager

        with patch("asyncio.sleep", new_callable=AsyncMock):  # Speed up the test
            with pytest.raises(Exception, match="Repository scan timed out"):
                await repository_parser.scan_for_repositories("/test/path")

    @pytest.mark.asyncio
    async def test_scan_for_repositories_with_error(self, repository_parser) -> None:
        """Test legacy scan with job error."""
        mock_job_manager = Mock()
        mock_job_manager.start_borg_command = AsyncMock(return_value="scan-job-123")
        mock_job_manager.get_job_status = Mock(
            return_value={
                "completed": False,
                "status": "failed",
                "output": "Some output",
                "error": "Scan failed with error",
            }
        )
        repository_parser.job_manager = mock_job_manager

        with patch("asyncio.sleep", new_callable=AsyncMock):
            with pytest.raises(Exception, match="Repository scan timed out"):
                await repository_parser.scan_for_repositories("/test/path")

    @pytest.mark.asyncio
    async def test_scan_for_repositories_default_path(self, repository_parser) -> None:
        """Test legacy scan with default path."""
        mock_job_manager = Mock()
        mock_job_manager.start_borg_command = AsyncMock(return_value="scan-job-123")
        mock_job_manager.get_job_status = Mock(
            return_value={
                "completed": True,
                "status": "completed",
                "output": "",
                "error": None,
            }
        )
        repository_parser.job_manager = mock_job_manager

        with patch("asyncio.sleep", new_callable=AsyncMock):
            await repository_parser.scan_for_repositories()

        # Should use default path /mnt
        call_args = mock_job_manager.start_borg_command.call_args[0][0]
        assert "/mnt" in call_args


class TestRepositoryParserErrorHandling:
    """Test error handling in RepositoryParser."""

    @pytest.mark.asyncio
    async def test_start_repository_scan_no_job_manager(
        self, repository_parser
    ) -> None:
        """Test scan start without job manager."""
        repository_parser.job_manager = None

        with pytest.raises(RuntimeError, match="JobManager not provided"):
            await repository_parser.start_repository_scan()

    @pytest.mark.asyncio
    async def test_start_repository_scan_job_manager_error(
        self, repository_parser
    ) -> None:
        """Test handling job manager errors during scan start."""
        mock_job_manager = Mock()
        mock_job_manager.start_borg_command = AsyncMock(
            side_effect=Exception("Job manager error")
        )
        repository_parser.job_manager = mock_job_manager

        with pytest.raises(Exception, match="Job manager error"):
            await repository_parser.start_repository_scan()

    @pytest.mark.asyncio
    async def test_get_scan_results_job_manager_error(self, repository_parser) -> None:
        """Test handling job manager errors during results retrieval."""
        mock_job_manager = Mock()
        mock_job_manager.get_job_status.side_effect = Exception("Job manager error")
        repository_parser.job_manager = mock_job_manager

        result = await repository_parser.get_scan_results("any-job")

        assert result == []

    def test_constructor_with_no_dependencies(self) -> None:
        """Test RepositoryParser constructor with default dependencies."""
        parser = RepositoryParser()

        assert parser.command_runner is not None
        assert parser.job_manager is None  # Should be None by default

    def test_constructor_with_custom_dependencies(self, mock_command_runner) -> None:
        """Test RepositoryParser constructor with custom dependencies."""
        mock_job_manager = Mock()

        parser = RepositoryParser(
            command_runner=mock_command_runner, job_manager=mock_job_manager
        )

        assert parser.command_runner == mock_command_runner
        assert parser.job_manager == mock_job_manager
