"""
Unit tests for Repository Service.
Tests business logic independent of HTTP concerns.
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch
from sqlalchemy.orm import Session

from borgitory.models.borg_info import RepositoryInitializationResult
from borgitory.protocols.repository_protocols import BackupServiceProtocol
from borgitory.services.repositories.repository_service import RepositoryService
from borgitory.models.repository_dtos import (
    ArchiveInfo,
    CreateRepositoryRequest,
    ImportRepositoryRequest,
    RepositoryOperationResult,
    RepositoryValidationError,
    RepositoryScanRequest,
    DeleteRepositoryRequest,
)


class TestRepositoryService:
    """Test cases for repository service business logic."""

    @pytest.fixture
    def mock_borg_service(self) -> BackupServiceProtocol:
        """Mock borg service."""
        mock: BackupServiceProtocol = Mock()
        mock.initialize_repository = AsyncMock()
        mock.verify_repository_access = AsyncMock()
        mock.scan_for_repositories = AsyncMock()
        mock.list_archives = AsyncMock()
        return mock

    @pytest.fixture
    def mock_scheduler_service(self):
        """Mock scheduler service."""
        mock = Mock()
        mock.remove_schedule = AsyncMock()
        return mock

    @pytest.fixture
    def mock_volume_service(self):
        """Mock volume service."""
        mock = Mock()
        return mock

    @pytest.fixture
    def mock_db_session(self):
        """Mock database session."""
        mock = Mock(spec=Session)
        mock.query.return_value.filter.return_value.first.return_value = None
        mock.query.return_value.filter.return_value.all.return_value = []
        mock.add = Mock()
        mock.commit = Mock()
        mock.refresh = Mock()
        mock.delete = Mock()
        mock.rollback = Mock()
        return mock

    @pytest.fixture
    def repository_service(
        self, mock_borg_service, mock_scheduler_service, mock_volume_service
    ):
        """Create repository service with mocked dependencies."""
        return RepositoryService(
            borg_service=mock_borg_service,
            scheduler_service=mock_scheduler_service,
            volume_service=mock_volume_service,
        )

    @pytest.mark.asyncio
    async def test_create_repository_success(
        self,
        repository_service: RepositoryService,
        mock_borg_service: Mock,
        mock_db_session: Mock,
    ) -> None:
        """Test successful repository creation."""
        # Arrange
        request = CreateRepositoryRequest(
            name="test-repo",
            path="/mnt/backup/test-repo",
            passphrase="secret123",
            user_id=1,
        )

        # Mock successful initialization
        mock_borg_service.initialize_repository.return_value = (
            RepositoryInitializationResult.success_result(
                "Repository initialized successfully",
                repository_path="/mnt/backup/test-repo",
            )
        )

        # Mock repository object
        mock_repo = Mock()
        mock_repo.id = 123
        mock_repo.name = "test-repo"
        mock_db_session.add = Mock()
        mock_db_session.commit = Mock()
        mock_db_session.refresh = Mock(side_effect=lambda x: setattr(x, "id", 123))

        with patch(
            "borgitory.services.repositories.repository_service.Repository",
            return_value=mock_repo,
        ):
            # Act
            result = await repository_service.create_repository(
                request, mock_db_session
            )

            # Assert
            assert result.success is True
            assert result.repository_id == 123
            assert result.repository_name == "test-repo"
            assert result.message is not None
            assert "created successfully" in result.message
            mock_borg_service.initialize_repository.assert_called_once()
            mock_db_session.add.assert_called_once()
            mock_db_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_repository_name_already_exists(
        self, repository_service, mock_db_session
    ) -> None:
        """Test repository creation fails when name already exists."""
        # Arrange
        request = CreateRepositoryRequest(
            name="existing-repo",
            path="/mnt/backup/test-repo",
            passphrase="secret123",
            user_id=1,
        )

        # Mock existing repository with same name
        existing_repo = Mock()
        existing_repo.name = "existing-repo"

        # Set up mock to return existing repo for name check, None for path check
        # The service checks name first, then path, so we use side_effect
        mock_db_session.query.return_value.filter.return_value.first.side_effect = [
            existing_repo,
            None,
        ]

        # Act
        result = await repository_service.create_repository(request, mock_db_session)

        # Assert
        assert result.success is False
        assert result.is_validation_error is True
        assert len(result.validation_errors) == 1
        assert result.validation_errors[0].field == "name"
        assert "already exists" in result.validation_errors[0].message

    @pytest.mark.asyncio
    async def test_create_repository_borg_initialization_fails(
        self,
        repository_service: RepositoryService,
        mock_borg_service: Mock,
        mock_db_session: Mock,
    ) -> None:
        """Test repository creation fails when Borg initialization fails."""
        from borgitory.models.borg_info import RepositoryInitializationResult

        # Arrange
        request = CreateRepositoryRequest(
            name="test-repo",
            path="/mnt/backup/test-repo",
            passphrase="secret123",
            user_id=1,
        )

        # Test different types of Borg failures
        mock_borg_service.initialize_repository.return_value = (
            RepositoryInitializationResult.failure_result(
                "Read-only file system"  # This should trigger specific error parsing
            )
        )

        # Act
        result = await repository_service.create_repository(request, mock_db_session)

        # Assert - Test that business logic parses the error correctly
        assert result.success is False
        assert result.is_borg_error is True
        assert result.error_message is not None
        assert "read-only" in result.error_message  # Tests error parsing logic
        assert (
            "writable location" in result.error_message
        )  # Tests user-friendly message

    @pytest.mark.asyncio
    async def test_scan_repositories_success(
        self, repository_service: RepositoryService, mock_borg_service: Mock
    ) -> None:
        """Test successful repository scanning."""
        # Arrange
        request = RepositoryScanRequest()

        from borgitory.models.borg_info import (
            BorgScannedRepository,
            RepositoryScanResponse,
        )

        mock_repos = [
            BorgScannedRepository(
                path="/mnt/backup/repo1",
                id="repo_1",
                encryption_mode="repokey",
                requires_keyfile=False,
                detected=True,
                config_preview="Encrypted repository",
            ),
            BorgScannedRepository(
                path="/mnt/backup/repo2",
                id="repo_2",
                encryption_mode="none",
                requires_keyfile=False,
                detected=True,
                config_preview="Unencrypted repository",
            ),
        ]

        mock_borg_service.scan_for_repositories.return_value = RepositoryScanResponse(
            repositories=mock_repos, scan_paths=["/mnt/backup"]
        )

        # Act
        result = await repository_service.scan_repositories(request)

        # Assert
        assert result.success is True
        assert len(result.repositories) == 2
        assert (
            result.repositories[0].name == ""
        )  # Borg doesn't provide name, will be set by user
        assert result.repositories[0].path == "/mnt/backup/repo1"
        assert result.repositories[0].encryption_mode == "repokey"
        assert result.repositories[0].requires_keyfile is False
        assert (
            result.repositories[1].name == ""
        )  # Borg doesn't provide name, will be set by user
        assert result.repositories[1].path == "/mnt/backup/repo2"
        assert result.repositories[1].encryption_mode == "none"
        assert result.repositories[1].requires_keyfile is False

    @pytest.mark.asyncio
    async def test_delete_repository_blocked_by_active_jobs(
        self, repository_service: RepositoryService, mock_db_session: Mock
    ) -> None:
        """Test repository deletion blocked by active jobs."""
        # Arrange
        request = DeleteRepositoryRequest(repository_id=123, user_id=1)

        # Mock repository exists
        mock_repo = Mock()
        mock_repo.id = 123
        mock_repo.name = "test-repo"

        # Mock active jobs exist
        mock_job1 = Mock()
        mock_job1.type = "backup"
        mock_job2 = Mock()
        mock_job2.type = "prune"

        # Set up query chain to return repository first, then active jobs
        repo_query = Mock()
        repo_query.filter.return_value.first.return_value = mock_repo

        jobs_query = Mock()
        jobs_query.filter.return_value.all.return_value = [mock_job1, mock_job2]

        mock_db_session.query.side_effect = [repo_query, jobs_query]

        with patch.multiple(
            "borgitory.services.repositories.repository_service",
            Repository=Mock(),
            Job=Mock(),
        ):
            # Act
            result = await repository_service.delete_repository(
                request, mock_db_session
            )

            # Assert
            assert result.success is False
            assert result.has_conflicts is True
            assert result.conflict_jobs == ["backup", "prune"]
            assert result.error_message is not None
            assert "active job(s) running" in result.error_message

    @pytest.mark.asyncio
    async def test_import_repository_success(
        self,
        repository_service: RepositoryService,
        mock_borg_service: Mock,
        mock_db_session: Mock,
    ) -> None:
        """Test successful repository import."""
        # Arrange
        request = ImportRepositoryRequest(
            name="imported-repo",
            path="/mnt/backup/imported-repo",
            passphrase="secret123",
            keyfile=None,
            user_id=1,
        )

        # Mock successful verification
        mock_borg_service.verify_repository_access.return_value = True
        mock_borg_service.list_archives.return_value = [
            ArchiveInfo(name="archive1", time="2023-01-01T10:00:00"),
            ArchiveInfo(name="archive2", time="2023-01-02T10:00:00"),
        ]

        # Mock repository object
        mock_repo = Mock()
        mock_repo.id = 124
        mock_repo.name = "imported-repo"

        with patch(
            "borgitory.services.repositories.repository_service.Repository",
            return_value=mock_repo,
        ):
            # Act
            result = await repository_service.import_repository(
                request, mock_db_session
            )

            # Assert
            assert result.success is True
            assert result.repository_id == 124
            assert result.repository_name == "imported-repo"
            mock_borg_service.verify_repository_access.assert_called_once()
            mock_db_session.add.assert_called_once()
            mock_db_session.commit.assert_called_once()

    def test_validation_error_properties(self) -> None:
        """Test RepositoryOperationResult validation error properties."""
        # Arrange
        errors = [
            RepositoryValidationError(field="name", message="Name required"),
            RepositoryValidationError(field="path", message="Path invalid"),
        ]

        result = RepositoryOperationResult(success=False, validation_errors=errors)

        # Assert
        assert result.is_validation_error is True
        assert result.is_borg_error is False
        assert result.validation_errors is not None
        assert len(result.validation_errors) == 2

    def test_borg_error_properties(self) -> None:
        """Test RepositoryOperationResult Borg error properties."""
        # Arrange
        result = RepositoryOperationResult(
            success=False, borg_error="Repository already exists"
        )

        # Assert
        assert result.is_borg_error is True
        assert result.is_validation_error is False
