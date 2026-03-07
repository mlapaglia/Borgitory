"""
Comprehensive happy path tests for PathService.

These tests cover successful scenarios for all PathService methods,
ensuring the service works correctly under normal conditions.
"""

import pytest
from typing import List, Any
from unittest.mock import Mock, AsyncMock

from borgitory.services.path.path_service import PathService
from borgitory.protocols.command_executor_protocol import CommandExecutorProtocol
from borgitory.protocols.command_protocols import CommandResult
from borgitory.models.borg_info import BorgDefaultDirectories
from borgitory.utils.secure_path import DirectoryInfo


@pytest.fixture
def mock_command_executor() -> Mock:
    """Create mock command executor for testing."""
    mock = Mock(spec=CommandExecutorProtocol)
    mock.execute_command = AsyncMock()
    return mock


@pytest.fixture
def path_service(mock_command_executor: Mock) -> PathService:
    """Create PathService with mocked dependencies."""
    return PathService(command_executor=mock_command_executor)


class TestSecureJoin:
    """Test secure_join method - happy paths."""

    def test_join_simple_paths(self, path_service: PathService) -> None:
        """Test joining simple path components."""
        result = path_service.secure_join("/home/user", "documents")
        assert result == "/home/user/documents"

    def test_join_multiple_components(self, path_service: PathService) -> None:
        """Test joining multiple path components at once."""
        result = path_service.secure_join("/home/user", "documents", "work", "projects")
        assert result == "/home/user/documents/work/projects"

    def test_join_with_trailing_slash(self, path_service: PathService) -> None:
        """Test joining when base path has trailing slash."""
        result = path_service.secure_join("/home/user/", "documents")
        assert result == "/home/user/documents"

    def test_join_absolute_base_path(self, path_service: PathService) -> None:
        """Test joining with absolute base path."""
        result = path_service.secure_join("/var/lib/borg", "repos", "backup1")
        assert result == "/var/lib/borg/repos/backup1"

    def test_join_relative_paths(self, path_service: PathService) -> None:
        """Test joining relative path components."""
        result = path_service.secure_join("backups", "2024", "january")
        assert "backups/2024/january" in result

    def test_join_deep_nested_structure(self, path_service: PathService) -> None:
        """Test joining deeply nested directory structure."""
        result = path_service.secure_join(
            "/opt/backups",
            "year",
            "month",
            "week",
            "day",
            "hour",
            "archive.tar",
        )
        assert result == "/opt/backups/year/month/week/day/hour/archive.tar"

    def test_join_with_empty_components_filtered(
        self, path_service: PathService
    ) -> None:
        """Test that empty path components are filtered out."""
        result = path_service.secure_join("/base", "", "path", "", "file")
        assert result == "/base/path/file"

    def test_join_normalizes_redundant_separators(
        self, path_service: PathService
    ) -> None:
        """Test that redundant separators are normalized."""
        result = path_service.secure_join("/home//user", "documents")
        assert "//" not in result
        assert result == "/home/user/documents"

    def test_join_handles_dot_segments_safely(self, path_service: PathService) -> None:
        """Test that single dot segments are normalized."""
        result = path_service.secure_join("/home/user", "./documents")
        assert result == "/home/user/documents"

    def test_join_unix_style_paths(self, path_service: PathService) -> None:
        """Test Unix-style path conventions."""
        result = path_service.secure_join("/mnt/storage", "backups", "borg")
        assert result == "/mnt/storage/backups/borg"


class TestPathExists:
    """Test path_exists method - happy paths."""

    @pytest.mark.asyncio
    async def test_existing_file(
        self, path_service: PathService, mock_command_executor: Mock
    ) -> None:
        """Test checking an existing file."""
        mock_command_executor.execute_command.return_value = CommandResult(
            success=True, return_code=0, stdout="", stderr="", duration=0.1
        )

        result = await path_service.path_exists("/home/user/file.txt")

        assert result is True
        mock_command_executor.execute_command.assert_called_once()
        call_args = mock_command_executor.execute_command.call_args[0][0]
        assert call_args == ["test", "-e", "/home/user/file.txt"]

    @pytest.mark.asyncio
    async def test_existing_directory(
        self, path_service: PathService, mock_command_executor: Mock
    ) -> None:
        """Test checking an existing directory."""
        mock_command_executor.execute_command.return_value = CommandResult(
            success=True, return_code=0, stdout="", stderr="", duration=0.1
        )

        result = await path_service.path_exists("/home/user/documents")

        assert result is True

    @pytest.mark.asyncio
    async def test_existing_hidden_file(
        self, path_service: PathService, mock_command_executor: Mock
    ) -> None:
        """Test checking an existing hidden file."""
        mock_command_executor.execute_command.return_value = CommandResult(
            success=True, return_code=0, stdout="", stderr="", duration=0.1
        )

        result = await path_service.path_exists("/home/user/.bashrc")

        assert result is True

    @pytest.mark.asyncio
    async def test_existing_symlink(
        self, path_service: PathService, mock_command_executor: Mock
    ) -> None:
        """Test checking an existing symbolic link."""
        mock_command_executor.execute_command.return_value = CommandResult(
            success=True, return_code=0, stdout="", stderr="", duration=0.1
        )

        result = await path_service.path_exists("/usr/bin/python3")

        assert result is True

    @pytest.mark.asyncio
    async def test_existing_deep_nested_path(
        self, path_service: PathService, mock_command_executor: Mock
    ) -> None:
        """Test checking a deeply nested existing path."""
        mock_command_executor.execute_command.return_value = CommandResult(
            success=True, return_code=0, stdout="", stderr="", duration=0.1
        )

        result = await path_service.path_exists(
            "/var/lib/borg/repos/server1/archives/2024/archive.tar"
        )

        assert result is True


class TestIsDirectory:
    """Test is_directory method - happy paths."""

    @pytest.mark.asyncio
    async def test_valid_directory(
        self, path_service: PathService, mock_command_executor: Mock
    ) -> None:
        """Test checking a valid directory."""
        mock_command_executor.execute_command.return_value = CommandResult(
            success=True, return_code=0, stdout="", stderr="", duration=0.1
        )

        result = await path_service.is_directory("/home/user/documents")

        assert result is True
        call_args = mock_command_executor.execute_command.call_args[0][0]
        assert call_args == ["test", "-d", "/home/user/documents"]

    @pytest.mark.asyncio
    async def test_root_directory(
        self, path_service: PathService, mock_command_executor: Mock
    ) -> None:
        """Test checking root directory."""
        mock_command_executor.execute_command.return_value = CommandResult(
            success=True, return_code=0, stdout="", stderr="", duration=0.1
        )

        result = await path_service.is_directory("/")

        assert result is True

    @pytest.mark.asyncio
    async def test_hidden_directory(
        self, path_service: PathService, mock_command_executor: Mock
    ) -> None:
        """Test checking a hidden directory."""
        mock_command_executor.execute_command.return_value = CommandResult(
            success=True, return_code=0, stdout="", stderr="", duration=0.1
        )

        result = await path_service.is_directory("/home/user/.config")

        assert result is True

    @pytest.mark.asyncio
    async def test_nested_directory(
        self, path_service: PathService, mock_command_executor: Mock
    ) -> None:
        """Test checking a deeply nested directory."""
        mock_command_executor.execute_command.return_value = CommandResult(
            success=True, return_code=0, stdout="", stderr="", duration=0.1
        )

        result = await path_service.is_directory("/opt/backups/borg/repos/server1")

        assert result is True

    @pytest.mark.asyncio
    async def test_mount_point_directory(
        self, path_service: PathService, mock_command_executor: Mock
    ) -> None:
        """Test checking a mount point directory."""
        mock_command_executor.execute_command.return_value = CommandResult(
            success=True, return_code=0, stdout="", stderr="", duration=0.1
        )

        result = await path_service.is_directory("/mnt/backup-drive")

        assert result is True


class TestListDirectory:
    """Test list_directory method - happy paths."""

    @pytest.mark.asyncio
    async def test_list_simple_directory(
        self, path_service: PathService, mock_command_executor: Mock
    ) -> None:
        """Test listing a simple directory with subdirectories."""
        ls_output = """total 12
drwxr-xr-x 2 user user 4096 Jan 15 10:00 documents
drwxr-xr-x 2 user user 4096 Jan 15 11:00 downloads
drwxr-xr-x 2 user user 4096 Jan 15 12:00 pictures
"""
        mock_command_executor.execute_command.return_value = CommandResult(
            success=True, return_code=0, stdout=ls_output, stderr="", duration=0.2
        )

        result = await path_service.list_directory("/home/user")

        assert len(result) == 3
        assert result[0].name == "documents"
        assert result[1].name == "downloads"
        assert result[2].name == "pictures"
        assert all(isinstance(item, DirectoryInfo) for item in result)

    @pytest.mark.asyncio
    async def test_list_directory_with_files(
        self, path_service: PathService, mock_command_executor: Mock
    ) -> None:
        """Test listing directory including files."""
        ls_output = """total 24
drwxr-xr-x 2 user user 4096 Jan 15 10:00 documents
-rw-r--r-- 1 user user 1234 Jan 15 11:00 readme.txt
-rw-r--r-- 1 user user 5678 Jan 15 12:00 data.json
drwxr-xr-x 2 user user 4096 Jan 15 13:00 backups
"""
        mock_command_executor.execute_command.return_value = CommandResult(
            success=True, return_code=0, stdout=ls_output, stderr="", duration=0.2
        )

        result = await path_service.list_directory("/home/user", include_files=True)

        assert len(result) == 4
        dir_names = [item.name for item in result]
        assert "documents" in dir_names
        assert "readme.txt" in dir_names
        assert "data.json" in dir_names
        assert "backups" in dir_names

    @pytest.mark.asyncio
    async def test_list_directory_sorted(
        self, path_service: PathService, mock_command_executor: Mock
    ) -> None:
        """Test that directory listing is properly sorted (directories first)."""
        ls_output = """total 24
-rw-r--r-- 1 user user 1234 Jan 15 11:00 zebra.txt
drwxr-xr-x 2 user user 4096 Jan 15 10:00 alpha
-rw-r--r-- 1 user user 5678 Jan 15 12:00 beta.json
drwxr-xr-x 2 user user 4096 Jan 15 13:00 gamma
"""
        mock_command_executor.execute_command.return_value = CommandResult(
            success=True, return_code=0, stdout=ls_output, stderr="", duration=0.2
        )

        result = await path_service.list_directory("/home/user", include_files=True)

        assert len(result) == 4
        # Directories should come first
        assert result[0].name == "alpha"
        assert result[1].name == "gamma"
        # Then files, alphabetically
        assert result[2].name == "beta.json"
        assert result[3].name == "zebra.txt"

    @pytest.mark.asyncio
    async def test_list_directory_with_borg_repo(
        self, path_service: PathService, mock_command_executor: Mock
    ) -> None:
        """Test listing directory that contains a Borg repository."""
        ls_output = """total 12
drwxr-xr-x 2 user user 4096 Jan 15 10:00 my-borg-repo
drwxr-xr-x 2 user user 4096 Jan 15 11:00 regular-folder
"""

        async def mock_execute(cmd: List[str], **kwargs: Any) -> CommandResult:
            if cmd[0] == "ls":
                return CommandResult(
                    success=True,
                    return_code=0,
                    stdout=ls_output,
                    stderr="",
                    duration=0.2,
                )
            elif cmd[0] == "find":
                return CommandResult(
                    success=True,
                    return_code=0,
                    stdout="/home/user/my-borg-repo/config\n",
                    stderr="",
                    duration=0.1,
                )
            elif cmd[0] == "grep" and "^\\[repository\\]" in " ".join(cmd):
                return CommandResult(
                    success=True,
                    return_code=0,
                    stdout="/home/user/my-borg-repo/config\n",
                    stderr="",
                    duration=0.1,
                )
            elif cmd[0] == "grep" and "^\\[cache\\]" in " ".join(cmd):
                return CommandResult(
                    success=False, return_code=1, stdout="", stderr="", duration=0.1
                )
            return CommandResult(
                success=True, return_code=0, stdout="", stderr="", duration=0.1
            )

        mock_command_executor.execute_command.side_effect = mock_execute

        result = await path_service.list_directory("/home/user")

        assert len(result) == 2
        borg_repo = next((r for r in result if r.name == "my-borg-repo"), None)
        assert borg_repo is not None
        assert borg_repo.is_borg_repo is True

    @pytest.mark.asyncio
    async def test_list_directory_with_borg_cache(
        self, path_service: PathService, mock_command_executor: Mock
    ) -> None:
        """Test listing directory that contains a Borg cache."""
        ls_output = """total 8
drwxr-xr-x 2 user user 4096 Jan 15 10:00 borg-cache
"""

        async def mock_execute(cmd: List[str], **kwargs: Any) -> CommandResult:
            if cmd[0] == "ls":
                return CommandResult(
                    success=True,
                    return_code=0,
                    stdout=ls_output,
                    stderr="",
                    duration=0.2,
                )
            elif cmd[0] == "find":
                return CommandResult(
                    success=True,
                    return_code=0,
                    stdout="/home/user/borg-cache/config\n",
                    stderr="",
                    duration=0.1,
                )
            elif cmd[0] == "grep" and "^\\[repository\\]" in " ".join(cmd):
                return CommandResult(
                    success=False, return_code=1, stdout="", stderr="", duration=0.1
                )
            elif cmd[0] == "grep" and "^\\[cache\\]" in " ".join(cmd):
                return CommandResult(
                    success=True,
                    return_code=0,
                    stdout="/home/user/borg-cache/config\n",
                    stderr="",
                    duration=0.1,
                )
            return CommandResult(
                success=True, return_code=0, stdout="", stderr="", duration=0.1
            )

        mock_command_executor.execute_command.side_effect = mock_execute

        result = await path_service.list_directory("/home/user")

        assert len(result) == 1
        cache_dir = result[0]
        assert cache_dir.name == "borg-cache"
        assert cache_dir.is_borg_cache is True

    @pytest.mark.asyncio
    async def test_list_large_directory(
        self, path_service: PathService, mock_command_executor: Mock
    ) -> None:
        """Test listing a directory with many entries."""
        # Generate ls output for 50 directories
        entries = [
            f"drwxr-xr-x 2 user user 4096 Jan 15 10:00 dir{i:03d}" for i in range(50)
        ]
        ls_output = "total 200\n" + "\n".join(entries)

        mock_command_executor.execute_command.return_value = CommandResult(
            success=True, return_code=0, stdout=ls_output, stderr="", duration=0.5
        )

        result = await path_service.list_directory("/home/user/archives")

        assert len(result) == 50
        assert all(item.name.startswith("dir") for item in result)

    @pytest.mark.asyncio
    async def test_list_empty_directory(
        self, path_service: PathService, mock_command_executor: Mock
    ) -> None:
        """Test listing an empty directory."""
        ls_output = "total 0\n"
        mock_command_executor.execute_command.return_value = CommandResult(
            success=True, return_code=0, stdout=ls_output, stderr="", duration=0.1
        )

        result = await path_service.list_directory("/home/user/empty")

        assert len(result) == 0
        assert isinstance(result, list)


class TestGetDefaultDirectories:
    """Test get_default_directories method - happy paths."""

    @pytest.mark.asyncio
    async def test_standard_home_directory(
        self, path_service: PathService, mock_command_executor: Mock
    ) -> None:
        """Test getting default directories with standard HOME setup."""
        env_output = """BORG_BASE_DIR=
HOME=/home/testuser
XDG_CACHE_HOME=
XDG_CONFIG_HOME=
TMPDIR=/tmp
HOME_FROM_CD=/home/testuser"""

        mock_command_executor.execute_command.return_value = CommandResult(
            success=True, return_code=0, stdout=env_output, stderr="", duration=0.1
        )

        result = await path_service.get_default_directories()

        assert isinstance(result, BorgDefaultDirectories)
        assert result.base_dir == "/home/testuser"
        assert result.cache_dir == "/home/testuser/.cache/borg"
        assert result.config_dir == "/home/testuser/.config/borg"
        assert result.security_dir == "/home/testuser/.config/borg/security"
        assert result.keys_dir == "/home/testuser/.config/borg/keys"
        assert result.temp_dir == "/tmp"

    @pytest.mark.asyncio
    async def test_custom_borg_base_dir(
        self, path_service: PathService, mock_command_executor: Mock
    ) -> None:
        """Test with custom BORG_BASE_DIR set."""
        env_output = """BORG_BASE_DIR=/custom/borg/base
HOME=/home/testuser
XDG_CACHE_HOME=
XDG_CONFIG_HOME=
TMPDIR=/tmp
HOME_FROM_CD=/home/testuser"""

        mock_command_executor.execute_command.return_value = CommandResult(
            success=True, return_code=0, stdout=env_output, stderr="", duration=0.1
        )

        result = await path_service.get_default_directories()

        assert result.base_dir == "/custom/borg/base"
        assert result.cache_dir == "/custom/borg/base/.cache/borg"
        assert result.config_dir == "/custom/borg/base/.config/borg"
        assert result.security_dir == "/custom/borg/base/.config/borg/security"
        assert result.keys_dir == "/custom/borg/base/.config/borg/keys"

    @pytest.mark.asyncio
    async def test_xdg_directories(
        self, path_service: PathService, mock_command_executor: Mock
    ) -> None:
        """Test with XDG_CACHE_HOME and XDG_CONFIG_HOME set."""
        env_output = """BORG_BASE_DIR=
HOME=/home/testuser
XDG_CACHE_HOME=/home/testuser/.local/cache
XDG_CONFIG_HOME=/home/testuser/.local/config
TMPDIR=/tmp
HOME_FROM_CD=/home/testuser"""

        mock_command_executor.execute_command.return_value = CommandResult(
            success=True, return_code=0, stdout=env_output, stderr="", duration=0.1
        )

        result = await path_service.get_default_directories()

        assert result.base_dir == "/home/testuser"
        assert result.cache_dir == "/home/testuser/.local/cache/borg"
        assert result.config_dir == "/home/testuser/.local/config/borg"
        assert result.security_dir == "/home/testuser/.local/config/borg/security"
        assert result.keys_dir == "/home/testuser/.local/config/borg/keys"

    @pytest.mark.asyncio
    async def test_custom_temp_dir(
        self, path_service: PathService, mock_command_executor: Mock
    ) -> None:
        """Test with custom TMPDIR."""
        env_output = """BORG_BASE_DIR=
HOME=/home/testuser
XDG_CACHE_HOME=
XDG_CONFIG_HOME=
TMPDIR=/var/tmp
HOME_FROM_CD=/home/testuser"""

        mock_command_executor.execute_command.return_value = CommandResult(
            success=True, return_code=0, stdout=env_output, stderr="", duration=0.1
        )

        result = await path_service.get_default_directories()

        assert result.temp_dir == "/var/tmp"

    @pytest.mark.asyncio
    async def test_root_user_directories(
        self, path_service: PathService, mock_command_executor: Mock
    ) -> None:
        """Test default directories for root user."""
        env_output = """BORG_BASE_DIR=
HOME=/root
XDG_CACHE_HOME=
XDG_CONFIG_HOME=
TMPDIR=/tmp
HOME_FROM_CD=/root"""

        mock_command_executor.execute_command.return_value = CommandResult(
            success=True, return_code=0, stdout=env_output, stderr="", duration=0.1
        )

        result = await path_service.get_default_directories()

        assert result.base_dir == "/root"
        assert result.cache_dir == "/root/.cache/borg"
        assert result.config_dir == "/root/.config/borg"
        assert result.security_dir == "/root/.config/borg/security"
        assert result.keys_dir == "/root/.config/borg/keys"

    @pytest.mark.asyncio
    async def test_alternate_home_from_cd(
        self, path_service: PathService, mock_command_executor: Mock
    ) -> None:
        """Test using HOME_FROM_CD when HOME is not set."""
        env_output = """BORG_BASE_DIR=
HOME=
XDG_CACHE_HOME=
XDG_CONFIG_HOME=
TMPDIR=/tmp
HOME_FROM_CD=/home/testuser"""

        mock_command_executor.execute_command.return_value = CommandResult(
            success=True, return_code=0, stdout=env_output, stderr="", duration=0.1
        )

        result = await path_service.get_default_directories()

        assert result.base_dir == "/home/testuser"
        assert result.cache_dir == "/home/testuser/.cache/borg"

    @pytest.mark.asyncio
    async def test_complex_directory_structure(
        self, path_service: PathService, mock_command_executor: Mock
    ) -> None:
        """Test with complex nested directory structure."""
        env_output = """BORG_BASE_DIR=/opt/storage/backups/borg/base
HOME=/home/testuser
XDG_CACHE_HOME=
XDG_CONFIG_HOME=
TMPDIR=/var/tmp/borg
HOME_FROM_CD=/home/testuser"""

        mock_command_executor.execute_command.return_value = CommandResult(
            success=True, return_code=0, stdout=env_output, stderr="", duration=0.1
        )

        result = await path_service.get_default_directories()

        assert result.base_dir == "/opt/storage/backups/borg/base"
        assert result.cache_dir == "/opt/storage/backups/borg/base/.cache/borg"
        assert result.config_dir == "/opt/storage/backups/borg/base/.config/borg"
        assert (
            result.security_dir
            == "/opt/storage/backups/borg/base/.config/borg/security"
        )
        assert result.keys_dir == "/opt/storage/backups/borg/base/.config/borg/keys"
        assert result.temp_dir == "/var/tmp/borg"


class TestIntegrationScenarios:
    """Test real-world integration scenarios."""

    @pytest.mark.asyncio
    async def test_complete_borg_workflow(
        self, path_service: PathService, mock_command_executor: Mock
    ) -> None:
        """Test a complete workflow: get defaults, check paths, list directories."""
        # Step 1: Get default directories
        env_output = """BORG_BASE_DIR=
HOME=/home/borguser
XDG_CACHE_HOME=
XDG_CONFIG_HOME=
TMPDIR=/tmp
HOME_FROM_CD=/home/borguser"""

        mock_command_executor.execute_command.return_value = CommandResult(
            success=True, return_code=0, stdout=env_output, stderr="", duration=0.1
        )

        defaults = await path_service.get_default_directories()
        assert defaults.base_dir == "/home/borguser"

        # Step 2: Check if config directory exists
        mock_command_executor.execute_command.return_value = CommandResult(
            success=True, return_code=0, stdout="", stderr="", duration=0.1
        )

        config_exists = await path_service.path_exists(defaults.config_dir)
        assert config_exists is True

        # Step 3: Verify it's a directory
        is_dir = await path_service.is_directory(defaults.config_dir)
        assert is_dir is True

    @pytest.mark.asyncio
    async def test_secure_path_construction(
        self, path_service: PathService, mock_command_executor: Mock
    ) -> None:
        """Test building secure paths for repository structure."""
        base_repo = "/var/backups/borg"
        server_name = "web-server-01"
        date = "2024-01-15"

        # Build repository path
        server_path = path_service.secure_join(base_repo, server_name)
        assert server_path == "/var/backups/borg/web-server-01"

        # Build archive path
        archive_path = path_service.secure_join(server_path, "archives", date)
        assert archive_path == "/var/backups/borg/web-server-01/archives/2024-01-15"

        # Verify path exists
        mock_command_executor.execute_command.return_value = CommandResult(
            success=True, return_code=0, stdout="", stderr="", duration=0.1
        )
        exists = await path_service.path_exists(archive_path)
        assert exists is True

    @pytest.mark.asyncio
    async def test_multiple_repository_discovery(
        self, path_service: PathService, mock_command_executor: Mock
    ) -> None:
        """Test discovering multiple Borg repositories in a directory."""
        ls_output = """total 24
drwxr-xr-x 2 user user 4096 Jan 15 10:00 server1-repo
drwxr-xr-x 2 user user 4096 Jan 15 11:00 server2-repo
drwxr-xr-x 2 user user 4096 Jan 15 12:00 server3-repo
drwxr-xr-x 2 user user 4096 Jan 15 13:00 not-a-repo
"""

        async def mock_execute(cmd: List[str], **kwargs: Any) -> CommandResult:
            if cmd[0] == "ls":
                return CommandResult(
                    success=True,
                    return_code=0,
                    stdout=ls_output,
                    stderr="",
                    duration=0.2,
                )
            elif cmd[0] == "find":
                return CommandResult(
                    success=True,
                    return_code=0,
                    stdout="/backups/server1-repo/config\n/backups/server2-repo/config\n/backups/server3-repo/config\n",
                    stderr="",
                    duration=0.1,
                )
            elif cmd[0] == "grep" and "^\\[repository\\]" in " ".join(cmd):
                return CommandResult(
                    success=True,
                    return_code=0,
                    stdout="/backups/server1-repo/config\n/backups/server2-repo/config\n/backups/server3-repo/config\n",
                    stderr="",
                    duration=0.1,
                )
            elif cmd[0] == "grep" and "^\\[cache\\]" in " ".join(cmd):
                return CommandResult(
                    success=False, return_code=1, stdout="", stderr="", duration=0.1
                )
            return CommandResult(
                success=True, return_code=0, stdout="", stderr="", duration=0.1
            )

        mock_command_executor.execute_command.side_effect = mock_execute

        result = await path_service.list_directory("/backups")

        assert len(result) == 4
        borg_repos = [r for r in result if r.is_borg_repo]
        assert len(borg_repos) == 3
        assert "server1-repo" in [r.name for r in borg_repos]
        assert "server2-repo" in [r.name for r in borg_repos]
        assert "server3-repo" in [r.name for r in borg_repos]
