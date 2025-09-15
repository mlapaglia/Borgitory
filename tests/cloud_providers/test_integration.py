"""
Integration Tests for Cloud Provider Strategy

These tests verify that the new provider strategy works end-to-end with the 
CloudSyncService and job execution system.
"""

import pytest
import json
from unittest.mock import AsyncMock, MagicMock, patch
from types import SimpleNamespace
from sqlalchemy.orm import Session

from services.cloud_sync_service import CloudSyncService
from services.jobs.job_executor import JobExecutor
from services.cloud_providers import CloudProviderFactory
from models.database import CloudSyncConfig
from models.schemas import CloudSyncConfigCreate, ProviderType


class TestCloudSyncServiceIntegration:
    """Test CloudSyncService with new provider strategy"""
    
    @pytest.fixture
    def mock_db(self):
        """Mock database session"""
        return MagicMock(spec=Session)
    
    @pytest.fixture
    def cloud_sync_service(self, mock_db):
        """CloudSyncService instance with mocked database"""
        return CloudSyncService(mock_db)
    
    @pytest.fixture
    def s3_config_create(self):
        """S3 configuration for creation"""
        return CloudSyncConfigCreate(
            name="test-s3-new",
            provider=ProviderType.S3,
            provider_config={
                "bucket_name": "test-bucket",
                "access_key": "AKIAIOSFODNN7EXAMPLE",
                "secret_key": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
                "region": "us-east-1",
                "storage_class": "STANDARD"
            },
            path_prefix="backups/"
        )
    
    @pytest.fixture
    def sftp_config_create(self):
        """SFTP configuration for creation"""
        return CloudSyncConfigCreate(
            name="test-sftp-new",
            provider=ProviderType.SFTP,
            provider_config={
                "host": "sftp.example.com",
                "username": "testuser",
                "password": "testpass",
                "remote_path": "/backups",
                "port": 22,
                "host_key_checking": True
            },
            path_prefix="borg/"
        )
    
    def test_create_s3_config_with_new_strategy(self, cloud_sync_service, mock_db, s3_config_create):
        """Test creating S3 config using new provider strategy"""
        # Setup mock database behavior
        mock_db.query.return_value.filter.return_value.first.return_value = None  # No existing config
        
        # Create config
        result = cloud_sync_service.create_cloud_sync_config(s3_config_create)
        
        # Verify database operations
        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()
        mock_db.refresh.assert_called_once()
        
        # Verify the created config
        created_config = mock_db.add.call_args[0][0]
        assert isinstance(created_config, CloudSyncConfig)
        assert created_config.name == "test-s3-new"
        assert created_config.provider == "s3"
        assert created_config.path_prefix == "backups/"
        
        # Verify provider_config is JSON
        provider_config = json.loads(created_config.provider_config)
        assert "encrypted_access_key" in provider_config
        assert "encrypted_secret_key" in provider_config
        assert provider_config["bucket_name"] == "test-bucket"
        assert "access_key" not in provider_config  # Should be encrypted
    
    def test_create_sftp_config_with_new_strategy(self, cloud_sync_service, mock_db, sftp_config_create):
        """Test creating SFTP config using new provider strategy"""
        mock_db.query.return_value.filter.return_value.first.return_value = None
        
        result = cloud_sync_service.create_cloud_sync_config(sftp_config_create)
        
        # Verify the created config
        created_config = mock_db.add.call_args[0][0]
        assert created_config.provider == "sftp"
        
        # Verify provider_config is JSON with encrypted fields
        provider_config = json.loads(created_config.provider_config)
        assert "encrypted_password" in provider_config
        assert provider_config["host"] == "sftp.example.com"
        assert "password" not in provider_config  # Should be encrypted
    
    def test_create_config_with_invalid_provider(self, cloud_sync_service, mock_db):
        """Test creating config with unsupported provider"""
        from fastapi import HTTPException
        
        invalid_config = CloudSyncConfigCreate(
            name="invalid-provider",
            provider="nonexistent",  # This will fail at Pydantic level
            provider_config={"some": "config"}
        )
        
        # This should fail at the Pydantic validation level
        with pytest.raises(ValueError):
            # The ProviderType enum validation will catch this
            pass
    
    def test_create_config_with_invalid_provider_config(self, cloud_sync_service, mock_db):
        """Test creating config with invalid provider configuration"""
        from fastapi import HTTPException
        
        invalid_s3_config = CloudSyncConfigCreate(
            name="invalid-s3",
            provider=ProviderType.S3,
            provider_config={
                "bucket_name": "ab",  # Too short
                "access_key": "invalid",
                "secret_key": "invalid"
            }
        )
        
        mock_db.query.return_value.filter.return_value.first.return_value = None
        
        with pytest.raises(HTTPException) as exc_info:
            cloud_sync_service.create_cloud_sync_config(invalid_s3_config)
        
        assert exc_info.value.status_code == 400
        assert "Invalid provider configuration" in str(exc_info.value.detail)
    
    def test_backward_compatibility_with_legacy_fields(self, cloud_sync_service, mock_db):
        """Test that legacy field-based configs still work"""
        legacy_config = CloudSyncConfigCreate(
            name="legacy-s3",
            provider=ProviderType.S3,
            bucket_name="legacy-bucket",
            access_key="AKIAIOSFODNN7EXAMPLE",
            secret_key="wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
            path_prefix="legacy/"
        )
        
        mock_db.query.return_value.filter.return_value.first.return_value = None
        
        result = cloud_sync_service.create_cloud_sync_config(legacy_config)
        
        # Should work and convert to new format
        created_config = mock_db.add.call_args[0][0]
        assert created_config.provider == "s3"
        
        # Should have provider_config populated from legacy fields
        provider_config = json.loads(created_config.provider_config)
        assert provider_config["bucket_name"] == "legacy-bucket"


class TestJobExecutorIntegration:
    """Test JobExecutor with new provider strategy"""
    
    @pytest.fixture
    def job_executor(self):
        """JobExecutor instance"""
        return JobExecutor()
    
    @pytest.fixture
    def mock_db_session(self):
        """Mock database session with cloud sync config"""
        mock_session = MagicMock()
        
        # Create a mock config with new JSON format
        mock_config = MagicMock(spec=CloudSyncConfig)
        mock_config.id = 1
        mock_config.name = "test-config"
        mock_config.provider = "s3"
        mock_config.enabled = True
        mock_config.path_prefix = "backups/"
        mock_config.provider_config = json.dumps({
            "encrypted_bucket_name": "encrypted_bucket_data",
            "encrypted_access_key": "encrypted_access_key_data",
            "encrypted_secret_key": "encrypted_secret_key_data",
            "region": "us-east-1",
            "storage_class": "STANDARD"
        })
        
        mock_session.query.return_value.filter.return_value.first.return_value = mock_config
        return mock_session
    
    @pytest.fixture
    def mock_db_session_factory(self, mock_db_session):
        """Mock database session factory"""
        def factory():
            return mock_db_session
        return factory
    
    @pytest.mark.asyncio
    async def test_execute_cloud_sync_with_new_strategy(
        self, 
        job_executor, 
        mock_db_session_factory
    ):
        """Test cloud sync execution using new provider strategy"""
        
        with patch('services.cloud_providers.CloudProviderFactory.create_provider') as mock_create_provider:
            # Setup mock provider
            mock_provider = AsyncMock()
            mock_provider.get_connection_info.return_value = {"provider": "s3", "bucket": "test"}
            
            # Setup mock sync generator
            async def mock_sync_generator(repository, path_prefix=""):
                yield {"type": "started", "command": "rclone sync", "pid": 12345}
                yield {"type": "progress", "transferred": "100MB", "percentage": 50}
                yield {"type": "completed", "return_code": 0, "status": "success"}
            
            mock_provider.sync_repository.return_value = mock_sync_generator(None)
            mock_create_provider.return_value = mock_provider
            
            # Setup output callback
            output_messages = []
            def output_callback(message, data):
                output_messages.append({"message": message, "data": data})
            
            # Execute cloud sync
            result = await job_executor.execute_cloud_sync_task(
                repository_path="/test/repo",
                passphrase="test-passphrase",
                cloud_sync_config_id=1,
                output_callback=output_callback,
                db_session_factory=mock_db_session_factory
            )
            
            # Verify provider was created and called
            mock_create_provider.assert_called_once()
            create_call_args = mock_create_provider.call_args
            assert create_call_args[0][0] == "s3"  # provider name
            
            # Verify sync was called
            mock_provider.sync_repository.assert_called_once()
            sync_call_args = mock_provider.sync_repository.call_args
            assert sync_call_args.kwargs["path_prefix"] == "backups/"
            
            # Verify output was generated
            assert len(output_messages) > 0
            assert any("Syncing to test-config" in msg["message"] for msg in output_messages)
            
            # Verify successful result
            assert result.return_code == 0
            assert result.error is None
    
    @pytest.mark.asyncio
    async def test_execute_cloud_sync_with_legacy_config(
        self, 
        job_executor
    ):
        """Test cloud sync execution with legacy database config (backward compatibility)"""
        
        # Create mock session with legacy config (no provider_config)
        mock_session = MagicMock()
        mock_config = MagicMock(spec=CloudSyncConfig)
        mock_config.id = 1
        mock_config.name = "legacy-s3"
        mock_config.provider = "s3"
        mock_config.enabled = True
        mock_config.path_prefix = "legacy/"
        mock_config.provider_config = None  # Legacy config has no JSON config
        
        # Legacy fields
        mock_config.bucket_name = "legacy-bucket"
        mock_config.get_credentials.return_value = ("AKIALEGACY", "secretlegacy")
        
        mock_session.query.return_value.filter.return_value.first.return_value = mock_config
        
        def session_factory():
            return mock_session
        
        with patch('services.cloud_providers.CloudProviderFactory.create_provider') as mock_create_provider:
            mock_provider = AsyncMock()
            mock_provider.get_connection_info.return_value = {"provider": "s3"}
            
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
            
            # Verify provider was created with legacy config converted to new format
            mock_create_provider.assert_called_once()
            create_call_args = mock_create_provider.call_args
            provider_config = create_call_args[0][1]  # config argument
            
            assert provider_config["bucket_name"] == "legacy-bucket"
            assert provider_config["access_key"] == "AKIALEGACY"
            assert provider_config["secret_key"] == "secretlegacy"
            
            assert result.return_code == 0
    
    @pytest.mark.asyncio
    async def test_execute_cloud_sync_provider_creation_error(
        self, 
        job_executor, 
        mock_db_session_factory
    ):
        """Test cloud sync execution when provider creation fails"""
        
        with patch('services.cloud_providers.CloudProviderFactory.create_provider') as mock_create_provider:
            mock_create_provider.side_effect = ValueError("Invalid configuration")
            
            result = await job_executor.execute_cloud_sync_task(
                repository_path="/test/repo",
                passphrase="test-passphrase",
                cloud_sync_config_id=1,
                db_session_factory=mock_db_session_factory
            )
            
            # Should handle the error gracefully
            assert result.return_code == 1
            assert "Failed to initialize cloud provider" in result.error
            assert "Invalid configuration" in result.error


class TestEndToEndStrategy:
    """End-to-end tests demonstrating the complete strategy"""
    
    def test_adding_new_provider_is_easy(self):
        """Demonstrate how easy it is to add a new provider"""
        from services.cloud_providers.base import CloudProvider, ProviderConfig
        from pydantic import Field
        
        # Step 1: Define provider config
        class MockCloudConfig(ProviderConfig):
            api_key: str = Field(..., min_length=1)
            endpoint: str = Field(default="https://api.mockcloud.com")
        
        # Step 2: Implement provider
        @CloudProviderFactory.register_provider("mockcloud")
        class MockCloudProvider(CloudProvider):
            @property
            def provider_name(self) -> str:
                return "mockcloud"
            
            def _validate_config(self, config):
                return MockCloudConfig(**config)
            
            async def sync_repository(self, repository, path_prefix=""):
                yield {"type": "started", "message": f"Syncing to MockCloud at {self.config.endpoint}"}
                yield {"type": "completed", "status": "success"}
            
            async def test_connection(self):
                return {"status": "success", "message": "MockCloud connection OK"}
            
            def get_connection_info(self):
                return {"provider": "mockcloud", "endpoint": self.config.endpoint}
            
            def _get_sensitive_fields(self):
                return ["api_key"]
        
        # Step 3: Use it immediately
        config = {"api_key": "secret123", "endpoint": "https://custom.mockcloud.com"}
        provider = CloudProviderFactory.create_provider("mockcloud", config)
        
        assert isinstance(provider, MockCloudProvider)
        assert provider.provider_name == "mockcloud"
        assert provider.config.api_key == "secret123"
        assert provider.config.endpoint == "https://custom.mockcloud.com"
        
        # Verify it's available
        assert "mockcloud" in CloudProviderFactory.get_available_providers()
        
        # Test sensitive field handling
        encrypted = provider.encrypt_sensitive_fields(config)
        assert "api_key" not in encrypted
        assert "encrypted_api_key" in encrypted
    
    def test_strategy_benefits_demonstrated(self):
        """Demonstrate the key benefits of the new strategy"""
        
        # 1. Type Safety
        s3_config = {
            "bucket_name": "test-bucket",
            "access_key": "AKIAIOSFODNN7EXAMPLE",
            "secret_key": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
        }
        
        # This works
        provider = CloudProviderFactory.create_provider("s3", s3_config)
        assert provider.config.bucket_name == "test-bucket"
        
        # This fails with clear error (type safety)
        invalid_s3_config = {"bucket_name": "ab"}  # Too short
        with pytest.raises(ValueError):
            CloudProviderFactory.create_provider("s3", invalid_s3_config)
        
        # 2. Extensibility - already demonstrated above
        
        # 3. Testability - dependency injection
        mock_rclone = MagicMock()
        provider_with_mock = CloudProviderFactory.create_provider(
            "s3", 
            s3_config, 
            rclone_service=mock_rclone
        )
        assert provider_with_mock._rclone_service is mock_rclone
        
        # 4. Consistency - all providers have same interface
        sftp_config = {
            "host": "sftp.example.com",
            "username": "test",
            "password": "pass",
            "remote_path": "/backups"
        }
        
        s3_provider = CloudProviderFactory.create_provider("s3", s3_config)
        sftp_provider = CloudProviderFactory.create_provider("sftp", sftp_config)
        
        # Both have same interface
        assert hasattr(s3_provider, 'sync_repository')
        assert hasattr(s3_provider, 'test_connection')
        assert hasattr(sftp_provider, 'sync_repository')
        assert hasattr(sftp_provider, 'test_connection')
        
        # Both handle encryption the same way
        s3_encrypted = s3_provider.encrypt_sensitive_fields(s3_config)
        sftp_encrypted = sftp_provider.encrypt_sensitive_fields(sftp_config)
        
        assert "encrypted_access_key" in s3_encrypted
        assert "encrypted_password" in sftp_encrypted
