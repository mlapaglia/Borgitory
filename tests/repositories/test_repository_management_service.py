"""
Unit tests for Repository Management Service - Business Logic.
Tests the new repository management features following the established codebase patterns.
"""

import pytest
import json
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from typing import Any

from borgitory.services.repositories.repository_service import RepositoryService
from borgitory.models.database import Repository


class TestRepositoryManagementService:
    """Test repository service business logic for new management features."""

    @pytest.fixture
    def mock_borg_service(self) -> Any:
        """Mock borg service."""
        mock = Mock()
        mock.initialize_repository = AsyncMock()
        mock.verify_repository_access = AsyncMock()
        mock.scan_for_repositories = AsyncMock()
        mock.list_archives = AsyncMock()
        return mock

    @pytest.fixture
    def mock_scheduler_service(self) -> Any:
        """Mock scheduler service."""
        mock = Mock()
        mock.remove_schedule = AsyncMock()
        return mock

    @pytest.fixture
    def mock_path_service(self) -> Any:
        """Create mock path service."""
        mock = Mock()
        mock.get_keyfiles_dir.return_value = "/test/keyfiles"
        mock.ensure_directory.return_value = True
        mock.secure_join.return_value = "/test/keyfiles/test_file"
        return mock

    @pytest.fixture
    def mock_file_service(self) -> Any:
        """Create mock file service."""
        mock = Mock()
        mock.write_file = AsyncMock()
        mock.remove_file = AsyncMock()
        mock.open_file = Mock()
        return mock

    @pytest.fixture
    def repository_service(
        self,
        mock_borg_service: Any,
        mock_scheduler_service: Any,
        mock_path_service: Any,
        mock_file_service: Any,
    ) -> RepositoryService:
        """Create repository service with mocked dependencies."""
        from unittest.mock import Mock, AsyncMock

        mock_command_executor = Mock()
        mock_command_executor.execute_command = AsyncMock()
        mock_command_executor.create_subprocess = AsyncMock()

        return RepositoryService(
            borg_service=mock_borg_service,
            scheduler_service=mock_scheduler_service,
            path_service=mock_path_service,
            command_executor=mock_command_executor,
            file_service=mock_file_service,
        )

    @pytest.fixture
    def mock_repository(self) -> Any:
        """Create mock repository."""
        repo = Mock(spec=Repository)
        repo.id = 1
        repo.name = "test-repo"
        repo.path = "/test/repo/path"
        repo.get_passphrase.return_value = "test_passphrase"
        repo.get_keyfile_content.return_value = None
        repo.cache_dir = "/mnt/test/cache/dir"
        return repo

    def test_format_bytes_helper(self, repository_service: RepositoryService) -> None:
        """Test the _format_bytes helper method."""
        assert repository_service._format_bytes(0) == "0 B"
        assert repository_service._format_bytes(1023) == "1023.0 B"
        assert repository_service._format_bytes(1024) == "1.0 KB"
        assert repository_service._format_bytes(1048576) == "1.0 MB"
        assert repository_service._format_bytes(1073741824) == "1.0 GB"
        assert repository_service._format_bytes(1099511627776) == "1.0 TB"

    def test_service_initialization(
        self, repository_service: RepositoryService
    ) -> None:
        """Test that repository service initializes correctly with dependencies."""
        assert repository_service is not None
        assert hasattr(repository_service, "_format_bytes")
        assert hasattr(repository_service, "check_repository_lock_status")
        assert hasattr(repository_service, "break_repository_lock")
        assert hasattr(repository_service, "get_repository_info")
        assert hasattr(repository_service, "export_repository_key")

    def test_repository_service_has_required_methods(
        self, repository_service: RepositoryService
    ) -> None:
        """Test that repository service has all the new management methods."""
        # Verify the new methods exist and are callable
        assert callable(
            getattr(repository_service, "check_repository_lock_status", None)
        )
        assert callable(getattr(repository_service, "break_repository_lock", None))
        assert callable(getattr(repository_service, "get_repository_info", None))
        assert callable(getattr(repository_service, "export_repository_key", None))

    def test_service_dependencies_injection(
        self,
        repository_service: RepositoryService,
        mock_borg_service: Any,
        mock_scheduler_service: Any,
    ) -> None:
        """Test that dependencies are properly injected."""
        assert repository_service.borg_service is mock_borg_service
        assert repository_service.scheduler_service is mock_scheduler_service

    def test_format_bytes_edge_cases(
        self, repository_service: RepositoryService
    ) -> None:
        """Test _format_bytes with edge cases."""
        # Test zero
        assert repository_service._format_bytes(0) == "0 B"

        # Test exact boundaries
        assert repository_service._format_bytes(1024) == "1.0 KB"
        assert repository_service._format_bytes(1048576) == "1.0 MB"
        assert repository_service._format_bytes(1073741824) == "1.0 GB"

        # Test just under boundaries
        assert repository_service._format_bytes(1023) == "1023.0 B"
        assert repository_service._format_bytes(1048575) == "1024.0 KB"

        # Test large numbers
        assert repository_service._format_bytes(1099511627776) == "1.0 TB"

        # Test very large numbers (should go to PB)
        assert repository_service._format_bytes(1125899906842624) == "1.0 PB"


class TestRepositoryManagementBusinessLogic:
    """Test the actual business logic of repository management methods using established patterns."""

    @pytest.fixture
    def mock_borg_service(self) -> Any:
        """Mock borg service."""
        return Mock()

    @pytest.fixture
    def mock_scheduler_service(self) -> Any:
        """Mock scheduler service."""
        return Mock()

    @pytest.fixture
    def mock_path_service(self) -> Any:
        """Create mock path service."""
        mock = Mock()
        mock.get_keyfiles_dir.return_value = "/test/keyfiles"
        mock.ensure_directory.return_value = True
        mock.secure_join.return_value = "/test/keyfiles/test_file"
        return mock

    @pytest.fixture
    def mock_file_service(self) -> Any:
        """Create mock file service."""
        mock = Mock()
        mock.write_file = AsyncMock()
        mock.remove_file = AsyncMock()
        mock.open_file = Mock()
        return mock

    @pytest.fixture
    def repository_service(
        self,
        mock_borg_service: Any,
        mock_scheduler_service: Any,
        mock_path_service: Any,
        mock_file_service: Any,
    ) -> RepositoryService:
        """Create repository service with mocked dependencies."""
        from unittest.mock import Mock, AsyncMock

        mock_command_executor = Mock()
        mock_command_executor.execute_command = AsyncMock()
        mock_command_executor.create_subprocess = AsyncMock()

        return RepositoryService(
            borg_service=mock_borg_service,
            scheduler_service=mock_scheduler_service,
            path_service=mock_path_service,
            command_executor=mock_command_executor,
            file_service=mock_file_service,
        )

    @pytest.fixture
    def mock_repository(self) -> Any:
        """Create mock repository."""
        repo = Mock(spec=Repository)
        repo.id = 1
        repo.name = "test-repo"
        repo.path = "/test/repo/path"
        repo.get_passphrase.return_value = "test_passphrase"
        repo.get_keyfile_content.return_value = None
        repo.cache_dir = "/mnt/test/cache/dir"
        return repo

    async def test_check_repository_lock_status_unlocked(
        self, repository_service: RepositoryService, mock_repository: Any
    ) -> None:
        """Test check_repository_lock_status when repository is unlocked."""
        # Mock successful subprocess execution (repository is accessible)
        mock_process = Mock()
        mock_process.returncode = 0
        mock_process.communicate = AsyncMock(
            return_value=(b"archive1\narchive2\n", b"")
        )

        with (
            patch(
                "borgitory.services.repositories.repository_service.create_borg_command"
            ) as mock_create_cmd,
            patch("asyncio.create_subprocess_exec", return_value=mock_process),
            patch("asyncio.wait_for", return_value=(b"archive1\narchive2\n", b"")),
        ):
            # Mock create_borg_command to return a BorgCommandResult object
            mock_borg_cmd = MagicMock()
            mock_borg_cmd.command = ["borg", "config", "--list", "/test/repo/path"]
            mock_borg_cmd.environment = {"BORG_PASSPHRASE": "test_passphrase"}
            mock_create_cmd.return_value = mock_borg_cmd

            result = await repository_service.check_repository_lock_status(
                mock_repository
            )

            # Verify the business logic results
            assert result["locked"] is False
            assert result["accessible"] is True
            assert result["message"] == "Repository is accessible"
            assert "error" not in result

            # Verify create_borg_command was called correctly
            mock_create_cmd.assert_called_once_with(
                base_command="borg config",
                repository_path=mock_repository.path,
                passphrase=mock_repository.get_passphrase(),
                additional_args=["--list"],
                environment_overrides={"BORG_CACHE_DIR": "/mnt/test/cache/dir"},
            )

    async def test_check_repository_lock_status_locked_timeout(
        self, repository_service: RepositoryService, mock_repository: Any
    ) -> None:
        """Test check_repository_lock_status when repository is locked (timeout)."""
        from borgitory.protocols.command_executor_protocol import (
            CommandResult as ExecutorCommandResult,
        )

        # Get the mock command executor from the repository service
        mock_executor = repository_service.command_executor

        # Mock the executor to return a timeout result
        mock_executor.execute_command = AsyncMock(
            return_value=ExecutorCommandResult(
                command=["borg", "list", "/test/repo/path", "--short"],
                return_code=-1,
                stdout="",
                stderr="Command timed out after 10.0 seconds",
                success=False,
                execution_time=10.0,
                error="Command timed out after 10.0 seconds",
            )
        )

        result = await repository_service.check_repository_lock_status(mock_repository)

        # Verify the business logic results for locked repository
        assert result["locked"] is True
        assert result["accessible"] is False
        assert (
            "timeout" in result["message"].lower()
            or "locked" in result["message"].lower()
        )

    async def test_check_repository_lock_status_error_with_lock_message(
        self, repository_service: RepositoryService, mock_repository: Any
    ) -> None:
        """Test check_repository_lock_status when borg returns lock error."""
        from borgitory.protocols.command_executor_protocol import (
            CommandResult as ExecutorCommandResult,
        )

        # Get the mock command executor from the repository service
        mock_executor = repository_service.command_executor

        # Mock the executor to return a lock error
        mock_executor.execute_command = AsyncMock(
            return_value=ExecutorCommandResult(
                command=["borg", "list", "/test/repo/path", "--short"],
                return_code=2,
                stdout="",
                stderr="Failed to create/acquire the lock",
                success=False,
                execution_time=5.0,
                error="Failed to create/acquire the lock",
            )
        )

        result = await repository_service.check_repository_lock_status(mock_repository)

        # Verify the business logic results for locked repository
        assert result["locked"] is True
        assert result["accessible"] is False
        assert "locked by another process" in result["message"]
        assert "error" in result

    async def test_break_repository_lock_success(
        self, repository_service: RepositoryService, mock_repository: Any
    ) -> None:
        """Test break_repository_lock when successful."""
        # Mock successful subprocess execution
        mock_process = Mock()
        mock_process.returncode = 0
        mock_process.communicate = AsyncMock(
            return_value=(b"Lock broken successfully\n", b"")
        )

        with (
            patch(
                "borgitory.services.repositories.repository_service.create_borg_command"
            ) as mock_create_cmd,
            patch("asyncio.create_subprocess_exec", return_value=mock_process),
            patch(
                "asyncio.wait_for", return_value=(b"Lock broken successfully\n", b"")
            ),
        ):
            # Mock create_borg_command to return a BorgCommandResult object
            mock_borg_cmd = MagicMock()
            mock_borg_cmd.command = ["borg", "break-lock", "/test/repo/path"]
            mock_borg_cmd.environment = {"BORG_PASSPHRASE": "test_passphrase"}
            mock_create_cmd.return_value = mock_borg_cmd

            result = await repository_service.break_repository_lock(mock_repository)

            # Verify the business logic results
            assert result["success"] is True
            assert "successfully" in result["message"].lower()
            assert "error" not in result

            # Verify create_borg_command was called correctly
            mock_create_cmd.assert_called_once_with(
                base_command="borg break-lock",
                repository_path=mock_repository.path,
                passphrase=mock_repository.get_passphrase(),
                additional_args=[],
                environment_overrides={"BORG_CACHE_DIR": "/mnt/test/cache/dir"},
            )

    async def test_break_repository_lock_failure(
        self, repository_service: RepositoryService, mock_repository: Any
    ) -> None:
        """Test break_repository_lock when it fails."""
        from borgitory.protocols.command_executor_protocol import (
            CommandResult as ExecutorCommandResult,
        )

        # Get the mock command executor from the repository service
        mock_executor = repository_service.command_executor

        # Mock the executor to return a failure result
        mock_executor.execute_command = AsyncMock(
            return_value=ExecutorCommandResult(
                command=["borg", "break-lock", "/test/repo/path"],
                return_code=1,
                stdout="",
                stderr="Permission denied",
                success=False,
                execution_time=2.0,
                error="Permission denied",
            )
        )

        result = await repository_service.break_repository_lock(mock_repository)

        # Verify the business logic results
        assert result["success"] is False
        assert "failed" in result["message"].lower()
        assert result["error"] == "Permission denied"

    async def test_get_repository_info_success(
        self, repository_service: RepositoryService, mock_repository: Any
    ) -> None:
        """Test get_repository_info when successful."""
        from borgitory.protocols.command_executor_protocol import (
            CommandResult as ExecutorCommandResult,
        )

        # Mock borg info JSON response
        borg_info_json = {
            "repository": {
                "id": "1ed5524364ba06c2d9a4cc363b8193589215e82e7f4d1853beb9e1c01bfcc28b",
                "location": "/test/repo/path",
            },
            "encryption": {"mode": "repokey"},
            "cache": {"path": "/home/user/.cache/borg/1ed5524364ba06c2"},
            "security_dir": "/home/user/.config/borg/security/1ed5524364ba06c2",
            "archives": [
                {"name": "archive1", "start": "2023-01-01T12:00:00"},
                {"name": "archive2", "start": "2023-01-02T12:00:00"},
            ],
        }

        # Mock borg config response
        borg_config_output = "repository.id = 1ed5524364ba06c2d9a4cc363b8193589215e82e7f4d1853beb9e1c01bfcc28b\nrepository.segments_per_dir = 1000\n"

        # Get the mock command executor from the repository service
        mock_executor = repository_service.command_executor

        # Mock the executor to return different results for different calls
        mock_executor.execute_command = AsyncMock(
            side_effect=[
                # First call: borg info
                ExecutorCommandResult(
                    command=["borg", "info", "/test/repo/path", "--json"],
                    return_code=0,
                    stdout=json.dumps(borg_info_json),
                    stderr="",
                    success=True,
                    execution_time=3.0,
                ),
                # Second call: borg config
                ExecutorCommandResult(
                    command=["borg", "config", "/test/repo/path", "--list"],
                    return_code=0,
                    stdout=borg_config_output,
                    stderr="",
                    success=True,
                    execution_time=1.0,
                ),
            ]
        )

        result = await repository_service.get_repository_info(mock_repository)

        # Verify the business logic results
        assert "repository_id" in result
        assert "location" in result
        assert "encryption" in result
        assert "archives_count" in result
        assert "config" in result
        assert (
            result["repository_id"]
            == "1ed5524364ba06c2d9a4cc363b8193589215e82e7f4d1853beb9e1c01bfcc28b"
        )
        assert result["location"] == "/test/repo/path"
        assert result["archives_count"] == 2
        assert "repository.id" in result["config"]

    async def test_export_repository_key_success(
        self, repository_service: RepositoryService, mock_repository: Any
    ) -> None:
        """Test export_repository_key when successful."""
        from borgitory.protocols.command_executor_protocol import (
            CommandResult as ExecutorCommandResult,
        )

        # Mock successful key export
        key_data = "BORG_KEY 1ed5524364ba06c2d9a4cc363b8193589215e82e7f4d1853beb9e1c01bfcc28b\nhQEMA..."

        # Get the mock command executor from the repository service
        mock_executor = repository_service.command_executor

        # Mock the executor to return successful key export
        mock_executor.execute_command = AsyncMock(
            return_value=ExecutorCommandResult(
                command=["borg", "key", "export", "/test/repo/path"],
                return_code=0,
                stdout=key_data,
                stderr="",
                success=True,
                execution_time=2.0,
            )
        )

        result = await repository_service.export_repository_key(mock_repository)

        # Verify the business logic results
        assert result["success"] is True
        assert result["key_data"] == key_data
        assert result["filename"] == "test-repo_key.txt"

    async def test_export_repository_key_failure(
        self, repository_service: RepositoryService, mock_repository: Any
    ) -> None:
        """Test export_repository_key when it fails."""
        from borgitory.protocols.command_executor_protocol import (
            CommandResult as ExecutorCommandResult,
        )

        # Get the mock command executor from the repository service
        mock_executor = repository_service.command_executor

        # Mock the executor to return a failure result
        mock_executor.execute_command = AsyncMock(
            return_value=ExecutorCommandResult(
                command=["borg", "key", "export", "/test/repo/path"],
                return_code=1,
                stdout="",
                stderr="Repository not found",
                success=False,
                execution_time=1.0,
                error="Repository not found",
            )
        )

        result = await repository_service.export_repository_key(mock_repository)

        # Verify the business logic results
        assert result["success"] is False
        assert "error_message" in result
        assert "Repository not found" in result["error_message"]
