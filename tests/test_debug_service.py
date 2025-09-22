"""
Tests for DebugService - Service to gather system and application debug information
"""

import pytest
from unittest.mock import patch, MagicMock, AsyncMock, Mock
from datetime import datetime
from sqlalchemy.orm import Session
from borgitory.services.debug_service import DebugService


class MockEnvironment:
    """Mock environment for testing"""

    def __init__(self):
        self.env_vars = {}
        self.cwd = "/test/dir"
        self.current_time = datetime(2023, 1, 1, 12, 0, 0)
        self.database_url = "sqlite:///test.db"

    def get_env(self, key: str, default: str = None) -> str:
        return self.env_vars.get(key, default)

    def get_cwd(self) -> str:
        return self.cwd

    def now_utc(self) -> datetime:
        return self.current_time

    def get_database_url(self) -> str:
        return self.database_url


@pytest.fixture
def mock_environment():
    return MockEnvironment()


@pytest.fixture
def mock_volume_service():
    """Mock volume service for testing"""
    from unittest.mock import AsyncMock

    mock_service = AsyncMock()
    mock_service.get_volume_info.return_value = {
        "mounted_volumes": ["/data", "/backup"],
        "total_mounted_volumes": 2,
    }
    return mock_service


@pytest.fixture
def mock_job_manager():
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
def debug_service(mock_environment, mock_volume_service, mock_job_manager):
    """Debug service with all required dependencies injected"""
    return DebugService(
        volume_service=mock_volume_service,
        job_manager=mock_job_manager,
        environment=mock_environment,
    )


@pytest.fixture
def mock_db_session():
    """Mock database session"""
    session = MagicMock(spec=Session)
    return session


class TestDebugService:
    """Test the DebugService class"""

    @pytest.mark.asyncio
    async def test_get_debug_info_all_sections_success(
        self, debug_service, mock_db_session
    ) -> None:
        """Test successful retrieval of all debug info sections"""
        # Mock data that matches our TypedDict structures
        system_info = {
            "platform": "Test Platform",
            "system": "TestOS",
            "release": "1.0",
            "version": "1.0.0",
            "architecture": "x64",
            "processor": "Test Processor",
            "hostname": "test-host",
            "python_version": "Python 3.9.0",
            "python_executable": "/usr/bin/python",
        }

        app_info = {
            "borgitory_version": "1.0.0",
            "debug_mode": False,
            "startup_time": "2023-01-01T12:00:00",
            "working_directory": "/test/dir",
        }

        db_info = {
            "repository_count": 5,
            "total_jobs": 100,
            "jobs_today": 10,
            "database_type": "SQLite",
            "database_url": "sqlite:///test.db",
            "database_size": "1.0 MB",
            "database_size_bytes": 1048576,
            "database_accessible": True,
        }

        volume_info = {
            "mounted_volumes": ["/data", "/backup"],
            "total_mounted_volumes": 2,
        }

        tools_info = {
            "borg": {"version": "borg 1.2.0", "accessible": True},
            "rclone": {"version": "rclone v1.58.0", "accessible": True},
        }

        env_info = {"PATH": "/usr/bin:/bin", "HOME": "/home/user", "DEBUG": "false"}

        job_manager_info = {
            "active_jobs": 2,
            "total_jobs": 5,
            "job_manager_running": True,
        }

        with patch.object(
            debug_service, "_get_system_info", return_value=system_info
        ), patch.object(
            debug_service, "_get_application_info", return_value=app_info
        ), patch.object(
            debug_service, "_get_database_info", return_value=db_info
        ), patch.object(
            debug_service, "_get_volume_info", return_value=volume_info
        ), patch.object(
            debug_service, "_get_tool_versions", return_value=tools_info
        ), patch.object(
            debug_service, "_get_environment_info", return_value=env_info
        ), patch.object(
            debug_service, "_get_job_manager_info", return_value=job_manager_info
        ):
            result = await debug_service.get_debug_info(mock_db_session)

            assert result["system"] == system_info
            assert result["application"] == app_info
            assert result["database"] == db_info
            assert result["volumes"] == volume_info
            assert result["tools"] == tools_info
            assert result["environment"] == env_info
            assert result["job_manager"] == job_manager_info

    @pytest.mark.asyncio
    async def test_get_debug_info_handles_section_failures(
        self, debug_service, mock_db_session
    ) -> None:
        """Test that individual section failures are handled internally by each method"""
        # In the new architecture, methods handle their own exceptions and return error dicts
        app_info = {
            "borgitory_version": "1.0.0",
            "debug_mode": False,
            "startup_time": "2023-01-01T12:00:00",
            "working_directory": "/test/dir",
        }

        volume_info = {"mounted_volumes": ["/data"], "total_mounted_volumes": 1}

        tools_info = {"borg": {"version": "borg 1.2.0", "accessible": True}}

        env_info = {"PATH": "/usr/bin:/bin", "DEBUG": "false"}

        job_manager_info = {
            "active_jobs": 1,
            "total_jobs": 3,
            "job_manager_running": True,
        }

        with patch.object(
            debug_service, "_get_system_info", return_value={"error": "System error"}
        ), patch.object(
            debug_service, "_get_application_info", return_value=app_info
        ), patch.object(
            debug_service,
            "_get_database_info",
            return_value={"error": "DB error", "database_accessible": False},
        ), patch.object(
            debug_service, "_get_volume_info", return_value=volume_info
        ), patch.object(
            debug_service, "_get_tool_versions", return_value=tools_info
        ), patch.object(
            debug_service, "_get_environment_info", return_value=env_info
        ), patch.object(
            debug_service, "_get_job_manager_info", return_value=job_manager_info
        ):
            result = await debug_service.get_debug_info(mock_db_session)

            assert result["system"] == {"error": "System error"}
            assert result["application"] == app_info
            assert result["database"] == {
                "error": "DB error",
                "database_accessible": False,
            }
            assert result["volumes"] == volume_info
            assert result["tools"] == tools_info
            assert result["environment"] == env_info
            assert result["job_manager"] == job_manager_info

    @pytest.mark.asyncio
    async def test_get_system_info(self, debug_service) -> None:
        """Test system info collection"""
        with patch("platform.platform", return_value="Test Platform"), patch(
            "platform.system", return_value="TestOS"
        ), patch("platform.release", return_value="1.0"), patch(
            "platform.version", return_value="1.0.0"
        ), patch("platform.architecture", return_value=("x64", "")), patch(
            "platform.processor", return_value="Test Processor"
        ), patch("platform.node", return_value="test-host"), patch(
            "sys.version", "Python 3.9.0"
        ), patch("sys.executable", "/usr/bin/python"):
            result = await debug_service._get_system_info()

            assert result["platform"] == "Test Platform"
            assert result["system"] == "TestOS"
            assert result["release"] == "1.0"
            assert result["version"] == "1.0.0"
            assert result["architecture"] == "x64"
            assert result["processor"] == "Test Processor"
            assert result["hostname"] == "test-host"
            assert result["python_version"] == "Python 3.9.0"
            assert result["python_executable"] == "/usr/bin/python"

    @pytest.mark.asyncio
    async def test_get_application_info(self, debug_service, mock_environment) -> None:
        """Test application info collection"""
        # Configure mock environment
        mock_environment.env_vars = {"BORGITORY_VERSION": "1.0.0", "DEBUG": "false"}
        mock_environment.cwd = "/test/dir"
        mock_environment.current_time = datetime(2023, 1, 1, 12, 0, 0)

        result = await debug_service._get_application_info()

        assert result["borgitory_version"] == "1.0.0"
        assert result["debug_mode"] is False
        assert result["working_directory"] == "/test/dir"
        assert result["startup_time"] == "2023-01-01T12:00:00"

    @pytest.mark.asyncio
    async def test_get_application_info_debug_mode_true(
        self, debug_service, mock_environment
    ) -> None:
        """Test application info with debug mode enabled"""
        # Configure mock environment for debug mode
        mock_environment.env_vars = {"DEBUG": "TRUE"}

        result = await debug_service._get_application_info()

        assert result["debug_mode"] is True

    def test_get_database_info_success(self, debug_service, mock_db_session) -> None:
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

        with patch("borgitory.config.DATABASE_URL", "sqlite:///test.db"), patch(
            "os.path.exists", return_value=True
        ), patch("os.path.getsize", return_value=1024 * 1024):  # 1MB
            result = debug_service._get_database_info(mock_db_session)

            assert result["repository_count"] == 5
            assert result["total_jobs"] == 100
            assert result["jobs_today"] == 10
            assert result["database_type"] == "SQLite"
            assert result["database_url"] == "sqlite:///test.db"
            assert result["database_size"] == "1.0 MB"
            assert result["database_size_bytes"] == 1024 * 1024
            assert result["database_accessible"] is True

    def test_get_database_info_size_formatting(
        self, debug_service, mock_db_session
    ) -> None:
        """Test database size formatting for different sizes"""
        mock_db_session.query.return_value.count.return_value = 1

        # Test bytes
        with patch("borgitory.config.DATABASE_URL", "sqlite:///test.db"), patch(
            "os.path.exists", return_value=True
        ), patch("os.path.getsize", return_value=512):
            result = debug_service._get_database_info(mock_db_session)
            assert result["database_size"] == "512 B"

        # Test KB
        with patch("borgitory.config.DATABASE_URL", "sqlite:///test.db"), patch(
            "os.path.exists", return_value=True
        ), patch("os.path.getsize", return_value=2048):
            result = debug_service._get_database_info(mock_db_session)
            assert result["database_size"] == "2.0 KB"

        # Test GB
        with patch("borgitory.config.DATABASE_URL", "sqlite:///test.db"), patch(
            "os.path.exists", return_value=True
        ), patch("os.path.getsize", return_value=2 * 1024 * 1024 * 1024):
            result = debug_service._get_database_info(mock_db_session)
            assert result["database_size"] == "2.0 GB"

    def test_get_database_info_exception_handling(
        self, debug_service, mock_db_session
    ) -> None:
        """Test database info exception handling"""
        mock_db_session.query.side_effect = Exception("Database error")

        result = debug_service._get_database_info(mock_db_session)

        assert "error" in result
        assert result["database_accessible"] is False

    @pytest.mark.asyncio
    async def test_get_volume_info_success(
        self, debug_service, mock_volume_service
    ) -> None:
        """Test volume info collection success"""
        # Configure the mock volume service
        mock_volume_service.get_volume_info.return_value = {
            "mounted_volumes": ["/data", "/backup"],
            "total_mounted_volumes": 2,
        }

        result = await debug_service._get_volume_info()

        assert result["mounted_volumes"] == ["/data", "/backup"]
        assert result["total_mounted_volumes"] == 2

    @pytest.mark.asyncio
    async def test_get_volume_info_with_volumes(
        self, debug_service, mock_volume_service
    ) -> None:
        """Test volume info when volumes are present"""
        # Configure the mock volume service for this specific test
        mock_volume_service.get_volume_info.return_value = {
            "mounted_volumes": ["/data"],
            "total_mounted_volumes": 1,
        }

        result = await debug_service._get_volume_info()

        assert result["mounted_volumes"] == ["/data"]
        assert result["total_mounted_volumes"] == 1

    @pytest.mark.asyncio
    async def test_get_volume_info_service_failure(
        self, debug_service, mock_volume_service
    ) -> None:
        """Test volume info when volume service fails"""
        # Configure the mock volume service to raise an exception
        mock_volume_service.get_volume_info.side_effect = Exception(
            "Volume service error"
        )

        result = await debug_service._get_volume_info()

        assert "error" in result
        assert result["mounted_volumes"] == []
        assert result["total_mounted_volumes"] == 0

    @pytest.mark.asyncio
    async def test_get_tool_versions_success(self, debug_service) -> None:
        """Test successful tool version detection"""
        # Mock borg process
        mock_borg_process = MagicMock()
        mock_borg_process.returncode = 0
        mock_borg_process.communicate = AsyncMock(return_value=(b"borg 1.2.0\n", b""))

        # Mock rclone process
        mock_rclone_process = MagicMock()
        mock_rclone_process.returncode = 0
        mock_rclone_process.communicate = AsyncMock(
            return_value=(b"rclone v1.58.0\n", b"")
        )

        async def create_subprocess_side_effect(*args, **kwargs):
            if "borg" in args:
                return mock_borg_process
            elif "rclone" in args:
                return mock_rclone_process

        with patch(
            "asyncio.create_subprocess_exec", side_effect=create_subprocess_side_effect
        ):
            result = await debug_service._get_tool_versions()

            assert result["borg"]["version"] == "borg 1.2.0"
            assert result["borg"]["accessible"] is True
            assert result["rclone"]["version"] == "rclone v1.58.0"
            assert result["rclone"]["accessible"] is True

    @pytest.mark.asyncio
    async def test_get_tool_versions_command_failures(self, debug_service) -> None:
        """Test tool version detection when commands fail"""
        # Mock borg process failure
        mock_borg_process = MagicMock()
        mock_borg_process.returncode = 1
        mock_borg_process.communicate = AsyncMock(
            return_value=(b"", b"command not found")
        )

        # Mock rclone exception
        async def create_subprocess_side_effect(*args, **kwargs):
            if "borg" in args:
                return mock_borg_process
            elif "rclone" in args:
                raise Exception("Rclone not installed")

        with patch(
            "asyncio.create_subprocess_exec", side_effect=create_subprocess_side_effect
        ):
            result = await debug_service._get_tool_versions()

            assert result["borg"]["accessible"] is False
            assert "error" in result["borg"]
            assert result["rclone"]["accessible"] is False
            assert "error" in result["rclone"]

    def test_get_environment_info(self, debug_service, mock_environment) -> None:
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
        self, debug_service, mock_environment
    ) -> None:
        """Test that non-sqlite database URLs are hidden"""
        mock_environment.env_vars = {
            "DATABASE_URL": "postgresql://user:pass@localhost/db"
        }

        result = debug_service._get_environment_info()

        assert result["DATABASE_URL"] == "***HIDDEN***"

    def test_get_job_manager_info_success(self, debug_service) -> None:
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

        assert result["active_jobs"] == 2  # 2 running jobs
        assert result["total_jobs"] == 3  # 3 total jobs
        assert result["job_manager_running"] is True

    def test_get_job_manager_info_no_jobs_attribute(self, debug_service) -> None:
        """Test job manager info when job manager has no jobs attribute"""
        mock_job_manager = MagicMock()
        del mock_job_manager.jobs  # Remove jobs attribute

        # Using constructor-injected job manager
        debug_service.job_manager = mock_job_manager
        result = debug_service._get_job_manager_info()

        assert result["active_jobs"] == 0
        assert result["total_jobs"] == 0
        assert result["job_manager_running"] is True

    def test_get_job_manager_info_exception_handling(self, debug_service) -> None:
        """Test job manager info exception handling"""
        # Simulate job manager error by making jobs attribute missing
        mock_job_manager = Mock()
        # Don't set jobs attribute to simulate AttributeError
        del mock_job_manager.jobs
        debug_service.job_manager = mock_job_manager

        result = debug_service._get_job_manager_info()

        # Should handle missing jobs attribute gracefully
        assert "active_jobs" in result
        assert result["total_jobs"] == 0  # Due to missing jobs attribute

    def test_get_job_manager_info_jobs_without_status(self, debug_service) -> None:
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

        assert result["active_jobs"] == 1  # Only job2 counts as running
        assert result["total_jobs"] == 2  # Both jobs counted in total
