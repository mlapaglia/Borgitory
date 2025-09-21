"""
Tests for CloudSyncConfigService - Business logic tests migrated from API tests
"""

import pytest
from fastapi import HTTPException
from sqlalchemy.orm import Session

from borgitory.services.cloud_sync_service import CloudSyncConfigService
from borgitory.models.database import CloudSyncConfig
from borgitory.models.schemas import CloudSyncConfigCreate, CloudSyncConfigUpdate
from tests.conftest import create_s3_cloud_sync_config, create_sftp_cloud_sync_config


@pytest.fixture
def service(test_db: Session):
    """CloudSyncConfigService instance with real database session."""
    from borgitory.services.cloud_providers.registry import get_metadata
    from borgitory.services.rclone_service import RcloneService
    from borgitory.services.cloud_providers import StorageFactory, EncryptionService

    rclone_service = RcloneService()
    storage_factory = StorageFactory(rclone_service)
    encryption_service = EncryptionService()

    return CloudSyncConfigService(
        db=test_db,
        rclone_service=rclone_service,
        storage_factory=storage_factory,
        encryption_service=encryption_service,
        get_metadata_func=get_metadata,
    )


class TestCloudSyncConfigService:
    """Test class for CloudSyncConfigService business logic."""

    def test_create_s3_config_success(self, service, test_db: Session) -> None:
        """Test successful S3 config creation."""
        config_data = CloudSyncConfigCreate(
            name="test-s3",
            provider="s3",
            provider_config={
                "bucket_name": "test-bucket",
                "access_key": "AKIAIOSFODNN7EXAMPLE",  # 20 characters
                "secret_key": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",  # 40 characters
                "region": "us-east-1",
                "storage_class": "STANDARD",
            },
            path_prefix="backups/",
        )

        result = service.create_cloud_sync_config(config_data)

        # Verify the result
        assert result.name == "test-s3"
        assert result.provider == "s3"
        assert result.path_prefix == "backups/"

        # Verify provider config JSON contains expected values
        import json

        config_data = json.loads(result.provider_config)
        assert config_data["bucket_name"] == "test-bucket"

        # Verify it was saved to database
        saved_config = (
            test_db.query(CloudSyncConfig)
            .filter(CloudSyncConfig.name == "test-s3")
            .first()
        )
        assert saved_config is not None
        assert saved_config.provider == "s3"

        # Verify saved config JSON
        saved_config_data = json.loads(saved_config.provider_config)
        assert saved_config_data["bucket_name"] == "test-bucket"

    def test_create_sftp_config_success(self, service, test_db: Session) -> None:
        """Test successful SFTP config creation with password."""
        config_data = CloudSyncConfigCreate(
            name="test-sftp",
            provider="sftp",
            provider_config={
                "host": "sftp.example.com",
                "port": 22,
                "username": "testuser",
                "password": "testpass",
                "remote_path": "/backups",
                "host_key_checking": True,
            },
            path_prefix="borg/",
        )

        result = service.create_cloud_sync_config(config_data)

        # Verify the result
        assert result.name == "test-sftp"
        assert result.provider == "sftp"

        # Verify provider config JSON contains expected values
        import json

        config_data = json.loads(result.provider_config)
        assert config_data["host"] == "sftp.example.com"
        assert config_data["port"] == 22
        assert config_data["username"] == "testuser"
        assert config_data["remote_path"] == "/backups"

        # Verify it was saved to database
        saved_config = (
            test_db.query(CloudSyncConfig)
            .filter(CloudSyncConfig.name == "test-sftp")
            .first()
        )
        assert saved_config is not None
        assert saved_config.provider == "sftp"

        # Verify saved config JSON
        saved_config_data = json.loads(saved_config.provider_config)
        assert saved_config_data["host"] == "sftp.example.com"

    def test_create_sftp_config_with_private_key(
        self, service, test_db: Session
    ) -> None:
        """Test successful SFTP config creation with private key."""
        config_data = CloudSyncConfigCreate(
            name="test-sftp-key",
            provider="sftp",
            provider_config={
                "host": "sftp.example.com",
                "port": 22,
                "username": "testuser",
                "private_key": "-----BEGIN RSA PRIVATE KEY-----\ntest-key-content\n-----END RSA PRIVATE KEY-----",
                "remote_path": "/backups",
                "host_key_checking": True,
            },
        )

        result = service.create_cloud_sync_config(config_data)

        # Verify the result
        assert result.name == "test-sftp-key"
        assert result.provider == "sftp"

        # Verify provider config JSON contains expected values
        import json

        config_data = json.loads(result.provider_config)
        assert config_data["username"] == "testuser"

        # Verify it was saved to database
        saved_config = (
            test_db.query(CloudSyncConfig)
            .filter(CloudSyncConfig.name == "test-sftp-key")
            .first()
        )
        assert saved_config is not None
        assert saved_config.provider == "sftp"

    def test_create_config_duplicate_name(self, service, test_db: Session) -> None:
        """Test creating config with duplicate name."""
        # First, create a config
        first_config = create_s3_cloud_sync_config(
            name="duplicate-test", bucket_name="first-bucket"
        )
        test_db.add(first_config)
        test_db.commit()

        # Try to create another with same name
        config_data = CloudSyncConfigCreate(
            name="duplicate-test",  # Same name
            provider="s3",
            provider_config={
                "bucket_name": "test-bucket",
                "access_key": "AKIAIOSFODNN7EXAMPLE",
                "secret_key": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
                "region": "us-east-1",
                "storage_class": "STANDARD",
            },
        )

        with pytest.raises(HTTPException) as exc_info:
            service.create_cloud_sync_config(config_data)

        assert exc_info.value.status_code == 400
        assert "already exists" in str(exc_info.value.detail)

    def test_create_s3_config_missing_credentials(
        self, service, test_db: Session
    ) -> None:
        """Test S3 config creation with missing credentials - schema validation."""
        # This test verifies that Pydantic schema validation catches missing credentials
        with pytest.raises(ValueError) as exc_info:
            CloudSyncConfigCreate(
                name="incomplete-s3",
                provider="s3",
                provider_config={
                    "bucket_name": "test-bucket",
                    # Missing access_key and secret_key
                },
            )

        assert "Invalid s3 configuration" in str(exc_info.value)

    def test_create_sftp_config_missing_required_fields(
        self, service, test_db: Session
    ) -> None:
        """Test SFTP config creation with missing required fields - schema validation."""
        # This test verifies that Pydantic schema validation catches missing username
        with pytest.raises(ValueError) as exc_info:
            CloudSyncConfigCreate(
                name="incomplete-sftp",
                provider="sftp",
                provider_config={
                    "host": "sftp.example.com",
                    # Missing username, remote_path, and auth method
                },
            )

        assert "Invalid sftp configuration" in str(exc_info.value)

    def test_create_sftp_config_missing_auth(self, service, test_db: Session) -> None:
        """Test SFTP config creation with missing authentication - schema validation."""
        # This test verifies that Pydantic schema validation catches missing auth
        with pytest.raises(ValueError) as exc_info:
            CloudSyncConfigCreate(
                name="sftp-no-auth",
                provider="sftp",
                provider_config={
                    "host": "sftp.example.com",
                    "username": "testuser",
                    "remote_path": "/backups",
                    # Missing both password and private_key
                },
            )

        assert "Invalid sftp configuration" in str(exc_info.value)

    def test_create_config_unsupported_provider(
        self, service, test_db: Session
    ) -> None:
        """Test config creation with unsupported provider."""
        from pydantic_core import ValidationError

        # Should fail at Pydantic validation level
        with pytest.raises(ValidationError) as exc_info:
            CloudSyncConfigCreate(
                name="unsupported",
                provider="azure",  # Not supported
                provider_config={"bucket_name": "test"},
            )

        assert "azure" in str(exc_info.value).lower()

    def test_list_configs_empty(self, service, test_db: Session) -> None:
        """Test listing configs when empty."""
        result = service.get_cloud_sync_configs()

        assert result == []

    def test_list_configs_with_data(self, service, test_db: Session) -> None:
        """Test listing configs with data."""
        # Create real configs in database
        config1 = create_s3_cloud_sync_config(
            name="s3-config", bucket_name="bucket1", enabled=True
        )
        config2 = create_sftp_cloud_sync_config(
            name="sftp-config",
            host="sftp.example.com",
            username="user",
            remote_path="/backup",
            enabled=False,
        )

        test_db.add(config1)
        test_db.add(config2)
        test_db.commit()

        result = service.get_cloud_sync_configs()

        assert len(result) == 2
        assert result[0].name == "s3-config"
        assert result[1].name == "sftp-config"

    def test_get_config_by_id_success(self, service, test_db: Session) -> None:
        """Test getting specific config by ID."""
        config = create_s3_cloud_sync_config(
            name="get-test", bucket_name="test-bucket", enabled=True
        )
        test_db.add(config)
        test_db.commit()
        test_db.refresh(config)  # Get the ID

        result = service.get_cloud_sync_config_by_id(config.id)

        assert result.name == "get-test"
        assert result.id == config.id

    def test_get_config_by_id_not_found(self, service, test_db: Session) -> None:
        """Test getting non-existent config."""
        with pytest.raises(HTTPException) as exc_info:
            service.get_cloud_sync_config_by_id(999)

        assert exc_info.value.status_code == 404

    def test_update_config_success(self, service, test_db: Session) -> None:
        """Test successful config update."""
        # Create existing config
        existing_config = create_s3_cloud_sync_config(name="update-test", enabled=True)
        test_db.add(existing_config)
        test_db.commit()
        test_db.refresh(existing_config)

        update_data = CloudSyncConfigUpdate(
            provider_config={
                "bucket_name": "new-bucket",
                "access_key": "AKIAIOSFODNN7EXAMPLE",
                "secret_key": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
                "region": "us-east-1",
                "storage_class": "STANDARD",
            },
            path_prefix="updated/",
        )

        result = service.update_cloud_sync_config(existing_config.id, update_data)

        # Verify the update
        import json

        provider_config = json.loads(result.provider_config)
        assert provider_config["bucket_name"] == "new-bucket"
        assert result.path_prefix == "updated/"

        # Verify in database
        updated_config = (
            test_db.query(CloudSyncConfig)
            .filter(CloudSyncConfig.id == existing_config.id)
            .first()
        )
        updated_provider_config = json.loads(updated_config.provider_config)
        assert updated_provider_config["bucket_name"] == "new-bucket"
        assert updated_config.path_prefix == "updated/"

    def test_update_config_duplicate_name(self, service, test_db: Session) -> None:
        """Test updating config with duplicate name."""
        # Create two configs
        config1 = create_s3_cloud_sync_config(name="config1", bucket_name="bucket1")
        config2 = create_s3_cloud_sync_config(name="config2", bucket_name="bucket2")
        test_db.add(config1)
        test_db.add(config2)
        test_db.commit()
        test_db.refresh(config1)
        test_db.refresh(config2)

        # Try to update config2 to have config1's name
        update_data = CloudSyncConfigUpdate(name="config1")

        with pytest.raises(HTTPException) as exc_info:
            service.update_cloud_sync_config(config2.id, update_data)

        assert exc_info.value.status_code == 400
        assert "already exists" in str(exc_info.value.detail)

    def test_delete_config_success(self, service, test_db: Session) -> None:
        """Test successful config deletion."""
        config = create_s3_cloud_sync_config(
            name="delete-test", bucket_name="delete-bucket"
        )
        test_db.add(config)
        test_db.commit()
        test_db.refresh(config)
        config_id = config.id

        service.delete_cloud_sync_config(config_id)

        # Verify config is deleted from database
        deleted_config = (
            test_db.query(CloudSyncConfig)
            .filter(CloudSyncConfig.id == config_id)
            .first()
        )
        assert deleted_config is None

    def test_delete_config_not_found(self, service, test_db: Session) -> None:
        """Test deleting non-existent config."""
        with pytest.raises(HTTPException) as exc_info:
            service.delete_cloud_sync_config(999)

        assert exc_info.value.status_code == 404

    def test_enable_config_success(self, service, test_db: Session) -> None:
        """Test enabling config."""
        config = create_s3_cloud_sync_config(
            name="enable-test", bucket_name="test-bucket", enabled=False
        )
        test_db.add(config)
        test_db.commit()
        test_db.refresh(config)

        result = service.enable_cloud_sync_config(config.id)

        assert result.enabled is True

        # Verify in database
        updated_config = (
            test_db.query(CloudSyncConfig)
            .filter(CloudSyncConfig.id == config.id)
            .first()
        )
        assert updated_config.enabled is True

    def test_disable_config_success(self, service, test_db: Session) -> None:
        """Test disabling config."""
        config = create_s3_cloud_sync_config(
            name="disable-test", bucket_name="test-bucket", enabled=True
        )
        test_db.add(config)
        test_db.commit()
        test_db.refresh(config)

        result = service.disable_cloud_sync_config(config.id)

        assert result.enabled is False

        # Verify in database
        updated_config = (
            test_db.query(CloudSyncConfig)
            .filter(CloudSyncConfig.id == config.id)
            .first()
        )
        assert updated_config.enabled is False

    def test_config_lifecycle(self, service, test_db: Session) -> None:
        """Test complete config lifecycle: create, update, enable/disable, delete."""
        # Create
        config_data = CloudSyncConfigCreate(
            name="lifecycle-test",
            provider="s3",
            provider_config={
                "bucket_name": "lifecycle-bucket",
                "access_key": "AKIAIOSFODNN7EXAMPLE",
                "secret_key": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
                "region": "us-east-1",
                "storage_class": "STANDARD",
            },
        )

        created_config = service.create_cloud_sync_config(config_data)
        assert created_config.name == "lifecycle-test"
        config_id = created_config.id

        # Update
        update_data = CloudSyncConfigUpdate(
            provider_config={
                "bucket_name": "updated-bucket",
                "access_key": "AKIAIOSFODNN7EXAMPLE",
                "secret_key": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
                "region": "us-east-1",
                "storage_class": "STANDARD",
            }
        )
        updated_config = service.update_cloud_sync_config(config_id, update_data)

        # Verify the update
        import json

        provider_config = json.loads(updated_config.provider_config)
        assert provider_config["bucket_name"] == "updated-bucket"

        # Disable
        disabled_config = service.disable_cloud_sync_config(config_id)
        assert disabled_config.enabled is False

        # Enable
        enabled_config = service.enable_cloud_sync_config(config_id)
        assert enabled_config.enabled is True

        # Delete
        service.delete_cloud_sync_config(config_id)

        # Verify config is completely removed
        deleted_config = (
            test_db.query(CloudSyncConfig)
            .filter(CloudSyncConfig.id == config_id)
            .first()
        )
        assert deleted_config is None
