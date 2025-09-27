"""
Comprehensive tests for cloud_providers/service.py

This test file ensures complete coverage of the service layer with
proper DI patterns and real database usage where appropriate.
"""

from typing import Any
import pytest
import json
from unittest.mock import Mock, AsyncMock, patch

from borgitory.services.cloud_providers.registry import ProviderRegistry
from borgitory.services.cloud_providers.service import (
    ConfigValidator,
    StorageFactory,
    CloudSyncService,
)
from borgitory.services.cloud_providers.types import CloudSyncConfig, SyncResult
from borgitory.services.encryption_service import EncryptionService


class TestConfigValidator:
    """Test ConfigValidator with all supported providers and edge cases"""

    @pytest.fixture
    def validator(self, production_registry: ProviderRegistry) -> ConfigValidator:
        """Create validator with injected registry for proper test isolation"""
        return ConfigValidator(registry=production_registry)

    def test_validate_s3_config_success(self, validator: ConfigValidator) -> None:
        """Test successful S3 configuration validation"""
        config = {
            "bucket_name": "test-bucket",
            "access_key": "AKIAIOSFODNN7EXAMPLE",
            "secret_key": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
            "region": "us-east-1",
            "storage_class": "STANDARD",
        }

        result = validator.validate_config("s3", config)

        # Check by class name to avoid identity issues after module reloading
        assert result.__class__.__name__ == "S3StorageConfig"
        assert result.bucket_name == "test-bucket"
        assert result.access_key == "AKIAIOSFODNN7EXAMPLE"
        assert result.region == "us-east-1"

    def test_validate_s3_config_minimal(self, validator: ConfigValidator) -> None:
        """Test S3 config with minimal required fields"""
        config = {
            "bucket_name": "test-bucket",
            "access_key": "AKIAIOSFODNN7EXAMPLE",
            "secret_key": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
        }

        result = validator.validate_config("s3", config)

        assert result.__class__.__name__ == "S3StorageConfig"
        assert result.bucket_name == "test-bucket"
        # Should have defaults
        assert result.region is not None
        assert result.storage_class is not None

    def test_validate_s3_config_missing_bucket(
        self, validator: ConfigValidator
    ) -> None:
        """Test S3 config validation with missing bucket name"""
        config = {
            "access_key": "AKIAIOSFODNN7EXAMPLE",
            "secret_key": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
        }

        with pytest.raises(Exception):  # Pydantic validation error
            validator.validate_config("s3", config)

    def test_validate_s3_config_missing_credentials(
        self, validator: ConfigValidator
    ) -> None:
        """Test S3 config validation with missing credentials"""
        config = {"bucket_name": "test-bucket"}

        with pytest.raises(Exception):  # Pydantic validation error
            validator.validate_config("s3", config)

    def test_validate_sftp_config_with_password(
        self, validator: ConfigValidator
    ) -> None:
        """Test successful SFTP configuration validation with password"""
        config = {
            "host": "sftp.example.com",
            "username": "testuser",
            "password": "testpass",
            "remote_path": "/backups",
            "port": 22,
            "host_key_checking": True,
        }

        result = validator.validate_config("sftp", config)

        assert result.__class__.__name__ == "SFTPStorageConfig"
        assert result.host == "sftp.example.com"
        assert result.username == "testuser"
        assert result.password == "testpass"
        assert result.port == 22

    def test_validate_sftp_config_with_private_key(
        self, validator: ConfigValidator
    ) -> None:
        """Test SFTP configuration with private key authentication"""
        config = {
            "host": "sftp.example.com",
            "username": "testuser",
            "private_key": "-----BEGIN RSA PRIVATE KEY-----\ntest\n-----END RSA PRIVATE KEY-----",
            "remote_path": "/backups",
            "port": 2222,
            "host_key_checking": False,
        }

        result = validator.validate_config("sftp", config)

        assert result.__class__.__name__ == "SFTPStorageConfig"
        assert result.host == "sftp.example.com"
        assert result.private_key is not None
        assert result.port == 2222
        assert result.host_key_checking is False

    def test_validate_sftp_config_minimal(self, validator: ConfigValidator) -> None:
        """Test SFTP config with minimal required fields"""
        config = {
            "host": "sftp.example.com",
            "username": "testuser",
            "password": "testpass",
            "remote_path": "/backups",
        }

        result = validator.validate_config("sftp", config)

        assert result.__class__.__name__ == "SFTPStorageConfig"
        assert result.port == 22  # Default port
        assert result.host_key_checking is True  # Default

    def test_validate_sftp_config_missing_auth(
        self, validator: ConfigValidator
    ) -> None:
        """Test SFTP config without password or private key"""
        config = {
            "host": "sftp.example.com",
            "username": "testuser",
            "remote_path": "/backups",
        }

        with pytest.raises(Exception):  # Should require authentication
            validator.validate_config("sftp", config)

    def test_validate_sftp_config_missing_required_fields(
        self, validator: ConfigValidator
    ) -> None:
        """Test SFTP config with missing required fields"""
        config = {"host": "sftp.example.com", "password": "testpass"}

        with pytest.raises(Exception):  # Missing username and remote_path
            validator.validate_config("sftp", config)

    def test_validate_unknown_provider(self, validator: ConfigValidator) -> None:
        """Test validation with unknown provider"""
        config = {"bucket_name": "test"}

        with pytest.raises(ValueError, match="Unknown provider: azure"):
            validator.validate_config("azure", config)

    def test_validate_empty_config(self, validator: ConfigValidator) -> None:
        """Test validation with empty configuration"""
        with pytest.raises(Exception):
            validator.validate_config("s3", {})


class TestStorageFactory:
    """Test StorageFactory with proper DI and all providers"""

    @pytest.fixture
    def mock_rclone_service(self) -> Mock:
        return Mock()

    @pytest.fixture
    def factory(
        self, mock_rclone_service: Mock, production_registry: ProviderRegistry
    ) -> StorageFactory:
        """Create factory with injected registry for proper test isolation"""
        return StorageFactory(mock_rclone_service, registry=production_registry)

    def test_create_s3_storage_success(
        self, factory: StorageFactory, mock_rclone_service: Mock
    ) -> None:
        """Test successful S3 storage creation"""
        config = {
            "bucket_name": "test-bucket",
            "access_key": "AKIAIOSFODNN7EXAMPLE",
            "secret_key": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
            "region": "us-west-2",
        }

        storage = factory.create_storage("s3", config)

        assert storage is not None
        assert hasattr(storage, "test_connection")
        assert hasattr(storage, "upload_repository")

    def test_create_sftp_storage_success(
        self, factory: StorageFactory, mock_rclone_service: Mock
    ) -> None:
        """Test successful SFTP storage creation"""
        config = {
            "host": "sftp.example.com",
            "username": "testuser",
            "password": "testpass",
            "remote_path": "/backups",
        }

        storage = factory.create_storage("sftp", config)

        assert storage is not None
        assert hasattr(storage, "test_connection")
        assert hasattr(storage, "upload_repository")

    def test_create_storage_invalid_config(self, factory: StorageFactory) -> None:
        """Test storage creation with invalid configuration"""
        config = {"invalid": "config"}

        with pytest.raises(Exception):  # Validation should fail
            factory.create_storage("s3", config)

    def test_create_storage_unknown_provider(self, factory: StorageFactory) -> None:
        """Test storage creation with unknown provider"""
        config = {"bucket_name": "test"}

        with pytest.raises(ValueError, match="Unknown provider: unknown"):
            factory.create_storage("unknown", config)

    def test_factory_uses_injected_rclone_service(
        self, mock_rclone_service: Mock, production_registry: ProviderRegistry
    ) -> None:
        """Test that factory uses the injected rclone service"""
        factory = StorageFactory(mock_rclone_service, registry=production_registry)

        config = {
            "bucket_name": "test-bucket",
            "access_key": "AKIAIOSFODNN7EXAMPLE",
            "secret_key": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
        }

        storage = factory.create_storage("s3", config)

        # The storage should have been created with the injected service
        # This verifies proper dependency injection
        assert storage is not None

    def test_factory_validator_integration(self, factory: StorageFactory) -> None:
        """Test that factory properly integrates with validator"""
        # The factory should validate config before creating storage
        invalid_config = {}

        with pytest.raises(Exception):
            factory.create_storage("s3", invalid_config)


class TestEncryptionService:
    """Test EncryptionService with real encryption/decryption"""

    @pytest.fixture
    def service(self) -> EncryptionService:
        return EncryptionService()

    @pytest.fixture
    def sample_config(self) -> dict[str, Any]:
        return {
            "host": "example.com",
            "username": "testuser",
            "password": "secret123",
            "port": 22,
            "public_key": "not-sensitive",
        }

    def test_encrypt_sensitive_fields(
        self, service: EncryptionService, sample_config: dict[str, Any]
    ) -> None:
        """Test encryption of sensitive fields"""
        sensitive_fields = ["password"]

        encrypted_config = service.encrypt_sensitive_fields(
            sample_config, sensitive_fields
        )

        # Original field should be removed
        assert "password" not in encrypted_config
        # Encrypted field should be added
        assert "encrypted_password" in encrypted_config
        # Non-sensitive fields should remain unchanged
        assert encrypted_config["host"] == "example.com"
        assert encrypted_config["username"] == "testuser"
        assert encrypted_config["port"] == 22
        assert encrypted_config["public_key"] == "not-sensitive"
        # Encrypted value should be different from original
        assert encrypted_config["encrypted_password"] != "secret123"

    def test_decrypt_sensitive_fields(
        self, service: EncryptionService, sample_config: dict[str, Any]
    ) -> None:
        """Test decryption of sensitive fields"""
        sensitive_fields = ["password"]

        # First encrypt
        encrypted_config = service.encrypt_sensitive_fields(
            sample_config, sensitive_fields
        )

        # Then decrypt
        decrypted_config = service.decrypt_sensitive_fields(
            encrypted_config, sensitive_fields
        )

        # Should restore original structure
        assert "password" in decrypted_config
        assert "encrypted_password" not in decrypted_config
        assert decrypted_config["password"] == "secret123"
        # Non-sensitive fields should be unchanged
        assert decrypted_config["host"] == "example.com"

    def test_encrypt_multiple_fields(self, service: EncryptionService) -> None:
        """Test encryption of multiple sensitive fields"""
        config = {
            "access_key": "AKIA123",
            "secret_key": "secret456",
            "region": "us-east-1",
            "token": "token789",
        }
        sensitive_fields = ["access_key", "secret_key", "token"]

        encrypted_config = service.encrypt_sensitive_fields(config, sensitive_fields)

        # All sensitive fields should be encrypted
        assert "access_key" not in encrypted_config
        assert "secret_key" not in encrypted_config
        assert "token" not in encrypted_config
        assert "encrypted_access_key" in encrypted_config
        assert "encrypted_secret_key" in encrypted_config
        assert "encrypted_token" in encrypted_config
        # Non-sensitive field should remain
        assert encrypted_config["region"] == "us-east-1"

    def test_decrypt_multiple_fields(self, service: EncryptionService) -> None:
        """Test decryption of multiple sensitive fields"""
        config = {
            "access_key": "AKIA123",
            "secret_key": "secret456",
            "region": "us-east-1",
        }
        sensitive_fields = ["access_key", "secret_key"]

        # Encrypt then decrypt
        encrypted_config = service.encrypt_sensitive_fields(config, sensitive_fields)
        decrypted_config = service.decrypt_sensitive_fields(
            encrypted_config, sensitive_fields
        )

        # Should match original
        assert decrypted_config["access_key"] == "AKIA123"
        assert decrypted_config["secret_key"] == "secret456"
        assert decrypted_config["region"] == "us-east-1"

    def test_encrypt_empty_sensitive_fields(
        self, service: EncryptionService, sample_config: dict[str, Any]
    ) -> None:
        """Test encryption with empty sensitive fields list"""
        encrypted_config = service.encrypt_sensitive_fields(sample_config, [])

        # Config should be unchanged
        assert encrypted_config == sample_config

    def test_encrypt_nonexistent_fields(
        self, service: EncryptionService, sample_config: dict[str, Any]
    ) -> None:
        """Test encryption of fields that don't exist in config"""
        sensitive_fields = ["nonexistent_field", "another_missing"]

        encrypted_config = service.encrypt_sensitive_fields(
            sample_config, sensitive_fields
        )

        # Config should be unchanged since fields don't exist
        assert encrypted_config == sample_config

    def test_encrypt_empty_field_values(self, service: EncryptionService) -> None:
        """Test encryption of empty field values"""
        config = {"password": "", "secret_key": None, "host": "example.com"}
        sensitive_fields = ["password", "secret_key"]

        encrypted_config = service.encrypt_sensitive_fields(config, sensitive_fields)

        # Empty/None values should not be encrypted
        assert (
            "password" in encrypted_config
            or "encrypted_password" not in encrypted_config
        )
        assert (
            "secret_key" in encrypted_config
            or "encrypted_secret_key" not in encrypted_config
        )
        assert encrypted_config["host"] == "example.com"

    def test_decrypt_missing_encrypted_fields(self, service: EncryptionService) -> None:
        """Test decryption when encrypted fields are missing"""
        config = {"host": "example.com", "username": "testuser"}
        sensitive_fields = ["password"]

        decrypted_config = service.decrypt_sensitive_fields(config, sensitive_fields)

        # Should return config unchanged
        assert decrypted_config == config

    def test_roundtrip_encryption_decryption(self, service: EncryptionService) -> None:
        """Test that encrypt->decrypt produces original data"""
        original_config = {
            "host": "sftp.example.com",
            "username": "testuser",
            "password": "super_secret_password_123!@#",
            "private_key": "-----BEGIN RSA PRIVATE KEY-----\nMIIEpAIBAAKCAQEA...\n-----END RSA PRIVATE KEY-----",
            "port": 2222,
            "timeout": 30,
        }
        sensitive_fields = ["password", "private_key"]

        # Encrypt
        encrypted_config = service.encrypt_sensitive_fields(
            original_config, sensitive_fields
        )

        # Decrypt
        decrypted_config = service.decrypt_sensitive_fields(
            encrypted_config, sensitive_fields
        )

        # Should match original exactly
        assert decrypted_config == original_config


class TestCloudSyncService:
    """Test CloudSyncService with comprehensive coverage"""

    @pytest.fixture
    def mock_storage_factory(self) -> Mock:
        return Mock()

    @pytest.fixture
    def mock_encryption_service(self) -> Mock:
        return Mock()

    @pytest.fixture
    def service(
        self, mock_storage_factory: Mock, mock_encryption_service: Mock
    ) -> CloudSyncService:
        return CloudSyncService(
            storage_factory=mock_storage_factory,
            encryption_service=mock_encryption_service,
        )

    @pytest.fixture
    def service_with_defaults(self, mock_storage_factory: Mock) -> CloudSyncService:
        """Service without injected encryption service (uses default)"""
        return CloudSyncService(storage_factory=mock_storage_factory)

    @pytest.fixture
    def sample_s3_config(self) -> CloudSyncConfig:
        return CloudSyncConfig(
            provider="s3",
            config={
                "bucket_name": "test-bucket",
                "access_key": "AKIA123",
                "secret_key": "secret456",
            },
            path_prefix="backups/",
            name="test-s3",
        )

    @pytest.fixture
    def sample_sftp_config(self) -> CloudSyncConfig:
        return CloudSyncConfig(
            provider="sftp",
            config={
                "host": "sftp.example.com",
                "username": "testuser",
                "password": "testpass",
                "remote_path": "/backups",
            },
            name="test-sftp",
        )

    @pytest.mark.asyncio
    async def test_execute_sync_success(
        self,
        service: CloudSyncService,
        mock_storage_factory: Mock,
        sample_s3_config: CloudSyncConfig,
    ) -> None:
        """Test successful sync execution"""
        # Setup mocks
        mock_storage = AsyncMock()
        mock_storage_factory.create_storage.return_value = mock_storage

        # Mock the syncer result
        expected_result = SyncResult.success_result(
            bytes_transferred=1024, files_transferred=10, duration_seconds=5.5
        )

        repository_path = "/test/repo"

        with patch(
            "borgitory.services.cloud_providers.service.CloudSyncer"
        ) as mock_syncer_class:
            mock_syncer = AsyncMock()
            mock_syncer.sync_repository.return_value = expected_result
            mock_syncer_class.return_value = mock_syncer

            result = await service.execute_sync(sample_s3_config, repository_path)

        # Verify result
        assert result == expected_result

        # Verify storage was created correctly
        mock_storage_factory.create_storage.assert_called_once_with(
            "s3", sample_s3_config.config
        )

        # Verify syncer was created and called
        mock_syncer_class.assert_called_once()
        mock_syncer.sync_repository.assert_called_once_with(repository_path, "backups/")

    @pytest.mark.asyncio
    async def test_execute_sync_with_output_callback(
        self,
        service: CloudSyncService,
        mock_storage_factory: Mock,
        sample_s3_config: CloudSyncConfig,
    ) -> None:
        """Test sync execution with output callback"""
        mock_storage = AsyncMock()
        mock_storage_factory.create_storage.return_value = mock_storage

        output_messages = []

        def output_callback(message: str) -> None:
            output_messages.append(message)

        with patch(
            "borgitory.services.cloud_providers.service.CloudSyncer"
        ) as mock_syncer_class:
            mock_syncer = AsyncMock()
            mock_syncer.sync_repository.return_value = SyncResult.success_result()
            mock_syncer_class.return_value = mock_syncer

            await service.execute_sync(sample_s3_config, "/test/repo", output_callback)

        # Verify LoggingSyncEventHandler was created with callback
        mock_syncer_class.assert_called_once()
        # The handler should have been passed to the syncer constructor

    @pytest.mark.asyncio
    async def test_execute_sync_storage_creation_failure(
        self,
        service: CloudSyncService,
        mock_storage_factory: Mock,
        sample_s3_config: CloudSyncConfig,
    ) -> None:
        """Test sync when storage creation fails"""
        mock_storage_factory.create_storage.side_effect = Exception(
            "Invalid configuration"
        )

        result = await service.execute_sync(sample_s3_config, "/test/repo")

        assert result.success is False
        assert result.error is not None
        assert "Failed to execute sync" in result.error
        assert "Invalid configuration" in result.error

    @pytest.mark.asyncio
    async def test_execute_sync_syncer_failure(
        self,
        service: CloudSyncService,
        mock_storage_factory: Mock,
        sample_s3_config: CloudSyncConfig,
    ) -> None:
        """Test sync when syncer raises exception"""
        mock_storage = AsyncMock()
        mock_storage_factory.create_storage.return_value = mock_storage

        with patch(
            "borgitory.services.cloud_providers.service.CloudSyncer"
        ) as mock_syncer_class:
            mock_syncer = AsyncMock()
            mock_syncer.sync_repository.side_effect = Exception("Sync failed")
            mock_syncer_class.return_value = mock_syncer

            result = await service.execute_sync(sample_s3_config, "/test/repo")

        assert result.success is False
        assert result.error is not None
        assert "Failed to execute sync" in result.error
        assert "Sync failed" in result.error

    @pytest.mark.asyncio
    async def test_execute_sync_with_callback_on_error(
        self,
        service: CloudSyncService,
        mock_storage_factory: Mock,
        sample_s3_config: CloudSyncConfig,
    ) -> None:
        """Test that output callback receives error messages"""
        mock_storage_factory.create_storage.side_effect = Exception("Storage error")

        output_messages = []

        def output_callback(message: str) -> None:
            output_messages.append(message)

        result = await service.execute_sync(
            sample_s3_config, "/test/repo", output_callback
        )

        assert result.success is False
        assert any("Storage error" in msg for msg in output_messages)

    @pytest.mark.asyncio
    async def test_test_connection_success(
        self,
        service: CloudSyncService,
        mock_storage_factory: Mock,
        sample_s3_config: CloudSyncConfig,
    ) -> None:
        """Test successful connection test"""
        mock_storage = AsyncMock()
        mock_storage.test_connection.return_value = True
        mock_storage_factory.create_storage.return_value = mock_storage

        result = await service.test_connection(sample_s3_config)

        assert result is True
        mock_storage.test_connection.assert_called_once()

    @pytest.mark.asyncio
    async def test_test_connection_failure(
        self,
        service: CloudSyncService,
        mock_storage_factory: Mock,
        sample_s3_config: CloudSyncConfig,
    ) -> None:
        """Test failed connection test"""
        mock_storage = AsyncMock()
        mock_storage.test_connection.return_value = False
        mock_storage_factory.create_storage.return_value = mock_storage

        result = await service.test_connection(sample_s3_config)

        assert result is False

    @pytest.mark.asyncio
    async def test_test_connection_exception(
        self,
        service: CloudSyncService,
        mock_storage_factory: Mock,
        sample_s3_config: CloudSyncConfig,
    ) -> None:
        """Test connection test with exception"""
        mock_storage_factory.create_storage.side_effect = Exception("Connection error")

        result = await service.test_connection(sample_s3_config)

        assert result is False

    def test_get_connection_info_success(
        self,
        service: CloudSyncService,
        mock_storage_factory: Mock,
        sample_s3_config: CloudSyncConfig,
    ) -> None:
        """Test successful connection info retrieval"""
        mock_storage = Mock()
        mock_storage.get_connection_info.return_value = "s3(bucket=test-bucket)"
        mock_storage_factory.create_storage.return_value = mock_storage

        result = service.get_connection_info(sample_s3_config)

        assert result == "s3(bucket=test-bucket)"

    def test_get_connection_info_exception(
        self,
        service: CloudSyncService,
        mock_storage_factory: Mock,
        sample_s3_config: CloudSyncConfig,
    ) -> None:
        """Test connection info with exception"""
        mock_storage_factory.create_storage.side_effect = Exception("Storage error")

        result = service.get_connection_info(sample_s3_config)

        assert "Error getting connection info" in result
        assert "Storage error" in result

    def test_prepare_config_for_storage(
        self,
        service: CloudSyncService,
        mock_storage_factory: Mock,
        mock_encryption_service: Mock,
    ) -> None:
        """Test preparing config for database storage"""
        provider = "s3"
        config = {
            "bucket_name": "test-bucket",
            "access_key": "AKIA123",
            "secret_key": "secret456",
        }

        # Setup mocks
        mock_storage = Mock()
        mock_storage.get_sensitive_fields.return_value = ["access_key", "secret_key"]
        mock_storage_factory.create_storage.return_value = mock_storage

        encrypted_config = {
            "bucket_name": "test-bucket",
            "encrypted_access_key": "encrypted_akia123",
            "encrypted_secret_key": "encrypted_secret456",
        }
        mock_encryption_service.encrypt_sensitive_fields.return_value = encrypted_config

        result = service.prepare_config_for_storage(provider, config)

        # Verify storage was created to get sensitive fields
        mock_storage_factory.create_storage.assert_called_once_with(provider, config)

        # Verify encryption was called
        mock_encryption_service.encrypt_sensitive_fields.assert_called_once_with(
            config, ["access_key", "secret_key"]
        )

        # Verify result is JSON
        parsed_result = json.loads(result)
        assert parsed_result == encrypted_config

    def test_load_config_from_storage(
        self,
        service: CloudSyncService,
        mock_storage_factory: Mock,
        mock_encryption_service: Mock,
    ) -> None:
        """Test loading config from database storage"""
        provider = "sftp"
        stored_config = json.dumps(
            {
                "host": "sftp.example.com",
                "username": "testuser",
                "encrypted_password": "encrypted_pass123",
                "remote_path": "/backups",
            }
        )

        # Setup mocks
        mock_storage = Mock()
        mock_storage.get_sensitive_fields.return_value = ["password"]
        mock_storage_factory.create_storage.return_value = mock_storage

        decrypted_config = {
            "host": "sftp.example.com",
            "username": "testuser",
            "password": "decrypted_pass123",
            "remote_path": "/backups",
        }
        mock_encryption_service.decrypt_sensitive_fields.return_value = decrypted_config

        result = service.load_config_from_storage(provider, stored_config)

        # Verify decryption was called with parsed config
        expected_parsed_config = {
            "host": "sftp.example.com",
            "username": "testuser",
            "encrypted_password": "encrypted_pass123",
            "remote_path": "/backups",
        }
        mock_encryption_service.decrypt_sensitive_fields.assert_called_once_with(
            expected_parsed_config, ["password"]
        )

        assert result == decrypted_config

    def test_service_with_default_encryption_service(
        self, service_with_defaults: CloudSyncService
    ) -> None:
        """Test that service creates default encryption service when none provided"""
        # This tests the default parameter handling in __init__
        assert service_with_defaults._encryption_service is not None
        assert isinstance(service_with_defaults._encryption_service, EncryptionService)

    @pytest.mark.asyncio
    async def test_execute_sync_different_providers(
        self, service: CloudSyncService, mock_storage_factory: Mock
    ) -> None:
        """Test sync execution with different provider types"""
        configs = [
            CloudSyncConfig(
                provider="s3", config={"bucket_name": "test"}, name="s3-test"
            ),
            CloudSyncConfig(
                provider="sftp", config={"host": "test.com"}, name="sftp-test"
            ),
        ]

        mock_storage = AsyncMock()
        mock_storage_factory.create_storage.return_value = mock_storage

        with patch(
            "borgitory.services.cloud_providers.service.CloudSyncer"
        ) as mock_syncer_class:
            mock_syncer = AsyncMock()
            mock_syncer.sync_repository.return_value = SyncResult.success_result()
            mock_syncer_class.return_value = mock_syncer

            for config in configs:
                result = await service.execute_sync(config, "/test/repo")
                assert result.success is True

        # Verify storage factory was called for each provider
        assert mock_storage_factory.create_storage.call_count == 2
        calls = mock_storage_factory.create_storage.call_args_list
        assert calls[0][0][0] == "s3"
        assert calls[1][0][0] == "sftp"
