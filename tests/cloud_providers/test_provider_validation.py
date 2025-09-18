"""
Tests for provider validation using registry and Pydantic validators.
"""

import pytest
from pydantic import ValidationError

from borgitory.services.cloud_providers.registry import (
    clear_registry,
    register_provider,
    is_provider_registered,
)
from borgitory.models.schemas import CloudSyncConfigCreate, CloudSyncConfigUpdate
from borgitory.services.cloud_providers.storage.base import (
    CloudStorage,
    CloudStorageConfig,
)
from borgitory.services.rclone_service import RcloneService


class MockStorageConfig(CloudStorageConfig):
    """Mock storage config for testing"""

    test_field: str


class MockStorage(CloudStorage):
    """Mock storage for testing"""

    def __init__(self, rclone_service: RcloneService, config) -> None:
        super().__init__()

    async def sync_to_cloud(self, source_path: str, destination_path: str) -> None:
        pass

    def get_rclone_config_section(self) -> dict:
        return {}

    def get_sensitive_fields(self) -> list:
        return ["test_field"]

    def get_display_details(self, config_dict: dict) -> dict:
        return {
            "provider_name": "Mock Provider",
            "provider_details": "<div>Mock details</div>",
        }


@pytest.fixture
def clean_registry():
    """Clean registry before each test"""
    clear_registry()
    # Force reload of storage modules to re-register providers after clearing
    import importlib
    import borgitory.services.cloud_providers.storage.s3_storage
    import borgitory.services.cloud_providers.storage.sftp_storage
    import borgitory.services.cloud_providers.storage.smb_storage

    importlib.reload(borgitory.services.cloud_providers.storage.s3_storage)
    importlib.reload(borgitory.services.cloud_providers.storage.sftp_storage)
    importlib.reload(borgitory.services.cloud_providers.storage.smb_storage)
    yield
    # Don't clear after - let the next test's setup handle it


class TestProviderValidation:
    """Test provider validation using registry"""

    def test_is_provider_registered_function(self, clean_registry) -> None:
        """Test is_provider_registered helper function"""
        # Should return False for unregistered provider
        assert not is_provider_registered("nonexistent")

        # Register a provider
        @register_provider(
            name="mock",
            label="Mock Provider",
            description="Test provider",
            supports_encryption=True,
            supports_versioning=False,
            requires_credentials=True,
        )
        class MockProvider:
            config_class = MockStorageConfig
            storage_class = MockStorage

        # Should return True for registered provider
        assert is_provider_registered("mock")

        # Should still return False for unregistered provider
        assert not is_provider_registered("stillnonexistent")


class TestPydanticValidation:
    """Test Pydantic schema validation with registry"""

    def test_create_config_with_valid_provider(self, clean_registry) -> None:
        """Test CloudSyncConfigCreate with valid registered provider"""
        config_data = {
            "name": "Test Config",
            "provider": "s3",
            "provider_config": {
                "bucket_name": "test-bucket",
                "access_key": "AKIAIOSFODNN7EXAMPLE",  # Valid length
                "secret_key": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",  # Valid length
                "region": "us-east-1",
                "storage_class": "STANDARD",
            },
        }

        # Should validate successfully
        config = CloudSyncConfigCreate(**config_data)
        assert config.provider == "s3"
        assert config.name == "Test Config"

    def test_create_config_with_invalid_provider(self, clean_registry) -> None:
        """Test CloudSyncConfigCreate with invalid provider"""
        config_data = {
            "name": "Test Config",
            "provider": "invalid_provider",
            "provider_config": {"some": "config"},
        }

        # Should raise validation error
        with pytest.raises(ValidationError) as exc_info:
            CloudSyncConfigCreate(**config_data)

        error_msg = str(exc_info.value)
        assert "invalid_provider" in error_msg
        assert "Unknown provider" in error_msg
        assert "Supported providers:" in error_msg

    def test_create_config_with_empty_provider(self, clean_registry) -> None:
        """Test CloudSyncConfigCreate with empty provider"""
        config_data = {
            "name": "Test Config",
            "provider": "",
            "provider_config": {"some": "config"},
        }

        # Should raise validation error
        with pytest.raises(ValidationError) as exc_info:
            CloudSyncConfigCreate(**config_data)

        error_msg = str(exc_info.value)
        assert "Provider is required" in error_msg

    def test_update_config_with_valid_provider(self, clean_registry) -> None:
        """Test CloudSyncConfigUpdate with valid provider"""
        update_data = {
            "provider": "sftp",
            "provider_config": {
                "host": "example.com",
                "username": "testuser",
                "password": "testpass",
                "remote_path": "/backup",
                "port": 22,
                "host_key_checking": True,
            },
        }

        # Should validate successfully
        config = CloudSyncConfigUpdate(**update_data)
        assert config.provider == "sftp"

    def test_update_config_with_invalid_provider(self, clean_registry) -> None:
        """Test CloudSyncConfigUpdate with invalid provider"""
        update_data = {
            "provider": "nonexistent_provider",
            "provider_config": {"some": "config"},
        }

        # Should raise validation error
        with pytest.raises(ValidationError) as exc_info:
            CloudSyncConfigUpdate(**update_data)

        error_msg = str(exc_info.value)
        assert "nonexistent_provider" in error_msg
        assert "Unknown provider" in error_msg

    def test_update_config_with_none_provider(self, clean_registry) -> None:
        """Test CloudSyncConfigUpdate with None provider (should be allowed)"""
        update_data = {"name": "Updated Name"}

        # Should validate successfully with None provider
        config = CloudSyncConfigUpdate(**update_data)
        assert config.provider is None
        assert config.name == "Updated Name"

    def test_validation_reflects_registry_changes(self, clean_registry) -> None:
        """Test that validation reflects changes in registry"""

        # Register a custom provider
        @register_provider(
            name="custom",
            label="Custom Provider",
            description="Custom test provider",
            supports_encryption=True,
            supports_versioning=False,
            requires_credentials=True,
        )
        class CustomProvider:
            config_class = MockStorageConfig
            storage_class = MockStorage

        config_data = {
            "name": "Test Config",
            "provider": "custom",
            "provider_config": {"test_field": "test_value"},
        }

        # Should validate successfully with the new provider
        config = CloudSyncConfigCreate(**config_data)
        assert config.provider == "custom"

    def test_base_config_provider_validation(self, clean_registry) -> None:
        """Test that base config also validates provider"""
        # Test with valid provider
        config_data = {
            "name": "Test Config",
            "provider": "smb",
            "provider_config": {
                "host": "192.168.1.100",
                "share_name": "backup",
                "user": "testuser",
                "pass": "testpass",
            },
        }

        config = CloudSyncConfigCreate(**config_data)
        assert config.provider == "smb"

        # Test with invalid provider should fail
        config_data["provider"] = "invalid"
        with pytest.raises(ValidationError) as exc_info:
            CloudSyncConfigCreate(**config_data)

        assert "Unknown provider 'invalid'" in str(exc_info.value)

    def test_error_message_includes_supported_providers(self, clean_registry) -> None:
        """Test that error messages include list of supported providers"""
        config_data = {
            "name": "Test Config",
            "provider": "unsupported",
            "provider_config": {"some": "config"},
        }

        with pytest.raises(ValidationError) as exc_info:
            CloudSyncConfigCreate(**config_data)

        error_msg = str(exc_info.value)
        # Should include some of the standard providers
        assert "s3" in error_msg
        assert "sftp" in error_msg
        assert "smb" in error_msg
        assert "Supported providers:" in error_msg
