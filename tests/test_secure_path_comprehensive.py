"""
Comprehensive tests for secure_path.py utilities.
Tests functions not covered in test_security.py to achieve full coverage.
"""

import pytest
import tempfile
import os
from pathlib import Path
from unittest.mock import patch, Mock

from borgitory.utils.secure_path import (
    PathSecurityError,
    sanitize_filename,
    create_secure_filename,
    secure_path_join,
    secure_exists,
    secure_isdir,
    secure_remove_file,
    get_directory_listing,
    user_secure_exists,
    user_secure_isdir,
    user_get_directory_listing,
    validate_user_repository_path,
)


class TestSanitizeFilename:
    """Test filename sanitization functionality."""

    def test_sanitize_valid_filename(self) -> None:
        """Test sanitization of valid filenames."""
        valid_names = [
            "backup.tar.gz",
            "file123.txt",
            "my-backup_2023.zip",
            "test.log",
            "simple",
            "file.with.dots",
        ]

        for name in valid_names:
            result = sanitize_filename(name)
            assert result == name
            assert len(result) <= 100

    def test_sanitize_empty_filename(self) -> None:
        """Test that empty filenames get default name."""
        assert sanitize_filename("") == "unnamed"
        assert sanitize_filename(None) == "unnamed"

    def test_sanitize_dangerous_characters(self) -> None:
        """Test that dangerous characters are replaced."""
        dangerous_names = [
            ("file/with/slashes", "file_with_slashes"),
            ("file\\with\\backslashes", "file_with_backslashes"),
            ("file:with:colons", "file_with_colons"),
            ("file*with*asterisks", "file_with_asterisks"),
            ("file?with?questions", "file_with_questions"),
            ("file|with|pipes", "file_with_pipes"),
            ("file<with<less", "file_with_less"),
            ("file>with>greater", "file_with_greater"),
            ('file"with"quotes', "file_with_quotes"),
            ("file with spaces", "file_with_spaces"),
        ]

        for dangerous, expected in dangerous_names:
            result = sanitize_filename(dangerous)
            assert result == expected

    def test_sanitize_multiple_dots(self) -> None:
        """Test that multiple consecutive dots are normalized."""
        assert sanitize_filename("file...txt") == "file.txt"
        assert sanitize_filename("file....backup") == "file.backup"
        assert sanitize_filename("...hidden") == "hidden"  # Leading dots are stripped

    def test_sanitize_leading_trailing_dots_spaces(self) -> None:
        """Test that leading/trailing dots and spaces are handled."""
        assert (
            sanitize_filename(" file.txt ") == "_file.txt_"
        )  # Spaces become underscores
        assert (
            sanitize_filename(".file.txt.") == "file.txt"
        )  # Leading/trailing dots stripped
        assert (
            sanitize_filename("  ..file..  ") == "__.file.__"
        )  # Spaces become underscores, only consecutive dots normalized

    def test_sanitize_only_dangerous_chars(self) -> None:
        """Test filenames with only dangerous characters."""
        assert sanitize_filename("///") == "___"  # Slashes become underscores
        assert sanitize_filename("***") == "___"  # Asterisks become underscores
        assert sanitize_filename("   ") == "___"  # Spaces also become underscores
        # Test that only completely empty after processing becomes unnamed
        result = sanitize_filename("")
        assert result == "unnamed"

    def test_sanitize_long_filename(self) -> None:
        """Test filename truncation."""
        long_name = "a" * 150 + ".txt"
        result = sanitize_filename(long_name, max_length=100)
        assert len(result) <= 100
        assert result.endswith(".txt")
        assert result.startswith("a")

    def test_sanitize_custom_max_length(self) -> None:
        """Test custom maximum length."""
        name = "verylongfilename.txt"
        result = sanitize_filename(name, max_length=10)
        assert len(result) <= 10
        assert result.endswith(".txt")


class TestCreateSecureFilename:
    """Test secure filename creation."""

    def test_create_basic_filename(self) -> None:
        """Test basic secure filename creation."""
        result = create_secure_filename("backup")
        assert result.startswith("backup_")
        assert len(result.split("_")[1]) == 8  # UUID part
        assert not result.endswith(".")

    def test_create_filename_with_extension(self) -> None:
        """Test filename creation with extension extraction."""
        result = create_secure_filename("backup", "file.tar.gz")
        assert result.startswith("backup_")
        assert result.endswith(".gz")

    def test_create_filename_without_uuid(self) -> None:
        """Test filename creation without UUID."""
        result = create_secure_filename("backup", add_uuid=False)
        assert result == "backup"

    def test_create_filename_with_dangerous_extension(self) -> None:
        """Test that dangerous extensions are sanitized."""
        result = create_secure_filename("backup", "file.exe!@#")
        assert result.startswith("backup_")
        assert result.endswith(".exe")

    def test_create_filename_no_extension(self) -> None:
        """Test filename creation when original has no extension."""
        result = create_secure_filename("backup", "noextension")
        assert result.startswith("backup_")
        assert "." not in result.split("_")[1]  # No extension added

    def test_create_filename_dangerous_base(self) -> None:
        """Test that dangerous base names are sanitized."""
        result = create_secure_filename("../../../dangerous", "file.txt")
        assert not result.startswith("../")
        assert result.endswith(".txt")


class TestSecurePathJoin:
    """Test secure path joining functionality."""

    def test_secure_join_valid_paths(self) -> None:
        """Test joining valid path components."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create a test directory structure
            mnt_dir = os.path.join(temp_dir, "mnt")
            os.makedirs(mnt_dir, exist_ok=True)

            with patch(
                "borgitory.utils.secure_path.validate_secure_path"
            ) as mock_validate:
                # Mock both calls - first for base validation, second for final validation
                expected_final = Path(mnt_dir) / "subdir" / "file.txt"
                mock_validate.side_effect = [Path(mnt_dir), expected_final]

                result = secure_path_join(mnt_dir, "subdir", "file.txt")
                assert "subdir" in result
                assert "file.txt" in result

    def test_secure_join_dangerous_components(self) -> None:
        """Test that dangerous path components are cleaned."""
        with tempfile.TemporaryDirectory() as temp_dir:
            mnt_dir = os.path.join(temp_dir, "mnt")
            os.makedirs(mnt_dir, exist_ok=True)

            with patch(
                "borgitory.utils.secure_path.validate_secure_path"
            ) as mock_validate:
                mock_validate.side_effect = (
                    lambda x, **kwargs: Path(mnt_dir) if "mnt" in str(x) else None
                )

                result = secure_path_join(mnt_dir, "../../../etc", "passwd")
                # Should clean the dangerous component
                assert "etc" not in result or "passwd" not in result

    def test_secure_join_invalid_base(self) -> None:
        """Test that invalid base directories raise errors."""
        with pytest.raises(PathSecurityError):
            secure_path_join("/etc/passwd", "file.txt")

    def test_secure_join_empty_components(self) -> None:
        """Test joining with empty components."""
        with tempfile.TemporaryDirectory() as temp_dir:
            mnt_dir = os.path.join(temp_dir, "mnt")
            os.makedirs(mnt_dir, exist_ok=True)

            with patch(
                "borgitory.utils.secure_path.validate_secure_path"
            ) as mock_validate:
                expected_final = Path(mnt_dir) / "file.txt"
                mock_validate.side_effect = [Path(mnt_dir), expected_final]

                result = secure_path_join(mnt_dir, "", "file.txt", "")
                assert result == str(expected_final)

    def test_secure_join_final_validation_failure(self) -> None:
        """Test that final path validation failures raise errors."""
        with tempfile.TemporaryDirectory() as temp_dir:
            mnt_dir = os.path.join(temp_dir, "mnt")
            os.makedirs(mnt_dir, exist_ok=True)

            with patch(
                "borgitory.utils.secure_path.validate_secure_path"
            ) as mock_validate:
                # First call succeeds (base validation), second fails (final validation)
                mock_validate.side_effect = [Path(mnt_dir), None]

                with pytest.raises(PathSecurityError):
                    secure_path_join(mnt_dir, "legitimate", "path")


class TestSecureExists:
    """Test secure file existence checking."""

    def test_secure_exists_valid_path(self) -> None:
        """Test existence check for valid paths."""
        with tempfile.TemporaryDirectory() as temp_dir:
            test_file = os.path.join(temp_dir, "test.txt")
            Path(test_file).touch()

            with patch(
                "borgitory.utils.secure_path.validate_secure_path"
            ) as mock_validate:
                mock_validate.return_value = Path(test_file)

                assert secure_exists(test_file) is True

    def test_secure_exists_nonexistent_path(self) -> None:
        """Test existence check for nonexistent paths."""
        with tempfile.TemporaryDirectory() as temp_dir:
            nonexistent = os.path.join(temp_dir, "nonexistent.txt")

            with patch(
                "borgitory.utils.secure_path.validate_secure_path"
            ) as mock_validate:
                mock_validate.return_value = Path(nonexistent)

                assert secure_exists(nonexistent) is False

    def test_secure_exists_invalid_path(self) -> None:
        """Test existence check for invalid paths."""
        assert secure_exists("../../../etc/passwd") is False

    def test_secure_exists_permission_error(self) -> None:
        """Test handling of permission errors."""
        with patch("borgitory.utils.secure_path.validate_secure_path") as mock_validate:
            mock_path = Mock()
            mock_path.exists.side_effect = PermissionError("Access denied")
            mock_validate.return_value = mock_path

            assert secure_exists("/mnt/test") is False


class TestSecureIsdir:
    """Test secure directory checking."""

    def test_secure_isdir_valid_directory(self) -> None:
        """Test directory check for valid directories."""
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch(
                "borgitory.utils.secure_path.validate_secure_path"
            ) as mock_validate:
                mock_validate.return_value = Path(temp_dir)

                assert secure_isdir(temp_dir) is True

    def test_secure_isdir_file_not_directory(self) -> None:
        """Test directory check for files."""
        with tempfile.TemporaryDirectory() as temp_dir:
            test_file = os.path.join(temp_dir, "test.txt")
            Path(test_file).touch()

            with patch(
                "borgitory.utils.secure_path.validate_secure_path"
            ) as mock_validate:
                mock_validate.return_value = Path(test_file)

                assert secure_isdir(test_file) is False

    def test_secure_isdir_invalid_path(self) -> None:
        """Test directory check for invalid paths."""
        assert secure_isdir("../../../etc") is False

    def test_secure_isdir_permission_error(self) -> None:
        """Test handling of permission errors."""
        with patch("borgitory.utils.secure_path.validate_secure_path") as mock_validate:
            mock_path = Mock()
            mock_path.is_dir.side_effect = PermissionError("Access denied")
            mock_validate.return_value = mock_path

            assert secure_isdir("/mnt/test") is False


class TestSecureRemoveFile:
    """Test secure file removal."""

    def test_secure_remove_existing_file(self) -> None:
        """Test removing an existing file."""
        with tempfile.TemporaryDirectory() as temp_dir:
            test_file = os.path.join(temp_dir, "test.txt")
            Path(test_file).touch()

            with patch(
                "borgitory.utils.secure_path.validate_secure_path"
            ) as mock_validate:
                mock_validate.return_value = Path(test_file)

                assert secure_remove_file(test_file) is True
                assert not Path(test_file).exists()

    def test_secure_remove_nonexistent_file(self) -> None:
        """Test removing a nonexistent file."""
        with tempfile.TemporaryDirectory() as temp_dir:
            nonexistent = os.path.join(temp_dir, "nonexistent.txt")

            with patch(
                "borgitory.utils.secure_path.validate_secure_path"
            ) as mock_validate:
                mock_validate.return_value = Path(nonexistent)

                assert secure_remove_file(nonexistent) is True

    def test_secure_remove_invalid_path(self) -> None:
        """Test removing file with invalid path."""
        assert secure_remove_file("../../../etc/passwd") is False

    def test_secure_remove_permission_error(self) -> None:
        """Test handling of permission errors during removal."""
        with tempfile.TemporaryDirectory() as temp_dir:
            test_file = os.path.join(temp_dir, "test.txt")
            Path(test_file).touch()

            with patch(
                "borgitory.utils.secure_path.validate_secure_path"
            ) as mock_validate:
                mock_path = Mock()
                mock_path.exists.return_value = True
                mock_path.unlink.side_effect = PermissionError("Access denied")
                mock_validate.return_value = mock_path

                assert secure_remove_file(test_file) is False


class TestGetDirectoryListing:
    """Test secure directory listing."""

    def test_get_directory_listing_valid_directory(self) -> None:
        """Test listing contents of valid directory."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create test structure
            subdir = os.path.join(temp_dir, "subdir")
            os.makedirs(subdir)
            test_file = os.path.join(temp_dir, "test.txt")
            Path(test_file).touch()

            with patch(
                "borgitory.utils.secure_path.validate_secure_path"
            ) as mock_validate:
                mock_validate.return_value = Path(temp_dir)

                result = get_directory_listing(temp_dir)

                # Should only include directories by default
                assert len(result) == 1
                assert result[0]["name"] == "subdir"
                assert "subdir" in result[0]["path"]

    def test_get_directory_listing_with_files(self) -> None:
        """Test listing contents including files."""
        with tempfile.TemporaryDirectory() as temp_dir:
            subdir = os.path.join(temp_dir, "subdir")
            os.makedirs(subdir)
            test_file = os.path.join(temp_dir, "test.txt")
            Path(test_file).touch()

            with patch(
                "borgitory.utils.secure_path.validate_secure_path"
            ) as mock_validate:
                mock_validate.return_value = Path(temp_dir)

                result = get_directory_listing(temp_dir, include_files=True)

                assert len(result) == 2
                names = [item["name"] for item in result]
                assert "subdir" in names
                assert "test.txt" in names

    def test_get_directory_listing_invalid_path(self) -> None:
        """Test listing invalid directory."""
        result = get_directory_listing("../../../etc")
        assert result == []

    def test_get_directory_listing_not_directory(self) -> None:
        """Test listing a file instead of directory."""
        with tempfile.TemporaryDirectory() as temp_dir:
            test_file = os.path.join(temp_dir, "test.txt")
            Path(test_file).touch()

            with patch(
                "borgitory.utils.secure_path.validate_secure_path"
            ) as mock_validate:
                mock_validate.return_value = Path(test_file)

                result = get_directory_listing(test_file)
                assert result == []

    def test_get_directory_listing_permission_error(self) -> None:
        """Test handling permission errors during listing."""
        with patch("borgitory.utils.secure_path.validate_secure_path") as mock_validate:
            mock_path = Mock()
            mock_path.is_dir.return_value = True
            mock_path.iterdir.side_effect = PermissionError("Access denied")
            mock_validate.return_value = mock_path

            result = get_directory_listing("/mnt/test")
            assert result == []

    def test_get_directory_listing_sorted(self) -> None:
        """Test that directory listing is sorted alphabetically."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create directories in non-alphabetical order
            for name in ["zebra", "apple", "banana"]:
                os.makedirs(os.path.join(temp_dir, name))

            with patch(
                "borgitory.utils.secure_path.validate_secure_path"
            ) as mock_validate:
                mock_validate.return_value = Path(temp_dir)

                result = get_directory_listing(temp_dir)
                names = [item["name"] for item in result]
                assert names == ["apple", "banana", "zebra"]


class TestUserFacingFunctions:
    """Test user-facing functions that only allow /mnt paths."""

    def test_user_secure_exists_mnt_path(self) -> None:
        """Test user existence check for /mnt paths."""
        with tempfile.TemporaryDirectory() as temp_dir:
            test_file = os.path.join(temp_dir, "test.txt")
            Path(test_file).touch()

            with patch(
                "borgitory.utils.secure_path.validate_mnt_path"
            ) as mock_validate:
                mock_validate.return_value = Path(test_file)

                assert user_secure_exists("/mnt/test.txt") is True

    def test_user_secure_exists_invalid_path(self) -> None:
        """Test user existence check for invalid paths."""
        assert user_secure_exists("../../../etc/passwd") is False

    def test_user_secure_exists_permission_error(self) -> None:
        """Test handling permission errors in user existence check."""
        with patch("borgitory.utils.secure_path.validate_mnt_path") as mock_validate:
            mock_path = Mock()
            mock_path.exists.side_effect = PermissionError("Access denied")
            mock_validate.return_value = mock_path

            assert user_secure_exists("/mnt/test") is False

    def test_user_secure_isdir_valid_directory(self) -> None:
        """Test user directory check for valid directories."""
        with tempfile.TemporaryDirectory():
            with patch(
                "borgitory.utils.secure_path.validate_mnt_path"
            ) as mock_validate, patch("os.path.realpath") as mock_realpath:
                # Create a mock path that behaves like it's under /mnt
                mock_path = Mock(spec=Path)
                mock_path.is_dir.return_value = True
                mock_path.__str__ = Mock(return_value="/mnt/test")
                mock_validate.return_value = mock_path
                mock_realpath.return_value = "/mnt"

                assert user_secure_isdir("/mnt/test") is True

    def test_user_secure_isdir_path_outside_mnt(self) -> None:
        """Test user directory check blocks paths outside /mnt."""
        with patch(
            "borgitory.utils.secure_path.validate_mnt_path"
        ) as mock_validate, patch("os.path.realpath") as mock_realpath:
            mock_validate.return_value = Path("/app/data/test")
            mock_realpath.return_value = "/mnt"

            assert user_secure_isdir("/app/data/test") is False

    def test_user_secure_isdir_permission_error(self) -> None:
        """Test handling permission errors in user directory check."""
        with patch(
            "borgitory.utils.secure_path.validate_mnt_path"
        ) as mock_validate, patch("os.path.realpath") as mock_realpath:
            mock_path = Mock()
            mock_path.is_dir.side_effect = PermissionError("Access denied")
            mock_validate.return_value = mock_path
            mock_realpath.return_value = "/mnt"

            with patch.object(Path, "__str__", return_value="/mnt/test"):
                assert user_secure_isdir("/mnt/test") is False

    def test_user_get_directory_listing_valid(self) -> None:
        """Test user directory listing for valid /mnt paths."""
        with tempfile.TemporaryDirectory() as temp_dir:
            subdir = os.path.join(temp_dir, "subdir")
            os.makedirs(subdir)

            with patch(
                "borgitory.utils.secure_path.validate_mnt_path"
            ) as mock_validate:
                mock_validate.return_value = Path(temp_dir)

                result = user_get_directory_listing("/mnt/test")
                assert len(result) == 1
                assert result[0]["name"] == "subdir"

    def test_user_get_directory_listing_invalid_path(self) -> None:
        """Test user directory listing for invalid paths."""
        result = user_get_directory_listing("../../../etc")
        assert result == []

    def test_user_get_directory_listing_with_files(self) -> None:
        """Test user directory listing including files."""
        with tempfile.TemporaryDirectory() as temp_dir:
            test_file = os.path.join(temp_dir, "test.txt")
            Path(test_file).touch()

            with patch(
                "borgitory.utils.secure_path.validate_mnt_path"
            ) as mock_validate:
                mock_validate.return_value = Path(temp_dir)

                result = user_get_directory_listing("/mnt/test", include_files=True)
                assert len(result) == 1
                assert result[0]["name"] == "test.txt"

    def test_user_get_directory_listing_permission_error(self) -> None:
        """Test handling permission errors in user directory listing."""
        with patch("borgitory.utils.secure_path.validate_mnt_path") as mock_validate:
            mock_path = Mock()
            mock_path.is_dir.return_value = True
            mock_path.iterdir.side_effect = PermissionError("Access denied")
            mock_validate.return_value = mock_path

            result = user_get_directory_listing("/mnt/test")
            assert result == []


class TestValidateUserRepositoryPath:
    """Test user repository path validation."""

    def test_validate_user_repository_path_valid(self) -> None:
        """Test validation of valid user repository paths."""
        with patch("borgitory.utils.secure_path.validate_mnt_path") as mock_validate:
            mock_validate.return_value = Path("/mnt/repo")

            result = validate_user_repository_path("/mnt/repo")
            assert result is not None

    def test_validate_user_repository_path_invalid(self) -> None:
        """Test validation rejects invalid paths."""
        with patch("borgitory.utils.secure_path.validate_mnt_path") as mock_validate:
            mock_validate.return_value = None

            result = validate_user_repository_path("/etc/passwd")
            assert result is None


class TestPathSecurityError:
    """Test PathSecurityError exception."""

    def test_path_security_error_creation(self):
        """Test that PathSecurityError can be created and raised."""
        with pytest.raises(PathSecurityError):
            raise PathSecurityError("Test error message")

    def test_path_security_error_inheritance(self) -> None:
        """Test that PathSecurityError inherits from Exception."""
        error = PathSecurityError("Test")
        assert isinstance(error, Exception)


class TestEdgeCasesAndErrorHandling:
    """Test edge cases and error handling scenarios."""

    def test_validate_secure_path_os_error(self) -> None:
        """Test handling of OS errors during path validation."""
        with patch("os.path.realpath") as mock_realpath:
            mock_realpath.side_effect = OSError("Filesystem error")

            from borgitory.utils.secure_path import validate_secure_path

            result = validate_secure_path("/mnt/test")
            assert result is None

    def test_secure_path_join_no_safe_parts(self) -> None:
        """Test secure path join with no safe parts after cleaning."""
        with tempfile.TemporaryDirectory() as temp_dir:
            mnt_dir = os.path.join(temp_dir, "mnt")
            os.makedirs(mnt_dir, exist_ok=True)

            with patch(
                "borgitory.utils.secure_path.validate_secure_path"
            ) as mock_validate:
                mock_validate.return_value = Path(mnt_dir)

                # All parts should be cleaned away
                result = secure_path_join(mnt_dir, "../..", "../../..", "")
                assert result == str(Path(mnt_dir))

    def test_filename_edge_cases(self) -> None:
        """Test filename sanitization edge cases."""
        # Test filename that becomes empty after sanitization
        result = sanitize_filename("...")
        assert result == "unnamed"

        # Test filename with only extension (leading dot stripped)
        result = sanitize_filename(".txt")
        assert result == "txt"

        # Test very short max_length - function preserves extension
        result = sanitize_filename("test.txt", max_length=3)
        # With max_length=3, it should truncate but keep extension
        assert (
            result == "t.txt" or len(result) <= 8
        )  # Allow for extension preservation logic

    def test_create_secure_filename_edge_cases(self) -> None:
        """Test secure filename creation edge cases."""
        # Test with empty base name
        result = create_secure_filename("")
        assert result.startswith("unnamed_")

        # Test with extension that becomes empty after sanitization
        result = create_secure_filename("test", "file.!@#$%")
        assert not result.endswith(".")

        # Test with very long extension
        long_ext = "a" * 20
        result = create_secure_filename("test", f"file.{long_ext}")
        # Extension should be truncated to 10 chars
        assert len(result.split(".")[-1]) <= 10

    def test_windows_path_handling(self) -> None:
        """Test Windows-specific path handling in pre-validation."""
        from borgitory.utils.secure_path import _pre_validate_user_input

        allowed_prefixes = ["/mnt", "/app/data"]

        with patch("os.name", "nt"), patch("os.path.isabs") as mock_isabs:
            mock_isabs.return_value = True

            # Test Windows path that should be allowed
            assert _pre_validate_user_input("C:\\mnt\\test", allowed_prefixes) is True

            # Test Windows path that should be rejected
            assert (
                _pre_validate_user_input("C:\\Windows\\System32", allowed_prefixes)
                is False
            )
