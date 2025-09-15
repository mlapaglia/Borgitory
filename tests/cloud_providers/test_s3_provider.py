"""
Tests for S3 Cloud Provider

These tests verify that the S3Provider correctly implements the CloudProvider interface
and handles S3-specific configuration and operations.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from types import SimpleNamespace
from services.cloud_providers.s3_provider import S3Provider, S3Config
from services.cloud_providers.base import CloudProvider


class TestS3Config:
    """Test S3 configuration validation"""
    
    def test_valid_s3_config(self):
        """Test valid S3 configuration"""
        config = S3Config(
            bucket_name="test-bucket",
            access_key="AKIAIOSFODNN7EXAMPLE",
            secret_key="wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
            region="us-west-2",
            storage_class="STANDARD"
        )
        
        assert config.bucket_name == "test-bucket"
        assert config.access_key == "AKIAIOSFODNN7EXAMPLE"
        assert config.region == "us-west-2"
        assert config.storage_class == "STANDARD"
    
    def test_bucket_name_validation(self):
        """Test bucket name validation"""
        # Too short
        with pytest.raises(ValueError, match="Bucket name must be between 3 and 63 characters"):
            S3Config(
                bucket_name="ab",
                access_key="AKIAIOSFODNN7EXAMPLE",
                secret_key="wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
            )
        
        # Too long
        with pytest.raises(ValueError, match="Bucket name must be between 3 and 63 characters"):
            S3Config(
                bucket_name="a" * 64,
                access_key="AKIAIOSFODNN7EXAMPLE",
                secret_key="wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
            )
    
    def test_storage_class_validation(self):
        """Test storage class validation"""
        # Invalid storage class
        with pytest.raises(ValueError, match="Invalid storage class"):
            S3Config(
                bucket_name="test-bucket",
                access_key="AKIAIOSFODNN7EXAMPLE",
                secret_key="wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
                storage_class="INVALID_CLASS"
            )
        
        # Valid storage class (case insensitive)
        config = S3Config(
            bucket_name="test-bucket",
            access_key="AKIAIOSFODNN7EXAMPLE",
            secret_key="wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
            storage_class="glacier"
        )
        assert config.storage_class == "GLACIER"
    
    def test_bucket_name_normalization(self):
        """Test bucket name is normalized to lowercase"""
        config = S3Config(
            bucket_name="TEST-BUCKET",
            access_key="AKIAIOSFODNN7EXAMPLE",
            secret_key="wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
        )
        assert config.bucket_name == "test-bucket"


class TestS3Provider:
    """Test S3Provider implementation"""
    
    @pytest.fixture
    def s3_config(self):
        """Valid S3 configuration"""
        return {
            "bucket_name": "test-bucket",
            "access_key": "AKIAIOSFODNN7EXAMPLE",
            "secret_key": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
            "region": "us-east-1",
            "storage_class": "STANDARD"
        }
    
    @pytest.fixture
    def mock_rclone_service(self):
        """Mock RcloneService for testing"""
        return AsyncMock()
    
    @pytest.fixture
    def s3_provider(self, s3_config, mock_rclone_service):
        """S3Provider instance with mocked dependencies"""
        return S3Provider(s3_config, rclone_service=mock_rclone_service)
    
    def test_provider_initialization(self, s3_config):
        """Test S3Provider initialization"""
        provider = S3Provider(s3_config)
        
        assert provider.provider_name == "s3"
        assert isinstance(provider.config, S3Config)
        assert provider.config.bucket_name == "test-bucket"
        assert provider.config.access_key == "AKIAIOSFODNN7EXAMPLE"
    
    def test_provider_implements_interface(self, s3_provider):
        """Test that S3Provider implements CloudProvider interface"""
        assert isinstance(s3_provider, CloudProvider)
        assert hasattr(s3_provider, 'sync_repository')
        assert hasattr(s3_provider, 'test_connection')
        assert hasattr(s3_provider, 'get_connection_info')
    
    def test_get_connection_info(self, s3_provider):
        """Test connection info sanitization"""
        info = s3_provider.get_connection_info()
        
        assert info["provider"] == "s3"
        assert info["bucket_name"] == "test-bucket"
        assert info["region"] == "us-east-1"
        assert info["storage_class"] == "STANDARD"
        # Access key should be masked
        assert info["access_key_id"].startswith("AKIA")
        assert "***" in info["access_key_id"]
        assert len(info["access_key_id"]) < 20  # Should be masked
    
    def test_get_sensitive_fields(self, s3_provider):
        """Test sensitive fields identification"""
        sensitive_fields = s3_provider._get_sensitive_fields()
        
        assert "access_key" in sensitive_fields
        assert "secret_key" in sensitive_fields
        assert len(sensitive_fields) == 2
    
    @pytest.mark.asyncio
    async def test_sync_repository_success(self, s3_provider, mock_rclone_service):
        """Test successful repository sync"""
        # Setup mock repository
        repository = SimpleNamespace(path="/test/repo/path")
        
        # Setup mock progress generator
        mock_progress = [
            {"type": "started", "command": "rclone sync", "pid": 12345},
            {"type": "progress", "transferred": "100MB", "percentage": 50},
            {"type": "completed", "return_code": 0, "status": "success"}
        ]
        
        # Setup async generator mock
        async def async_generator():
            for progress in mock_progress:
                yield progress
        
        mock_rclone_service.sync_repository_to_s3.return_value = async_generator()
        
        # Execute sync
        progress_list = []
        async for progress in s3_provider.sync_repository(repository, "backups/"):
            progress_list.append(progress)
        
        # Verify rclone service was called correctly
        mock_rclone_service.sync_repository_to_s3.assert_called_once_with(
            repository=repository,
            access_key_id="AKIAIOSFODNN7EXAMPLE",
            secret_access_key="wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
            bucket_name="test-bucket",
            path_prefix="backups/",
        )
        
        # Verify progress was yielded correctly
        assert len(progress_list) == 3
        assert progress_list[0]["type"] == "started"
        assert progress_list[1]["type"] == "progress"
        assert progress_list[2]["type"] == "completed"
    
    @pytest.mark.asyncio
    async def test_sync_repository_error(self, s3_provider, mock_rclone_service):
        """Test repository sync with error"""
        repository = SimpleNamespace(path="/test/repo/path")
        
        # Setup mock to raise exception
        mock_rclone_service.sync_repository_to_s3.side_effect = Exception("Connection failed")
        
        # Execute sync
        progress_list = []
        async for progress in s3_provider.sync_repository(repository):
            progress_list.append(progress)
        
        # Verify error was handled
        assert len(progress_list) == 1
        assert progress_list[0]["type"] == "error"
        assert "S3 sync failed" in progress_list[0]["message"]
        assert "Connection failed" in progress_list[0]["message"]
    
    @pytest.mark.asyncio
    async def test_test_connection_success(self, s3_provider, mock_rclone_service):
        """Test successful connection test"""
        expected_result = {
            "status": "success",
            "message": "Connection successful",
            "details": {"read_test": "passed", "write_test": "passed"}
        }
        mock_rclone_service.test_s3_connection.return_value = expected_result
        
        result = await s3_provider.test_connection()
        
        # Verify rclone service was called correctly
        mock_rclone_service.test_s3_connection.assert_called_once_with(
            access_key_id="AKIAIOSFODNN7EXAMPLE",
            secret_access_key="wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
            bucket_name="test-bucket",
        )
        
        assert result == expected_result
    
    @pytest.mark.asyncio
    async def test_test_connection_error(self, s3_provider, mock_rclone_service):
        """Test connection test with error"""
        mock_rclone_service.test_s3_connection.side_effect = Exception("Network error")
        
        result = await s3_provider.test_connection()
        
        assert result["status"] == "error"
        assert "Connection test failed" in result["message"]
        assert "Network error" in result["message"]
    
    def test_encrypt_sensitive_fields(self, s3_provider):
        """Test encryption of sensitive fields"""
        test_data = {
            "bucket_name": "test-bucket",
            "access_key": "AKIAIOSFODNN7EXAMPLE",
            "secret_key": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
            "region": "us-east-1"
        }
        
        encrypted_data = s3_provider.encrypt_sensitive_fields(test_data)
        
        # Non-sensitive fields should remain
        assert encrypted_data["bucket_name"] == "test-bucket"
        assert encrypted_data["region"] == "us-east-1"
        
        # Sensitive fields should be encrypted and original removed
        assert "access_key" not in encrypted_data
        assert "secret_key" not in encrypted_data
        assert "encrypted_access_key" in encrypted_data
        assert "encrypted_secret_key" in encrypted_data
        
        # Encrypted values should be different from originals
        assert encrypted_data["encrypted_access_key"] != "AKIAIOSFODNN7EXAMPLE"
        assert encrypted_data["encrypted_secret_key"] != "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
    
    def test_decrypt_sensitive_fields(self, s3_provider):
        """Test decryption of sensitive fields"""
        # First encrypt some data
        test_data = {
            "bucket_name": "test-bucket",
            "access_key": "AKIAIOSFODNN7EXAMPLE",
            "secret_key": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
            "region": "us-east-1"
        }
        
        encrypted_data = s3_provider.encrypt_sensitive_fields(test_data)
        decrypted_data = s3_provider.decrypt_sensitive_fields(encrypted_data)
        
        # Should restore original sensitive fields
        assert decrypted_data["access_key"] == "AKIAIOSFODNN7EXAMPLE"
        assert decrypted_data["secret_key"] == "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
        
        # Non-sensitive fields should remain
        assert decrypted_data["bucket_name"] == "test-bucket"
        assert decrypted_data["region"] == "us-east-1"
        
        # Encrypted fields should be removed
        assert "encrypted_access_key" not in decrypted_data
        assert "encrypted_secret_key" not in decrypted_data
    
    def test_dependency_injection(self, s3_config):
        """Test that dependencies are properly injected"""
        mock_service = MagicMock()
        provider = S3Provider(s3_config, rclone_service=mock_service)
        
        # Should use injected service
        assert provider._rclone_service is mock_service
        assert provider._get_rclone_service() is mock_service
    
    def test_lazy_dependency_creation(self, s3_config):
        """Test that dependencies are created lazily when not injected"""
        provider = S3Provider(s3_config)
        
        # Should be None initially
        assert provider._rclone_service is None
        
        # Should create service on first access
        with patch('services.rclone_service.RcloneService') as mock_rclone_class:
            mock_service = MagicMock()
            mock_rclone_class.return_value = mock_service
            
            service = provider._get_rclone_service()
            
            assert service is mock_service
            assert provider._rclone_service is mock_service
            mock_rclone_class.assert_called_once()
    
    def test_invalid_config(self):
        """Test provider with invalid configuration"""
        invalid_config = {
            "bucket_name": "ab",  # Too short
            "access_key": "invalid",
            "secret_key": "invalid"
        }
        
        with pytest.raises(ValueError):
            S3Provider(invalid_config)
