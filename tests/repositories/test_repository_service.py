"""
Unit tests for Repository Service.
Tests business logic independent of HTTP concerns.
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch
from sqlalchemy.orm import Session

from borgitory.models.borg_info import RepositoryInitializationResult
from borgitory.protocols.repository_protocols import BackupServiceProtocol
from borgitory.protocols.command_executor_protocol import CommandExecutorProtocol
from borgitory.services.repositories.repository_service import RepositoryService
from borgitory.models.repository_dtos import (
    CreateRepositoryRequest,
    ImportRepositoryRequest,
)
from borgitory.models.database import Repository


class TestRepositoryService:
    """Test cases for repository service business logic."""

    @pytest.fixture
    def mock_borg_service(self) -> Mock:
        """Mock borg service."""
        mock = Mock(spec=BackupServiceProtocol)
        mock.initialize_repository = AsyncMock()
        mock.verify_repository_access = AsyncMock()
        mock.scan_for_repositories = AsyncMock()
        mock.list_archives = AsyncMock()
        return mock

    @pytest.fixture
    def mock_scheduler_service(self) -> Mock:
        """Mock scheduler service."""
        mock = Mock()
        mock.remove_schedule = AsyncMock()
        return mock

    @pytest.fixture
    def mock_db_session(self) -> Mock:
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
    def mock_path_service(self) -> Mock:
        """Create mock path service."""
        mock = Mock()
        mock.get_keyfiles_dir.return_value = "/test/keyfiles"
        mock.ensure_directory.return_value = True
        mock.secure_join.return_value = "/test/keyfiles/test_file"
        return mock

    @pytest.fixture
    def mock_command_executor(self) -> Mock:
        """Create mock command executor."""
        mock = Mock(spec=CommandExecutorProtocol)
        mock.execute_command = AsyncMock()
        mock.create_subprocess = AsyncMock()
        return mock

    @pytest.fixture
    def mock_file_service(self) -> Mock:
        """Create mock file service."""
        mock = Mock()
        mock.write_file = AsyncMock()
        mock.remove_file = AsyncMock()
        mock.open_file = Mock()
        return mock

    @pytest.fixture
    def repository_service(
        self,
        mock_borg_service: Mock,
        mock_scheduler_service: Mock,
        mock_path_service: Mock,
        mock_command_executor: Mock,
        mock_file_service: Mock,
    ) -> RepositoryService:
        """Create repository service with mocked dependencies."""
        return RepositoryService(
            borg_service=mock_borg_service,
            scheduler_service=mock_scheduler_service,
            path_service=mock_path_service,
            command_executor=mock_command_executor,
            file_service=mock_file_service,
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
        self, repository_service: RepositoryService, mock_db_session: Mock
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
        assert result.validation_errors is not None
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
    async def test_check_repository_lock_status_accessible(
        self,
        repository_service: RepositoryService,
        mock_command_executor: Mock,
    ) -> None:
        """Test checking repository lock status when repository is accessible."""
        from borgitory.protocols.command_executor_protocol import CommandResult
        from borgitory.models.database import Repository

        # Arrange
        repository = Repository()
        repository.path = "/test/repo"
        repository.set_passphrase("test123")

        # Mock successful command execution
        mock_command_executor.execute_command.return_value = CommandResult(
            command=["borg", "list", "/test/repo", "--short"],
            return_code=0,
            stdout="archive1\narchive2\n",
            stderr="",
            success=True,
            execution_time=1.5,
        )

        # Act
        result = await repository_service.check_repository_lock_status(repository)

        # Assert
        assert result["locked"] is False
        assert result["accessible"] is True
        assert result["message"] == "Repository is accessible"
        mock_command_executor.execute_command.assert_called_once()

    @pytest.mark.asyncio
    async def test_check_repository_lock_status_locked(
        self,
        repository_service: RepositoryService,
        mock_command_executor: Mock,
    ) -> None:
        """Test checking repository lock status when repository is locked."""
        from borgitory.protocols.command_executor_protocol import CommandResult
        from borgitory.models.database import Repository

        # Arrange
        repository = Repository()
        repository.path = "/test/repo"
        repository.set_passphrase("test123")

        # Mock failed command execution due to lock
        mock_command_executor.execute_command.return_value = CommandResult(
            command=["borg", "list", "/test/repo", "--short"],
            return_code=2,
            stdout="",
            stderr="Failed to create/acquire the lock",
            success=False,
            execution_time=10.0,
        )

        # Act
        result = await repository_service.check_repository_lock_status(repository)

        # Assert
        assert result["locked"] is True
        assert result["accessible"] is False
        assert result["message"] == "Repository is locked by another process"
        assert "Failed to create/acquire the lock" in result["error"]

    @pytest.mark.asyncio
    async def test_check_repository_lock_status_timeout(
        self,
        repository_service: RepositoryService,
        mock_command_executor: Mock,
    ) -> None:
        """Test checking repository lock status when command times out."""
        from borgitory.protocols.command_executor_protocol import CommandResult
        from borgitory.models.database import Repository

        # Arrange
        repository = Repository()
        repository.path = "/test/repo"
        repository.set_passphrase("test123")

        # Mock timeout
        mock_command_executor.execute_command.return_value = CommandResult(
            command=["borg", "list", "/test/repo", "--short"],
            return_code=-1,
            stdout="",
            stderr="Command timed out after 10.0 seconds",
            success=False,
            execution_time=10.0,
        )

        # Act
        result = await repository_service.check_repository_lock_status(repository)

        # Assert
        assert result["locked"] is True
        assert result["accessible"] is False
        assert result["message"] == "Repository check timed out (possibly locked)"

    @pytest.mark.asyncio
    async def test_break_repository_lock_success(
        self,
        repository_service: RepositoryService,
        mock_command_executor: Mock,
    ) -> None:
        """Test successfully breaking repository lock."""
        from borgitory.protocols.command_executor_protocol import CommandResult
        from borgitory.models.database import Repository

        # Arrange
        repository = Repository()
        repository.name = "test-repo"
        repository.path = "/test/repo"
        repository.set_passphrase("test123")

        # Mock successful lock break
        mock_command_executor.execute_command.return_value = CommandResult(
            command=["borg", "break-lock", "/test/repo"],
            return_code=0,
            stdout="Lock broken successfully",
            stderr="",
            success=True,
            execution_time=2.0,
        )

        # Act
        result = await repository_service.break_repository_lock(repository)

        # Assert
        assert result["success"] is True
        assert result["message"] == "Repository lock successfully removed"
        mock_command_executor.execute_command.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_repository_info_success(
        self,
        repository_service: RepositoryService,
        mock_command_executor: Mock,
    ) -> None:
        """Test getting repository info successfully."""
        from borgitory.protocols.command_executor_protocol import CommandResult
        from borgitory.models.database import Repository
        import json

        # Arrange
        repository = Repository()
        repository.name = "test-repo"
        repository.path = "/test/repo"
        repository.set_passphrase("test123")

        # Mock borg info JSON response
        info_json = {
            "repository": {"id": "abc123", "location": "/test/repo"},
            "encryption": {"mode": "repokey"},
            "cache": {"path": "/cache"},
            "security_dir": "/security",
            "archives": [
                {
                    "name": "archive1",
                    "start": "2023-01-01T10:00:00",
                    "stats": {
                        "original_size": 1000000,
                        "compressed_size": 500000,
                        "deduplicated_size": 300000,
                    },
                }
            ],
        }

        # Mock successful info command
        mock_command_executor.execute_command.side_effect = [
            # First call for borg info
            CommandResult(
                command=["borg", "info", "/test/repo", "--json"],
                return_code=0,
                stdout=json.dumps(info_json),
                stderr="",
                success=True,
                execution_time=3.0,
            ),
            # Second call for borg config
            CommandResult(
                command=["borg", "config", "/test/repo", "--list"],
                return_code=0,
                stdout="repository.id = abc123\nrepository.segments_per_dir = 1000\n",
                stderr="",
                success=True,
                execution_time=1.0,
            ),
        ]

        # Act
        result = await repository_service.get_repository_info(repository)

        # Assert
        assert result["success"] is True
        assert result["repository_id"] == "abc123"
        assert result["location"] == "/test/repo"
        assert result["encryption"]["mode"] == "repokey"
        assert result["archives_count"] == 1
        assert "original_size" in result
        assert "config" in result
        assert result["config"]["repository.id"] == "abc123"

    # Import Repository Tests

    @pytest.mark.asyncio
    async def test_import_repository_success_without_keyfile(
        self,
        repository_service: RepositoryService,
        mock_borg_service: Mock,
        test_db: Session,
    ) -> None:
        """Test successful repository import without keyfile."""
        # Arrange
        request = ImportRepositoryRequest(
            name="imported-repo",
            path="/mnt/backup/existing-repo",
            passphrase="secret123",
            user_id=1,
        )

        # Mock successful verification
        mock_borg_service.verify_repository_access = AsyncMock(return_value=True)

        # Mock successful archive listing
        mock_archives_response = Mock()
        mock_archives_response.archives = [Mock(), Mock()]  # 2 archives
        mock_borg_service.list_archives.return_value = mock_archives_response

        # Act
        result = await repository_service.import_repository(request, test_db)

        # Assert
        assert result.success is True
        assert result.repository_id is not None
        assert result.repository_name == "imported-repo"
        assert result.message == "Repository 'imported-repo' imported successfully"

        # Verify database operations
        mock_borg_service.verify_repository_access.assert_called_once()
        mock_borg_service.list_archives.assert_called_once()

        # Verify repository was saved to database
        saved_repo = (
            test_db.query(Repository).filter(Repository.name == "imported-repo").first()
        )
        assert saved_repo is not None
        assert saved_repo.path == "/mnt/backup/existing-repo"
        assert saved_repo.get_passphrase() == "secret123"

    @pytest.mark.asyncio
    async def test_import_repository_success_with_keyfile_upload(
        self,
        repository_service: RepositoryService,
        mock_borg_service: Mock,
        mock_path_service: Mock,
        mock_file_service: Mock,
        test_db: Session,
    ) -> None:
        """Test successful repository import with keyfile upload."""
        # Arrange
        mock_keyfile = Mock()
        mock_keyfile.filename = "test.key"
        mock_keyfile.read = AsyncMock(return_value=b"keyfile content")

        request = ImportRepositoryRequest(
            name="imported-repo",
            path="/mnt/backup/existing-repo",
            passphrase="secret123",
            keyfile=mock_keyfile,
            user_id=1,
        )

        # Mock successful keyfile save
        mock_path_service.get_keyfiles_dir = AsyncMock(return_value="/test/keyfiles")
        mock_path_service.ensure_directory = AsyncMock()
        mock_path_service.secure_join.return_value = (
            "/test/keyfiles/imported-repo_test.key_uuid"
        )

        # Mock successful verification
        mock_borg_service.verify_repository_access = AsyncMock(return_value=True)

        # Mock successful archive listing
        mock_archives_response = Mock()
        mock_archives_response.archives = []
        mock_borg_service.list_archives.return_value = mock_archives_response

        # Act
        result = await repository_service.import_repository(request, test_db)

        # Assert
        assert result.success is True
        assert result.repository_id is not None
        assert result.repository_name == "imported-repo"

        # Verify keyfile operations
        mock_path_service.get_keyfiles_dir.assert_called_once()
        mock_path_service.ensure_directory.assert_called_once()
        mock_keyfile.read.assert_called_once()
        mock_file_service.write_file.assert_called_once_with(
            "/test/keyfiles/imported-repo_test.key_uuid", b"keyfile content"
        )

        # Verify verification was called with keyfile path
        mock_borg_service.verify_repository_access.assert_called_once()
        call_args = mock_borg_service.verify_repository_access.call_args
        assert (
            call_args[1]["keyfile_path"] == "/test/keyfiles/imported-repo_test.key_uuid"
        )

    @pytest.mark.asyncio
    async def test_import_repository_success_with_keyfile_content(
        self,
        repository_service: RepositoryService,
        mock_borg_service: Mock,
        test_db: Session,
    ) -> None:
        """Test successful repository import with keyfile content."""
        # Arrange
        request = ImportRepositoryRequest(
            name="imported-repo",
            path="/mnt/backup/existing-repo",
            passphrase="secret123",
            keyfile_content="keyfile content as text",
            encryption_type="keyfile",
            user_id=1,
        )

        # Mock successful verification
        mock_borg_service.verify_repository_access = AsyncMock(return_value=True)

        # Mock successful archive listing
        mock_archives_response = Mock()
        mock_archives_response.archives = [Mock()]
        mock_borg_service.list_archives.return_value = mock_archives_response

        # Act
        result = await repository_service.import_repository(request, test_db)

        # Assert
        assert result.success is True
        assert result.repository_id is not None
        assert result.repository_name == "imported-repo"

        # Verify verification was called with keyfile content
        mock_borg_service.verify_repository_access.assert_called_once()
        call_args = mock_borg_service.verify_repository_access.call_args
        assert call_args[1]["keyfile_content"] == "keyfile content as text"

        # Verify repository was saved with keyfile content and encryption type
        saved_repo = (
            test_db.query(Repository).filter(Repository.name == "imported-repo").first()
        )
        assert saved_repo is not None
        assert saved_repo.encryption_type == "keyfile"
        assert saved_repo.get_keyfile_content() == "keyfile content as text"

    @pytest.mark.asyncio
    async def test_import_repository_name_already_exists(
        self,
        repository_service: RepositoryService,
        test_db: Session,
    ) -> None:
        """Test import fails when repository name already exists."""
        # Arrange - create existing repository
        existing_repo = Repository()
        existing_repo.name = "existing-repo"
        existing_repo.path = "/different/path"
        existing_repo.set_passphrase("different-passphrase")
        test_db.add(existing_repo)
        test_db.commit()

        request = ImportRepositoryRequest(
            name="existing-repo",
            path="/mnt/backup/new-repo",
            passphrase="secret123",
            user_id=1,
        )

        # Act
        result = await repository_service.import_repository(request, test_db)

        # Assert
        assert result.success is False
        assert result.is_validation_error is True
        assert result.validation_errors is not None
        assert len(result.validation_errors) == 1
        assert result.validation_errors[0].field == "name"
        assert "already exists" in result.validation_errors[0].message

    @pytest.mark.asyncio
    async def test_import_repository_path_already_exists(
        self,
        repository_service: RepositoryService,
        test_db: Session,
    ) -> None:
        """Test import fails when repository path already exists."""
        # Arrange - create existing repository
        existing_repo = Repository()
        existing_repo.name = "different-repo"
        existing_repo.path = "/mnt/backup/existing-repo"
        existing_repo.set_passphrase("different-passphrase")
        test_db.add(existing_repo)
        test_db.commit()

        request = ImportRepositoryRequest(
            name="new-repo",
            path="/mnt/backup/existing-repo",
            passphrase="secret123",
            user_id=1,
        )

        # Act
        result = await repository_service.import_repository(request, test_db)

        # Assert
        assert result.success is False
        assert result.is_validation_error is True
        assert result.validation_errors is not None
        assert len(result.validation_errors) == 1
        assert result.validation_errors[0].field == "path"
        assert "already exists" in result.validation_errors[0].message
        assert "different-repo" in result.validation_errors[0].message

    @pytest.mark.asyncio
    async def test_import_repository_keyfile_save_fails(
        self,
        repository_service: RepositoryService,
        mock_path_service: Mock,
        mock_file_service: Mock,
        test_db: Session,
    ) -> None:
        """Test import fails when keyfile save fails."""
        # Arrange
        mock_keyfile = Mock()
        mock_keyfile.filename = "test.key"
        mock_keyfile.read = AsyncMock(side_effect=Exception("File read error"))

        request = ImportRepositoryRequest(
            name="imported-repo",
            path="/mnt/backup/existing-repo",
            passphrase="secret123",
            keyfile=mock_keyfile,
            user_id=1,
        )

        # Mock path service methods to be async
        mock_path_service.get_keyfiles_dir = AsyncMock(return_value="/test/keyfiles")
        mock_path_service.ensure_directory = AsyncMock()

        # Act
        result = await repository_service.import_repository(request, test_db)

        # Assert
        assert result.success is False
        assert result.error_message is not None
        assert "Failed to import repository" in result.error_message

    @pytest.mark.asyncio
    async def test_import_repository_verification_fails(
        self,
        repository_service: RepositoryService,
        mock_borg_service: Mock,
        test_db: Session,
    ) -> None:
        """Test import fails when repository verification fails."""
        # Arrange
        request = ImportRepositoryRequest(
            name="imported-repo",
            path="/mnt/backup/existing-repo",
            passphrase="wrong-passphrase",
            user_id=1,
        )

        # Mock failed verification
        mock_borg_service.verify_repository_access = AsyncMock(return_value=False)

        # Act
        result = await repository_service.import_repository(request, test_db)

        # Assert
        assert result.success is False
        assert result.error_message is not None
        assert "Failed to verify repository access" in result.error_message

        # Verify repository was not saved to database (verification happens before save now)
        saved_repo = (
            test_db.query(Repository).filter(Repository.name == "imported-repo").first()
        )
        assert saved_repo is None

    @pytest.mark.asyncio
    async def test_import_repository_with_cache_dir(
        self,
        repository_service: RepositoryService,
        mock_borg_service: Mock,
        test_db: Session,
    ) -> None:
        """Test successful repository import with cache directory."""
        # Arrange
        request = ImportRepositoryRequest(
            name="imported-repo",
            path="/mnt/backup/existing-repo",
            passphrase="secret123",
            cache_dir="/custom/cache/dir",
            user_id=1,
        )

        # Mock successful verification
        mock_borg_service.verify_repository_access = AsyncMock(return_value=True)

        # Mock successful archive listing
        mock_archives_response = Mock()
        mock_archives_response.archives = []
        mock_borg_service.list_archives.return_value = mock_archives_response

        # Act
        result = await repository_service.import_repository(request, test_db)

        # Assert
        assert result.success is True
        assert result.repository_id is not None

        # Verify repository was saved with cache directory
        saved_repo = (
            test_db.query(Repository).filter(Repository.name == "imported-repo").first()
        )
        assert saved_repo is not None
        assert saved_repo.cache_dir == "/custom/cache/dir"

    @pytest.mark.asyncio
    async def test_import_repository_exception_handling(
        self,
        repository_service: RepositoryService,
        mock_borg_service: Mock,
        test_db: Session,
    ) -> None:
        """Test import handles exceptions and performs rollback."""
        # Arrange
        request = ImportRepositoryRequest(
            name="imported-repo",
            path="/mnt/backup/existing-repo",
            passphrase="secret123",
            user_id=1,
        )

        # Mock verification to raise exception during the verification step
        mock_borg_service.verify_repository_access = AsyncMock(
            side_effect=Exception("Database error")
        )

        # Act
        result = await repository_service.import_repository(request, test_db)

        # Assert
        assert result.success is False
        assert result.error_message is not None
        assert "Failed to import repository" in result.error_message
        assert "Database error" in result.error_message

        # Verify repository was not saved to database (verification happens before save now)
        saved_repo = (
            test_db.query(Repository).filter(Repository.name == "imported-repo").first()
        )
        assert saved_repo is None

    @pytest.mark.asyncio
    async def test_import_repository_archive_listing_exception(
        self,
        repository_service: RepositoryService,
        mock_borg_service: Mock,
        test_db: Session,
    ) -> None:
        """Test import succeeds even when archive listing fails."""
        # Arrange
        request = ImportRepositoryRequest(
            name="imported-repo",
            path="/mnt/backup/existing-repo",
            passphrase="secret123",
            user_id=1,
        )

        # Mock successful verification
        mock_borg_service.verify_repository_access = AsyncMock(return_value=True)

        # Mock archive listing to raise exception
        mock_borg_service.list_archives.side_effect = Exception(
            "Archive listing failed"
        )

        # Act
        result = await repository_service.import_repository(request, test_db)

        # Assert
        assert result.success is True
        assert result.repository_id is not None
        assert result.repository_name == "imported-repo"

        # Verify repository was still saved despite archive listing failure
        saved_repo = (
            test_db.query(Repository).filter(Repository.name == "imported-repo").first()
        )
        assert saved_repo is not None
