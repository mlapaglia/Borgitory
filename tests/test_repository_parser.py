"""
Tests for RepositoryParser - Handles Borg repository discovery and parsing
"""

import pytest
import os
from unittest.mock import Mock, AsyncMock, patch, mock_open
from types import SimpleNamespace

from app.services.repositories.repository_parser import RepositoryParser
from app.models.database import Repository
from app.services.simple_command_runner import SimpleCommandRunner


@pytest.fixture
def mock_command_runner():
    """Mock SimpleCommandRunner."""
    mock = Mock(spec=SimpleCommandRunner)
    mock.run_command = AsyncMock()
    return mock


@pytest.fixture
def repository_parser(mock_command_runner):
    """RepositoryParser instance with mocked dependencies."""
    return RepositoryParser(command_runner=mock_command_runner)


@pytest.fixture
def test_repository():
    """Test repository object."""
    repo = Repository(id=1, name="test-repo", path="/tmp/test-repo")
    repo.set_passphrase("test-passphrase")
    return repo


class TestRepositoryParser:
    """Test class for RepositoryParser."""

    def test_init_with_dependencies(self):
        """Test RepositoryParser initialization with provided dependencies."""
        mock_runner = Mock(spec=SimpleCommandRunner)
        parser = RepositoryParser(command_runner=mock_runner)

        assert parser.command_runner is mock_runner

    def test_init_with_defaults(self):
        """Test RepositoryParser initialization with default dependencies."""
        parser = RepositoryParser()

        assert isinstance(parser.command_runner, SimpleCommandRunner)

    @patch("os.path.exists")
    @patch("os.listdir")
    def test_parse_borg_config_valid_encrypted(
        self, mock_listdir, mock_exists, repository_parser
    ):
        """Test parsing a valid encrypted Borg repository config."""

        # Setup file system mocks - normalize paths for Windows compatibility
        def mock_exists_side_effect(path):
            normalized = os.path.normpath(path)
            return {
                os.path.normpath("/tmp/test-repo/config"): True,
                os.path.normpath("/tmp/test-repo/security"): True,
                os.path.normpath("/tmp/test-repo/key-type"): True,
            }.get(normalized, False)

        mock_exists.side_effect = mock_exists_side_effect

        # Mock listdir for security directory
        mock_listdir.return_value = ["manifest", "nonce"]

        # Mock file contents for different files
        def mock_open_side_effect(*args, **kwargs):
            filename = os.path.normpath(args[0])
            if filename.endswith("config"):
                return mock_open(
                    read_data="[repository]\nversion = 1\nsegments_per_dir = 1000\n"
                )()
            elif filename.endswith("key-type"):
                return mock_open(read_data="blake2-chacha20-poly1305")()
            else:
                raise FileNotFoundError(f"No mock for {filename}")

        with patch("builtins.open", side_effect=mock_open_side_effect):
            result = repository_parser.parse_borg_config("/tmp/test-repo")

        assert result["mode"] == "encrypted"
        assert result["requires_keyfile"] is False
        assert "Key type: blake2-chacha20-poly1305" in result["preview"]

    @patch("os.path.exists")
    def test_parse_borg_config_with_key_type(self, mock_exists, repository_parser):
        """Test parsing config with key-type file."""

        # Setup file system mocks - normalize paths for Windows compatibility
        def mock_exists_side_effect(path):
            normalized = os.path.normpath(path)
            return {
                os.path.normpath("/tmp/test-repo/config"): True,
                os.path.normpath("/tmp/test-repo/key-type"): True,
            }.get(normalized, False)

        mock_exists.side_effect = mock_exists_side_effect

        # Mock file contents for different files
        def mock_open_side_effect(*args, **kwargs):
            filename = os.path.normpath(args[0])
            if filename.endswith("config"):
                return mock_open(read_data="[repository]\nversion = 1\n")()
            elif filename.endswith("key-type"):
                return mock_open(read_data="blake2-chacha20-poly1305")()
            else:
                raise FileNotFoundError(f"No mock for {filename}")

        with patch("builtins.open", side_effect=mock_open_side_effect):
            result = repository_parser.parse_borg_config("/tmp/test-repo")

        assert result["mode"] == "encrypted"
        assert result["requires_keyfile"] is False
        assert "Key type: blake2-chacha20-poly1305" in result["preview"]

    @patch("os.path.exists")
    def test_parse_borg_config_keyfile_mode(self, mock_exists, repository_parser):
        """Test parsing config for key file mode encryption."""

        # Setup file system mocks - normalize paths for Windows compatibility
        def mock_exists_side_effect(path):
            normalized = os.path.normpath(path)
            return {
                os.path.normpath("/tmp/test-repo/config"): True,
                os.path.normpath("/tmp/test-repo/key-type"): True,
            }.get(normalized, False)

        mock_exists.side_effect = mock_exists_side_effect

        # Mock file contents for different files
        def mock_open_side_effect(*args, **kwargs):
            filename = os.path.normpath(args[0])
            if filename.endswith("config"):
                return mock_open(read_data="[repository]\nversion = 1\n")()
            elif filename.endswith("key-type"):
                return mock_open(read_data="blake2-aes256-ctr-hmac-sha256")()
            else:
                raise FileNotFoundError(f"No mock for {filename}")

        with patch("builtins.open", side_effect=mock_open_side_effect):
            result = repository_parser.parse_borg_config("/tmp/test-repo")

        assert result["mode"] == "encrypted"
        assert result["requires_keyfile"] is True

    @patch("os.path.exists")
    def test_parse_borg_config_no_config_file(self, mock_exists, repository_parser):
        """Test parsing when config file doesn't exist."""
        mock_exists.return_value = False

        result = repository_parser.parse_borg_config("/tmp/nonexistent")

        assert result["mode"] == "unknown"
        assert result["requires_keyfile"] is False
        assert "Config file not found" in result["preview"]

    @patch("os.path.exists")
    @patch("builtins.open")
    def test_parse_borg_config_invalid_config(
        self, mock_open_func, mock_exists, repository_parser
    ):
        """Test parsing invalid config file."""
        mock_exists.return_value = True
        mock_open_func.return_value.__enter__.return_value.read.return_value = (
            "[invalid]\nnotrepo = true\n"
        )

        result = repository_parser.parse_borg_config("/tmp/test-repo")

        assert result["mode"] == "invalid"
        assert "Not a valid Borg repository" in result["preview"]

    @patch("os.path.exists")
    @patch("builtins.open")
    def test_parse_borg_config_exception_handling(
        self, mock_open_func, mock_exists, repository_parser
    ):
        """Test exception handling in config parsing."""
        mock_exists.return_value = True
        mock_open_func.side_effect = IOError("Permission denied")

        result = repository_parser.parse_borg_config("/tmp/test-repo")

        assert result["mode"] == "error"
        assert "Parse error" in result["preview"]

    @pytest.mark.asyncio
    async def test_start_repository_scan_default_path(self, repository_parser):
        """Test starting repository scan with default path."""
        with patch(
            "app.services.repositories.repository_parser.get_job_manager"
        ) as mock_get_manager:
            mock_job_manager = Mock()
            mock_job_manager.start_borg_command = AsyncMock(return_value="job-123")
            mock_get_manager.return_value = mock_job_manager

            job_id = await repository_parser.start_repository_scan()

            assert job_id == "job-123"
            mock_job_manager.start_borg_command.assert_called_once()
            # Verify the command includes the default scan path
            call_args = mock_job_manager.start_borg_command.call_args[0][0]
            assert "/mnt" in call_args

    @pytest.mark.asyncio
    async def test_start_repository_scan_custom_path(self, repository_parser):
        """Test starting repository scan with custom path."""
        with patch(
            "app.services.repositories.repository_parser.get_job_manager"
        ) as mock_get_manager:
            mock_job_manager = Mock()
            mock_job_manager.start_borg_command = AsyncMock(return_value="job-456")
            mock_get_manager.return_value = mock_job_manager

            job_id = await repository_parser.start_repository_scan("/custom/path")

            assert job_id == "job-456"
            # Verify the command includes the custom scan path
            call_args = mock_job_manager.start_borg_command.call_args[0][0]
            assert "/custom/path" in call_args

    @pytest.mark.asyncio
    async def test_start_repository_scan_error(self, repository_parser):
        """Test repository scan startup error."""
        with patch(
            "app.services.repositories.repository_parser.get_job_manager"
        ) as mock_get_manager:
            mock_job_manager = Mock()
            mock_job_manager.start_borg_command = AsyncMock(
                side_effect=Exception("Job manager error")
            )
            mock_get_manager.return_value = mock_job_manager

            with pytest.raises(Exception) as exc_info:
                await repository_parser.start_repository_scan()

            assert "Job manager error" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_check_scan_status_success(self, repository_parser):
        """Test checking scan status for existing job."""
        with patch(
            "app.services.repositories.repository_parser.get_job_manager"
        ) as mock_get_manager:
            mock_job_manager = Mock()
            mock_job_manager.get_job_status.return_value = {
                "completed": True,
                "status": "success",
                "output": "Found repositories",
                "error": None,
            }
            mock_get_manager.return_value = mock_job_manager

            status = await repository_parser.check_scan_status("job-123")

            assert status["exists"] is True
            assert status["completed"] is True
            assert status["status"] == "success"
            assert status["output"] == "Found repositories"

    @pytest.mark.asyncio
    async def test_check_scan_status_not_found(self, repository_parser):
        """Test checking scan status for non-existent job."""
        with patch(
            "app.services.repositories.repository_parser.get_job_manager"
        ) as mock_get_manager:
            mock_job_manager = Mock()
            mock_job_manager.get_job_status.return_value = None
            mock_get_manager.return_value = mock_job_manager

            status = await repository_parser.check_scan_status("nonexistent-job")

            assert status["exists"] is False
            assert status["completed"] is False
            assert status["status"] == "not_found"
            assert "Job not found" in status["error"]

    @pytest.mark.asyncio
    async def test_check_scan_status_exception(self, repository_parser):
        """Test scan status check with exception."""
        with patch(
            "app.services.repositories.repository_parser.get_job_manager"
        ) as mock_get_manager:
            mock_get_manager.side_effect = Exception("Job manager error")

            status = await repository_parser.check_scan_status("job-123")

            assert status["exists"] is False
            assert status["status"] == "error"
            assert "Job manager error" in status["error"]

    @pytest.mark.asyncio
    async def test_get_scan_results_success(self, repository_parser):
        """Test getting scan results for completed job."""
        with patch(
            "app.services.repositories.repository_parser.get_job_manager"
        ) as mock_get_manager:
            mock_job_manager = Mock()
            mock_job_manager.get_job_status.return_value = {
                "completed": True,
                "output": "/repo1\n/repo2\n",
                "error": None,
            }
            mock_get_manager.return_value = mock_job_manager

            # Mock _parse_scan_output
            repository_parser._parse_scan_output = AsyncMock(
                return_value=[
                    {"name": "repo1", "path": "/repo1"},
                    {"name": "repo2", "path": "/repo2"},
                ]
            )

            results = await repository_parser.get_scan_results("job-123")

            assert len(results) == 2
            assert results[0]["name"] == "repo1"
            repository_parser._parse_scan_output.assert_called_once_with(
                "/repo1\n/repo2\n"
            )

    @pytest.mark.asyncio
    async def test_get_scan_results_not_completed(self, repository_parser):
        """Test getting scan results for incomplete job."""
        with patch(
            "app.services.repositories.repository_parser.get_job_manager"
        ) as mock_get_manager:
            mock_job_manager = Mock()
            mock_job_manager.get_job_status.return_value = {
                "completed": False,
                "output": "",
                "error": None,
            }
            mock_get_manager.return_value = mock_job_manager

            results = await repository_parser.get_scan_results("job-123")

            assert results == []

    @pytest.mark.asyncio
    async def test_get_scan_results_with_errors(self, repository_parser):
        """Test getting scan results for job with errors."""
        with patch(
            "app.services.repositories.repository_parser.get_job_manager"
        ) as mock_get_manager:
            mock_job_manager = Mock()
            mock_job_manager.get_job_status.return_value = {
                "completed": True,
                "output": "/repo1\n",
                "error": "Some scan errors occurred",
            }
            mock_get_manager.return_value = mock_job_manager

            repository_parser._parse_scan_output = AsyncMock(
                return_value=[{"name": "repo1"}]
            )

            results = await repository_parser.get_scan_results("job-123")

            assert len(results) == 1

    @pytest.mark.asyncio
    @patch("os.path.exists")
    async def test_parse_scan_output_success(self, mock_exists, repository_parser):
        """Test parsing scan output with valid repositories."""
        mock_exists.return_value = True

        # Mock parse_borg_config
        repository_parser.parse_borg_config = Mock(
            return_value={
                "mode": "encrypted",
                "requires_keyfile": False,
                "preview": "Borg repository (encrypted)",
            }
        )

        # Mock _get_repository_metadata
        repository_parser._get_repository_metadata = AsyncMock(
            return_value={"size": "1.2G", "last_backup": "2023-01-01T12:00:00Z"}
        )

        output = "/tmp/repo1\n/tmp/repo2\n"

        results = await repository_parser._parse_scan_output(output)

        assert len(results) == 2
        assert results[0]["name"] == "repo1"
        assert results[0]["path"] == "/tmp/repo1"
        assert results[0]["encryption_mode"] == "encrypted"
        assert results[0]["size"] == "1.2G"

    @pytest.mark.asyncio
    async def test_parse_scan_output_empty(self, repository_parser):
        """Test parsing empty scan output."""
        results = await repository_parser._parse_scan_output("")

        assert results == []

    @pytest.mark.asyncio
    @patch("os.path.exists")
    async def test_parse_scan_output_invalid_repos(
        self, mock_exists, repository_parser
    ):
        """Test parsing scan output with invalid repositories."""
        mock_exists.return_value = True

        # Mock parse_borg_config to return invalid
        repository_parser.parse_borg_config = Mock(
            return_value={
                "mode": "invalid",
                "requires_keyfile": False,
                "preview": "Not a Borg repository",
            }
        )

        output = "/tmp/invalid_repo\n"

        results = await repository_parser._parse_scan_output(output)

        assert results == []

    @pytest.mark.asyncio
    @patch("os.path.exists")
    async def test_parse_scan_output_nonexistent_path(
        self, mock_exists, repository_parser
    ):
        """Test parsing scan output with nonexistent paths."""
        mock_exists.return_value = False

        output = "/tmp/nonexistent\n"

        results = await repository_parser._parse_scan_output(output)

        assert results == []

    @pytest.mark.asyncio
    async def test_get_repository_metadata_success(
        self, repository_parser, mock_command_runner
    ):
        """Test successful repository metadata retrieval."""
        # Mock du command result
        du_result = SimpleNamespace()
        du_result.returncode = 0
        du_result.stdout = "1.2G\t/tmp/test-repo"
        mock_command_runner.run_command.return_value = du_result

        # Mock os.walk for last backup time
        with patch("os.path.exists", return_value=True):
            with patch("os.walk") as mock_walk:
                mock_walk.return_value = [
                    ("/tmp/test-repo/data", [], ["file1", "file2"])
                ]
                with patch(
                    "os.path.getmtime", return_value=1640995200.0
                ):  # 2022-01-01 00:00:00
                    with patch(
                        "os.path.join", side_effect=lambda *args: "/".join(args)
                    ):
                        metadata = await repository_parser._get_repository_metadata(
                            "/tmp/test-repo"
                        )

        assert metadata["size"] == "1.2G"
        assert metadata["last_backup"] is not None
        mock_command_runner.run_command.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_repository_metadata_du_error(
        self, repository_parser, mock_command_runner
    ):
        """Test repository metadata with du command error."""
        # Mock du command failure
        du_result = SimpleNamespace()
        du_result.returncode = 1
        mock_command_runner.run_command.return_value = du_result

        metadata = await repository_parser._get_repository_metadata("/tmp/test-repo")

        # Should still return metadata dict, just without size
        assert isinstance(metadata, dict)
        assert "size" not in metadata

    @pytest.mark.asyncio
    async def test_get_repository_metadata_no_data_dir(
        self, repository_parser, mock_command_runner
    ):
        """Test metadata retrieval when data directory doesn't exist."""
        # Mock du command
        du_result = SimpleNamespace()
        du_result.returncode = 0
        du_result.stdout = "1.0G\t/tmp/test-repo"
        mock_command_runner.run_command.return_value = du_result

        def mock_exists_side_effect(path):
            # Return True for the repo path but False for data directory
            if path.endswith("/data"):
                return False
            return True

        with patch("os.path.exists", side_effect=mock_exists_side_effect):
            metadata = await repository_parser._get_repository_metadata(
                "/tmp/test-repo"
            )

        assert metadata["size"] == "1.0G"
        assert "last_backup" not in metadata

    @pytest.mark.asyncio
    async def test_verify_repository_access_success(
        self, repository_parser, test_repository
    ):
        """Test successful repository access verification."""
        with patch(
            "app.services.repositories.repository_parser.build_secure_borg_command"
        ) as mock_build_cmd:
            mock_build_cmd.return_value = (
                ["borg", "info"],
                {"BORG_PASSPHRASE": "test"},
            )

            with patch(
                "app.services.repositories.repository_parser.get_job_manager"
            ) as mock_get_manager:
                mock_job_manager = Mock()
                mock_job_manager.start_borg_command = AsyncMock(
                    return_value="verify-job"
                )
                mock_job_manager.get_job_status.return_value = {
                    "completed": True,
                    "status": "completed",
                    "error": None,
                    "output": '{"repository": {"id": "abc123"}}',
                }
                mock_get_manager.return_value = mock_job_manager

                result = await repository_parser.verify_repository_access(
                    test_repository
                )

        assert result["accessible"] is True
        assert result["error"] is None
        assert "repository_info" in result

    @pytest.mark.asyncio
    async def test_verify_repository_access_wrong_passphrase(
        self, repository_parser, test_repository
    ):
        """Test repository access verification with wrong passphrase."""
        with patch(
            "app.services.repositories.repository_parser.build_secure_borg_command"
        ) as mock_build_cmd:
            mock_build_cmd.return_value = (
                ["borg", "info"],
                {"BORG_PASSPHRASE": "wrong"},
            )

            with patch(
                "app.services.repositories.repository_parser.get_job_manager"
            ) as mock_get_manager:
                mock_job_manager = Mock()
                mock_job_manager.start_borg_command = AsyncMock(
                    return_value="verify-job"
                )
                mock_job_manager.get_job_status.return_value = {
                    "completed": True,
                    "status": "failed",
                    "error": "PassphraseWrong: passphrase supplied in BORG_PASSPHRASE is wrong",
                    "output": "",
                }
                mock_get_manager.return_value = mock_job_manager

                result = await repository_parser.verify_repository_access(
                    test_repository
                )

        assert result["accessible"] is False
        assert "Incorrect passphrase" in result["error"]
        assert result["requires_passphrase"] is True

    @pytest.mark.asyncio
    async def test_verify_repository_access_not_exists(
        self, repository_parser, test_repository
    ):
        """Test repository access verification for non-existent repository."""
        with patch(
            "app.services.repositories.repository_parser.build_secure_borg_command"
        ) as mock_build_cmd:
            mock_build_cmd.return_value = (
                ["borg", "info"],
                {"BORG_PASSPHRASE": "test"},
            )

            with patch(
                "app.services.repositories.repository_parser.get_job_manager"
            ) as mock_get_manager:
                mock_job_manager = Mock()
                mock_job_manager.start_borg_command = AsyncMock(
                    return_value="verify-job"
                )
                mock_job_manager.get_job_status.return_value = {
                    "completed": True,
                    "status": "failed",
                    "error": "Repository does not exist",
                    "output": "",
                }
                mock_get_manager.return_value = mock_job_manager

                result = await repository_parser.verify_repository_access(
                    test_repository
                )

        assert result["accessible"] is False
        assert "does not exist" in result["error"]
        assert result["requires_passphrase"] is False

    @pytest.mark.asyncio
    async def test_verify_repository_access_timeout(
        self, repository_parser, test_repository
    ):
        """Test repository access verification timeout."""
        with patch(
            "app.services.repositories.repository_parser.build_secure_borg_command"
        ) as mock_build_cmd:
            mock_build_cmd.return_value = (
                ["borg", "info"],
                {"BORG_PASSPHRASE": "test"},
            )

            with patch(
                "app.services.repositories.repository_parser.get_job_manager"
            ) as mock_get_manager:
                mock_job_manager = Mock()
                mock_job_manager.start_borg_command = AsyncMock(
                    return_value="verify-job"
                )
                # Simulate job that never completes
                mock_job_manager.get_job_status.return_value = {
                    "completed": False,
                    "status": "running",
                    "error": None,
                    "output": "",
                }
                mock_get_manager.return_value = mock_job_manager

                with patch("asyncio.sleep", new_callable=AsyncMock):
                    result = await repository_parser.verify_repository_access(
                        test_repository
                    )

        assert result["accessible"] is False
        assert "timed out" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_verify_repository_access_security_error(
        self, repository_parser, test_repository
    ):
        """Test repository access verification with security validation error."""
        with patch(
            "app.services.repositories.repository_parser.build_secure_borg_command"
        ) as mock_build_cmd:
            mock_build_cmd.side_effect = Exception("Security validation failed")

            result = await repository_parser.verify_repository_access(test_repository)

        assert result["accessible"] is False
        assert "Security validation failed" in result["error"]

    @pytest.mark.asyncio
    async def test_verify_repository_access_job_not_found(
        self, repository_parser, test_repository
    ):
        """Test repository access verification when job is not found."""
        with patch(
            "app.services.repositories.repository_parser.build_secure_borg_command"
        ) as mock_build_cmd:
            mock_build_cmd.return_value = (
                ["borg", "info"],
                {"BORG_PASSPHRASE": "test"},
            )

            with patch(
                "app.services.repositories.repository_parser.get_job_manager"
            ) as mock_get_manager:
                mock_job_manager = Mock()
                mock_job_manager.start_borg_command = AsyncMock(
                    return_value="verify-job"
                )
                mock_job_manager.get_job_status.return_value = None
                mock_get_manager.return_value = mock_job_manager

                result = await repository_parser.verify_repository_access(
                    test_repository
                )

        assert result["accessible"] is False
        assert "Verification job not found" in result["error"]

    @pytest.mark.asyncio
    async def test_scan_for_repositories_legacy_method(self, repository_parser):
        """Test the legacy scan_for_repositories method."""
        # Mock the internal methods
        repository_parser.start_repository_scan = AsyncMock(return_value="scan-job")
        repository_parser.check_scan_status = AsyncMock()
        repository_parser.get_scan_results = AsyncMock(
            return_value=[{"name": "test-repo", "path": "/tmp/test-repo"}]
        )

        # Mock the status progression
        status_responses = [
            {"completed": False, "status": "running", "output": "", "error": None},
            {"completed": False, "status": "running", "output": "", "error": None},
            {
                "completed": True,
                "status": "completed",
                "output": "/tmp/test-repo",
                "error": None,
            },
        ]
        repository_parser.check_scan_status.side_effect = status_responses

        with patch("asyncio.sleep", new_callable=AsyncMock):
            results = await repository_parser.scan_for_repositories("/custom/path")

        assert len(results) == 1
        assert results[0]["name"] == "test-repo"
        repository_parser.start_repository_scan.assert_called_once_with("/custom/path")

    @pytest.mark.asyncio
    async def test_scan_for_repositories_with_error(self, repository_parser):
        """Test legacy scan method with job error."""
        repository_parser.start_repository_scan = AsyncMock(return_value="scan-job")
        repository_parser.check_scan_status = AsyncMock(
            return_value={
                "completed": False,
                "status": "failed",
                "output": "",
                "error": "Scan failed",
            }
        )

        with patch("asyncio.sleep", new_callable=AsyncMock):
            with pytest.raises(Exception) as exc_info:
                await repository_parser.scan_for_repositories()

        assert "Repository scan timed out" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_verify_repository_access_with_custom_passphrase(
        self, repository_parser, test_repository
    ):
        """Test repository verification with custom passphrase."""
        with patch(
            "app.services.repositories.repository_parser.build_secure_borg_command"
        ) as mock_build_cmd:
            mock_build_cmd.return_value = (
                ["borg", "info"],
                {"BORG_PASSPHRASE": "custom"},
            )

            with patch(
                "app.services.repositories.repository_parser.get_job_manager"
            ) as mock_get_manager:
                mock_job_manager = Mock()
                mock_job_manager.start_borg_command = AsyncMock(
                    return_value="verify-job"
                )
                mock_job_manager.get_job_status.return_value = {
                    "completed": True,
                    "status": "completed",
                    "error": None,
                    "output": '{"repository": {}}',
                }
                mock_get_manager.return_value = mock_job_manager

                result = await repository_parser.verify_repository_access(
                    test_repository, test_passphrase="custom-passphrase"
                )

        assert result["accessible"] is True
        # Verify the custom passphrase was used
        mock_build_cmd.assert_called_once()
        call_kwargs = mock_build_cmd.call_args[1]
        assert call_kwargs["passphrase"] == "custom-passphrase"
