"""
Tests for registry integration with the service layer.

These tests focus on business logic and verify that the registry system
is properly integrated with the cloud sync services.
"""

import pytest
from unittest.mock import Mock, patch
from borgitory.services.cloud_sync_service import _get_sensitive_fields_for_provider
from borgitory.api.cloud_sync import _get_supported_providers
from borgitory.services.cloud_providers.registry import ProviderRegistry


class TestRegistryBusinessLogic:
    """Test registry functions directly (business logic)"""

    def test_get_all_provider_info_with_registered_providers(
        self, production_registry: ProviderRegistry
    ) -> None:
        """Test getting all provider info when providers are registered"""
        provider_info = production_registry.get_all_provider_info()

        # Should have all three providers
        assert len(provider_info) >= 3
        assert "s3" in provider_info
        assert "sftp" in provider_info
        assert "smb" in provider_info

        # Check S3 info
        s3_info = provider_info["s3"]
        assert s3_info.label == "AWS S3"
        assert s3_info.description == "Amazon S3 compatible storage"
        assert s3_info.supports_encryption is True
        assert s3_info.supports_versioning is True

        # Check SMB info
        smb_info = provider_info["smb"]
        assert smb_info.label == "SMB/CIFS"
        assert (
            smb_info.description == "Server Message Block / Common Internet File System"
        )
        assert smb_info.supports_encryption is True
        assert smb_info.supports_versioning is False

    def test_get_supported_providers_returns_sorted_list(
        self, production_registry: ProviderRegistry
    ) -> None:
        """Test that supported providers are returned in sorted order"""
        providers = production_registry.get_supported_providers()

        # Should include our three providers, possibly more
        assert "s3" in providers
        assert "sftp" in providers
        assert "smb" in providers

        # Should be sorted
        assert providers == sorted(providers)

    def test_get_config_class_returns_correct_classes(
        self, production_registry: ProviderRegistry
    ) -> None:
        """Test that config classes are returned correctly"""
        # Test by class name to avoid identity issues after module reloading
        s3_config_class = production_registry.get_config_class("s3")
        sftp_config_class = production_registry.get_config_class("sftp")
        smb_config_class = production_registry.get_config_class("smb")

        assert s3_config_class is not None
        assert s3_config_class.__name__ == "S3StorageConfig"
        assert sftp_config_class is not None
        assert sftp_config_class.__name__ == "SFTPStorageConfig"
        assert smb_config_class is not None
        assert smb_config_class.__name__ == "SMBStorageConfig"
        assert production_registry.get_config_class("unknown") is None

    def test_get_storage_class_returns_correct_classes(
        self, production_registry: ProviderRegistry
    ) -> None:
        """Test that storage classes are returned correctly"""
        # Test by class name to avoid identity issues after module reloading
        s3_storage_class = production_registry.get_storage_class("s3")
        sftp_storage_class = production_registry.get_storage_class("sftp")
        smb_storage_class = production_registry.get_storage_class("smb")

        assert s3_storage_class is not None
        assert s3_storage_class.__name__ == "S3Storage"
        assert sftp_storage_class is not None
        assert sftp_storage_class.__name__ == "SFTPStorage"
        assert smb_storage_class is not None
        assert smb_storage_class.__name__ == "SMBStorage"
        assert production_registry.get_storage_class("unknown") is None


class TestSensitiveFieldsIntegration:
    """Test sensitive fields detection using registry"""

    def test_get_sensitive_fields_for_registered_providers(
        self, production_registry: ProviderRegistry
    ) -> None:
        """Test that sensitive fields are correctly retrieved from registry"""
        # Import storage modules to trigger registration (if not already done)

        # Test each provider
        s3_fields = _get_sensitive_fields_for_provider("s3")
        assert set(s3_fields) == {"access_key", "secret_key"}

        sftp_fields = _get_sensitive_fields_for_provider("sftp")
        assert set(sftp_fields) == {"password", "private_key"}

        smb_fields = _get_sensitive_fields_for_provider("smb")
        assert set(smb_fields) == {"pass"}

    def test_get_sensitive_fields_for_unknown_provider(self) -> None:
        """Test that unknown providers return empty list with warning"""
        # Import storage modules to trigger registration

        with patch("borgitory.services.cloud_sync_service.logger") as mock_logger:
            fields = _get_sensitive_fields_for_provider("unknown")

            assert fields == []
            mock_logger.warning.assert_called_once()
            assert "Unknown provider 'unknown'" in mock_logger.warning.call_args[0][0]

    def test_get_sensitive_fields_fallback_on_error(self) -> None:
        """Test that fallback values are used when registry fails"""
        # Import storage modules to trigger registration (if not already done)

        # Mock get_storage_class to return None (simulating unknown provider)
        with patch(
            "borgitory.services.cloud_sync_service.get_storage_class", return_value=None
        ):
            with patch("borgitory.services.cloud_sync_service.logger") as mock_logger:
                fields = _get_sensitive_fields_for_provider("unknown_provider")

                # Should return empty list and log warning
                assert fields == []
                mock_logger.warning.assert_called_once()
                assert (
                    "Unknown provider 'unknown_provider'"
                    in mock_logger.warning.call_args[0][0]
                )


class TestAPIProviderIntegration:
    """Test API layer integration with registry"""

    def test_api_get_supported_providers_format(self) -> None:
        """Test that API returns providers in correct format"""
        # Import storage modules to trigger registration
        from borgitory.services.cloud_providers.registry import get_registry

        registry = get_registry()
        providers = _get_supported_providers(registry)

        # Should be a list of dicts with correct structure
        assert isinstance(providers, list)
        assert len(providers) == 3

        # Check structure of first provider (s3, since it's sorted)
        s3_provider = providers[0]
        assert s3_provider["value"] == "s3"
        assert s3_provider["label"] == "AWS S3"
        assert s3_provider["description"] == "Amazon S3 compatible storage"

        # Check that all providers have required fields
        for provider in providers:
            assert "value" in provider
            assert "label" in provider
            assert "description" in provider
            assert isinstance(provider["value"], str)
            assert isinstance(provider["label"], str)
            assert isinstance(provider["description"], str)

    def test_api_providers_are_sorted(self) -> None:
        """Test that API returns providers in sorted order"""
        # Import storage modules to trigger registration
        from borgitory.services.cloud_providers.registry import get_registry

        registry = get_registry()
        providers = _get_supported_providers(registry)

        values = [p["value"] for p in providers]
        assert values == sorted(values)  # Should be sorted
        assert values == ["s3", "sftp", "smb"]


class TestServiceLayerIntegration:
    """Test service layer integration with registry"""

    def test_config_validator_uses_registry(self) -> None:
        """Test that ConfigValidator uses registry for validation"""
        # Import storage modules to trigger registration (if not already done)
        from borgitory.services.cloud_providers.service import ConfigValidator

        validator = ConfigValidator()

        # Test valid provider with complete config
        config = validator.validate_config(
            "s3",
            {
                "bucket_name": "test-bucket",
                "access_key": "AKIAIOSFODNN7EXAMPLE",
                "secret_key": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
                "region": "us-east-1",
            },
        )
        assert config.bucket_name == "test-bucket"
        assert config.access_key == "AKIAIOSFODNN7EXAMPLE"

        # Test invalid provider
        with pytest.raises(ValueError) as exc_info:
            validator.validate_config("unknown", {})

        error_msg = str(exc_info.value)
        assert "Unknown provider: unknown" in error_msg
        assert "Supported providers:" in error_msg

    def test_storage_factory_uses_registry(self) -> None:
        """Test that StorageFactory uses registry for creation"""
        # Import storage modules to trigger registration (if not already done)
        from borgitory.services.cloud_providers.service import StorageFactory

        mock_rclone = Mock()
        factory = StorageFactory(mock_rclone)

        # Test valid provider with complete config
        storage_instance = factory.create_storage(
            "s3",
            {
                "bucket_name": "test-bucket",
                "access_key": "AKIAIOSFODNN7EXAMPLE",
                "secret_key": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
                "region": "us-east-1",
            },
        )
        assert storage_instance.__class__.__name__ == "S3Storage"

        # Test invalid provider
        with pytest.raises(ValueError) as exc_info:
            factory.create_storage("unknown", {})

        error_msg = str(exc_info.value)
        assert "Unknown provider: unknown" in error_msg
        assert "Supported providers:" in error_msg

    def test_storage_factory_get_supported_providers(self) -> None:
        """Test that StorageFactory returns supported providers from registry"""
        # Import storage modules to trigger registration (if not already done)
        from borgitory.services.cloud_providers.service import StorageFactory

        mock_rclone = Mock()
        factory = StorageFactory(mock_rclone)

        providers = factory.get_supported_providers()
        # Should include our three providers, possibly more
        assert "s3" in providers
        assert "sftp" in providers
        assert "smb" in providers


class TestCloudSyncConfigServiceIntegration:
    """Test CloudSyncConfigService integration with registry"""

    def test_cloud_sync_service_validates_providers_using_registry(self) -> None:
        """Test that CloudSyncConfigService validates providers using registry"""
        # Import storage modules to trigger registration (if not already done)
        from borgitory.services.cloud_sync_service import CloudSyncConfigService
        from fastapi import HTTPException

        mock_db = Mock()
        mock_db.query().filter().first.return_value = None  # No existing config

        # Get the registry for the service
        from borgitory.services.cloud_providers.registry import get_metadata
        from borgitory.services.rclone_service import RcloneService
        from borgitory.services.cloud_providers import StorageFactory, EncryptionService

        mock_rclone = Mock(spec=RcloneService)
        mock_storage_factory = Mock(spec=StorageFactory)
        mock_encryption = Mock(spec=EncryptionService)

        service = CloudSyncConfigService(
            db=mock_db,
            rclone_service=mock_rclone,
            storage_factory=mock_storage_factory,
            encryption_service=mock_encryption,
            get_metadata_func=get_metadata,
        )

        # Create a mock config object that bypasses pydantic validation
        mock_config = Mock()
        mock_config.name = "test-config"
        mock_config.provider = "unknown"  # Invalid provider (now a simple string)
        mock_config.provider_config = {}

        # Test with invalid provider - should use registry validation
        with pytest.raises(HTTPException) as exc_info:
            service.create_cloud_sync_config(mock_config)

        assert exc_info.value.status_code == 400
        detail = str(exc_info.value.detail)
        assert "Unsupported provider:" in detail
        assert "unknown" in detail
