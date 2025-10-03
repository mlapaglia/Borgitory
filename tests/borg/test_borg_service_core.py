"""
Tests for BorgService - Core functionality tests
"""

import pytest
import re
from unittest.mock import Mock, AsyncMock

from borgitory.services.borg_service import BorgService
from borgitory.protocols.command_executor_protocol import CommandExecutorProtocol
from borgitory.models.database import Repository


@pytest.fixture
def mock_command_executor() -> Mock:
    """Create mock command executor."""
    mock = Mock(spec=CommandExecutorProtocol)
    mock.create_subprocess = AsyncMock()
    mock.execute_command = AsyncMock()
    return mock


@pytest.fixture
def mock_job_executor() -> Mock:
    """Create mock job executor."""
    return Mock()


@pytest.fixture
def mock_command_runner() -> Mock:
    """Create mock command runner."""
    return Mock()


@pytest.fixture
def mock_job_manager() -> Mock:
    """Create mock job manager."""
    return Mock()


@pytest.fixture
def mock_archive_service() -> Mock:
    """Create mock archive service."""
    return Mock()


@pytest.fixture
def borg_service(
    mock_job_executor: Mock,
    mock_command_runner: Mock,
    mock_job_manager: Mock,
    mock_archive_service: Mock,
    mock_command_executor: Mock,
) -> BorgService:
    """Create BorgService with mock dependencies."""
    return BorgService(
        job_executor=mock_job_executor,
        command_runner=mock_command_runner,
        job_manager=mock_job_manager,
        archive_service=mock_archive_service,
        command_executor=mock_command_executor,
    )


@pytest.fixture
def mock_repository() -> Mock:
    """Create mock repository."""
    repo = Mock(spec=Repository)
    repo.name = "test-repo"
    repo.path = "/test/repo/path"
    repo.get_passphrase.return_value = "test-passphrase"
    repo.get_keyfile_content.return_value = None
    return repo


class TestBorgServiceCore:
    """Test core BorgService functionality."""

    def test_service_initialization(
        self,
        mock_job_executor: Mock,
        mock_command_runner: Mock,
        mock_job_manager: Mock,
        mock_archive_service: Mock,
        mock_command_executor: Mock,
    ) -> None:
        """Test BorgService initializes correctly with all dependencies."""
        service = BorgService(
            job_executor=mock_job_executor,
            command_runner=mock_command_runner,
            job_manager=mock_job_manager,
            archive_service=mock_archive_service,
            command_executor=mock_command_executor,
        )

        assert service.job_executor is mock_job_executor
        assert service.command_runner is mock_command_runner
        assert service.job_manager is mock_job_manager
        assert service.archive_service is mock_archive_service
        assert service.command_executor is mock_command_executor

    def test_progress_pattern_matching(self, borg_service: BorgService) -> None:
        """Test that the progress pattern regex works correctly."""
        # Test pattern exists
        assert hasattr(borg_service, "progress_pattern")
        assert isinstance(borg_service.progress_pattern, re.Pattern)

        # Test pattern matching
        test_line = "1024 512 256 5 /home/user/test.txt"
        match = borg_service.progress_pattern.match(test_line)

        assert match is not None
        assert match.group("original_size") == "1024"
        assert match.group("compressed_size") == "512"
        assert match.group("deduplicated_size") == "256"
        assert match.group("nfiles") == "5"
        assert match.group("path") == "/home/user/test.txt"

    def test_has_required_methods(self, borg_service: BorgService) -> None:
        """Test that BorgService has all required methods."""
        required_methods = [
            "list_archives",
            "initialize_repository",
            "verify_repository_access",
        ]

        for method_name in required_methods:
            assert hasattr(borg_service, method_name)
            assert callable(getattr(borg_service, method_name))


class TestBorgServiceIntegration:
    """Test integration scenarios."""

    def test_dependency_injection_pattern(
        self,
        mock_job_executor: Mock,
        mock_command_runner: Mock,
        mock_job_manager: Mock,
        mock_archive_service: Mock,
        mock_command_executor: Mock,
    ) -> None:
        """Test that BorgService follows proper dependency injection patterns."""
        # Should be able to create multiple instances with different dependencies
        service1 = BorgService(
            job_executor=mock_job_executor,
            command_runner=mock_command_runner,
            job_manager=mock_job_manager,
            archive_service=mock_archive_service,
            command_executor=mock_command_executor,
        )

        # Create different mocks
        other_job_executor = Mock()
        other_command_executor = Mock(spec=CommandExecutorProtocol)

        service2 = BorgService(
            job_executor=other_job_executor,
            command_runner=mock_command_runner,
            job_manager=mock_job_manager,
            archive_service=mock_archive_service,
            command_executor=other_command_executor,
        )

        # Services should have different dependencies
        assert service1.job_executor is not service2.job_executor
        assert service1.command_executor is not service2.command_executor

        # But same shared dependencies should be the same
        assert service1.command_runner is service2.command_runner
        assert service1.job_manager is service2.job_manager
        assert service1.archive_service is service2.archive_service
