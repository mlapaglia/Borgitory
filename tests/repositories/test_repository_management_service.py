"""
Unit tests for Repository Management Service - Business Logic.
Tests the new repository management features using proper DI without patching.
"""

import pytest
from unittest.mock import Mock, AsyncMock
from typing import Any

from borgitory.services.repositories.repository_service import RepositoryService
from borgitory.models.database import Repository


class TestRepositoryService:
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
    def mock_volume_service(self) -> Any:
        """Mock volume service."""
        return Mock()

    @pytest.fixture
    def repository_service(
        self,
        mock_borg_service: Any,
        mock_scheduler_service: Any,
        mock_volume_service: Any,
    ) -> RepositoryService:
        """Create repository service with mocked dependencies."""
        return RepositoryService(
            borg_service=mock_borg_service,
            scheduler_service=mock_scheduler_service,
            volume_service=mock_volume_service,
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

    def test_mock_repository_structure(self, mock_repository: Any) -> None:
        """Test that mock repository has expected attributes."""
        assert mock_repository.id == 1
        assert mock_repository.name == "test-repo"
        assert mock_repository.path == "/test/repo/path"
        assert mock_repository.get_passphrase() == "test_passphrase"
        assert mock_repository.get_keyfile_content() is None
