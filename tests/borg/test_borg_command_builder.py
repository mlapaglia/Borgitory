"""
Tests for BorgCommandBuilder - Borg command construction and validation
"""

import pytest
from unittest.mock import patch, MagicMock

from borgitory.services.borg_command_builder import BorgCommandBuilder
from borgitory.models.database import Repository


class TestBorgCommandBuilder:
    """Test BorgCommandBuilder functionality"""

    def setup_method(self) -> None:
        """Set up test fixtures"""
        self.builder = BorgCommandBuilder()

        # Create mock repository
        self.mock_repository = MagicMock(spec=Repository)
        self.mock_repository.path = "/test/repo/path"
        self.mock_repository.get_passphrase.return_value = "test_passphrase"

    def test_initialization(self) -> None:
        """Test BorgCommandBuilder initialization"""
        builder = BorgCommandBuilder()
        assert builder is not None

    @patch("borgitory.services.borg_command_builder.build_secure_borg_command")
    @patch("borgitory.services.borg_command_builder.validate_compression")
    @patch("borgitory.services.borg_command_builder.validate_archive_name")
    def test_build_backup_command_default(
        self, mock_validate_archive, mock_validate_compression, mock_build_secure
    ) -> None:
        """Test building basic backup command with defaults"""
        mock_build_secure.return_value = (
            ["borg", "create"],
            {"BORG_PASSPHRASE": "test_passphrase"},
        )

        command, env = self.builder.build_backup_command(
            repository=self.mock_repository, source_path="/source/path"
        )

        # Verify validation was called
        mock_validate_compression.assert_called_once_with("zstd")
        mock_validate_archive.assert_called_once()

        # Verify build_secure_borg_command was called with correct parameters
        mock_build_secure.assert_called_once()
        call_args = mock_build_secure.call_args
        assert call_args[1]["base_command"] == "borg create"
        assert call_args[1]["repository_path"] == "/test/repo/path"
        assert call_args[1]["passphrase"] == "test_passphrase"

        # Verify additional args contain expected elements
        additional_args = call_args[1]["additional_args"]
        assert "--compression" in additional_args
        assert "zstd" in additional_args
        assert "--stats" in additional_args
        assert "--progress" in additional_args
        assert "--json" in additional_args
        assert "/source/path" in additional_args
        assert any(
            arg.startswith("/test/repo/path::backup-") for arg in additional_args
        )

        assert command == ["borg", "create"]
        assert env == {"BORG_PASSPHRASE": "test_passphrase"}

    @patch("borgitory.services.borg_command_builder.build_secure_borg_command")
    @patch("borgitory.services.borg_command_builder.validate_compression")
    @patch("borgitory.services.borg_command_builder.validate_archive_name")
    def test_build_backup_command_with_custom_options(
        self, mock_validate_archive, mock_validate_compression, mock_build_secure
    ) -> None:
        """Test building backup command with custom options"""
        mock_build_secure.return_value = (
            ["borg", "create"],
            {"BORG_PASSPHRASE": "test_passphrase"},
        )

        command, env = self.builder.build_backup_command(
            repository=self.mock_repository,
            source_path="/source/path",
            compression="lz4",
            dry_run=True,
            archive_name="custom-archive-name",
        )

        # Verify validation was called with custom compression
        mock_validate_compression.assert_called_once_with("lz4")
        mock_validate_archive.assert_called_once_with("custom-archive-name")

        # Verify additional args contain custom options
        call_args = mock_build_secure.call_args
        additional_args = call_args[1]["additional_args"]
        assert "--dry-run" in additional_args
        assert "--compression" in additional_args
        assert "lz4" in additional_args
        assert "/test/repo/path::custom-archive-name" in additional_args

    @patch("borgitory.services.borg_command_builder.validate_compression")
    def test_build_backup_command_validation_failure(
        self, mock_validate_compression
    ) -> None:
        """Test backup command building fails with invalid compression"""
        mock_validate_compression.side_effect = Exception("Invalid compression")

        with pytest.raises(Exception, match="Validation failed: Invalid compression"):
            self.builder.build_backup_command(
                repository=self.mock_repository,
                source_path="/source/path",
                compression="invalid",
            )

    @patch("borgitory.services.borg_command_builder.build_secure_borg_command")
    def test_build_backup_command_security_failure(self, mock_build_secure) -> None:
        """Test backup command building fails when security validation fails"""
        mock_build_secure.side_effect = Exception("Security validation failed")

        with pytest.raises(Exception, match="Security validation failed"):
            self.builder.build_backup_command(
                repository=self.mock_repository, source_path="/source/path"
            )

    @patch("borgitory.services.borg_command_builder.build_secure_borg_command")
    def test_build_list_archives_command(self, mock_build_secure) -> None:
        """Test building list archives command"""
        mock_build_secure.return_value = (
            ["borg", "list"],
            {"BORG_PASSPHRASE": "test_passphrase"},
        )

        command, env = self.builder.build_list_archives_command(self.mock_repository)

        # Verify build_secure_borg_command was called correctly
        mock_build_secure.assert_called_once_with(
            base_command="borg list",
            repository_path="/test/repo/path",
            passphrase="test_passphrase",
            additional_args=["--json"],
        )

        assert command == ["borg", "list"]
        assert env == {"BORG_PASSPHRASE": "test_passphrase"}

    @patch("borgitory.services.borg_command_builder.build_secure_borg_command")
    def test_build_repo_info_command(self, mock_build_secure) -> None:
        """Test building repository info command"""
        mock_build_secure.return_value = (
            ["borg", "info"],
            {"BORG_PASSPHRASE": "test_passphrase"},
        )

        command, env = self.builder.build_repo_info_command(self.mock_repository)

        mock_build_secure.assert_called_once_with(
            base_command="borg info",
            repository_path="/test/repo/path",
            passphrase="test_passphrase",
            additional_args=["--json"],
        )

        assert command == ["borg", "info"]
        assert env == {"BORG_PASSPHRASE": "test_passphrase"}

    @patch("borgitory.services.borg_command_builder.build_secure_borg_command")
    @patch("borgitory.services.borg_command_builder.validate_archive_name")
    def test_build_list_archive_contents_command(
        self, mock_validate_archive, mock_build_secure
    ) -> None:
        """Test building list archive contents command"""
        mock_build_secure.return_value = (
            ["borg", "list"],
            {"BORG_PASSPHRASE": "test_passphrase"},
        )

        command, env = self.builder.build_list_archive_contents_command(
            repository=self.mock_repository, archive_name="test-archive"
        )

        mock_validate_archive.assert_called_once_with("test-archive")

        call_args = mock_build_secure.call_args
        assert call_args[1]["base_command"] == "borg list"
        additional_args = call_args[1]["additional_args"]
        assert "--json-lines" in additional_args
        assert "/test/repo/path::test-archive" in additional_args

    @patch("borgitory.services.borg_command_builder.build_secure_borg_command")
    @patch("borgitory.services.borg_command_builder.validate_archive_name")
    @patch("borgitory.services.borg_command_builder.sanitize_path")
    def test_build_list_archive_contents_command_with_directory(
        self, mock_sanitize_path, mock_validate_archive, mock_build_secure
    ) -> None:
        """Test building list archive contents command with directory filter"""
        mock_build_secure.return_value = (
            ["borg", "list"],
            {"BORG_PASSPHRASE": "test_passphrase"},
        )
        mock_sanitize_path.return_value = "sanitized/path"

        command, env = self.builder.build_list_archive_contents_command(
            repository=self.mock_repository,
            archive_name="test-archive",
            directory_path="/some/directory",
        )

        mock_validate_archive.assert_called_once_with("test-archive")
        mock_sanitize_path.assert_called_once_with("/some/directory")

        call_args = mock_build_secure.call_args
        additional_args = call_args[1]["additional_args"]
        assert "/test/repo/path::test-archive::sanitized/path" in additional_args

    @patch("borgitory.services.borg_command_builder.validate_archive_name")
    def test_build_list_archive_contents_command_invalid_archive(
        self, mock_validate_archive
    ) -> None:
        """Test list archive contents command fails with invalid archive name"""
        mock_validate_archive.side_effect = Exception("Invalid archive name")

        with pytest.raises(Exception, match="Archive name validation failed"):
            self.builder.build_list_archive_contents_command(
                repository=self.mock_repository, archive_name="invalid-archive"
            )

    @patch("borgitory.services.borg_command_builder.build_secure_borg_command")
    @patch("borgitory.services.borg_command_builder.validate_archive_name")
    @patch("borgitory.services.borg_command_builder.sanitize_path")
    def test_build_extract_command(
        self, mock_sanitize_path, mock_validate_archive, mock_build_secure
    ) -> None:
        """Test building extract command"""
        mock_build_secure.return_value = (
            ["borg", "extract"],
            {"BORG_PASSPHRASE": "test_passphrase"},
        )
        mock_sanitize_path.return_value = "sanitized/file/path"

        command, env = self.builder.build_extract_command(
            repository=self.mock_repository,
            archive_name="test-archive",
            file_path="/path/to/file.txt",
        )

        mock_validate_archive.assert_called_once_with("test-archive")
        mock_sanitize_path.assert_called_once_with("/path/to/file.txt")

        call_args = mock_build_secure.call_args
        assert call_args[1]["base_command"] == "borg extract"
        additional_args = call_args[1]["additional_args"]
        assert "--stdout" in additional_args
        assert "/test/repo/path::test-archive" in additional_args
        assert "sanitized/file/path" in additional_args

    @patch("borgitory.services.borg_command_builder.build_secure_borg_command")
    @patch("borgitory.services.borg_command_builder.validate_archive_name")
    @patch("borgitory.services.borg_command_builder.sanitize_path")
    def test_build_extract_command_no_stdout(
        self, mock_sanitize_path, mock_validate_archive, mock_build_secure
    ) -> None:
        """Test building extract command without stdout option"""
        mock_build_secure.return_value = (
            ["borg", "extract"],
            {"BORG_PASSPHRASE": "test_passphrase"},
        )
        mock_sanitize_path.return_value = "sanitized/file/path"

        command, env = self.builder.build_extract_command(
            repository=self.mock_repository,
            archive_name="test-archive",
            file_path="/path/to/file.txt",
            extract_to_stdout=False,
        )

        call_args = mock_build_secure.call_args
        additional_args = call_args[1]["additional_args"]
        assert "--stdout" not in additional_args

    @patch("borgitory.services.borg_command_builder.build_secure_borg_command")
    def test_build_initialize_repository_command(self, mock_build_secure) -> None:
        """Test building repository initialization command"""
        mock_build_secure.return_value = (
            ["borg", "init"],
            {"BORG_PASSPHRASE": "test_passphrase"},
        )

        command, env = self.builder.build_initialize_repository_command(
            self.mock_repository
        )

        call_args = mock_build_secure.call_args
        assert call_args[1]["base_command"] == "borg init"
        additional_args = call_args[1]["additional_args"]
        assert "--encryption" in additional_args
        assert "repokey-blake2" in additional_args
        assert "/test/repo/path" in additional_args

    @patch("borgitory.services.borg_command_builder.build_secure_borg_command")
    def test_build_initialize_repository_command_custom_encryption(
        self, mock_build_secure
    ) -> None:
        """Test building repository initialization command with custom encryption"""
        mock_build_secure.return_value = (
            ["borg", "init"],
            {"BORG_PASSPHRASE": "test_passphrase"},
        )

        command, env = self.builder.build_initialize_repository_command(
            repository=self.mock_repository, encryption_mode="keyfile"
        )

        call_args = mock_build_secure.call_args
        additional_args = call_args[1]["additional_args"]
        assert "keyfile" in additional_args

    @patch("borgitory.services.borg_command_builder.build_secure_borg_command")
    def test_build_prune_command_basic(self, mock_build_secure) -> None:
        """Test building basic prune command"""
        mock_build_secure.return_value = (
            ["borg", "prune"],
            {"BORG_PASSPHRASE": "test_passphrase"},
        )

        command, env = self.builder.build_prune_command(self.mock_repository)

        call_args = mock_build_secure.call_args
        assert call_args[1]["base_command"] == "borg prune"
        additional_args = call_args[1]["additional_args"]
        assert "--list" in additional_args
        assert "--stats" in additional_args
        assert "/test/repo/path" in additional_args

    @patch("borgitory.services.borg_command_builder.build_secure_borg_command")
    def test_build_prune_command_with_retention(self, mock_build_secure) -> None:
        """Test building prune command with retention policies"""
        mock_build_secure.return_value = (
            ["borg", "prune"],
            {"BORG_PASSPHRASE": "test_passphrase"},
        )

        command, env = self.builder.build_prune_command(
            repository=self.mock_repository,
            keep_within="1d",
            keep_secondly=7,
            keep_minutely=7,
            keep_hourly=7,
            keep_daily=7,
            keep_weekly=4,
            keep_monthly=6,
            keep_yearly=1,
            dry_run=True,
            save_space=True,
            force_prune=True,
        )

        call_args = mock_build_secure.call_args
        additional_args = call_args[1]["additional_args"]
        assert "--keep-within" in additional_args
        assert "1d" in additional_args
        assert "--keep-daily" in additional_args
        assert "7" in additional_args
        assert "--keep-weekly" in additional_args
        assert "4" in additional_args
        assert "--keep-monthly" in additional_args
        assert "6" in additional_args
        assert "--keep-yearly" in additional_args
        assert "1" in additional_args
        assert "--dry-run" in additional_args
        assert "--save-space" in additional_args
        assert "--force" in additional_args

    @patch("borgitory.services.borg_command_builder.build_secure_borg_command")
    def test_build_check_command_repository_only(self, mock_build_secure) -> None:
        """Test building check command for repository only"""
        mock_build_secure.return_value = (
            ["borg", "check"],
            {"BORG_PASSPHRASE": "test_passphrase"},
        )

        command, env = self.builder.build_check_command(
            repository=self.mock_repository, check_type="repository_only"
        )

        call_args = mock_build_secure.call_args
        assert call_args[1]["base_command"] == "borg check"
        additional_args = call_args[1]["additional_args"]
        assert "--repository-only" in additional_args

    @patch("borgitory.services.borg_command_builder.build_secure_borg_command")
    def test_build_check_command_with_options(self, mock_build_secure) -> None:
        """Test building check command with various options"""
        mock_build_secure.return_value = (
            ["borg", "check"],
            {"BORG_PASSPHRASE": "test_passphrase"},
        )

        command, env = self.builder.build_check_command(
            repository=self.mock_repository,
            check_type="full",
            verify_data=True,
            repair_mode=True,
            save_space=True,
            max_duration=3600,
            archive_prefix="backup",
            first_n_archives=10,
        )

        call_args = mock_build_secure.call_args
        additional_args = call_args[1]["additional_args"]
        assert "--verify-data" in additional_args
        assert "--repair" in additional_args
        assert "--save-space" in additional_args
        assert "--max-duration" in additional_args
        assert "3600" in additional_args
        assert "--glob-archives" in additional_args
        assert "backup*" in additional_args
        assert "--first" in additional_args
        assert "10" in additional_args

    @patch("borgitory.services.borg_command_builder.build_secure_borg_command")
    def test_build_check_command_with_glob(self, mock_build_secure) -> None:
        """Test building check command with custom glob pattern"""
        mock_build_secure.return_value = (
            ["borg", "check"],
            {"BORG_PASSPHRASE": "test_passphrase"},
        )

        command, env = self.builder.build_check_command(
            repository=self.mock_repository, archive_glob="*-2023-*", last_n_archives=5
        )

        call_args = mock_build_secure.call_args
        additional_args = call_args[1]["additional_args"]
        assert "--glob-archives" in additional_args
        assert "*-2023-*" in additional_args
        assert "--last" in additional_args
        assert "5" in additional_args

    @patch("borgitory.services.borg_command_builder.now_utc")
    @patch("borgitory.services.borg_command_builder.validate_archive_name")
    def test_generate_archive_name_default(
        self, mock_validate_archive, mock_now_utc
    ) -> None:
        """Test generating default archive name"""
        mock_now_utc.return_value.strftime.return_value = "2024-01-15_14-30-45"

        archive_name = self.builder.generate_archive_name()

        assert archive_name == "backup-2024-01-15_14-30-45"
        mock_validate_archive.assert_called_once_with("backup-2024-01-15_14-30-45")

    @patch("borgitory.services.borg_command_builder.now_utc")
    @patch("borgitory.services.borg_command_builder.validate_archive_name")
    def test_generate_archive_name_custom_prefix(
        self, mock_validate_archive, mock_now_utc
    ) -> None:
        """Test generating archive name with custom prefix"""
        mock_now_utc.return_value.strftime.return_value = "2024-01-15_14-30-45"

        archive_name = self.builder.generate_archive_name("custom")

        assert archive_name == "custom-2024-01-15_14-30-45"
        mock_validate_archive.assert_called_once_with("custom-2024-01-15_14-30-45")

    @patch("borgitory.services.borg_command_builder.now_utc")
    @patch("borgitory.services.borg_command_builder.validate_archive_name")
    @patch("borgitory.services.borg_command_builder.logger")
    def test_generate_archive_name_validation_fails(
        self, mock_logger, mock_validate_archive, mock_now_utc
    ) -> None:
        """Test generating archive name when validation fails"""
        mock_now_utc.return_value.strftime.side_effect = [
            "2024-01-15_14-30-45",
            "20240115_143045",
        ]
        mock_validate_archive.side_effect = Exception("Invalid name")

        archive_name = self.builder.generate_archive_name()

        assert archive_name == "backup-20240115_143045"
        mock_logger.warning.assert_called_once()

    @patch("borgitory.services.borg_command_builder.validate_archive_name")
    @patch("borgitory.services.borg_command_builder.sanitize_path")
    @patch("borgitory.services.borg_command_builder.validate_compression")
    def test_validate_command_parameters_success(
        self, mock_validate_compression, mock_sanitize_path, mock_validate_archive
    ) -> None:
        """Test parameter validation with all valid inputs"""
        errors = self.builder.validate_command_parameters(
            repository=self.mock_repository,
            archive_name="test-archive",
            source_path="/test/source",
            compression="zstd",
        )

        assert errors == {}
        mock_validate_archive.assert_called_once_with("test-archive")
        mock_sanitize_path.assert_called_once_with("/test/source")
        mock_validate_compression.assert_called_once_with("zstd")

    def test_validate_command_parameters_no_repository(self) -> None:
        """Test parameter validation with missing repository"""
        errors = self.builder.validate_command_parameters(repository=None)

        assert "repository" in errors
        assert "Repository path is required" in errors["repository"]

    def test_validate_command_parameters_empty_repository_path(self) -> None:
        """Test parameter validation with empty repository path"""
        mock_repo = MagicMock(spec=Repository)
        mock_repo.path = ""

        errors = self.builder.validate_command_parameters(repository=mock_repo)

        assert "repository" in errors

    @patch("borgitory.services.borg_command_builder.validate_archive_name")
    def test_validate_command_parameters_invalid_archive(
        self, mock_validate_archive
    ) -> None:
        """Test parameter validation with invalid archive name"""
        mock_validate_archive.side_effect = Exception("Invalid archive name")

        errors = self.builder.validate_command_parameters(
            repository=self.mock_repository, archive_name="invalid-archive"
        )

        assert "archive_name" in errors
        assert "Invalid archive name" in errors["archive_name"]

    @patch("borgitory.services.borg_command_builder.sanitize_path")
    def test_validate_command_parameters_invalid_path(self, mock_sanitize_path) -> None:
        """Test parameter validation with invalid source path"""
        mock_sanitize_path.side_effect = Exception("Invalid path")

        errors = self.builder.validate_command_parameters(
            repository=self.mock_repository, source_path="/invalid/path"
        )

        assert "source_path" in errors
        assert "Invalid path" in errors["source_path"]

    @patch("borgitory.services.borg_command_builder.validate_compression")
    def test_validate_command_parameters_invalid_compression(
        self, mock_validate_compression
    ) -> None:
        """Test parameter validation with invalid compression"""
        mock_validate_compression.side_effect = Exception("Invalid compression")

        errors = self.builder.validate_command_parameters(
            repository=self.mock_repository, compression="invalid"
        )

        assert "compression" in errors
        assert "Invalid compression" in errors["compression"]

    @patch("borgitory.services.borg_command_builder.validate_archive_name")
    @patch("borgitory.services.borg_command_builder.sanitize_path")
    @patch("borgitory.services.borg_command_builder.validate_compression")
    def test_validate_command_parameters_multiple_errors(
        self, mock_validate_compression, mock_sanitize_path, mock_validate_archive
    ) -> None:
        """Test parameter validation with multiple validation errors"""
        mock_validate_archive.side_effect = Exception("Bad archive")
        mock_sanitize_path.side_effect = Exception("Bad path")
        mock_validate_compression.side_effect = Exception("Bad compression")

        errors = self.builder.validate_command_parameters(
            repository=None,
            archive_name="bad-archive",
            source_path="/bad/path",
            compression="bad",
        )

        assert len(errors) == 4
        assert "repository" in errors
        assert "archive_name" in errors
        assert "source_path" in errors
        assert "compression" in errors

    def test_validate_command_parameters_minimal_valid(self) -> None:
        """Test parameter validation with only repository (minimal valid case)"""
        errors = self.builder.validate_command_parameters(
            repository=self.mock_repository
        )

        assert errors == {}
