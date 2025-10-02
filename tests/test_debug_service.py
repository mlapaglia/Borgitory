"""
Tests for DebugService - Service to gather system and application debug information
"""

import pytest
import subprocess
from typing import Any, Optional, cast
from unittest.mock import patch, MagicMock, Mock, AsyncMock
from datetime import datetime
from sqlalchemy.orm import Session
from borgitory.protocols.command_executor_protocol import CommandResult
from borgitory.services.debug_service import DebugService


class MockEnvironment:
    """Mock environment for testing"""

    def __init__(self) -> None:
        self.env_vars: dict[str, str] = {}
        self.cwd = "/test/dir"
        self.current_time = datetime(2023, 1, 1, 12, 0, 0)
        self.database_url = "sqlite:///test.db"

    def get_env(self, key: str, default: Optional[str] = None) -> Optional[str]:
        return self.env_vars.get(key, default)

    def get_cwd(self) -> str:
        return self.cwd

    def now_utc(self) -> datetime:
        return self.current_time

    def get_database_url(self) -> str:
        return self.database_url


@pytest.fixture
def mock_environment() -> MockEnvironment:
    return MockEnvironment()


@pytest.fixture
def mock_job_manager() -> Mock:
    """Mock job manager for testing"""
    from unittest.mock import Mock

    mock_manager = Mock()
    mock_manager.jobs = {
        "job1": Mock(status="running"),
        "job2": Mock(status="completed"),
        "job3": Mock(status="running"),
    }
    return mock_manager


@pytest.fixture
def mock_command_executor() -> Mock:
    """Mock command executor for testing"""
    from unittest.mock import Mock

    mock_executor = Mock()
    # Set up default return values for common commands
    mock_executor.execute_command.return_value = Mock(
        return_code=0,
        stdout="",
        stderr="",
        success=True,
        execution_time=0.1,
        error=None,
    )
    return mock_executor


@pytest.fixture
def debug_service(
    mock_environment: MockEnvironment,
    mock_job_manager: Mock,
    mock_command_executor: Mock,
) -> DebugService:
    """Debug service with all required dependencies injected"""
    return DebugService(
        job_manager=mock_job_manager,
        environment=mock_environment,
        command_executor=mock_command_executor,
    )


@pytest.fixture
def mock_db_session() -> MagicMock:
    """Mock database session"""
    session = MagicMock(spec=Session)
    return session


class TestDebugService:
    """Test the DebugService class"""

    @pytest.mark.asyncio
    async def test_get_debug_info_all_sections_success(
        self, debug_service: DebugService, mock_db_session: MagicMock
    ) -> None:
        """Test successful retrieval of all debug info sections"""
        # Mock data using class instances
        from borgitory.services.debug_service import (
            SystemInfo,
            ApplicationInfo,
            DatabaseInfo,
            ToolInfo,
            JobManagerInfo,
        )

        # Create system info
        system_info = SystemInfo()
        system_info.platform = "Test Platform"
        system_info.system = "TestOS"
        system_info.release = "1.0"
        system_info.version = "1.0.0"
        system_info.architecture = "x64"
        system_info.processor = "Test Processor"
        system_info.hostname = "test-host"
        system_info.python_version = "Python 3.9.0"
        system_info.python_executable = "/usr/bin/python"

        # Create application info
        app_info = ApplicationInfo()
        app_info.borgitory_version = "1.0.0"
        app_info.debug_mode = False
        app_info.startup_time = "2023-01-01T12:00:00"
        app_info.working_directory = "/test/dir"

        # Create database info
        db_info = DatabaseInfo()
        db_info.repository_count = 5
        db_info.total_jobs = 100
        db_info.jobs_today = 10
        db_info.database_type = "SQLite"
        db_info.database_url = "sqlite:///test.db"
        db_info.database_size = "1.0 MB"
        db_info.database_size_bytes = 1048576
        db_info.database_accessible = True

        # Create tool info
        borg_tool = ToolInfo()
        borg_tool.version = "borg 1.2.0"
        borg_tool.accessible = True

        rclone_tool = ToolInfo()
        rclone_tool.version = "rclone v1.58.0"
        rclone_tool.accessible = True

        tools_info = {
            "borg": borg_tool,
            "rclone": rclone_tool,
        }

        env_info = {"PATH": "/usr/bin:/bin", "HOME": "/home/user", "DEBUG": "false"}

        # Create job manager info
        job_manager_info = JobManagerInfo()
        job_manager_info.active_jobs = 2
        job_manager_info.total_jobs = 5
        job_manager_info.job_manager_running = True

        with (
            patch.object(debug_service, "_get_system_info", return_value=system_info),
            patch.object(debug_service, "_get_application_info", return_value=app_info),
            patch.object(debug_service, "_get_database_info", return_value=db_info),
            patch.object(debug_service, "_get_tool_versions", return_value=tools_info),
            patch.object(debug_service, "_get_environment_info", return_value=env_info),
            patch.object(
                debug_service, "_get_job_manager_info", return_value=job_manager_info
            ),
        ):
            result = await debug_service.get_debug_info(mock_db_session)

            assert result.system == system_info
            assert result.application == app_info
            assert result.database == db_info
            assert result.tools == tools_info
            assert result.environment == env_info
            assert result.job_manager == job_manager_info

    @pytest.mark.asyncio
    async def test_get_debug_info_handles_section_failures(
        self, debug_service: DebugService, mock_db_session: MagicMock
    ) -> None:
        """Test that individual section failures are handled internally by each method"""
        # In the new architecture, methods handle their own exceptions and return class instances
        from borgitory.services.debug_service import (
            SystemInfo,
            ApplicationInfo,
            DatabaseInfo,
            ToolInfo,
            JobManagerInfo,
        )

        # Create system info with error
        system_info = SystemInfo()
        system_info.error = "System error"

        # Create application info
        app_info = ApplicationInfo()
        app_info.borgitory_version = "1.0.0"
        app_info.debug_mode = False
        app_info.startup_time = "2023-01-01T12:00:00"
        app_info.working_directory = "/test/dir"

        # Create tool info
        borg_tool = ToolInfo()
        borg_tool.version = "borg 1.2.0"
        borg_tool.accessible = True
        tools_info = {"borg": borg_tool}

        env_info = {"PATH": "/usr/bin:/bin", "DEBUG": "false"}

        # Create database info with error
        db_info = DatabaseInfo()
        db_info.error = "DB error"
        db_info.database_accessible = False

        # Create job manager info
        job_manager_info = JobManagerInfo()
        job_manager_info.active_jobs = 1
        job_manager_info.total_jobs = 3
        job_manager_info.job_manager_running = True

        with (
            patch.object(debug_service, "_get_system_info", return_value=system_info),
            patch.object(debug_service, "_get_application_info", return_value=app_info),
            patch.object(
                debug_service,
                "_get_database_info",
                return_value=db_info,
            ),
            patch.object(debug_service, "_get_tool_versions", return_value=tools_info),
            patch.object(debug_service, "_get_environment_info", return_value=env_info),
            patch.object(
                debug_service, "_get_job_manager_info", return_value=job_manager_info
            ),
        ):
            result = await debug_service.get_debug_info(mock_db_session)

            assert result.system.error == "System error"
            assert result.application == app_info
            assert result.database.error == "DB error"
            assert not result.database.database_accessible
            assert result.tools == tools_info
            assert result.environment == env_info
            assert result.job_manager == job_manager_info

    @pytest.mark.asyncio
    async def test_get_system_info(self, debug_service: DebugService) -> None:
        """Test system info collection"""
        with (
            patch("platform.platform", return_value="Test Platform"),
            patch("platform.system", return_value="TestOS"),
            patch("platform.release", return_value="1.0"),
            patch("platform.version", return_value="1.0.0"),
            patch("platform.architecture", return_value=("x64", "")),
            patch("platform.processor", return_value="Test Processor"),
            patch("platform.node", return_value="test-host"),
            patch("sys.version", "Python 3.9.0"),
            patch("sys.executable", "/usr/bin/python"),
        ):
            result = await debug_service._get_system_info()

            assert result.platform == "Test Platform"
            assert result.system == "TestOS"
            assert result.release == "1.0"
            assert result.version == "1.0.0"
            assert result.architecture == "x64"
            assert result.processor == "Test Processor"
            assert result.hostname == "test-host"
            assert result.python_version == "Python 3.9.0"
            assert result.python_executable == "/usr/bin/python"

    @pytest.mark.asyncio
    async def test_get_application_info(
        self, debug_service: DebugService, mock_environment: MockEnvironment
    ) -> None:
        """Test application info collection"""
        # Configure mock environment
        mock_environment.env_vars = {"DEBUG": "false"}
        mock_environment.cwd = "/test/dir"
        mock_environment.current_time = datetime(2023, 1, 1, 12, 0, 0)

        # Mock the version method to return expected version
        with patch.object(
            debug_service, "_get_borgitory_version", return_value="1.0.0"
        ):
            result = await debug_service._get_application_info()

            assert result.borgitory_version == "1.0.0"
            assert result.debug_mode is False
            assert result.working_directory == "/test/dir"
            assert result.startup_time == "2023-01-01T12:00:00"

    @pytest.mark.asyncio
    async def test_get_application_info_debug_mode_true(
        self, debug_service: DebugService, mock_environment: MockEnvironment
    ) -> None:
        """Test application info with debug mode enabled"""
        # Configure mock environment for debug mode
        mock_environment.env_vars = {"DEBUG": "TRUE"}

        result = await debug_service._get_application_info()

        assert result.debug_mode is True

    def test_get_database_info_success(
        self, debug_service: DebugService, mock_db_session: MagicMock
    ) -> None:
        """Test successful database info collection"""
        # Mock query results with different chains for different calls
        repo_query_mock = MagicMock()
        repo_query_mock.count.return_value = 5

        job_query_mock = MagicMock()
        job_query_mock.count.return_value = 100

        filtered_job_query_mock = MagicMock()
        filtered_job_query_mock.count.return_value = 10

        # Setup the mock to return different objects for different query calls
        mock_db_session.query.side_effect = [
            repo_query_mock,
            job_query_mock,
            filtered_job_query_mock,
        ]

        # Mock the filter method for the third query (recent jobs)
        filtered_job_query_mock.filter = MagicMock(return_value=filtered_job_query_mock)
        mock_db_session.query.return_value.filter = MagicMock(
            return_value=filtered_job_query_mock
        )

        with (
            patch("borgitory.config.DATABASE_URL", "sqlite:///test.db"),
            patch("os.path.exists", return_value=True),
            patch("os.path.getsize", return_value=1024 * 1024),
        ):  # 1MB
            result = debug_service._get_database_info(mock_db_session)

            assert result.repository_count == 5
            assert result.total_jobs == 100
            assert result.jobs_today == 10
            assert result.database_type == "SQLite"
            assert result.database_url == "sqlite:///test.db"
            assert result.database_size == "1.0 MB"
            assert result.database_size_bytes == 1024 * 1024
            assert result.database_accessible is True

    def test_get_database_info_size_formatting(
        self, debug_service: DebugService, mock_db_session: MagicMock
    ) -> None:
        """Test database size formatting for different sizes"""
        mock_db_session.query.return_value.count.return_value = 1

        # Test bytes
        with (
            patch("borgitory.config.DATABASE_URL", "sqlite:///test.db"),
            patch("os.path.exists", return_value=True),
            patch("os.path.getsize", return_value=512),
        ):
            result = debug_service._get_database_info(mock_db_session)
            assert result.database_size == "512 B"

        # Test KB
        with (
            patch("borgitory.config.DATABASE_URL", "sqlite:///test.db"),
            patch("os.path.exists", return_value=True),
            patch("os.path.getsize", return_value=2048),
        ):
            result = debug_service._get_database_info(mock_db_session)
            assert result.database_size == "2.0 KB"

        # Test GB
        with (
            patch("borgitory.config.DATABASE_URL", "sqlite:///test.db"),
            patch("os.path.exists", return_value=True),
            patch("os.path.getsize", return_value=2 * 1024 * 1024 * 1024),
        ):
            result = debug_service._get_database_info(mock_db_session)
            assert result.database_size == "2.0 GB"

    def test_get_database_info_exception_handling(
        self, debug_service: DebugService, mock_db_session: MagicMock
    ) -> None:
        """Test database info exception handling"""
        mock_db_session.query.side_effect = Exception("Database error")

        result = debug_service._get_database_info(mock_db_session)

        assert result.error != ""
        assert result.database_accessible is False

    @pytest.mark.asyncio
    async def test_get_tool_versions_success(self, debug_service: DebugService) -> None:
        """Test successful tool version detection"""

        async def mock_run_command(
            command: list[str],
            timeout: Optional[float] = None,
        ) -> tuple[int, str, str]:
            if command[0] == "borg":
                return 0, "borg 1.2.0\n", ""
            elif command[0] == "rclone":
                return 0, "rclone v1.58.0\n", ""
            elif command[0] == "dpkg":
                return (
                    0,
                    "ii  fuse3  3.10.3-2  amd64  Filesystem in Userspace (library)\n",
                    "",
                )
            return 1, "", "command not found"

        with patch.object(debug_service, "_run_command", side_effect=mock_run_command):
            result = await debug_service._get_tool_versions()

            assert result["borg"].version == "borg 1.2.0"
            assert result["borg"].accessible is True
            assert result["rclone"].version == "rclone v1.58.0"
            assert result["rclone"].accessible is True

    @pytest.mark.asyncio
    async def test_get_tool_versions_command_failures(
        self, debug_service: DebugService
    ) -> None:
        """Test tool version detection when commands fail"""

        async def mock_run_command(
            command: list[str],
            timeout: Optional[float] = None,
        ) -> tuple[int, str, str]:
            if command[0] == "borg":
                return 1, "", "command not found"
            elif command[0] == "rclone":
                return 1, "", "rclone not installed"
            elif command[0] == "dpkg":
                return 1, "", "package not found"
            return 1, "", "command not found"

        with patch.object(debug_service, "_run_command", side_effect=mock_run_command):
            result = await debug_service._get_tool_versions()

            assert result["borg"].accessible is False
            assert result["borg"].error != ""
            assert result["rclone"].accessible is False
            assert result["rclone"].error != ""

    def test_get_environment_info(
        self, debug_service: DebugService, mock_environment: MockEnvironment
    ) -> None:
        """Test environment info collection"""
        # Configure mock environment
        mock_environment.env_vars = {
            "PATH": "/usr/bin:/bin",
            "HOME": "/home/user",
            "DATABASE_URL": "sqlite:///test.db",
            "DEBUG": "false",
            "SECRET_KEY": "super_secret",  # Should not appear in result
            "PASSWORD": "hidden_password",  # Should not appear in result
        }

        result = debug_service._get_environment_info()

        assert result["PATH"] == "/usr/bin:/bin"
        assert result["HOME"] == "/home/user"
        assert result["DATABASE_URL"] == "sqlite:///test.db"
        assert result["DEBUG"] == "false"
        # Sensitive vars should be hidden
        assert "SECRET_KEY" not in result  # Not in safe list
        assert "PASSWORD" not in result  # Not in safe list

    def test_get_environment_info_hides_sensitive_database_url(
        self, debug_service: DebugService, mock_environment: MockEnvironment
    ) -> None:
        """Test that non-sqlite database URLs are hidden"""
        mock_environment.env_vars = {
            "DATABASE_URL": "postgresql://user:pass@localhost/db"
        }

        result = debug_service._get_environment_info()

        assert result["DATABASE_URL"] == "***HIDDEN***"

    def test_get_job_manager_info_success(self, debug_service: DebugService) -> None:
        """Test successful job manager info collection"""
        # Mock job manager with jobs
        mock_job_manager = MagicMock()
        mock_job1 = MagicMock()
        mock_job1.status = "running"
        mock_job2 = MagicMock()
        mock_job2.status = "completed"
        mock_job3 = MagicMock()
        mock_job3.status = "running"

        mock_job_manager.jobs = {
            "job1": mock_job1,
            "job2": mock_job2,
            "job3": mock_job3,
        }

        # Using constructor-injected job manager
        debug_service.job_manager = mock_job_manager
        result = debug_service._get_job_manager_info()

        assert result.active_jobs == 2  # 2 running jobs
        assert result.total_jobs == 3  # 3 total jobs
        assert result.job_manager_running is True

    def test_get_job_manager_info_no_jobs_attribute(
        self, debug_service: DebugService
    ) -> None:
        """Test job manager info when job manager has no jobs attribute"""
        mock_job_manager = MagicMock()
        del mock_job_manager.jobs  # Remove jobs attribute

        # Using constructor-injected job manager
        debug_service.job_manager = mock_job_manager
        result = debug_service._get_job_manager_info()

        assert result.active_jobs == 0
        assert result.total_jobs == 0
        assert result.job_manager_running is True

    def test_get_job_manager_info_exception_handling(
        self, debug_service: DebugService
    ) -> None:
        """Test job manager info exception handling"""
        # Simulate job manager error by making jobs attribute missing
        mock_job_manager = Mock()
        # Don't set jobs attribute to simulate AttributeError
        del mock_job_manager.jobs
        debug_service.job_manager = mock_job_manager

        result = debug_service._get_job_manager_info()

        # Should handle missing jobs attribute gracefully
        assert hasattr(result, "active_jobs")
        assert result.total_jobs == 0  # Due to missing jobs attribute

    def test_get_job_manager_info_jobs_without_status(
        self, debug_service: DebugService
    ) -> None:
        """Test job manager info when jobs don't have status attribute"""
        mock_job_manager = MagicMock()
        mock_job1 = MagicMock()
        del mock_job1.status  # Remove status attribute
        mock_job2 = MagicMock()
        mock_job2.status = "running"

        mock_job_manager.jobs = {"job1": mock_job1, "job2": mock_job2}

        # Using constructor-injected job manager
        debug_service.job_manager = mock_job_manager
        result = debug_service._get_job_manager_info()

        assert result.active_jobs == 1  # Only job2 counts as running
        assert result.total_jobs == 2  # Both jobs counted in total

    def _create_command_result(
        self,
        command: list[str],
        return_code: int,
        stdout: str,
        stderr: str = "",
        success: Optional[bool] = None,
    ) -> CommandResult:
        """Helper to create CommandResult objects for testing"""
        if success is None:
            success = return_code == 0
        return CommandResult(
            command=command,
            return_code=return_code,
            stdout=stdout,
            stderr=stderr,
            success=success,
            execution_time=0.1,
            error=stderr if not success and stderr else None,
        )

    @pytest.mark.asyncio
    async def test_get_wsl_info_not_windows(self, debug_service: DebugService) -> None:
        """Test WSL info when not running on Windows"""
        # Mock environment to return non-Windows OS
        mock_env = cast(MockEnvironment, debug_service.environment)
        mock_env.env_vars["OS"] = "Linux"

        with patch("platform.system", return_value="Linux"):
            result = await debug_service._get_wsl_info()

            assert result.wsl_available is False
            assert result.error == "Not running on Windows - WSL not applicable"

    @pytest.mark.asyncio
    async def test_get_wsl_info_windows_no_wsl(
        self, debug_service: DebugService
    ) -> None:
        """Test WSL info on Windows but WSL not available"""
        # Mock environment to return Windows OS
        mock_env = cast(MockEnvironment, debug_service.environment)
        mock_env.env_vars["OS"] = "Windows_NT"

        # Mock command executor to simulate WSL not available
        mock_result = self._create_command_result(
            command=["cat", "/proc/version"],
            return_code=1,
            stdout="",
            stderr="cat: /proc/version: No such file or directory",
        )

        with patch.object(
            debug_service.command_executor,
            "execute_command",
            AsyncMock(return_value=mock_result),
        ):
            with patch("platform.system", return_value="Windows"):
                result = await debug_service._get_wsl_info()

                assert result.wsl_available is False
                assert "WSL not available" in result.error

    @pytest.mark.asyncio
    async def test_get_wsl_info_os_release_failure(
        self, debug_service: DebugService
    ) -> None:
        """Test WSL info when /etc/os-release cannot be read"""
        # Mock environment to return Windows OS
        mock_env = cast(MockEnvironment, debug_service.environment)
        mock_env.env_vars["OS"] = "Windows_NT"

        async def mock_execute_command(
            command: list[str], **kwargs: Any
        ) -> CommandResult:
            if command == ["cat", "/proc/version"]:
                return self._create_command_result(
                    command, 0, "Linux version 6.6.87.2-microsoft-standard-WSL2"
                )
            elif command == ["cat", "/etc/os-release"]:
                return self._create_command_result(command, 1, "", "Permission denied")
            else:
                return self._create_command_result(command, 1, "", "Command not found")

        with patch.object(
            debug_service.command_executor,
            "execute_command",
            AsyncMock(side_effect=mock_execute_command),
        ):
            with patch("platform.system", return_value="Windows"):
                result = await debug_service._get_wsl_info()

                assert result.wsl_available is True
                assert result.wsl_version == "WSL 2"
                assert result.default_distribution == "Unknown Linux Distribution"

    @pytest.mark.asyncio
    async def test_get_wsl_info_mount_access_failure(
        self, debug_service: DebugService
    ) -> None:
        """Test WSL info when mount point access fails"""
        # Mock environment to return Windows OS
        mock_env = cast(MockEnvironment, debug_service.environment)
        mock_env.env_vars["OS"] = "Windows_NT"

        async def mock_execute_command(
            command: list[str], **kwargs: Any
        ) -> CommandResult:
            if command == ["cat", "/proc/version"]:
                return self._create_command_result(
                    command, 0, "Linux version 6.6.87.2-microsoft-standard-WSL2"
                )
            elif command == ["ls", "/mnt"]:
                return self._create_command_result(command, 1, "", "Permission denied")
            else:
                return self._create_command_result(command, 1, "", "Command not found")

        with patch.object(
            debug_service.command_executor,
            "execute_command",
            AsyncMock(side_effect=mock_execute_command),
        ):
            with patch("platform.system", return_value="Windows"):
                result = await debug_service._get_wsl_info()

                assert result.wsl_available is True
                assert result.wsl_path_accessible is False
                assert len(result.mount_points) == 0

    @pytest.mark.asyncio
    async def test_get_wsl_info_command_executor_exception(
        self, debug_service: DebugService
    ) -> None:
        """Test WSL info when command executor raises exception"""
        # Mock environment to return Windows OS
        mock_env = cast(MockEnvironment, debug_service.environment)
        mock_env.env_vars["OS"] = "Windows_NT"

        # Mock command executor to raise exception
        with patch.object(
            debug_service.command_executor,
            "execute_command",
            AsyncMock(side_effect=FileNotFoundError("WSL command not found")),
        ):
            with patch("platform.system", return_value="Windows"):
                result = await debug_service._get_wsl_info()

                assert result.wsl_available is False
                assert "WSL command not found" in result.error

    @pytest.mark.asyncio
    async def test_get_wsl_info_unexpected_exception(
        self, debug_service: DebugService
    ) -> None:
        """Test WSL info when unexpected exception occurs"""
        # Mock environment to return Windows OS
        mock_env = cast(MockEnvironment, debug_service.environment)
        mock_env.env_vars["OS"] = "Windows_NT"

        with patch("platform.system", return_value="Windows"):
            # Mock an unexpected exception in the command executor
            with patch.object(
                debug_service.command_executor,
                "execute_command",
                AsyncMock(side_effect=RuntimeError("Unexpected error")),
            ):
                result = await debug_service._get_wsl_info()

                assert result.wsl_available is False
                assert "Unexpected error" in result.error

    def test_get_windows_version_with_platform_info(
        self, debug_service: DebugService
    ) -> None:
        """Test Windows version detection using platform.platform()"""
        with patch("platform.platform", return_value="Windows-10-10.0.19041-SP0"):
            result = debug_service._get_windows_version()
            assert result == "Windows-10-10.0.19041-SP0"

    def test_get_windows_version_with_cmd_ver(
        self, debug_service: DebugService
    ) -> None:
        """Test Windows version detection using cmd ver command"""
        with patch(
            "platform.platform", return_value="Linux-5.4.0"
        ):  # Non-Windows platform
            with patch("platform.system", return_value="Windows"):
                with patch("subprocess.run") as mock_run:
                    # Mock successful ver command
                    mock_result = Mock()
                    mock_result.returncode = 0
                    mock_result.stdout = "Microsoft Windows [Version 10.0.19045.5011]"
                    mock_run.return_value = mock_result

                    result = debug_service._get_windows_version()
                    assert result == "Microsoft Windows [Version 10.0.19045.5011]"

                    # Verify subprocess.run was called with correct arguments
                    mock_run.assert_called_with(
                        ["cmd", "/c", "ver"], capture_output=True, text=True, timeout=5
                    )

    def test_get_windows_version_with_systeminfo(
        self, debug_service: DebugService
    ) -> None:
        """Test Windows version detection using systeminfo command"""
        with patch(
            "platform.platform", return_value="Linux-5.4.0"
        ):  # Non-Windows platform
            with patch("platform.system", return_value="Windows"):
                with patch("subprocess.run") as mock_run:
                    # Mock ver command failure, systeminfo success
                    def mock_run_side_effect(cmd: list[str], **kwargs: Any) -> Mock:
                        if cmd == ["cmd", "/c", "ver"]:
                            mock_result = Mock()
                            mock_result.returncode = 1
                            mock_result.stdout = ""
                            return mock_result
                        elif cmd == ["systeminfo", "/fo", "csv"]:
                            mock_result = Mock()
                            mock_result.returncode = 0
                            mock_result.stdout = '"OS Name","OS Version","OS Manufacturer"\n"Microsoft Windows 11 Pro","10.0.22000 N/A Build 22000","Microsoft Corporation"'
                            return mock_result
                        else:
                            mock_result = Mock()
                            mock_result.returncode = 1
                            return mock_result

                    mock_run.side_effect = mock_run_side_effect

                    result = debug_service._get_windows_version()
                    assert result == "Microsoft Windows 11 Pro"

    def test_get_windows_version_fallback_to_platform(
        self, debug_service: DebugService
    ) -> None:
        """Test Windows version fallback to basic platform info"""
        with patch(
            "platform.platform", return_value="Linux-5.4.0"
        ):  # Non-Windows platform
            with patch("platform.system", return_value="Windows"):
                with patch("platform.release", return_value="10"):
                    with patch("subprocess.run") as mock_run:
                        # Mock all subprocess commands to fail
                        mock_result = Mock()
                        mock_result.returncode = 1
                        mock_result.stdout = ""
                        mock_run.return_value = mock_result

                        result = debug_service._get_windows_version()
                        assert result == "Windows 10"

    def test_get_windows_version_exception_handling(
        self, debug_service: DebugService
    ) -> None:
        """Test Windows version detection exception handling"""
        with patch("platform.platform", side_effect=RuntimeError("Platform error")):
            result = debug_service._get_windows_version()
            assert result == "Unknown"

    def test_get_windows_version_subprocess_timeout(
        self, debug_service: DebugService
    ) -> None:
        """Test Windows version detection with subprocess timeout"""
        with patch(
            "platform.platform", return_value="Linux-5.4.0"
        ):  # Non-Windows platform
            with patch("platform.system", return_value="Windows"):
                with patch("platform.release", return_value="10"):
                    with patch(
                        "subprocess.run",
                        side_effect=subprocess.TimeoutExpired("cmd", 5),
                    ):
                        result = debug_service._get_windows_version()
                        assert result == "Windows 10"

    def test_get_windows_version_non_windows_system(
        self, debug_service: DebugService
    ) -> None:
        """Test Windows version detection on non-Windows system"""
        with patch("platform.platform", return_value="Linux-5.4.0-generic"):
            with patch("platform.system", return_value="Linux"):
                with patch("platform.release", return_value="5.4.0"):
                    result = debug_service._get_windows_version()
                    assert result == "Linux 5.4.0"
