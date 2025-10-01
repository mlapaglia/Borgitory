"""
Tests for PathService - Unified path service implementation.

These tests use proper dependency injection to avoid excessive patching.
"""

import pytest
import asyncio
from unittest.mock import Mock, patch
from typing import List, Optional

from borgitory.services.path.path_service import PathService
from borgitory.protocols.command_executor_protocol import CommandResult
from borgitory.protocols.path_protocols import PathConfigurationInterface


class MockPathConfiguration(PathConfigurationInterface):
    """Mock path configuration for testing."""

    def __init__(self, platform: str = "linux", is_docker: bool = False):
        self.platform = platform
        self._is_docker = is_docker

    def is_windows(self) -> bool:
        return self.platform == "windows"

    def is_linux(self) -> bool:
        return self.platform == "linux"

    def is_docker(self) -> bool:
        return self._is_docker

    def get_platform_name(self) -> str:
        if self._is_docker:
            return "docker"
        return self.platform

    def get_base_data_dir(self) -> str:
        if self._is_docker:
            return "/app/data"
        elif self.platform == "linux":
            return "/home/user/.local/share/borgitory"
        else:
            return "/unknown"

    def get_base_temp_dir(self) -> str:
        return "/tmp/borgitory"

    def get_base_cache_dir(self) -> str:
        if self._is_docker:
            return "/cache/borgitory"
        return "/home/user/.cache/borgitory"


class MockCommandExecutor:
    """Mock command executor for testing."""

    def __init__(self) -> None:
        self.commands_executed: List[List[str]] = []
        self.command_responses: dict[tuple[str, ...], CommandResult] = {}
        self.default_response = CommandResult(
            command=[],
            return_code=0,
            stdout="",
            stderr="",
            success=True,
            execution_time=0.1,
            error=None,
        )

    def set_command_response(self, command: List[str], response: CommandResult) -> None:
        """Set a specific response for a command."""
        self.command_responses[tuple(command)] = response

    async def execute_command(
        self,
        command: List[str],
        env: Optional[dict[str, str]] = None,
        cwd: Optional[str] = None,
        timeout: Optional[float] = None,
        input_data: Optional[str] = None,
    ) -> CommandResult:
        """Mock command execution."""
        self.commands_executed.append(command.copy())

        # Return specific response if configured
        command_key = tuple(command)
        if command_key in self.command_responses:
            return self.command_responses[command_key]

        # Return default response
        return CommandResult(
            command=command,
            return_code=0,
            stdout="",
            stderr="",
            success=True,
            execution_time=0.1,
            error=None,
        )

    async def create_subprocess(
        self,
        command: List[str],
        env: Optional[dict[str, str]] = None,
        cwd: Optional[str] = None,
        stdout: Optional[int] = None,
        stderr: Optional[int] = None,
        stdin: Optional[int] = None,
    ) -> asyncio.subprocess.Process:
        """Mock subprocess creation."""
        return Mock()

    def get_platform_name(self) -> str:
        """Get the platform name this executor handles."""
        return "mock"


@pytest.fixture
def mock_config_linux() -> MockPathConfiguration:
    """Mock configuration for Linux platform."""
    return MockPathConfiguration(platform="linux")


@pytest.fixture
def mock_config_windows() -> MockPathConfiguration:
    """Mock configuration for Windows platform."""
    return MockPathConfiguration(platform="windows")


@pytest.fixture
def mock_config_docker() -> MockPathConfiguration:
    """Mock configuration for Docker platform."""
    return MockPathConfiguration(platform="linux", is_docker=True)


@pytest.fixture
def mock_executor() -> MockCommandExecutor:
    """Mock command executor."""
    return MockCommandExecutor()


@pytest.fixture
def path_service_linux(
    mock_config_linux: MockPathConfiguration, mock_executor: MockCommandExecutor
) -> PathService:
    """PathService configured for Linux."""
    return PathService(config=mock_config_linux, command_executor=mock_executor)


@pytest.fixture
def path_service_windows(
    mock_config_windows: MockPathConfiguration, mock_executor: MockCommandExecutor
) -> PathService:
    """PathService configured for Windows."""
    return PathService(config=mock_config_windows, command_executor=mock_executor)


@pytest.fixture
def path_service_docker(
    mock_config_docker: MockPathConfiguration, mock_executor: MockCommandExecutor
) -> PathService:
    """PathService configured for Docker."""
    return PathService(config=mock_config_docker, command_executor=mock_executor)


class TestPathServiceBasicPaths:
    """Test basic path operations."""

    @pytest.mark.asyncio
    async def test_get_data_dir_linux(
        self, path_service_linux: PathService, mock_executor: MockCommandExecutor
    ) -> None:
        """Test getting data directory on Linux."""
        # Mock mkdir command
        mock_executor.set_command_response(
            ["mkdir", "-p", "/home/user/.local/share/borgitory"],
            CommandResult(
                command=["mkdir", "-p", "/home/user/.local/share/borgitory"],
                return_code=0,
                stdout="",
                stderr="",
                success=True,
                execution_time=0.1,
                error=None,
            ),
        )

        result = await path_service_linux.get_data_dir()

        assert result == "/home/user/.local/share/borgitory"
        assert [
            "mkdir",
            "-p",
            "/home/user/.local/share/borgitory",
        ] in mock_executor.commands_executed

    @pytest.mark.asyncio
    async def test_get_data_dir_windows(
        self, path_service_windows: PathService, mock_executor: MockCommandExecutor
    ) -> None:
        """Test getting data directory on Windows (WSL paths)."""
        with patch.object(
            path_service_windows, "_get_current_user", return_value="testuser"
        ):
            # Mock mkdir command
            expected_path = "/mnt/c/Users/testuser/.local/share/borgitory"
            mock_executor.set_command_response(
                ["mkdir", "-p", expected_path],
                CommandResult(
                    command=["mkdir", "-p", expected_path],
                    return_code=0,
                    stdout="",
                    stderr="",
                    success=True,
                    execution_time=0.1,
                    error=None,
                ),
            )

            result = await path_service_windows.get_data_dir()

            assert result == expected_path
            assert ["mkdir", "-p", expected_path] in mock_executor.commands_executed

    @pytest.mark.asyncio
    async def test_get_temp_dir_linux(
        self, path_service_linux: PathService, mock_executor: MockCommandExecutor
    ) -> None:
        """Test getting temp directory on Linux."""
        mock_executor.set_command_response(
            ["mkdir", "-p", "/tmp/borgitory"],
            CommandResult(
                command=["mkdir", "-p", "/tmp/borgitory"],
                return_code=0,
                stdout="",
                stderr="",
                success=True,
                execution_time=0.1,
                error=None,
            ),
        )

        result = await path_service_linux.get_temp_dir()

        assert result == "/tmp/borgitory"
        assert ["mkdir", "-p", "/tmp/borgitory"] in mock_executor.commands_executed

    @pytest.mark.asyncio
    async def test_get_cache_dir_docker(
        self, path_service_docker: PathService, mock_executor: MockCommandExecutor
    ) -> None:
        """Test getting cache directory in Docker."""
        mock_executor.set_command_response(
            ["mkdir", "-p", "/cache/borgitory"],
            CommandResult(
                command=["mkdir", "-p", "/cache/borgitory"],
                return_code=0,
                stdout="",
                stderr="",
                success=True,
                execution_time=0.1,
                error=None,
            ),
        )

        result = await path_service_docker.get_cache_dir()

        assert result == "/cache/borgitory"
        assert ["mkdir", "-p", "/cache/borgitory"] in mock_executor.commands_executed

    @pytest.mark.asyncio
    async def test_get_keyfiles_dir(
        self, path_service_linux: PathService, mock_executor: MockCommandExecutor
    ) -> None:
        """Test getting keyfiles directory."""
        # Mock mkdir commands for both data dir and keyfiles dir
        mock_executor.set_command_response(
            ["mkdir", "-p", "/home/user/.local/share/borgitory"],
            CommandResult(
                command=["mkdir", "-p", "/home/user/.local/share/borgitory"],
                return_code=0,
                stdout="",
                stderr="",
                success=True,
                execution_time=0.1,
                error=None,
            ),
        )
        mock_executor.set_command_response(
            ["mkdir", "-p", "/home/user/.local/share/borgitory/keyfiles"],
            CommandResult(
                command=["mkdir", "-p", "/home/user/.local/share/borgitory/keyfiles"],
                return_code=0,
                stdout="",
                stderr="",
                success=True,
                execution_time=0.1,
                error=None,
            ),
        )

        result = await path_service_linux.get_keyfiles_dir()

        assert result == "/home/user/.local/share/borgitory/keyfiles"
        assert [
            "mkdir",
            "-p",
            "/home/user/.local/share/borgitory/keyfiles",
        ] in mock_executor.commands_executed

    @pytest.mark.asyncio
    async def test_get_mount_base_dir(
        self, path_service_linux: PathService, mock_executor: MockCommandExecutor
    ) -> None:
        """Test getting mount base directory."""
        # Mock mkdir commands
        mock_executor.set_command_response(
            ["mkdir", "-p", "/tmp/borgitory"],
            CommandResult(
                command=["mkdir", "-p", "/tmp/borgitory"],
                return_code=0,
                stdout="",
                stderr="",
                success=True,
                execution_time=0.1,
                error=None,
            ),
        )
        mock_executor.set_command_response(
            ["mkdir", "-p", "/tmp/borgitory/borgitory-mounts"],
            CommandResult(
                command=["mkdir", "-p", "/tmp/borgitory/borgitory-mounts"],
                return_code=0,
                stdout="",
                stderr="",
                success=True,
                execution_time=0.1,
                error=None,
            ),
        )

        result = await path_service_linux.get_mount_base_dir()

        assert result == "/tmp/borgitory/borgitory-mounts"
        assert [
            "mkdir",
            "-p",
            "/tmp/borgitory/borgitory-mounts",
        ] in mock_executor.commands_executed


class TestSecureJoin:
    """Test secure path joining functionality."""

    def test_secure_join_basic(self, path_service_linux: PathService) -> None:
        """Test basic secure join operation."""
        result = path_service_linux.secure_join("/base", "subdir", "file.txt")
        assert result == "/base/subdir/file.txt"

    def test_secure_join_empty_base_raises_error(
        self, path_service_linux: PathService
    ) -> None:
        """Test that empty base path raises ValueError."""
        with pytest.raises(ValueError, match="Base path cannot be empty"):
            path_service_linux.secure_join("", "subdir")

    def test_secure_join_no_path_parts(self, path_service_linux: PathService) -> None:
        """Test secure join with no additional path parts."""
        result = path_service_linux.secure_join("/base/path")
        assert result == "/base/path"

    def test_secure_join_filters_empty_parts(
        self, path_service_linux: PathService
    ) -> None:
        """Test that empty path parts are filtered out."""
        result = path_service_linux.secure_join("/base", "", "subdir", "  ", "file.txt")
        assert result == "/base/subdir/file.txt"

    def test_secure_join_prevents_traversal(
        self, path_service_linux: PathService
    ) -> None:
        """Test that path traversal attempts are blocked."""
        with pytest.raises(ValueError, match="Invalid path operation"):
            path_service_linux.secure_join("/base", "../../../etc/passwd")

    def test_secure_join_prevents_absolute_injection(
        self, path_service_linux: PathService
    ) -> None:
        """Test that absolute path injection is blocked."""
        with pytest.raises(ValueError, match="Invalid path operation"):
            path_service_linux.secure_join("/base", "/etc/passwd")

    def test_secure_join_normalizes_paths(
        self, path_service_linux: PathService
    ) -> None:
        """Test that paths are properly normalized."""
        result = path_service_linux.secure_join("/base//path/", "./subdir/../file.txt")
        assert result == "/base/path/file.txt"


class TestFilesystemOperations:
    """Test filesystem operation methods."""

    @pytest.mark.asyncio
    async def test_path_exists_true(
        self, path_service_linux: PathService, mock_executor: MockCommandExecutor
    ) -> None:
        """Test path_exists returns True when path exists."""
        mock_executor.set_command_response(
            ["test", "-e", "/some/path"],
            CommandResult(
                command=["test", "-e", "/some/path"],
                return_code=0,
                stdout="",
                stderr="",
                success=True,
                execution_time=0.1,
                error=None,
            ),
        )

        result = await path_service_linux.path_exists("/some/path")

        assert result is True
        assert ["test", "-e", "/some/path"] in mock_executor.commands_executed

    @pytest.mark.asyncio
    async def test_path_exists_false(
        self, path_service_linux: PathService, mock_executor: MockCommandExecutor
    ) -> None:
        """Test path_exists returns False when path doesn't exist."""
        mock_executor.set_command_response(
            ["test", "-e", "/nonexistent/path"],
            CommandResult(
                command=["test", "-e", "/nonexistent/path"],
                return_code=1,
                stdout="",
                stderr="",
                success=False,
                execution_time=0.1,
                error="File not found",
            ),
        )

        result = await path_service_linux.path_exists("/nonexistent/path")

        assert result is False

    @pytest.mark.asyncio
    async def test_is_directory_true(
        self, path_service_linux: PathService, mock_executor: MockCommandExecutor
    ) -> None:
        """Test is_directory returns True for directories."""
        mock_executor.set_command_response(
            ["test", "-d", "/some/directory"],
            CommandResult(
                command=["test", "-d", "/some/directory"],
                return_code=0,
                stdout="",
                stderr="",
                success=True,
                execution_time=0.1,
                error=None,
            ),
        )

        result = await path_service_linux.is_directory("/some/directory")

        assert result is True

    @pytest.mark.asyncio
    async def test_is_directory_false(
        self, path_service_linux: PathService, mock_executor: MockCommandExecutor
    ) -> None:
        """Test is_directory returns False for files."""
        mock_executor.set_command_response(
            ["test", "-d", "/some/file.txt"],
            CommandResult(
                command=["test", "-d", "/some/file.txt"],
                return_code=1,
                stdout="",
                stderr="",
                success=False,
                execution_time=0.1,
                error="Not a directory",
            ),
        )

        result = await path_service_linux.is_directory("/some/file.txt")

        assert result is False

    @pytest.mark.asyncio
    async def test_ensure_directory_success(
        self, path_service_linux: PathService, mock_executor: MockCommandExecutor
    ) -> None:
        """Test ensure_directory creates directory successfully."""
        mock_executor.set_command_response(
            ["mkdir", "-p", "/new/directory"],
            CommandResult(
                command=["mkdir", "-p", "/new/directory"],
                return_code=0,
                stdout="",
                stderr="",
                success=True,
                execution_time=0.1,
                error=None,
            ),
        )

        # Should not raise exception
        await path_service_linux.ensure_directory("/new/directory")

        assert ["mkdir", "-p", "/new/directory"] in mock_executor.commands_executed

    @pytest.mark.asyncio
    async def test_ensure_directory_failure(
        self, path_service_linux: PathService, mock_executor: MockCommandExecutor
    ) -> None:
        """Test ensure_directory raises OSError on failure."""
        mock_executor.set_command_response(
            ["mkdir", "-p", "/protected/directory"],
            CommandResult(
                command=["mkdir", "-p", "/protected/directory"],
                return_code=1,
                stdout="",
                stderr="Permission denied",
                success=False,
                execution_time=0.1,
                error="Permission denied",
            ),
        )

        with pytest.raises(OSError, match="Failed to create directory"):
            await path_service_linux.ensure_directory("/protected/directory")

    @pytest.mark.asyncio
    async def test_ensure_directory_empty_path(
        self, path_service_linux: PathService, mock_executor: MockCommandExecutor
    ) -> None:
        """Test ensure_directory handles empty path gracefully."""
        # Should not execute any commands
        await path_service_linux.ensure_directory("")

        assert len(mock_executor.commands_executed) == 0


class TestListDirectory:
    """Test directory listing functionality."""

    @pytest.mark.asyncio
    async def test_list_directory_basic(
        self, path_service_linux: PathService, mock_executor: MockCommandExecutor
    ) -> None:
        """Test basic directory listing."""
        ls_output = """total 12
drwxr-xr-x 3 user user 4096 Jan  1 12:00 subdir1
drwxr-xr-x 2 user user 4096 Jan  1 12:00 subdir2
-rw-r--r-- 1 user user  100 Jan  1 12:00 file.txt"""

        mock_executor.set_command_response(
            ["ls", "-la", "/test/path"],
            CommandResult(
                command=["ls", "-la", "/test/path"],
                return_code=0,
                stdout=ls_output,
                stderr="",
                success=True,
                execution_time=0.1,
                error=None,
            ),
        )

        # Mock the batch check commands
        mock_executor.set_command_response(
            [
                "find",
                "/test/path/subdir1",
                "/test/path/subdir2",
                "-maxdepth",
                "1",
                "-name",
                "config",
                "-type",
                "f",
            ],
            CommandResult(
                command=[
                    "find",
                    "/test/path/subdir1",
                    "/test/path/subdir2",
                    "-maxdepth",
                    "1",
                    "-name",
                    "config",
                    "-type",
                    "f",
                ],
                return_code=0,
                stdout="",
                stderr="",
                success=True,
                execution_time=0.1,
                error=None,
            ),
        )

        result = await path_service_linux.list_directory(
            "/test/path", include_files=False
        )

        assert len(result) == 2  # Only directories, no files
        assert result[0].name == "subdir1"
        assert result[0].path == "/test/path/subdir1"
        assert result[1].name == "subdir2"
        assert result[1].path == "/test/path/subdir2"

    @pytest.mark.asyncio
    async def test_list_directory_with_files(
        self, path_service_linux: PathService, mock_executor: MockCommandExecutor
    ) -> None:
        """Test directory listing including files."""
        ls_output = """total 8
drwxr-xr-x 2 user user 4096 Jan  1 12:00 subdir
-rw-r--r-- 1 user user  100 Jan  1 12:00 file.txt"""

        mock_executor.set_command_response(
            ["ls", "-la", "/test/path"],
            CommandResult(
                command=["ls", "-la", "/test/path"],
                return_code=0,
                stdout=ls_output,
                stderr="",
                success=True,
                execution_time=0.1,
                error=None,
            ),
        )

        # Mock the batch check commands
        mock_executor.set_command_response(
            [
                "find",
                "/test/path/subdir",
                "-maxdepth",
                "1",
                "-name",
                "config",
                "-type",
                "f",
            ],
            CommandResult(
                command=[
                    "find",
                    "/test/path/subdir",
                    "-maxdepth",
                    "1",
                    "-name",
                    "config",
                    "-type",
                    "f",
                ],
                return_code=0,
                stdout="",
                stderr="",
                success=True,
                execution_time=0.1,
                error=None,
            ),
        )

        result = await path_service_linux.list_directory(
            "/test/path", include_files=True
        )

        assert len(result) == 2  # Directory and file
        # Directories should come first
        assert result[0].name == "subdir"
        assert result[1].name == "file.txt"

    @pytest.mark.asyncio
    async def test_list_directory_skips_hidden_files(
        self, path_service_linux: PathService, mock_executor: MockCommandExecutor
    ) -> None:
        """Test that hidden files are skipped."""
        ls_output = """total 8
drwxr-xr-x 2 user user 4096 Jan  1 12:00 .hidden_dir
-rw-r--r-- 1 user user  100 Jan  1 12:00 .hidden_file
drwxr-xr-x 2 user user 4096 Jan  1 12:00 visible_dir"""

        mock_executor.set_command_response(
            ["ls", "-la", "/test/path"],
            CommandResult(
                command=["ls", "-la", "/test/path"],
                return_code=0,
                stdout=ls_output,
                stderr="",
                success=True,
                execution_time=0.1,
                error=None,
            ),
        )

        # Mock the batch check commands
        mock_executor.set_command_response(
            [
                "find",
                "/test/path/visible_dir",
                "-maxdepth",
                "1",
                "-name",
                "config",
                "-type",
                "f",
            ],
            CommandResult(
                command=[
                    "find",
                    "/test/path/visible_dir",
                    "-maxdepth",
                    "1",
                    "-name",
                    "config",
                    "-type",
                    "f",
                ],
                return_code=0,
                stdout="",
                stderr="",
                success=True,
                execution_time=0.1,
                error=None,
            ),
        )

        result = await path_service_linux.list_directory(
            "/test/path", include_files=True
        )

        assert len(result) == 1
        assert result[0].name == "visible_dir"

    @pytest.mark.asyncio
    async def test_list_directory_failure(
        self, path_service_linux: PathService, mock_executor: MockCommandExecutor
    ) -> None:
        """Test directory listing failure handling."""
        mock_executor.set_command_response(
            ["ls", "-la", "/nonexistent"],
            CommandResult(
                command=["ls", "-la", "/nonexistent"],
                return_code=1,
                stdout="",
                stderr="No such file or directory",
                success=False,
                execution_time=0.1,
                error="No such file or directory",
            ),
        )

        result = await path_service_linux.list_directory("/nonexistent")

        assert result == []


class TestBorgDetection:
    """Test Borg repository and cache detection."""

    @pytest.mark.asyncio
    async def test_batch_check_borg_repositories(
        self, path_service_linux: PathService, mock_executor: MockCommandExecutor
    ) -> None:
        """Test batch checking for Borg repositories."""
        ls_output = """total 8
drwxr-xr-x 2 user user 4096 Jan  1 12:00 repo1
drwxr-xr-x 2 user user 4096 Jan  1 12:00 repo2"""

        mock_executor.set_command_response(
            ["ls", "-la", "/test/path"],
            CommandResult(
                command=["ls", "-la", "/test/path"],
                return_code=0,
                stdout=ls_output,
                stderr="",
                success=True,
                execution_time=0.1,
                error=None,
            ),
        )

        # Mock find command to return config files
        mock_executor.set_command_response(
            [
                "find",
                "/test/path/repo1",
                "/test/path/repo2",
                "-maxdepth",
                "1",
                "-name",
                "config",
                "-type",
                "f",
            ],
            CommandResult(
                command=[
                    "find",
                    "/test/path/repo1",
                    "/test/path/repo2",
                    "-maxdepth",
                    "1",
                    "-name",
                    "config",
                    "-type",
                    "f",
                ],
                return_code=0,
                stdout="/test/path/repo1/config\n/test/path/repo2/config",
                stderr="",
                success=True,
                execution_time=0.1,
                error=None,
            ),
        )

        # Mock grep for repository sections
        mock_executor.set_command_response(
            [
                "grep",
                "-l",
                "^\\[repository\\]",
                "/test/path/repo1/config",
                "/test/path/repo2/config",
            ],
            CommandResult(
                command=[
                    "grep",
                    "-l",
                    "^\\[repository\\]",
                    "/test/path/repo1/config",
                    "/test/path/repo2/config",
                ],
                return_code=0,
                stdout="/test/path/repo1/config",
                stderr="",
                success=True,
                execution_time=0.1,
                error=None,
            ),
        )

        # Mock grep for cache sections
        mock_executor.set_command_response(
            [
                "grep",
                "-l",
                "^\\[cache\\]",
                "/test/path/repo1/config",
                "/test/path/repo2/config",
            ],
            CommandResult(
                command=[
                    "grep",
                    "-l",
                    "^\\[cache\\]",
                    "/test/path/repo1/config",
                    "/test/path/repo2/config",
                ],
                return_code=0,
                stdout="/test/path/repo2/config",
                stderr="",
                success=True,
                execution_time=0.1,
                error=None,
            ),
        )

        result = await path_service_linux.list_directory("/test/path")

        assert len(result) == 2

        # Find repo1 and repo2 in results
        repo1 = next((r for r in result if r.name == "repo1"), None)
        repo2 = next((r for r in result if r.name == "repo2"), None)

        assert repo1 is not None
        assert repo2 is not None

        # repo1 should be marked as Borg repository
        assert repo1.is_borg_repo is True
        assert repo1.is_borg_cache is False

        # repo2 should be marked as Borg cache
        assert repo2.is_borg_repo is False
        assert repo2.is_borg_cache is True


class TestPlatformMethods:
    """Test platform-specific methods."""

    def test_get_platform_name(self, path_service_linux: PathService) -> None:
        """Test getting platform name."""
        result = path_service_linux.get_platform_name()
        assert result == "linux"

    def test_get_current_user_with_env(self, path_service_windows: PathService) -> None:
        """Test getting current user from environment."""
        with patch.dict("os.environ", {"USERNAME": "testuser"}):
            result = path_service_windows._get_current_user()
            assert result == "testuser"

    def test_get_current_user_default(self, path_service_windows: PathService) -> None:
        """Test getting current user with default fallback."""
        with patch.dict("os.environ", {}, clear=True):
            result = path_service_windows._get_current_user()
            assert result == "user"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
