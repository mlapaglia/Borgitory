"""
Tests for CloudSyncManager - Handles cloud synchronization operations
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch
from datetime import datetime, UTC

from services.cloud_sync_manager import CloudSyncManager
from models.database import Repository, CloudSyncConfig


@pytest.fixture
def mock_db_session():
    """Mock database session."""
    mock_session = Mock()
    mock_session.__enter__ = Mock(return_value=mock_session)
    mock_session.__exit__ = Mock(return_value=None)
    return mock_session


@pytest.fixture
def mock_db_session_factory(mock_db_session):
    """Mock database session factory."""
    return Mock(return_value=mock_db_session)


@pytest.fixture
def cloud_sync_manager(mock_db_session_factory):
    """CloudSyncManager instance with mocked dependencies."""
    return CloudSyncManager(db_session_factory=mock_db_session_factory)


@pytest.fixture
def test_repository():
    """Test repository object."""
    repo = Repository(id=1, name="test-repo", path="/tmp/test-repo")
    repo.set_passphrase("test-passphrase")
    return repo


@pytest.fixture
def test_cloud_config():
    """Test cloud sync configuration."""
    config = CloudSyncConfig(
        id=1,
        name="test-s3-config",
        provider="s3",
        bucket_name="test-bucket",
        enabled=True,
    )
    config.set_credentials("test_access_key", "test_secret_key")
    return config


class TestCloudSyncManager:
    """Test class for CloudSyncManager."""

    def test_init_with_dependencies(self):
        """Test CloudSyncManager initialization with provided dependencies."""
        mock_factory = Mock()
        manager = CloudSyncManager(db_session_factory=mock_factory)

        assert manager._db_session_factory is mock_factory

    def test_init_with_defaults(self):
        """Test CloudSyncManager initialization with default dependencies."""
        with patch("services.cloud_sync_manager.get_db_session") as mock_get_session:
            manager = CloudSyncManager()
            assert manager._db_session_factory is mock_get_session

    @pytest.mark.asyncio
    async def test_execute_cloud_sync_task_no_config(
        self, cloud_sync_manager, mock_db_session
    ):
        """Test cloud sync task execution with no cloud config."""
        # Setup repository data
        repo_data = {"id": 1, "name": "test-repo", "path": "/tmp/test-repo"}
        cloud_sync_manager._get_repository_data = Mock(return_value=repo_data)

        output_messages = []

        def capture_output(message):
            output_messages.append(message)

        result = await cloud_sync_manager.execute_cloud_sync_task(
            repository_id=1, cloud_sync_config_id=None, output_callback=capture_output
        )

        assert result is True  # Not an error, just skipped
        assert any("No cloud backup configuration" in msg for msg in output_messages)

    @pytest.mark.asyncio
    async def test_execute_cloud_sync_task_repository_not_found(
        self, cloud_sync_manager
    ):
        """Test cloud sync task with non-existent repository."""
        cloud_sync_manager._get_repository_data = Mock(return_value=None)

        result = await cloud_sync_manager.execute_cloud_sync_task(
            repository_id=999, cloud_sync_config_id=1
        )

        assert result is False

    @pytest.mark.asyncio
    async def test_execute_cloud_sync_task_config_not_found(
        self, cloud_sync_manager, mock_db_session
    ):
        """Test cloud sync task with non-existent config."""
        # Setup repository data
        repo_data = {"id": 1, "name": "test-repo", "path": "/tmp/test-repo"}
        cloud_sync_manager._get_repository_data = Mock(return_value=repo_data)

        # Mock query to return None
        mock_query = Mock()
        mock_query.filter.return_value.first.return_value = None
        mock_db_session.query.return_value = mock_query

        output_messages = []

        def capture_output(message):
            output_messages.append(message)

        result = await cloud_sync_manager.execute_cloud_sync_task(
            repository_id=1, cloud_sync_config_id=999, output_callback=capture_output
        )

        assert result is True  # Not an error, just skipped
        assert any("not found or disabled" in msg for msg in output_messages)

    @pytest.mark.asyncio
    async def test_execute_cloud_sync_task_config_disabled(
        self, cloud_sync_manager, mock_db_session, test_cloud_config
    ):
        """Test cloud sync task with disabled config."""
        # Setup repository data
        repo_data = {"id": 1, "name": "test-repo", "path": "/tmp/test-repo"}
        cloud_sync_manager._get_repository_data = Mock(return_value=repo_data)

        # Disable the config
        test_cloud_config.enabled = False

        # Mock query to return disabled config
        mock_query = Mock()
        mock_query.filter.return_value.first.return_value = test_cloud_config
        mock_db_session.query.return_value = mock_query

        result = await cloud_sync_manager.execute_cloud_sync_task(
            repository_id=1, cloud_sync_config_id=1
        )

        assert result is True  # Not an error, just skipped

    @pytest.mark.asyncio
    async def test_execute_cloud_sync_task_s3_success(
        self, cloud_sync_manager, mock_db_session, test_cloud_config
    ):
        """Test successful S3 cloud sync task."""
        # Setup repository data
        repo_data = {"id": 1, "name": "test-repo", "path": "/tmp/test-repo"}
        cloud_sync_manager._get_repository_data = Mock(return_value=repo_data)

        # Mock query to return enabled config
        mock_query = Mock()
        mock_query.filter.return_value.first.return_value = test_cloud_config
        mock_db_session.query.return_value = mock_query

        # Mock _sync_to_s3 method
        cloud_sync_manager._sync_to_s3 = AsyncMock(return_value=True)

        output_messages = []

        def capture_output(message):
            output_messages.append(message)

        result = await cloud_sync_manager.execute_cloud_sync_task(
            repository_id=1, cloud_sync_config_id=1, output_callback=capture_output
        )

        assert result is True
        assert any("Starting cloud sync" in msg for msg in output_messages)
        cloud_sync_manager._sync_to_s3.assert_called_once_with(
            test_cloud_config, repo_data, capture_output
        )

    @pytest.mark.asyncio
    async def test_execute_cloud_sync_task_unsupported_provider(
        self, cloud_sync_manager, mock_db_session, test_cloud_config
    ):
        """Test cloud sync task with unsupported provider."""
        # Setup repository data
        repo_data = {"id": 1, "name": "test-repo", "path": "/tmp/test-repo"}
        cloud_sync_manager._get_repository_data = Mock(return_value=repo_data)

        # Change provider to unsupported
        test_cloud_config.provider = "unsupported"

        # Mock query to return config with unsupported provider
        mock_query = Mock()
        mock_query.filter.return_value.first.return_value = test_cloud_config
        mock_db_session.query.return_value = mock_query

        result = await cloud_sync_manager.execute_cloud_sync_task(
            repository_id=1, cloud_sync_config_id=1
        )

        assert result is False

    @pytest.mark.asyncio
    async def test_sync_to_s3_success(self, cloud_sync_manager, test_cloud_config):
        """Test successful S3 sync."""
        repo_data = {"id": 1, "name": "test-repo", "path": "/tmp/test-repo"}

        # Mock RcloneService
        mock_rclone_service = Mock()

        # Create async generator for sync events
        async def mock_sync_generator():
            yield {"type": "started", "command": "rclone sync"}
            yield {"type": "progress", "message": "Syncing files..."}
            yield {"type": "log", "message": "Transfer complete"}
            yield {"type": "completed", "status": "success"}

        mock_rclone_service.sync_repository_to_s3.return_value = mock_sync_generator()

        output_messages = []

        def capture_output(message):
            output_messages.append(message)

        with patch(
            "services.rclone_service.RcloneService",
            return_value=mock_rclone_service,
        ):
            result = await cloud_sync_manager._sync_to_s3(
                test_cloud_config, repo_data, capture_output
            )

        assert result is True
        assert any("Starting sync" in msg for msg in output_messages)
        assert any("Progress" in msg for msg in output_messages)
        assert any("completed successfully" in msg for msg in output_messages)

    @pytest.mark.asyncio
    async def test_sync_to_s3_failure(self, cloud_sync_manager, test_cloud_config):
        """Test failed S3 sync."""
        repo_data = {"id": 1, "name": "test-repo", "path": "/tmp/test-repo"}

        # Mock RcloneService
        mock_rclone_service = Mock()

        # Create async generator for sync events with failure
        async def mock_sync_generator():
            yield {"type": "started", "command": "rclone sync"}
            yield {"type": "completed", "status": "failed", "return_code": 1}

        mock_rclone_service.sync_repository_to_s3.return_value = mock_sync_generator()

        output_messages = []

        def capture_output(message):
            output_messages.append(message)

        with patch(
            "services.rclone_service.RcloneService",
            return_value=mock_rclone_service,
        ):
            result = await cloud_sync_manager._sync_to_s3(
                test_cloud_config, repo_data, capture_output
            )

        assert result is False
        assert any("failed" in msg for msg in output_messages)

    @pytest.mark.asyncio
    async def test_sync_to_s3_rclone_import_error(
        self, cloud_sync_manager, test_cloud_config
    ):
        """Test S3 sync with RcloneService import error."""
        repo_data = {"id": 1, "name": "test-repo", "path": "/tmp/test-repo"}

        output_messages = []

        def capture_output(message):
            output_messages.append(message)

        with patch(
            "services.rclone_service.RcloneService",
            side_effect=ImportError("Module not found"),
        ):
            result = await cloud_sync_manager._sync_to_s3(
                test_cloud_config, repo_data, capture_output
            )

        assert result is False
        assert any("RcloneService not available" in msg for msg in output_messages)

    def test_get_repository_data_success(
        self, cloud_sync_manager, mock_db_session, test_repository
    ):
        """Test successful repository data retrieval."""
        # Mock query to return repository
        mock_query = Mock()
        mock_query.filter.return_value.first.return_value = test_repository
        mock_db_session.query.return_value = mock_query

        result = cloud_sync_manager._get_repository_data(1)

        assert result is not None
        assert result["id"] == 1
        assert result["name"] == "test-repo"
        assert result["path"] == "/tmp/test-repo"

    def test_get_repository_data_not_found(self, cloud_sync_manager, mock_db_session):
        """Test repository data retrieval when repository not found."""
        # Mock query to return None
        mock_query = Mock()
        mock_query.filter.return_value.first.return_value = None
        mock_db_session.query.return_value = mock_query

        result = cloud_sync_manager._get_repository_data(999)

        assert result is None

    def test_get_repository_data_database_error(
        self, cloud_sync_manager, mock_db_session_factory
    ):
        """Test repository data retrieval with database error."""
        mock_db_session_factory.side_effect = Exception("Database connection error")

        result = cloud_sync_manager._get_repository_data(1)

        assert result is None

    @pytest.mark.asyncio
    async def test_validate_cloud_config_success(
        self, cloud_sync_manager, mock_db_session, test_cloud_config
    ):
        """Test successful cloud config validation."""
        # Mock query to return valid config
        mock_query = Mock()
        mock_query.filter.return_value.first.return_value = test_cloud_config
        mock_db_session.query.return_value = mock_query

        cloud_sync_manager._validate_s3_config = AsyncMock(
            return_value={"valid": True, "provider": "s3", "bucket": "test-bucket"}
        )

        result = await cloud_sync_manager.validate_cloud_config(1)

        assert result["valid"] is True
        assert result["provider"] == "s3"
        assert result["bucket"] == "test-bucket"

    @pytest.mark.asyncio
    async def test_validate_cloud_config_not_found(
        self, cloud_sync_manager, mock_db_session
    ):
        """Test cloud config validation when config not found."""
        # Mock query to return None
        mock_query = Mock()
        mock_query.filter.return_value.first.return_value = None
        mock_db_session.query.return_value = mock_query

        result = await cloud_sync_manager.validate_cloud_config(999)

        assert result["valid"] is False
        assert "not found" in result["error"]

    @pytest.mark.asyncio
    async def test_validate_cloud_config_disabled(
        self, cloud_sync_manager, mock_db_session, test_cloud_config
    ):
        """Test cloud config validation with disabled config."""
        test_cloud_config.enabled = False

        # Mock query to return disabled config
        mock_query = Mock()
        mock_query.filter.return_value.first.return_value = test_cloud_config
        mock_db_session.query.return_value = mock_query

        result = await cloud_sync_manager.validate_cloud_config(1)

        assert result["valid"] is False
        assert "disabled" in result["error"]

    @pytest.mark.asyncio
    async def test_validate_cloud_config_unsupported_provider(
        self, cloud_sync_manager, mock_db_session, test_cloud_config
    ):
        """Test cloud config validation with unsupported provider."""
        test_cloud_config.provider = "unsupported"

        # Mock query to return config with unsupported provider
        mock_query = Mock()
        mock_query.filter.return_value.first.return_value = test_cloud_config
        mock_db_session.query.return_value = mock_query

        result = await cloud_sync_manager.validate_cloud_config(1)

        assert result["valid"] is False
        assert "Unsupported provider" in result["error"]

    @pytest.mark.asyncio
    async def test_validate_s3_config_success(
        self, cloud_sync_manager, test_cloud_config
    ):
        """Test successful S3 config validation."""
        result = await cloud_sync_manager._validate_s3_config(test_cloud_config)

        assert result["valid"] is True
        assert result["provider"] == "s3"
        assert result["bucket"] == "test-bucket"

    @pytest.mark.asyncio
    async def test_validate_s3_config_missing_bucket(
        self, cloud_sync_manager, test_cloud_config
    ):
        """Test S3 config validation with missing bucket name."""
        test_cloud_config.bucket_name = None

        result = await cloud_sync_manager._validate_s3_config(test_cloud_config)

        assert result["valid"] is False
        assert "bucket name is required" in result["error"]

    @pytest.mark.asyncio
    async def test_validate_s3_config_missing_credentials(
        self, cloud_sync_manager, test_cloud_config
    ):
        """Test S3 config validation with missing credentials."""
        # Mock get_credentials to return empty values
        test_cloud_config.get_credentials = Mock(return_value=(None, None))

        result = await cloud_sync_manager._validate_s3_config(test_cloud_config)

        assert result["valid"] is False
        assert "credentials are required" in result["error"]

    @pytest.mark.asyncio
    async def test_validate_s3_config_credential_error(
        self, cloud_sync_manager, test_cloud_config
    ):
        """Test S3 config validation with credential decryption error."""
        # Mock get_credentials to raise exception
        test_cloud_config.get_credentials = Mock(
            side_effect=Exception("Decryption error")
        )

        result = await cloud_sync_manager._validate_s3_config(test_cloud_config)

        assert result["valid"] is False
        assert "Invalid S3 credentials" in result["error"]

    @pytest.mark.asyncio
    async def test_get_sync_status_success(
        self, cloud_sync_manager, mock_db_session, test_cloud_config
    ):
        """Test successful sync status retrieval."""
        test_cloud_config.created_at = datetime.now(UTC)

        # Mock query to return config
        mock_query = Mock()
        mock_query.filter.return_value.first.return_value = test_cloud_config
        mock_db_session.query.return_value = mock_query

        result = await cloud_sync_manager.get_sync_status(1)

        assert result["exists"] is True
        assert result["enabled"] is True
        assert result["provider"] == "s3"
        assert result["name"] == "test-s3-config"
        assert result["bucket_name"] == "test-bucket"
        assert result["created_at"] is not None

    @pytest.mark.asyncio
    async def test_get_sync_status_not_found(self, cloud_sync_manager, mock_db_session):
        """Test sync status retrieval when config not found."""
        # Mock query to return None
        mock_query = Mock()
        mock_query.filter.return_value.first.return_value = None
        mock_db_session.query.return_value = mock_query

        result = await cloud_sync_manager.get_sync_status(999)

        assert result["exists"] is False
        assert "not found" in result["error"]

    @pytest.mark.asyncio
    async def test_get_sync_status_database_error(
        self, cloud_sync_manager, mock_db_session_factory
    ):
        """Test sync status retrieval with database error."""
        mock_db_session_factory.side_effect = Exception("Database error")

        result = await cloud_sync_manager.get_sync_status(1)

        assert result["exists"] is False
        assert "error" in result["error"]

    @pytest.mark.asyncio
    async def test_get_sync_status_no_created_at(
        self, cloud_sync_manager, mock_db_session
    ):
        """Test sync status retrieval with config missing created_at."""
        # Create a config without created_at
        config_without_created_at = Mock()
        config_without_created_at.enabled = True
        config_without_created_at.provider = "s3"
        config_without_created_at.name = "test-config"
        config_without_created_at.bucket_name = "test-bucket"
        config_without_created_at.created_at = None

        # Mock query to return config
        mock_query = Mock()
        mock_query.filter.return_value.first.return_value = config_without_created_at
        mock_db_session.query.return_value = mock_query

        result = await cloud_sync_manager.get_sync_status(1)

        assert result["exists"] is True
        assert result["created_at"] is None
