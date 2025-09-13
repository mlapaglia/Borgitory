"""
Tests for CloudSyncService - Business logic tests migrated from API tests
"""
import pytest
from unittest.mock import Mock
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.services.cloud_sync_service import CloudSyncService
from app.models.database import CloudSyncConfig
from app.models.schemas import CloudSyncConfigCreate, CloudSyncConfigUpdate


@pytest.fixture
def mock_db_session():
    """Mock database session."""
    mock_session = Mock(spec=Session)
    return mock_session


@pytest.fixture
def service(mock_db_session):
    """CloudSyncService instance with mocked database session."""
    return CloudSyncService(mock_db_session)


class TestCloudSyncService:
    """Test class for CloudSyncService business logic."""

    def test_create_s3_config_success(self, service, mock_db_session):
        """Test successful S3 config creation."""
        config_data = CloudSyncConfigCreate(
            name="test-s3",
            provider="s3",
            bucket_name="test-bucket",
            access_key="AKIAIOSFODNN7EXAMPLE",  # 20 characters
            secret_key="wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",  # 40 characters
            path_prefix="backups/"
        )

        # Mock no existing config
        mock_db_session.query.return_value.filter.return_value.first.return_value = None

        # Mock the created config
        created_config = Mock(spec=CloudSyncConfig)
        created_config.name = "test-s3"
        created_config.provider = "s3"
        created_config.bucket_name = "test-bucket"
        created_config.path_prefix = "backups/"
        mock_db_session.refresh = Mock()

        result = service.create_cloud_sync_config(config_data)

        # Verify database operations
        mock_db_session.add.assert_called_once()
        mock_db_session.commit.assert_called_once()
        mock_db_session.refresh.assert_called_once()

    def test_create_sftp_config_success(self, service, mock_db_session):
        """Test successful SFTP config creation with password."""
        config_data = CloudSyncConfigCreate(
            name="test-sftp",
            provider="sftp",
            host="sftp.example.com",
            port=22,
            username="testuser",
            password="testpass",
            remote_path="/backups",
            path_prefix="borg/"
        )

        # Mock no existing config
        mock_db_session.query.return_value.filter.return_value.first.return_value = None

        result = service.create_cloud_sync_config(config_data)

        # Verify database operations
        mock_db_session.add.assert_called_once()
        mock_db_session.commit.assert_called_once()
        mock_db_session.refresh.assert_called_once()

    def test_create_sftp_config_with_private_key(self, service, mock_db_session):
        """Test successful SFTP config creation with private key."""
        config_data = CloudSyncConfigCreate(
            name="test-sftp-key",
            provider="sftp",
            host="sftp.example.com",
            port=22,
            username="testuser",
            private_key="-----BEGIN RSA PRIVATE KEY-----\ntest-key-content\n-----END RSA PRIVATE KEY-----",
            remote_path="/backups"
        )

        # Mock no existing config
        mock_db_session.query.return_value.filter.return_value.first.return_value = None

        result = service.create_cloud_sync_config(config_data)

        # Verify database operations
        mock_db_session.add.assert_called_once()
        mock_db_session.commit.assert_called_once()

    def test_create_config_duplicate_name(self, service, mock_db_session):
        """Test creating config with duplicate name."""
        config_data = CloudSyncConfigCreate(
            name="duplicate-test",
            provider="s3",
            bucket_name="test-bucket",
            access_key="AKIAIOSFODNN7EXAMPLE",
            secret_key="wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
        )

        # Mock existing config
        existing_config = Mock(spec=CloudSyncConfig)
        existing_config.name = "duplicate-test"
        mock_db_session.query.return_value.filter.return_value.first.return_value = existing_config

        with pytest.raises(HTTPException) as exc_info:
            service.create_cloud_sync_config(config_data)

        assert exc_info.value.status_code == 400
        assert "already exists" in str(exc_info.value.detail)

    def test_create_s3_config_missing_credentials(self, service, mock_db_session):
        """Test S3 config creation with missing credentials - schema validation."""
        # This test verifies that Pydantic schema validation catches missing credentials
        with pytest.raises(ValueError) as exc_info:
            config_data = CloudSyncConfigCreate(
                name="incomplete-s3",
                provider="s3",
                bucket_name="test-bucket"
                # Missing access_key and secret_key
            )

        assert "AWS Access Key ID is required" in str(exc_info.value)

    def test_create_sftp_config_missing_required_fields(self, service, mock_db_session):
        """Test SFTP config creation with missing required fields - schema validation."""
        # This test verifies that Pydantic schema validation catches missing username
        with pytest.raises(ValueError) as exc_info:
            config_data = CloudSyncConfigCreate(
                name="incomplete-sftp",
                provider="sftp",
                host="sftp.example.com"
                # Missing username, remote_path, and auth method
            )

        assert "SFTP username is required" in str(exc_info.value)

    def test_create_sftp_config_missing_auth(self, service, mock_db_session):
        """Test SFTP config creation with missing authentication - schema validation."""
        # This test verifies that Pydantic schema validation catches missing auth
        with pytest.raises(ValueError) as exc_info:
            config_data = CloudSyncConfigCreate(
                name="sftp-no-auth",
                provider="sftp",
                host="sftp.example.com",
                username="testuser",
                remote_path="/backups"
                # Missing both password and private_key
            )

        assert "Either SFTP password or private key is required" in str(exc_info.value)

    def test_create_config_unsupported_provider(self, service, mock_db_session):
        """Test config creation with unsupported provider."""
        config_data = CloudSyncConfigCreate(
            name="unsupported",
            provider="azure",  # Not supported
            bucket_name="test"
        )

        # Mock no existing config
        mock_db_session.query.return_value.filter.return_value.first.return_value = None

        with pytest.raises(HTTPException) as exc_info:
            service.create_cloud_sync_config(config_data)

        assert exc_info.value.status_code == 400
        assert "Unsupported provider" in str(exc_info.value.detail)

    def test_list_configs_empty(self, service, mock_db_session):
        """Test listing configs when empty."""
        mock_db_session.query.return_value.all.return_value = []

        result = service.get_cloud_sync_configs()

        assert result == []

    def test_list_configs_with_data(self, service, mock_db_session):
        """Test listing configs with data."""
        # Mock configs
        config1 = Mock(spec=CloudSyncConfig)
        config1.name = "s3-config"
        config1.provider = "s3"
        config1.enabled = True

        config2 = Mock(spec=CloudSyncConfig)
        config2.name = "sftp-config"
        config2.provider = "sftp"
        config2.enabled = False

        mock_db_session.query.return_value.all.return_value = [config1, config2]

        result = service.get_cloud_sync_configs()

        assert len(result) == 2
        assert result[0].name == "s3-config"
        assert result[1].name == "sftp-config"

    def test_get_config_by_id_success(self, service, mock_db_session):
        """Test getting specific config by ID."""
        mock_config = Mock(spec=CloudSyncConfig)
        mock_config.id = 1
        mock_config.name = "get-test"
        mock_db_session.query.return_value.filter.return_value.first.return_value = mock_config

        result = service.get_cloud_sync_config_by_id(1)

        assert result.name == "get-test"
        assert result.id == 1

    def test_get_config_by_id_not_found(self, service, mock_db_session):
        """Test getting non-existent config."""
        mock_db_session.query.return_value.filter.return_value.first.return_value = None

        with pytest.raises(HTTPException) as exc_info:
            service.get_cloud_sync_config_by_id(999)

        assert exc_info.value.status_code == 404

    def test_update_config_success(self, service, mock_db_session):
        """Test successful config update."""
        # Mock existing config
        existing_config = Mock(spec=CloudSyncConfig)
        existing_config.id = 1
        existing_config.name = "update-test"
        existing_config.bucket_name = "old-bucket"
        existing_config.path_prefix = ""
        mock_db_session.query.return_value.filter.return_value.first.return_value = existing_config

        update_data = CloudSyncConfigUpdate(
            bucket_name="new-bucket",
            path_prefix="updated/"
        )

        result = service.update_cloud_sync_config(1, update_data)

        mock_db_session.commit.assert_called_once()
        mock_db_session.refresh.assert_called_once()

    def test_update_config_duplicate_name(self, service, mock_db_session):
        """Test updating config with duplicate name."""
        # Mock existing config to update
        config_to_update = Mock(spec=CloudSyncConfig)
        config_to_update.id = 2
        config_to_update.name = "config2"

        # Mock duplicate name config
        duplicate_config = Mock(spec=CloudSyncConfig)
        duplicate_config.id = 1
        duplicate_config.name = "config1"

        # First call returns config to update, second call returns duplicate
        mock_db_session.query.return_value.filter.return_value.first.side_effect = [
            config_to_update,  # Config being updated
            duplicate_config   # Existing config with duplicate name
        ]

        update_data = CloudSyncConfigUpdate(name="config1")

        with pytest.raises(HTTPException) as exc_info:
            service.update_cloud_sync_config(2, update_data)

        assert exc_info.value.status_code == 400
        assert "already exists" in str(exc_info.value.detail)

    def test_delete_config_success(self, service, mock_db_session):
        """Test successful config deletion."""
        mock_config = Mock(spec=CloudSyncConfig)
        mock_config.id = 1
        mock_config.name = "delete-test"
        mock_db_session.query.return_value.filter.return_value.first.return_value = mock_config

        service.delete_cloud_sync_config(1)

        mock_db_session.delete.assert_called_once_with(mock_config)
        mock_db_session.commit.assert_called_once()

    def test_delete_config_not_found(self, service, mock_db_session):
        """Test deleting non-existent config."""
        mock_db_session.query.return_value.filter.return_value.first.return_value = None

        with pytest.raises(HTTPException) as exc_info:
            service.delete_cloud_sync_config(999)

        assert exc_info.value.status_code == 404

    def test_enable_config_success(self, service, mock_db_session):
        """Test enabling config."""
        mock_config = Mock(spec=CloudSyncConfig)
        mock_config.id = 1
        mock_config.name = "enable-test"
        mock_config.enabled = False
        mock_db_session.query.return_value.filter.return_value.first.return_value = mock_config

        result = service.enable_cloud_sync_config(1)

        assert mock_config.enabled is True
        mock_db_session.commit.assert_called_once()
        # Service doesn't call refresh for enable/disable operations

    def test_disable_config_success(self, service, mock_db_session):
        """Test disabling config."""
        mock_config = Mock(spec=CloudSyncConfig)
        mock_config.id = 1
        mock_config.name = "disable-test"
        mock_config.enabled = True
        mock_db_session.query.return_value.filter.return_value.first.return_value = mock_config

        result = service.disable_cloud_sync_config(1)

        assert mock_config.enabled is False
        mock_db_session.commit.assert_called_once()
        # Service doesn't call refresh for enable/disable operations

    def test_config_lifecycle(self, service, mock_db_session):
        """Test complete config lifecycle: create, update, enable/disable, delete."""
        # Mock no existing config for creation
        mock_db_session.query.return_value.filter.return_value.first.return_value = None

        # Create
        config_data = CloudSyncConfigCreate(
            name="lifecycle-test",
            provider="s3",
            bucket_name="lifecycle-bucket",
            access_key="AKIAIOSFODNN7EXAMPLE",
            secret_key="wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
        )

        # Mock created config
        created_config = Mock(spec=CloudSyncConfig)
        created_config.id = 1
        created_config.name = "lifecycle-test"
        created_config.bucket_name = "lifecycle-bucket"
        created_config.enabled = True

        service.create_cloud_sync_config(config_data)

        # Update - mock the config exists
        mock_db_session.query.return_value.filter.return_value.first.return_value = created_config

        update_data = CloudSyncConfigUpdate(bucket_name="updated-bucket")
        service.update_cloud_sync_config(1, update_data)

        # Disable
        service.disable_cloud_sync_config(1)

        # Enable
        service.enable_cloud_sync_config(1)

        # Delete
        service.delete_cloud_sync_config(1)

        # Verify all database operations were called
        assert mock_db_session.add.call_count >= 1
        assert mock_db_session.commit.call_count >= 5  # create, update, disable, enable, delete
        assert mock_db_session.delete.call_count >= 1