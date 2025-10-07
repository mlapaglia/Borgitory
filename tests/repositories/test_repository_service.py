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
        mock.list_archive_directory_contents = AsyncMock()
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

    # List Archives Tests

    @pytest.mark.asyncio
    async def test_list_archives_success_with_multiple_archives(
        self,
        repository_service: RepositoryService,
        mock_borg_service: Mock,
        test_db: Session,
    ) -> None:
        """Test successful archive listing with multiple archives."""
        from borgitory.models.borg_info import BorgArchive, BorgArchiveListResponse

        # Arrange - create repository in database
        repository = Repository()
        repository.id = 1
        repository.name = "test-repo"
        repository.path = "/test/repo"
        repository.set_passphrase("test123")
        test_db.add(repository)
        test_db.commit()

        # Create mock archives
        archive1 = BorgArchive(
            name="archive1",
            id="id1",
            start="2023-01-01T10:00:00",
            end="2023-01-01T10:05:00",
            duration=300.0,
            original_size=1024000,  # 1MB
            compressed_size=512000,  # 512KB
            deduplicated_size=256000,  # 256KB
            nfiles=100,
        )
        archive2 = BorgArchive(
            name="archive2",
            id="id2",
            start="2023-01-02T10:00:00",
            end="2023-01-02T10:05:00",
            duration=300.0,
            original_size=2048000,  # 2MB
            compressed_size=1024000,  # 1MB
            deduplicated_size=512000,  # 512KB
            nfiles=200,
        )

        # Mock borg service response
        mock_archives_response = BorgArchiveListResponse(archives=[archive1, archive2])
        mock_borg_service.list_archives.return_value = mock_archives_response

        # Act
        result = await repository_service.list_archives(1, test_db)

        # Assert
        assert result.success is True
        assert result.repository_id == 1
        assert result.repository_name == "test-repo"
        assert len(result.archives) == 2
        assert len(result.recent_archives) == 2

        # Check first archive
        archive_info1 = result.archives[0]
        assert archive_info1.name == "archive1"
        assert archive_info1.time == "2023-01-01T10:00:00"
        assert archive_info1.formatted_time is not None
        assert archive_info1.size_info == "1000.0 KB"  # 1024000 bytes = 1000 KB
        assert archive_info1.stats is not None
        assert archive_info1.stats["original_size"] == 1024000

        # Check second archive
        archive_info2 = result.archives[1]
        assert archive_info2.name == "archive2"
        assert archive_info2.time == "2023-01-02T10:00:00"
        assert archive_info2.formatted_time is not None
        assert archive_info2.size_info == "2.0 MB"  # 2048000 bytes = 2 MB
        assert archive_info2.stats is not None
        assert archive_info2.stats["original_size"] == 2048000

        # Check recent archives are in reverse order (newest first)
        assert result.recent_archives[0].name == "archive2"
        assert result.recent_archives[1].name == "archive1"

        mock_borg_service.list_archives.assert_called_once_with(repository)

    @pytest.mark.asyncio
    async def test_list_archives_success_with_no_archives(
        self,
        repository_service: RepositoryService,
        mock_borg_service: Mock,
        test_db: Session,
    ) -> None:
        """Test successful archive listing with no archives."""
        from borgitory.models.borg_info import BorgArchiveListResponse

        # Arrange - create repository in database
        repository = Repository()
        repository.id = 1
        repository.name = "empty-repo"
        repository.path = "/test/empty-repo"
        repository.set_passphrase("test123")
        test_db.add(repository)
        test_db.commit()

        # Mock empty archives response
        mock_archives_response = BorgArchiveListResponse(archives=[])
        mock_borg_service.list_archives.return_value = mock_archives_response

        # Act
        result = await repository_service.list_archives(1, test_db)

        # Assert
        assert result.success is True
        assert result.repository_id == 1
        assert result.repository_name == "empty-repo"
        assert len(result.archives) == 0
        assert len(result.recent_archives) == 0
        assert result.error_message is None

        mock_borg_service.list_archives.assert_called_once_with(repository)

    @pytest.mark.asyncio
    async def test_list_archives_repository_not_found(
        self,
        repository_service: RepositoryService,
        test_db: Session,
    ) -> None:
        """Test archive listing when repository is not found in database."""
        # Act
        result = await repository_service.list_archives(999, test_db)

        # Assert
        assert result.success is False
        assert result.repository_id == 999
        assert result.repository_name == "Unknown"
        assert len(result.archives) == 0
        assert len(result.recent_archives) == 0
        assert result.error_message == "Repository not found"

    @pytest.mark.asyncio
    async def test_list_archives_borg_service_exception(
        self,
        repository_service: RepositoryService,
        mock_borg_service: Mock,
        test_db: Session,
    ) -> None:
        """Test archive listing when borg service raises an exception."""
        # Arrange - create repository in database
        repository = Repository()
        repository.id = 1
        repository.name = "test-repo"
        repository.path = "/test/repo"
        repository.set_passphrase("test123")
        test_db.add(repository)
        test_db.commit()

        # Mock borg service to raise exception
        mock_borg_service.list_archives.side_effect = Exception("Borg service error")

        # Act
        result = await repository_service.list_archives(1, test_db)

        # Assert
        assert result.success is False
        assert result.repository_id == 1
        assert result.repository_name == "Unknown"
        assert len(result.archives) == 0
        assert len(result.recent_archives) == 0
        assert result.error_message is not None
        assert "Error loading archives: Borg service error" in result.error_message

        mock_borg_service.list_archives.assert_called_once_with(repository)

    @pytest.mark.asyncio
    async def test_list_archives_archive_size_formatting(
        self,
        repository_service: RepositoryService,
        mock_borg_service: Mock,
        test_db: Session,
    ) -> None:
        """Test archive size formatting for different sizes."""
        from borgitory.models.borg_info import BorgArchive, BorgArchiveListResponse

        # Arrange - create repository in database
        repository = Repository()
        repository.id = 1
        repository.name = "test-repo"
        repository.path = "/test/repo"
        repository.set_passphrase("test123")
        test_db.add(repository)
        test_db.commit()

        # Create archives with different sizes
        archives = [
            BorgArchive(
                name="small",
                id="id1",
                start="2023-01-01T10:00:00",
                end="2023-01-01T10:05:00",
                duration=300.0,
                original_size=500,  # 500 bytes
            ),
            BorgArchive(
                name="medium",
                id="id2",
                start="2023-01-02T10:00:00",
                end="2023-01-02T10:05:00",
                duration=300.0,
                original_size=1048576,  # 1 MB
            ),
            BorgArchive(
                name="large",
                id="id3",
                start="2023-01-03T10:00:00",
                end="2023-01-03T10:05:00",
                duration=300.0,
                original_size=1073741824,  # 1 GB
            ),
            BorgArchive(
                name="huge",
                id="id4",
                start="2023-01-04T10:00:00",
                end="2023-01-04T10:05:00",
                duration=300.0,
                original_size=1099511627776,  # 1 TB
            ),
        ]

        mock_archives_response = BorgArchiveListResponse(archives=archives)
        mock_borg_service.list_archives.return_value = mock_archives_response

        # Act
        result = await repository_service.list_archives(1, test_db)

        # Assert
        assert result.success is True
        assert len(result.archives) == 4

        # Check size formatting
        assert result.archives[0].size_info == "500.0 B"  # 500 bytes
        assert result.archives[1].size_info == "1.0 MB"  # 1 MB
        assert result.archives[2].size_info == "1.0 GB"  # 1 GB
        assert result.archives[3].size_info == "1.0 TB"  # 1 TB

    @pytest.mark.asyncio
    async def test_list_archives_archive_with_no_size(
        self,
        repository_service: RepositoryService,
        mock_borg_service: Mock,
        test_db: Session,
    ) -> None:
        """Test archive listing with archive that has no size information."""
        from borgitory.models.borg_info import BorgArchive, BorgArchiveListResponse

        # Arrange - create repository in database
        repository = Repository()
        repository.id = 1
        repository.name = "test-repo"
        repository.path = "/test/repo"
        repository.set_passphrase("test123")
        test_db.add(repository)
        test_db.commit()

        # Create archive with no size information
        archive = BorgArchive(
            name="no-size-archive",
            id="id1",
            start="2023-01-01T10:00:00",
            end="2023-01-01T10:05:00",
            duration=300.0,
            original_size=None,  # No size information
        )

        mock_archives_response = BorgArchiveListResponse(archives=[archive])
        mock_borg_service.list_archives.return_value = mock_archives_response

        # Act
        result = await repository_service.list_archives(1, test_db)

        # Assert
        assert result.success is True
        assert len(result.archives) == 1

        archive_info = result.archives[0]
        assert archive_info.name == "no-size-archive"
        assert archive_info.time == "2023-01-01T10:00:00"
        assert archive_info.formatted_time is not None
        assert archive_info.size_info is None  # No size info should be set
        assert archive_info.stats is None  # No stats should be set

    @pytest.mark.asyncio
    async def test_list_archives_recent_archives_limit(
        self,
        repository_service: RepositoryService,
        mock_borg_service: Mock,
        test_db: Session,
    ) -> None:
        """Test that recent archives are limited to 10 and in reverse order."""
        from borgitory.models.borg_info import BorgArchive, BorgArchiveListResponse

        # Arrange - create repository in database
        repository = Repository()
        repository.id = 1
        repository.name = "test-repo"
        repository.path = "/test/repo"
        repository.set_passphrase("test123")
        test_db.add(repository)
        test_db.commit()

        # Create 15 archives
        archives = []
        for i in range(15):
            archive = BorgArchive(
                name=f"archive{i:02d}",
                id=f"id{i}",
                start=f"2023-01-{i + 1:02d}T10:00:00",
                end=f"2023-01-{i + 1:02d}T10:05:00",
                duration=300.0,
                original_size=1024,
            )
            archives.append(archive)

        mock_archives_response = BorgArchiveListResponse(archives=archives)
        mock_borg_service.list_archives.return_value = mock_archives_response

        # Act
        result = await repository_service.list_archives(1, test_db)

        # Assert
        assert result.success is True
        assert len(result.archives) == 15  # All archives
        assert len(result.recent_archives) == 10  # Limited to 10

        # Check that recent archives are the last 10 in reverse order
        expected_recent_names = [f"archive{i:02d}" for i in range(14, 4, -1)]
        actual_recent_names = [arch.name for arch in result.recent_archives]
        assert actual_recent_names == expected_recent_names

    @pytest.mark.asyncio
    async def test_list_archives_archive_time_formatting(
        self,
        repository_service: RepositoryService,
        mock_borg_service: Mock,
        test_db: Session,
    ) -> None:
        """Test archive time formatting."""
        from borgitory.models.borg_info import BorgArchive, BorgArchiveListResponse

        # Arrange - create repository in database
        repository = Repository()
        repository.id = 1
        repository.name = "test-repo"
        repository.path = "/test/repo"
        repository.set_passphrase("test123")
        test_db.add(repository)
        test_db.commit()

        # Create archive with valid timestamp
        archive = BorgArchive(
            name="test-archive",
            id="id1",
            start="2023-01-01T10:30:45",  # Valid ISO format
            end="2023-01-01T10:35:45",
            duration=300.0,
            original_size=1024,
        )

        mock_archives_response = BorgArchiveListResponse(archives=[archive])
        mock_borg_service.list_archives.return_value = mock_archives_response

        # Act
        result = await repository_service.list_archives(1, test_db)

        # Assert
        assert result.success is True
        assert len(result.archives) == 1

        archive_info = result.archives[0]
        assert archive_info.name == "test-archive"
        assert archive_info.time == "2023-01-01T10:30:45"
        assert archive_info.formatted_time is not None
        assert archive_info.formatted_time != archive_info.time  # Should be formatted

    @pytest.mark.asyncio
    async def test_list_archives_archive_invalid_time(
        self,
        repository_service: RepositoryService,
        mock_borg_service: Mock,
        test_db: Session,
    ) -> None:
        """Test archive with invalid time format falls back to original time."""
        from borgitory.models.borg_info import BorgArchive, BorgArchiveListResponse

        # Arrange - create repository in database
        repository = Repository()
        repository.id = 1
        repository.name = "test-repo"
        repository.path = "/test/repo"
        repository.set_passphrase("test123")
        test_db.add(repository)
        test_db.commit()

        # Create archive with invalid timestamp
        archive = BorgArchive(
            name="invalid-time-archive",
            id="id1",
            start="invalid-timestamp",  # Invalid format
            end="2023-01-01T10:35:45",
            duration=300.0,
            original_size=1024,
        )

        mock_archives_response = BorgArchiveListResponse(archives=[archive])
        mock_borg_service.list_archives.return_value = mock_archives_response

        # Act
        result = await repository_service.list_archives(1, test_db)

        # Assert
        assert result.success is True
        assert len(result.archives) == 1

        archive_info = result.archives[0]
        assert archive_info.name == "invalid-time-archive"
        assert archive_info.time == "invalid-timestamp"
        assert (
            archive_info.formatted_time == "invalid-timestamp"
        )  # Falls back to original

    # Get Directories Tests

    @pytest.mark.asyncio
    async def test_get_directories_success_with_directories_only(
        self,
        repository_service: RepositoryService,
        mock_file_service: Mock,
    ) -> None:
        """Test successful directory listing with directories only."""
        from borgitory.models.repository_dtos import DirectoryListingRequest
        from borgitory.utils.secure_path import DirectoryInfo

        # Arrange
        request = DirectoryListingRequest(
            path="/test/path",
            include_files=False,
            max_items=1000,
        )

        # Mock directory data
        mock_directory_data = [
            DirectoryInfo(
                name="dir1",
                path="/test/path/dir1",
                is_borg_repo=False,
                is_borg_cache=False,
                has_permission_error=False,
            ),
            DirectoryInfo(
                name="dir2",
                path="/test/path/dir2",
                is_borg_repo=True,
                is_borg_cache=False,
                has_permission_error=False,
            ),
            DirectoryInfo(
                name="dir3",
                path="/test/path/dir3",
                is_borg_repo=False,
                is_borg_cache=True,
                has_permission_error=False,
            ),
        ]

        with (
            patch(
                "borgitory.services.repositories.repository_service.secure_exists",
                return_value=True,
            ),
            patch(
                "borgitory.services.repositories.repository_service.secure_isdir",
                return_value=True,
            ),
            patch(
                "borgitory.services.repositories.repository_service.get_directory_listing",
                return_value=mock_directory_data,
            ),
        ):
            # Act
            result = await repository_service.get_directories(request)

            # Assert
            assert result.success is True
            assert result.path == "/test/path"
            assert result.directories == ["dir1", "dir2", "dir3"]
            assert result.error_message is None

    @pytest.mark.asyncio
    async def test_get_directories_success_with_files_included(
        self,
        repository_service: RepositoryService,
        mock_file_service: Mock,
    ) -> None:
        """Test successful directory listing with files included."""
        from borgitory.models.repository_dtos import DirectoryListingRequest
        from borgitory.utils.secure_path import DirectoryInfo

        # Arrange
        request = DirectoryListingRequest(
            path="/test/path",
            include_files=True,
            max_items=1000,
        )

        # Mock directory data with files
        mock_directory_data = [
            DirectoryInfo(
                name="dir1",
                path="/test/path/dir1",
                is_borg_repo=False,
                is_borg_cache=False,
                has_permission_error=False,
            ),
            DirectoryInfo(
                name="file1.txt",
                path="/test/path/file1.txt",
                is_borg_repo=False,
                is_borg_cache=False,
                has_permission_error=False,
            ),
            DirectoryInfo(
                name="file2.log",
                path="/test/path/file2.log",
                is_borg_repo=False,
                is_borg_cache=False,
                has_permission_error=False,
            ),
        ]

        with (
            patch(
                "borgitory.services.repositories.repository_service.secure_exists",
                return_value=True,
            ),
            patch(
                "borgitory.services.repositories.repository_service.secure_isdir",
                return_value=True,
            ),
            patch(
                "borgitory.services.repositories.repository_service.get_directory_listing",
                return_value=mock_directory_data,
            ),
        ):
            # Act
            result = await repository_service.get_directories(request)

            # Assert
            assert result.success is True
            assert result.path == "/test/path"
            assert result.directories == ["dir1", "file1.txt", "file2.log"]
            assert result.error_message is None

    @pytest.mark.asyncio
    async def test_get_directories_success_with_max_items_limit(
        self,
        repository_service: RepositoryService,
        mock_file_service: Mock,
    ) -> None:
        """Test successful directory listing with max_items limit."""
        from borgitory.models.repository_dtos import DirectoryListingRequest
        from borgitory.utils.secure_path import DirectoryInfo

        # Arrange
        request = DirectoryListingRequest(
            path="/test/path",
            include_files=False,
            max_items=2,  # Limit to 2 items
        )

        # Mock directory data with more items than limit
        mock_directory_data = [
            DirectoryInfo(
                name="dir1",
                path="/test/path/dir1",
                is_borg_repo=False,
                is_borg_cache=False,
                has_permission_error=False,
            ),
            DirectoryInfo(
                name="dir2",
                path="/test/path/dir2",
                is_borg_repo=False,
                is_borg_cache=False,
                has_permission_error=False,
            ),
            DirectoryInfo(
                name="dir3",
                path="/test/path/dir3",
                is_borg_repo=False,
                is_borg_cache=False,
                has_permission_error=False,
            ),
        ]

        with (
            patch(
                "borgitory.services.repositories.repository_service.secure_exists",
                return_value=True,
            ),
            patch(
                "borgitory.services.repositories.repository_service.secure_isdir",
                return_value=True,
            ),
            patch(
                "borgitory.services.repositories.repository_service.get_directory_listing",
                return_value=mock_directory_data,
            ),
        ):
            # Act
            result = await repository_service.get_directories(request)

            # Assert
            assert result.success is True
            assert result.path == "/test/path"
            assert len(result.directories) == 2  # Limited to max_items
            assert result.directories == ["dir1", "dir2"]  # First 2 items
            assert result.error_message is None

    @pytest.mark.asyncio
    async def test_get_directories_path_not_exists(
        self,
        repository_service: RepositoryService,
        mock_file_service: Mock,
    ) -> None:
        """Test directory listing when path does not exist."""
        from borgitory.models.repository_dtos import DirectoryListingRequest

        # Arrange
        request = DirectoryListingRequest(
            path="/nonexistent/path",
            include_files=False,
            max_items=1000,
        )

        with patch(
            "borgitory.services.repositories.repository_service.secure_exists",
            return_value=False,
        ):
            # Act
            result = await repository_service.get_directories(request)

            # Assert
            assert result.success is True  # Still successful, just empty
            assert result.path == "/nonexistent/path"
            assert result.directories == []
            assert result.error_message is None

    @pytest.mark.asyncio
    async def test_get_directories_path_not_directory(
        self,
        repository_service: RepositoryService,
        mock_file_service: Mock,
    ) -> None:
        """Test directory listing when path is not a directory."""
        from borgitory.models.repository_dtos import DirectoryListingRequest

        # Arrange
        request = DirectoryListingRequest(
            path="/test/file.txt",
            include_files=False,
            max_items=1000,
        )

        with (
            patch(
                "borgitory.services.repositories.repository_service.secure_exists",
                return_value=True,
            ),
            patch(
                "borgitory.services.repositories.repository_service.secure_isdir",
                return_value=False,
            ),
        ):
            # Act
            result = await repository_service.get_directories(request)

            # Assert
            assert result.success is True  # Still successful, just empty
            assert result.path == "/test/file.txt"
            assert result.directories == []
            assert result.error_message is None

    @pytest.mark.asyncio
    async def test_get_directories_exception_handling(
        self,
        repository_service: RepositoryService,
        mock_file_service: Mock,
    ) -> None:
        """Test directory listing exception handling."""
        from borgitory.models.repository_dtos import DirectoryListingRequest

        # Arrange
        request = DirectoryListingRequest(
            path="/test/path",
            include_files=False,
            max_items=1000,
        )

        with (
            patch(
                "borgitory.services.repositories.repository_service.secure_exists",
                return_value=True,
            ),
            patch(
                "borgitory.services.repositories.repository_service.secure_isdir",
                return_value=True,
            ),
            patch(
                "borgitory.services.repositories.repository_service.get_directory_listing",
                side_effect=Exception("Permission denied"),
            ),
        ):
            # Act
            result = await repository_service.get_directories(request)

            # Assert
            assert result.success is False
            assert result.path == "/test/path"
            assert result.directories == []
            assert result.error_message is not None
            assert (
                "Failed to list directories: Permission denied" in result.error_message
            )

    # Get Archive Contents Tests

    @pytest.mark.asyncio
    async def test_get_archive_contents_success(
        self,
        repository_service: RepositoryService,
        mock_borg_service: Mock,
        test_db: Session,
    ) -> None:
        """Test successful archive contents retrieval."""
        from borgitory.models.repository_dtos import ArchiveContentsRequest
        from borgitory.services.archives.archive_models import ArchiveEntry

        # Arrange - create repository in database
        repository = Repository()
        repository.id = 1
        repository.name = "test-repo"
        repository.path = "/test/repo"
        repository.set_passphrase("test123")
        test_db.add(repository)
        test_db.commit()

        # Create mock archive entries
        mock_entries = [
            ArchiveEntry(
                path="documents/file1.txt",
                name="file1.txt",
                type="f",
                size=1024,
                isdir=False,
                mtime="2023-01-01T10:00:00",
            ),
            ArchiveEntry(
                path="documents/subdir",
                name="subdir",
                type="d",
                size=0,
                isdir=True,
                mtime="2023-01-01T09:00:00",
            ),
            ArchiveEntry(
                path="documents/file2.pdf",
                name="file2.pdf",
                type="f",
                size=2048,
                isdir=False,
                mtime="2023-01-01T11:00:00",
            ),
        ]

        mock_borg_service.list_archive_directory_contents.return_value = mock_entries

        request = ArchiveContentsRequest(
            repository_id=1,
            archive_name="test-archive",
            path="documents",
        )

        # Act
        result = await repository_service.get_archive_contents(request, test_db)

        # Assert
        assert result.success is True
        assert result.repository_id == 1
        assert result.archive_name == "test-archive"
        assert result.path == "documents"
        assert len(result.items) == 3
        assert result.breadcrumb_parts == ["documents"]

        # Check first item
        item1 = result.items[0]
        assert item1.name == "file1.txt"
        assert item1.type == "f"
        assert item1.path == "documents/file1.txt"
        assert item1.size == 1024
        assert item1.modified == "2023-01-01T10:00:00"

        # Check second item (directory)
        item2 = result.items[1]
        assert item2.name == "subdir"
        assert item2.type == "d"
        assert item2.path == "documents/subdir"
        assert item2.size == 0
        assert item2.modified == "2023-01-01T09:00:00"

        # Check third item
        item3 = result.items[2]
        assert item3.name == "file2.pdf"
        assert item3.type == "f"
        assert item3.path == "documents/file2.pdf"
        assert item3.size == 2048
        assert item3.modified == "2023-01-01T11:00:00"

        mock_borg_service.list_archive_directory_contents.assert_called_once_with(
            repository, "test-archive", "documents"
        )

    @pytest.mark.asyncio
    async def test_get_archive_contents_success_root_path(
        self,
        repository_service: RepositoryService,
        mock_borg_service: Mock,
        test_db: Session,
    ) -> None:
        """Test successful archive contents retrieval for root path."""
        from borgitory.models.repository_dtos import ArchiveContentsRequest
        from borgitory.services.archives.archive_models import ArchiveEntry

        # Arrange - create repository in database
        repository = Repository()
        repository.id = 1
        repository.name = "test-repo"
        repository.path = "/test/repo"
        repository.set_passphrase("test123")
        test_db.add(repository)
        test_db.commit()

        # Create mock archive entries for root
        mock_entries = [
            ArchiveEntry(
                path="documents",
                name="documents",
                type="d",
                size=0,
                isdir=True,
                mtime="2023-01-01T10:00:00",
            ),
            ArchiveEntry(
                path="images",
                name="images",
                type="d",
                size=0,
                isdir=True,
                mtime="2023-01-01T11:00:00",
            ),
        ]

        mock_borg_service.list_archive_directory_contents.return_value = mock_entries

        request = ArchiveContentsRequest(
            repository_id=1,
            archive_name="test-archive",
            path="",  # Root path
        )

        # Act
        result = await repository_service.get_archive_contents(request, test_db)

        # Assert
        assert result.success is True
        assert result.repository_id == 1
        assert result.archive_name == "test-archive"
        assert result.path == ""
        assert len(result.items) == 2
        assert result.breadcrumb_parts == []  # Empty for root path

        mock_borg_service.list_archive_directory_contents.assert_called_once_with(
            repository, "test-archive", ""
        )

    @pytest.mark.asyncio
    async def test_get_archive_contents_success_nested_path(
        self,
        repository_service: RepositoryService,
        mock_borg_service: Mock,
        test_db: Session,
    ) -> None:
        """Test successful archive contents retrieval for nested path."""
        from borgitory.models.repository_dtos import ArchiveContentsRequest
        from borgitory.services.archives.archive_models import ArchiveEntry

        # Arrange - create repository in database
        repository = Repository()
        repository.id = 1
        repository.name = "test-repo"
        repository.path = "/test/repo"
        repository.set_passphrase("test123")
        test_db.add(repository)
        test_db.commit()

        # Create mock archive entries for nested path
        mock_entries = [
            ArchiveEntry(
                path="documents/work/project1/file1.txt",
                name="file1.txt",
                type="f",
                size=1024,
                isdir=False,
                mtime="2023-01-01T10:00:00",
            ),
        ]

        mock_borg_service.list_archive_directory_contents.return_value = mock_entries

        request = ArchiveContentsRequest(
            repository_id=1,
            archive_name="test-archive",
            path="documents/work/project1",
        )

        # Act
        result = await repository_service.get_archive_contents(request, test_db)

        # Assert
        assert result.success is True
        assert result.repository_id == 1
        assert result.archive_name == "test-archive"
        assert result.path == "documents/work/project1"
        assert len(result.items) == 1
        assert result.breadcrumb_parts == ["documents", "work", "project1"]

        mock_borg_service.list_archive_directory_contents.assert_called_once_with(
            repository, "test-archive", "documents/work/project1"
        )

    @pytest.mark.asyncio
    async def test_get_archive_contents_repository_not_found(
        self,
        repository_service: RepositoryService,
        test_db: Session,
    ) -> None:
        """Test archive contents when repository is not found."""
        from borgitory.models.repository_dtos import ArchiveContentsRequest

        request = ArchiveContentsRequest(
            repository_id=999,
            archive_name="test-archive",
            path="documents",
        )

        # Act
        result = await repository_service.get_archive_contents(request, test_db)

        # Assert
        assert result.success is False
        assert result.repository_id == 999
        assert result.archive_name == "test-archive"
        assert result.path == "documents"
        assert len(result.items) == 0
        assert result.breadcrumb_parts == []
        assert result.error_message == "Repository not found"

    @pytest.mark.asyncio
    async def test_get_archive_contents_borg_service_exception(
        self,
        repository_service: RepositoryService,
        mock_borg_service: Mock,
        test_db: Session,
    ) -> None:
        """Test archive contents when borg service raises an exception."""
        from borgitory.models.repository_dtos import ArchiveContentsRequest

        # Arrange - create repository in database
        repository = Repository()
        repository.id = 1
        repository.name = "test-repo"
        repository.path = "/test/repo"
        repository.set_passphrase("test123")
        test_db.add(repository)
        test_db.commit()

        # Mock borg service to raise exception
        mock_borg_service.list_archive_directory_contents.side_effect = Exception(
            "Archive not found"
        )

        request = ArchiveContentsRequest(
            repository_id=1,
            archive_name="nonexistent-archive",
            path="documents",
        )

        # Act
        result = await repository_service.get_archive_contents(request, test_db)

        # Assert
        assert result.success is False
        assert result.repository_id == 1
        assert result.archive_name == "nonexistent-archive"
        assert result.path == "documents"
        assert len(result.items) == 0
        assert result.breadcrumb_parts == []
        assert result.error_message is not None
        assert (
            "Error loading directory contents: Archive not found"
            in result.error_message
        )

        mock_borg_service.list_archive_directory_contents.assert_called_once_with(
            repository, "nonexistent-archive", "documents"
        )

    @pytest.mark.asyncio
    async def test_get_archive_contents_empty_archive(
        self,
        repository_service: RepositoryService,
        mock_borg_service: Mock,
        test_db: Session,
    ) -> None:
        """Test archive contents when archive is empty."""
        from borgitory.models.repository_dtos import ArchiveContentsRequest

        # Arrange - create repository in database
        repository = Repository()
        repository.id = 1
        repository.name = "test-repo"
        repository.path = "/test/repo"
        repository.set_passphrase("test123")
        test_db.add(repository)
        test_db.commit()

        # Mock empty archive contents
        mock_borg_service.list_archive_directory_contents.return_value = []

        request = ArchiveContentsRequest(
            repository_id=1,
            archive_name="empty-archive",
            path="documents",
        )

        # Act
        result = await repository_service.get_archive_contents(request, test_db)

        # Assert
        assert result.success is True
        assert result.repository_id == 1
        assert result.archive_name == "empty-archive"
        assert result.path == "documents"
        assert len(result.items) == 0
        assert result.breadcrumb_parts == ["documents"]
        assert result.error_message is None

        mock_borg_service.list_archive_directory_contents.assert_called_once_with(
            repository, "empty-archive", "documents"
        )
