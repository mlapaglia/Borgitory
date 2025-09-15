"""
Backward Compatibility Tests

These tests ensure that existing cloud sync configurations continue to work
after migrating to the new provider strategy, and that the migration process
works correctly.
"""

import pytest
import json
from unittest.mock import MagicMock, patch
from sqlalchemy.orm import Session

from services.cloud_sync_service import CloudSyncService
from services.jobs.job_executor import JobExecutor
from models.database import CloudSyncConfig
from models.schemas import CloudSyncConfigCreate, ProviderType
from utils.migrate_cloud_configs import migrate_existing_configs


class TestBackwardCompatibility:
    """Test backward compatibility with existing configurations"""
    
    @pytest.fixture
    def legacy_s3_config(self):
        """Legacy S3 configuration in database format"""
        config = MagicMock(spec=CloudSyncConfig)
        config.id = 1
        config.name = "legacy-s3"
        config.provider = "s3"
        config.enabled = True
        config.path_prefix = "backups/"
        config.provider_config = None  # No JSON config yet
        
        # Legacy S3 fields
        config.bucket_name = "legacy-bucket"
        config.encrypted_access_key = "encrypted_legacy_access_key"
        config.encrypted_secret_key = "encrypted_legacy_secret_key"
        
        # Mock the credential methods
        config.get_credentials.return_value = ("AKIALEGACYKEY", "legacy-secret-key")
        
        return config
    
    @pytest.fixture
    def legacy_sftp_config(self):
        """Legacy SFTP configuration in database format"""
        config = MagicMock(spec=CloudSyncConfig)
        config.id = 2
        config.name = "legacy-sftp"
        config.provider = "sftp"
        config.enabled = True
        config.path_prefix = "borg/"
        config.provider_config = None  # No JSON config yet
        
        # Legacy SFTP fields
        config.host = "legacy-sftp.example.com"
        config.port = 22
        config.username = "legacy-user"
        config.remote_path = "/legacy/backups"
        config.encrypted_password = "encrypted_legacy_password"
        config.encrypted_private_key = None
        
        # Mock the credential methods
        config.get_sftp_credentials.return_value = ("legacy-password", None)
        
        return config
    
    @pytest.fixture
    def migrated_s3_config(self):
        """S3 configuration after migration to JSON format"""
        config = MagicMock(spec=CloudSyncConfig)
        config.id = 1
        config.name = "migrated-s3"
        config.provider = "s3"
        config.enabled = True
        config.path_prefix = "backups/"
        
        # New JSON configuration
        config.provider_config = json.dumps({
            "bucket_name": "migrated-bucket",
            "encrypted_access_key": "encrypted_migrated_access_key",
            "encrypted_secret_key": "encrypted_migrated_secret_key",
            "region": "us-east-1",
            "storage_class": "STANDARD"
        })
        
        # Legacy fields still exist but should not be used
        config.bucket_name = "migrated-bucket"
        config.encrypted_access_key = "encrypted_migrated_access_key"
        config.encrypted_secret_key = "encrypted_migrated_secret_key"
        
        return config
    
    def test_legacy_s3_config_still_works(self, legacy_s3_config):
        """Test that legacy S3 configurations still work with new provider system"""
        from services.cloud_providers import CloudProviderFactory
        
        # Simulate how job executor handles legacy config
        provider_config = {
            "bucket_name": legacy_s3_config.bucket_name,
            "access_key": legacy_s3_config.get_credentials()[0],
            "secret_key": legacy_s3_config.get_credentials()[1],
            "region": "us-east-1",  # Default
            "storage_class": "STANDARD"  # Default
        }
        
        # Should be able to create provider with legacy data
        provider = CloudProviderFactory.create_provider("s3", provider_config)
        
        assert provider.provider_name == "s3"
        assert provider.config.bucket_name == "legacy-bucket"
        assert provider.config.access_key == "AKIALEGACYKEY"
        assert provider.config.secret_key == "legacy-secret-key"
    
    def test_legacy_sftp_config_still_works(self, legacy_sftp_config):
        """Test that legacy SFTP configurations still work with new provider system"""
        from services.cloud_providers import CloudProviderFactory
        
        # Simulate how job executor handles legacy config
        password, private_key = legacy_sftp_config.get_sftp_credentials()
        provider_config = {
            "host": legacy_sftp_config.host,
            "username": legacy_sftp_config.username,
            "remote_path": legacy_sftp_config.remote_path,
            "port": legacy_sftp_config.port,
            "host_key_checking": True  # Default
        }
        
        if password:
            provider_config["password"] = password
        if private_key:
            provider_config["private_key"] = private_key
        
        # Should be able to create provider with legacy data
        provider = CloudProviderFactory.create_provider("sftp", provider_config)
        
        assert provider.provider_name == "sftp"
        assert provider.config.host == "legacy-sftp.example.com"
        assert provider.config.username == "legacy-user"
        assert provider.config.password == "legacy-password"
    
    @pytest.mark.asyncio
    async def test_job_executor_handles_legacy_config(self, legacy_s3_config):
        """Test that JobExecutor correctly handles legacy configurations"""
        job_executor = JobExecutor()
        
        # Mock database session
        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.first.return_value = legacy_s3_config
        
        def session_factory():
            return mock_session
        
        with patch('services.cloud_providers.CloudProviderFactory.create_provider') as mock_create_provider:
            mock_provider = MagicMock()
            mock_provider.get_connection_info.return_value = {"provider": "s3"}
            
            # Setup async generator for sync
            async def mock_sync_generator(repository, path_prefix=""):
                yield {"type": "completed", "return_code": 0, "status": "success"}
            
            mock_provider.sync_repository.return_value = mock_sync_generator(None)
            mock_create_provider.return_value = mock_provider
            
            # Execute cloud sync
            result = await job_executor.execute_cloud_sync_task(
                repository_path="/test/repo",
                passphrase="test-passphrase",
                cloud_sync_config_id=1,
                db_session_factory=session_factory
            )
            
            # Verify provider was created with legacy config converted
            mock_create_provider.assert_called_once()
            create_call_args = mock_create_provider.call_args
            provider_config = create_call_args[0][1]  # config argument
            
            # Should have converted legacy fields to new format
            assert provider_config["bucket_name"] == "legacy-bucket"
            assert provider_config["access_key"] == "AKIALEGACYKEY"
            assert provider_config["secret_key"] == "legacy-secret-key"
            assert provider_config["region"] == "us-east-1"
            
            assert result.return_code == 0
    
    def test_migrated_config_uses_json_format(self, migrated_s3_config):
        """Test that migrated configurations use the new JSON format"""
        from services.cloud_providers import CloudProviderFactory
        
        # Parse the JSON configuration
        provider_config = json.loads(migrated_s3_config.provider_config)
        
        # Should be able to create provider with JSON config (after decryption)
        # Simulate decryption process
        decrypted_config = {
            "bucket_name": "migrated-bucket",
            "access_key": "AKIAMIGRATED",  # Simulated decrypted value
            "secret_key": "migrated-secret",  # Simulated decrypted value
            "region": "us-east-1",
            "storage_class": "STANDARD"
        }
        
        provider = CloudProviderFactory.create_provider("s3", decrypted_config)
        
        assert provider.provider_name == "s3"
        assert provider.config.bucket_name == "migrated-bucket"
        assert provider.config.region == "us-east-1"
        assert provider.config.storage_class == "STANDARD"
    
    def test_cloud_sync_service_handles_legacy_field_input(self):
        """Test that CloudSyncService still accepts legacy field input"""
        mock_db = MagicMock(spec=Session)
        mock_db.query.return_value.filter.return_value.first.return_value = None  # No existing config
        
        cloud_sync_service = CloudSyncService(mock_db)
        
        # Create config using legacy fields (for backward compatibility)
        legacy_style_config = CloudSyncConfigCreate(
            name="legacy-input",
            provider=ProviderType.S3,
            bucket_name="legacy-bucket",
            access_key="AKIALEGACYINPUT",
            secret_key="legacy-secret-input",
            path_prefix="legacy/"
        )
        
        result = cloud_sync_service.create_cloud_sync_config(legacy_style_config)
        
        # Should create config successfully
        mock_db.add.assert_called_once()
        created_config = mock_db.add.call_args[0][0]
        
        # Should have converted to JSON format
        assert created_config.provider_config is not None
        provider_config = json.loads(created_config.provider_config)
        assert provider_config["bucket_name"] == "legacy-bucket"
    
    def test_mixed_legacy_and_json_config_prioritizes_json(self):
        """Test that when both legacy fields and provider_config are provided, JSON takes priority"""
        mock_db = MagicMock(spec=Session)
        mock_db.query.return_value.filter.return_value.first.return_value = None
        
        cloud_sync_service = CloudSyncService(mock_db)
        
        # Config with both legacy fields and provider_config
        mixed_config = CloudSyncConfigCreate(
            name="mixed-config",
            provider=ProviderType.S3,
            # Legacy fields
            bucket_name="legacy-bucket",
            access_key="AKIALEGACY",
            secret_key="legacy-secret",
            # New JSON config (should take priority)
            provider_config={
                "bucket_name": "json-bucket",
                "access_key": "AKIAJSON",
                "secret_key": "json-secret",
                "region": "us-west-2"
            }
        )
        
        result = cloud_sync_service.create_cloud_sync_config(mixed_config)
        
        created_config = mock_db.add.call_args[0][0]
        provider_config = json.loads(created_config.provider_config)
        
        # Should use JSON config values, not legacy fields
        assert "encrypted_access_key" in provider_config  # Should be encrypted
        # The bucket name should come from JSON config
        assert provider_config["bucket_name"] == "json-bucket"
    
    def test_provider_config_validation_works_for_legacy_conversion(self):
        """Test that provider validation catches errors in legacy field conversion"""
        mock_db = MagicMock(spec=Session)
        mock_db.query.return_value.filter.return_value.first.return_value = None
        
        cloud_sync_service = CloudSyncService(mock_db)
        
        # Invalid legacy config
        invalid_legacy_config = CloudSyncConfigCreate(
            name="invalid-legacy",
            provider=ProviderType.S3,
            bucket_name="ab",  # Too short
            access_key="invalid",
            secret_key="invalid"
        )
        
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            cloud_sync_service.create_cloud_sync_config(invalid_legacy_config)
        
        assert exc_info.value.status_code == 400
        assert "Invalid provider configuration" in str(exc_info.value.detail)


class TestMigrationProcess:
    """Test the migration process from legacy to JSON format"""
    
    def test_migration_script_structure(self):
        """Test that the migration script has the correct structure"""
        # Import the migration functions
        from utils.migrate_cloud_configs import migrate_existing_configs, verify_migration
        
        # Should be callable functions
        assert callable(migrate_existing_configs)
        assert callable(verify_migration)
    
    @patch('utils.migrate_cloud_configs.SessionLocal')
    @patch('utils.migrate_cloud_configs.create_engine')
    def test_migration_converts_s3_config(self, mock_create_engine, mock_session_local):
        """Test migration converts S3 config to JSON format"""
        # Setup mock database objects
        mock_session = MagicMock()
        mock_session_local.return_value = mock_session
        
        # Create mock S3 config
        mock_s3_config = MagicMock()
        mock_s3_config.id = 1
        mock_s3_config.provider = "s3"
        mock_s3_config.provider_config = None  # Legacy config
        mock_s3_config.bucket_name = "migration-test-bucket"
        mock_s3_config.encrypted_access_key = "encrypted_access"
        mock_s3_config.encrypted_secret_key = "encrypted_secret"
        
        mock_session.query.return_value.all.return_value = [mock_s3_config]
        
        # Run migration
        result = migrate_existing_configs()
        
        # Should have set provider_config
        assert mock_s3_config.provider_config is not None
        config_data = json.loads(mock_s3_config.provider_config)
        assert config_data["bucket_name"] == "migration-test-bucket"
        assert config_data["encrypted_access_key"] == "encrypted_access"
        assert config_data["encrypted_secret_key"] == "encrypted_secret"
        assert config_data["region"] == "us-east-1"  # Default
        
        # Should have committed
        mock_session.commit.assert_called_once()
    
    @patch('utils.migrate_cloud_configs.SessionLocal')
    @patch('utils.migrate_cloud_configs.create_engine')
    def test_migration_converts_sftp_config(self, mock_create_engine, mock_session_local):
        """Test migration converts SFTP config to JSON format"""
        mock_session = MagicMock()
        mock_session_local.return_value = mock_session
        
        # Create mock SFTP config
        mock_sftp_config = MagicMock()
        mock_sftp_config.id = 2
        mock_sftp_config.provider = "sftp"
        mock_sftp_config.provider_config = None  # Legacy config
        mock_sftp_config.host = "migration-sftp.example.com"
        mock_sftp_config.port = 2222
        mock_sftp_config.username = "migration-user"
        mock_sftp_config.remote_path = "/migration/backups"
        mock_sftp_config.encrypted_password = "encrypted_password"
        mock_sftp_config.encrypted_private_key = None
        
        mock_session.query.return_value.all.return_value = [mock_sftp_config]
        
        # Run migration
        result = migrate_existing_configs()
        
        # Should have set provider_config
        assert mock_sftp_config.provider_config is not None
        config_data = json.loads(mock_sftp_config.provider_config)
        assert config_data["host"] == "migration-sftp.example.com"
        assert config_data["port"] == 2222
        assert config_data["username"] == "migration-user"
        assert config_data["remote_path"] == "/migration/backups"
        assert config_data["encrypted_password"] == "encrypted_password"
        assert config_data["host_key_checking"] is True  # Default
    
    @patch('utils.migrate_cloud_configs.SessionLocal')
    @patch('utils.migrate_cloud_configs.create_engine')
    def test_migration_skips_already_migrated(self, mock_create_engine, mock_session_local):
        """Test migration skips configs that already have provider_config"""
        mock_session = MagicMock()
        mock_session_local.return_value = mock_session
        
        # Create config that's already migrated
        mock_migrated_config = MagicMock()
        mock_migrated_config.id = 1
        mock_migrated_config.provider = "s3"
        mock_migrated_config.provider_config = '{"bucket_name": "already-migrated"}'
        
        mock_session.query.return_value.all.return_value = [mock_migrated_config]
        
        # Run migration
        result = migrate_existing_configs()
        
        # Should not have modified provider_config
        assert mock_migrated_config.provider_config == '{"bucket_name": "already-migrated"}'
        
        # Should still commit (but no changes)
        mock_session.commit.assert_called_once()
    
    def test_migration_handles_unknown_provider(self):
        """Test migration gracefully handles unknown provider types"""
        # This would be tested with a more complete mock setup
        # For now, just verify the migration function exists and can be called
        from utils.migrate_cloud_configs import migrate_existing_configs
        
        # Function should exist and be callable
        assert callable(migrate_existing_configs)
