"""
Comprehensive tests for secure_path utilities.

Tests all functions in the secure_path module to ensure they handle
various edge cases and security scenarios correctly.
"""

import os
import tempfile
from pathlib import Path
from unittest.mock import patch
from typing import IO, Optional
from contextlib import asynccontextmanager
import io

from borgitory.protocols.file_protocols import FileServiceProtocol
from borgitory.utils.secure_path import (
    DirectoryInfo,
    _is_borg_repository,
    _is_borg_cache,
    sanitize_filename,
    create_secure_filename,
    secure_path_join,
    secure_exists,
    secure_isdir,
    secure_remove_file,
    get_directory_listing,
)


class MockFileService(FileServiceProtocol):
    """Mock implementation of FileServiceProtocol for testing."""

    def __init__(self) -> None:
        self.mock_files: dict[str, bytes] = {}
        self.mock_errors: dict[str, Exception] = {}
        self.mock_exists: dict[str, bool] = {}
        self.mock_isfile: dict[str, bool] = {}

    @asynccontextmanager
    async def create_temp_file(self, suffix: str, content: Optional[bytes] = None):
        """Create a temporary file with optional content."""
        temp_file = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
        temp_path = temp_file.name

        try:
            if content is not None:
                temp_file.write(content)
            temp_file.close()

            yield temp_path
        finally:
            try:
                os.unlink(temp_path)
            except OSError:
                pass

    async def open_file(self, file_path: str, mode: str) -> IO[bytes]:
        """Mock file opening with configurable content and errors."""
        if file_path in self.mock_errors:
            raise self.mock_errors[file_path]

        content = self.mock_files.get(file_path, b"")
        return io.BytesIO(content)

    async def write_file(self, file_path: str, content: bytes) -> None:
        """Mock file writing."""
        self.mock_files[file_path] = content

    async def remove_file(self, file_path: str) -> None:
        """Mock file removal."""
        if file_path in self.mock_files:
            del self.mock_files[file_path]

    async def exists(self, file_path: str) -> bool:
        """Mock file existence check."""
        if file_path in self.mock_exists:
            return self.mock_exists[file_path]
        return file_path in self.mock_files

    async def isfile(self, file_path: str) -> bool:
        """Mock file type check."""
        if file_path in self.mock_isfile:
            return self.mock_isfile[file_path]
        return file_path in self.mock_files

    def get_platform_name(self) -> str:
        """Get the platform name this file service handles."""
        return "linux"


class TestDirectoryInfo:
    """Test the DirectoryInfo dataclass."""

    def test_directory_info_creation(self) -> None:
        """Test basic DirectoryInfo creation."""
        info = DirectoryInfo(name="test", path="/test/path")
        assert info.name == "test"
        assert info.path == "/test/path"
        assert info.is_borg_repo is False
        assert info.is_borg_cache is False

    def test_directory_info_with_flags(self) -> None:
        """Test DirectoryInfo creation with borg flags."""
        info = DirectoryInfo(
            name="repo", path="/repo/path", is_borg_repo=True, is_borg_cache=True
        )
        assert info.name == "repo"
        assert info.path == "/repo/path"
        assert info.is_borg_repo is True
        assert info.is_borg_cache is True


class TestIsBorgRepository:
    """Test the _is_borg_repository function."""

    async def test_is_borg_repository_with_valid_config(self) -> None:
        """Test detection of valid borg repository."""
        file_service = MockFileService()
        config_content = """
[repository]
version = 1
segments_per_dir = 1000
"""
        # Use os.path.join to get the correct path format for the current OS
        config_path = os.path.join("/test/repo", "config")
        file_service.mock_files[config_path] = config_content.encode("utf-8")
        file_service.mock_exists[config_path] = True
        file_service.mock_isfile[config_path] = True

        assert await _is_borg_repository("/test/repo", file_service) is True

    async def test_is_borg_repository_no_config_file(self) -> None:
        """Test with missing config file."""
        file_service = MockFileService()
        config_path = os.path.join("/test/repo", "config")
        file_service.mock_exists[config_path] = False

        assert await _is_borg_repository("/test/repo", file_service) is False

    async def test_is_borg_repository_config_is_directory(self) -> None:
        """Test with config being a directory instead of file."""
        file_service = MockFileService()
        config_path = os.path.join("/test/repo", "config")
        file_service.mock_exists[config_path] = True
        file_service.mock_isfile[config_path] = False

        assert await _is_borg_repository("/test/repo", file_service) is False

    async def test_is_borg_repository_no_repository_section(self) -> None:
        """Test with config file missing [repository] section."""
        file_service = MockFileService()
        config_content = """
[cache]
version = 1
"""
        config_path = os.path.join("/test/repo", "config")
        file_service.mock_files[config_path] = config_content.encode("utf-8")
        file_service.mock_exists[config_path] = True
        file_service.mock_isfile[config_path] = True

        assert await _is_borg_repository("/test/repo", file_service) is False

    async def test_is_borg_repository_invalid_config(self) -> None:
        """Test with invalid config file content."""
        file_service = MockFileService()
        config_content = "invalid config content"
        config_path = os.path.join("/test/repo", "config")
        file_service.mock_files[config_path] = config_content.encode("utf-8")
        file_service.mock_exists[config_path] = True
        file_service.mock_isfile[config_path] = True

        assert await _is_borg_repository("/test/repo", file_service) is False

    async def test_is_borg_repository_permission_error(self) -> None:
        """Test handling of permission errors."""
        file_service = MockFileService()
        config_path = os.path.join("/test/repo", "config")
        file_service.mock_errors[config_path] = PermissionError("Access denied")
        file_service.mock_exists[config_path] = True
        file_service.mock_isfile[config_path] = True

        assert await _is_borg_repository("/test/repo", file_service) is False

    async def test_is_borg_repository_unicode_error(self) -> None:
        """Test handling of unicode decode errors."""
        file_service = MockFileService()
        config_path = os.path.join("/test/repo", "config")
        file_service.mock_errors[config_path] = UnicodeDecodeError(
            "utf-8", b"", 0, 1, "invalid"
        )
        file_service.mock_exists[config_path] = True
        file_service.mock_isfile[config_path] = True

        assert await _is_borg_repository("/test/repo", file_service) is False

    async def test_is_borg_repository_general_exception(self) -> None:
        """Test handling of general exceptions."""
        file_service = MockFileService()

        # Mock the exists method to raise an exception
        async def mock_exists_raises(file_path: str) -> bool:
            raise Exception("General error")

        file_service.exists = mock_exists_raises

        assert await _is_borg_repository("/test/repo", file_service) is False


class TestIsBorgCache:
    """Test the _is_borg_cache function."""

    async def test_is_borg_cache_with_valid_config(self) -> None:
        """Test detection of valid borg cache."""
        file_service = MockFileService()
        config_content = """
[cache]
version = 1
repository = /path/to/repo
"""
        config_path = os.path.join("/test/cache", "config")
        file_service.mock_files[config_path] = config_content.encode("utf-8")
        file_service.mock_exists[config_path] = True
        file_service.mock_isfile[config_path] = True

        assert await _is_borg_cache("/test/cache", file_service) is True

    async def test_is_borg_cache_no_config_file(self) -> None:
        """Test with missing config file."""
        file_service = MockFileService()
        config_path = os.path.join("/test/cache", "config")
        file_service.mock_exists[config_path] = False

        assert await _is_borg_cache("/test/cache", file_service) is False

    async def test_is_borg_cache_no_cache_section(self) -> None:
        """Test with config file missing [cache] section."""
        file_service = MockFileService()
        config_content = """
[repository]
version = 1
"""
        config_path = os.path.join("/test/cache", "config")
        file_service.mock_files[config_path] = config_content.encode("utf-8")
        file_service.mock_exists[config_path] = True
        file_service.mock_isfile[config_path] = True

        assert await _is_borg_cache("/test/cache", file_service) is False

    async def test_is_borg_cache_permission_error(self) -> None:
        """Test handling of permission errors."""
        file_service = MockFileService()
        config_path = os.path.join("/test/cache", "config")
        file_service.mock_errors[config_path] = PermissionError("Access denied")
        file_service.mock_exists[config_path] = True
        file_service.mock_isfile[config_path] = True

        assert await _is_borg_cache("/test/cache", file_service) is False


class TestSanitizeFilename:
    """Test the sanitize_filename function."""

    def test_sanitize_filename_basic(self) -> None:
        """Test basic filename sanitization."""
        result = sanitize_filename("test_file.txt")
        assert result == "test_file.txt"

    def test_sanitize_filename_dangerous_chars(self) -> None:
        """Test sanitization of dangerous characters."""
        result = sanitize_filename("test/../file.txt")
        assert result == "test_._file.txt"

    def test_sanitize_filename_special_chars(self) -> None:
        """Test sanitization of various special characters."""
        result = sanitize_filename("test@#$%^&*()file.txt")
        assert result == "test_________file.txt"

    def test_sanitize_filename_multiple_dots(self) -> None:
        """Test handling of multiple consecutive dots."""
        result = sanitize_filename("test...file.txt")
        assert result == "test.file.txt"

    def test_sanitize_filename_leading_trailing_dots_spaces(self) -> None:
        """Test removal of leading/trailing dots and spaces."""
        result = sanitize_filename("  .test_file.  ")
        # Spaces become underscores, dots and spaces are stripped but underscores remain
        assert result == "__.test_file.__"

    def test_sanitize_filename_empty_string(self) -> None:
        """Test handling of empty string."""
        result = sanitize_filename("")
        assert result == "unnamed"

    def test_sanitize_filename_only_special_chars(self) -> None:
        """Test filename with only special characters."""
        result = sanitize_filename("@#$%^&*()")
        # Special chars become underscores, but underscores are not stripped
        assert result == "_________"

    def test_sanitize_filename_max_length(self) -> None:
        """Test filename length truncation."""
        long_name = "a" * 150 + ".txt"
        result = sanitize_filename(long_name, max_length=100)
        assert len(result) == 100
        assert result.endswith(".txt")

    def test_sanitize_filename_max_length_no_extension(self) -> None:
        """Test filename length truncation without extension."""
        long_name = "a" * 150
        result = sanitize_filename(long_name, max_length=50)
        assert len(result) == 50


class TestCreateSecureFilename:
    """Test the create_secure_filename function."""

    def test_create_secure_filename_basic(self) -> None:
        """Test basic secure filename creation."""
        result = create_secure_filename("test", "original.txt")
        assert result.startswith("test_")
        assert result.endswith(".txt")
        assert len(result.split("_")[1].split(".")[0]) == 8  # UUID length

    def test_create_secure_filename_no_uuid(self) -> None:
        """Test secure filename creation without UUID."""
        result = create_secure_filename("test", "original.txt", add_uuid=False)
        assert result == "test.txt"

    def test_create_secure_filename_no_extension(self) -> None:
        """Test secure filename creation without extension."""
        result = create_secure_filename("test", "", add_uuid=False)
        assert result == "test"

    def test_create_secure_filename_invalid_extension(self) -> None:
        """Test handling of invalid extension characters."""
        result = create_secure_filename("test", "file.@#$", add_uuid=False)
        assert result == "test"

    def test_create_secure_filename_long_extension(self) -> None:
        """Test truncation of long extensions."""
        result = create_secure_filename(
            "test", "file.verylongextension", add_uuid=False
        )
        assert result == "test.verylongex"  # Extension truncated to 10 chars

    def test_create_secure_filename_dangerous_base_name(self) -> None:
        """Test sanitization of dangerous base name."""
        result = create_secure_filename("../test", "file.txt", add_uuid=False)
        assert result == "_test.txt"


class TestSecurePathJoin:
    """Test the secure_path_join function."""

    def test_secure_path_join_basic(self) -> None:
        """Test basic path joining."""
        result = secure_path_join("/base", "subdir", "file.txt")
        expected = str(Path("/base") / "subdir" / "file.txt")
        assert result == expected

    def test_secure_path_join_traversal_attack(self) -> None:
        """Test prevention of directory traversal attacks."""
        result = secure_path_join("/base", "../../../etc", "passwd")
        # Should remove the traversal sequences
        expected = str(Path("/base") / "etc" / "passwd")
        assert result == expected

    def test_secure_path_join_empty_parts(self) -> None:
        """Test handling of empty path parts."""
        result = secure_path_join("/base", "", "subdir", "", "file.txt")
        expected = str(Path("/base") / "subdir" / "file.txt")
        assert result == expected

    def test_secure_path_join_no_parts(self) -> None:
        """Test with no additional path parts."""
        result = secure_path_join("/base")
        # On Windows, paths get converted to backslashes
        expected = str(Path("/base"))
        assert result == expected

    def test_secure_path_join_all_empty_parts(self) -> None:
        """Test with all empty path parts."""
        result = secure_path_join("/base", "", "", "")
        # On Windows, paths get converted to backslashes
        expected = str(Path("/base"))
        assert result == expected


class TestSecureExists:
    """Test the secure_exists function."""

    def test_secure_exists_existing_path(self) -> None:
        """Test with existing path."""
        with tempfile.TemporaryDirectory() as temp_dir:
            assert secure_exists(temp_dir) is True

    def test_secure_exists_non_existing_path(self) -> None:
        """Test with non-existing path."""
        assert secure_exists("/non/existing/path") is False

    def test_secure_exists_permission_error(self) -> None:
        """Test handling of permission errors."""
        with patch.object(Path, "exists", side_effect=PermissionError("Access denied")):
            assert secure_exists("/test/path") is False

    def test_secure_exists_os_error(self) -> None:
        """Test handling of OS errors."""
        with patch.object(Path, "exists", side_effect=OSError("OS error")):
            assert secure_exists("/test/path") is False


class TestSecureIsdir:
    """Test the secure_isdir function."""

    def test_secure_isdir_existing_directory(self) -> None:
        """Test with existing directory."""
        with tempfile.TemporaryDirectory() as temp_dir:
            assert secure_isdir(temp_dir) is True

    def test_secure_isdir_existing_file(self) -> None:
        """Test with existing file (not directory)."""
        with tempfile.NamedTemporaryFile() as temp_file:
            assert secure_isdir(temp_file.name) is False

    def test_secure_isdir_non_existing_path(self) -> None:
        """Test with non-existing path."""
        assert secure_isdir("/non/existing/path") is False

    def test_secure_isdir_permission_error(self) -> None:
        """Test handling of permission errors."""
        with patch.object(Path, "is_dir", side_effect=PermissionError("Access denied")):
            assert secure_isdir("/test/path") is False


class TestSecureRemoveFile:
    """Test the secure_remove_file function."""

    def test_secure_remove_file_existing_file(self) -> None:
        """Test removing an existing file."""
        with tempfile.NamedTemporaryFile(delete=False) as temp_file:
            temp_path = temp_file.name

        assert os.path.exists(temp_path)
        result = secure_remove_file(temp_path)
        assert result is True
        assert not os.path.exists(temp_path)

    def test_secure_remove_file_non_existing_file(self) -> None:
        """Test removing a non-existing file."""
        result = secure_remove_file("/non/existing/file.txt")
        assert result is True  # Should return True even if file doesn't exist

    def test_secure_remove_file_permission_error(self) -> None:
        """Test handling of permission errors."""
        with (
            patch.object(Path, "exists", return_value=True),
            patch.object(Path, "unlink", side_effect=PermissionError("Access denied")),
        ):
            result = secure_remove_file("/test/file.txt")
            assert result is False

    def test_secure_remove_file_os_error(self) -> None:
        """Test handling of OS errors."""
        with (
            patch.object(Path, "exists", return_value=True),
            patch.object(Path, "unlink", side_effect=OSError("OS error")),
        ):
            result = secure_remove_file("/test/file.txt")
            assert result is False


class TestGetDirectoryListing:
    """Test the get_directory_listing function."""

    async def test_get_directory_listing_basic(self) -> None:
        """Test basic directory listing."""
        file_service = MockFileService()

        with tempfile.TemporaryDirectory() as temp_dir:
            # Create test directories
            subdir1 = Path(temp_dir) / "subdir1"
            subdir2 = Path(temp_dir) / "subdir2"
            subdir1.mkdir()
            subdir2.mkdir()

            # Create a test file
            test_file = Path(temp_dir) / "test.txt"
            test_file.write_text("test")

            result = await get_directory_listing(temp_dir, file_service)

            assert len(result) == 2  # Only directories by default
            dir_names = [item.name for item in result]
            assert "subdir1" in dir_names
            assert "subdir2" in dir_names

    async def test_get_directory_listing_include_files(self) -> None:
        """Test directory listing including files."""
        file_service = MockFileService()

        with tempfile.TemporaryDirectory() as temp_dir:
            # Create test directory and file
            subdir = Path(temp_dir) / "subdir"
            subdir.mkdir()
            test_file = Path(temp_dir) / "test.txt"
            test_file.write_text("test")

            result = await get_directory_listing(
                temp_dir, file_service, include_files=True
            )

            assert len(result) == 2  # Directory + file
            names = [item.name for item in result]
            assert "subdir" in names
            assert "test.txt" in names

    async def test_get_directory_listing_borg_repo(self) -> None:
        """Test detection of borg repositories."""
        file_service = MockFileService()

        with tempfile.TemporaryDirectory() as temp_dir:
            # Create a mock borg repository
            repo_dir = Path(temp_dir) / "borg_repo"
            repo_dir.mkdir()
            config_file = repo_dir / "config"
            config_file.write_text("[repository]\nversion = 1\n")

            # Set up the mock file service to return the config content
            file_service.mock_files[str(config_file)] = (
                "[repository]\nversion = 1\n".encode("utf-8")
            )

            result = await get_directory_listing(temp_dir, file_service)

            assert len(result) == 1
            assert result[0].name == "borg_repo"
            assert result[0].is_borg_repo is True
            assert result[0].is_borg_cache is False

    async def test_get_directory_listing_borg_cache(self) -> None:
        """Test detection of borg caches."""
        file_service = MockFileService()

        with tempfile.TemporaryDirectory() as temp_dir:
            # Create a mock borg cache
            cache_dir = Path(temp_dir) / "borg_cache"
            cache_dir.mkdir()
            config_file = cache_dir / "config"
            config_file.write_text("[cache]\nversion = 1\n")

            # Set up the mock file service to return the config content
            file_service.mock_files[str(config_file)] = "[cache]\nversion = 1\n".encode(
                "utf-8"
            )

            result = await get_directory_listing(temp_dir, file_service)

            assert len(result) == 1
            assert result[0].name == "borg_cache"
            assert result[0].is_borg_repo is False
            assert result[0].is_borg_cache is True

    async def test_get_directory_listing_non_directory(self) -> None:
        """Test with non-directory path."""
        file_service = MockFileService()

        with tempfile.NamedTemporaryFile() as temp_file:
            result = await get_directory_listing(temp_file.name, file_service)
            assert result == []

    async def test_get_directory_listing_permission_error(self) -> None:
        """Test handling of permission errors."""
        file_service = MockFileService()

        with (
            patch.object(Path, "is_dir", return_value=True),
            patch.object(Path, "iterdir", side_effect=PermissionError("Access denied")),
        ):
            result = await get_directory_listing("/test/path", file_service)
            assert result == []

    async def test_get_directory_listing_sorted(self) -> None:
        """Test that results are sorted alphabetically."""
        file_service = MockFileService()

        with tempfile.TemporaryDirectory() as temp_dir:
            # Create directories in non-alphabetical order
            dirs = ["zebra", "apple", "banana"]
            for dir_name in dirs:
                (Path(temp_dir) / dir_name).mkdir()

            result = await get_directory_listing(temp_dir, file_service)

            names = [item.name for item in result]
            assert names == ["apple", "banana", "zebra"]
