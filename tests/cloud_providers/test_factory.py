"""
Tests for Cloud Provider Factory

These tests verify that the CloudProviderFactory correctly manages provider registration,
creation, and dependency injection.
"""

import pytest
from unittest.mock import MagicMock
from services.cloud_providers.factory import CloudProviderFactory
from services.cloud_providers.base import CloudProvider, ProviderConfig
from services.cloud_providers.s3_provider import S3Provider
from services.cloud_providers.sftp_provider import SFTPProvider


class TestCloudProviderFactory:
    """Test CloudProviderFactory functionality"""
    
    def setup_method(self):
        """Reset factory state before each test"""
        # Save original providers
        self.original_providers = CloudProviderFactory._providers.copy()
    
    def teardown_method(self):
        """Restore factory state after each test"""
        # Restore original providers
        CloudProviderFactory._providers = self.original_providers
    
    def test_get_available_providers(self):
        """Test getting list of available providers"""
        providers = CloudProviderFactory.get_available_providers()
        
        # Should include our registered providers
        assert "s3" in providers
        assert "sftp" in providers
        assert isinstance(providers, list)
    
    def test_is_provider_available(self):
        """Test checking if provider is available"""
        assert CloudProviderFactory.is_provider_available("s3") is True
        assert CloudProviderFactory.is_provider_available("sftp") is True
        assert CloudProviderFactory.is_provider_available("nonexistent") is False
    
    def test_create_s3_provider(self):
        """Test creating S3 provider"""
        config = {
            "bucket_name": "test-bucket",
            "access_key": "AKIAIOSFODNN7EXAMPLE",
            "secret_key": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
        }
        
        provider = CloudProviderFactory.create_provider("s3", config)
        
        assert isinstance(provider, S3Provider)
        assert provider.provider_name == "s3"
        assert provider.config.bucket_name == "test-bucket"
    
    def test_create_sftp_provider(self):
        """Test creating SFTP provider"""
        config = {
            "host": "sftp.example.com",
            "username": "testuser",
            "password": "testpass",
            "remote_path": "/backups"
        }
        
        provider = CloudProviderFactory.create_provider("sftp", config)
        
        assert isinstance(provider, SFTPProvider)
        assert provider.provider_name == "sftp"
        assert provider.config.host == "sftp.example.com"
    
    def test_create_provider_with_dependencies(self):
        """Test creating provider with dependency injection"""
        config = {
            "bucket_name": "test-bucket",
            "access_key": "AKIAIOSFODNN7EXAMPLE",
            "secret_key": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
        }
        mock_rclone = MagicMock()
        
        provider = CloudProviderFactory.create_provider(
            "s3", 
            config, 
            rclone_service=mock_rclone
        )
        
        assert isinstance(provider, S3Provider)
        assert provider._rclone_service is mock_rclone
    
    def test_create_unknown_provider(self):
        """Test creating unknown provider raises error"""
        config = {"some": "config"}
        
        with pytest.raises(ValueError, match="Unknown provider 'unknown'"):
            CloudProviderFactory.create_provider("unknown", config)
    
    def test_register_provider_decorator(self):
        """Test provider registration decorator"""
        # Create a mock provider class
        class MockConfig(ProviderConfig):
            test_field: str = "test"
        
        @CloudProviderFactory.register_provider("test_provider")
        class TestProvider(CloudProvider):
            @property
            def provider_name(self) -> str:
                return "test_provider"
            
            def _validate_config(self, config):
                return MockConfig(**config)
            
            async def sync_repository(self, repository, path_prefix=""):
                yield {"type": "test", "message": "mock sync"}
            
            async def test_connection(self):
                return {"status": "success", "message": "mock test"}
            
            def get_connection_info(self):
                return {"provider": "test_provider"}
            
            def _get_sensitive_fields(self):
                return []
        
        # Verify registration
        assert "test_provider" in CloudProviderFactory.get_available_providers()
        assert CloudProviderFactory.is_provider_available("test_provider")
        
        # Test creation
        provider = CloudProviderFactory.create_provider("test_provider", {"test_field": "value"})
        assert isinstance(provider, TestProvider)
        assert provider.provider_name == "test_provider"
    
    def test_get_provider_info(self):
        """Test getting provider information"""
        info = CloudProviderFactory.get_provider_info()
        
        assert isinstance(info, dict)
        assert "s3" in info
        assert "sftp" in info
        
        s3_info = info["s3"]
        assert s3_info["name"] == "s3"
        assert s3_info["class_name"] == "S3Provider"
        assert "s3_provider" in s3_info["module"]
    
    def test_provider_registration_idempotent(self):
        """Test that registering the same provider twice overwrites"""
        original_count = len(CloudProviderFactory.get_available_providers())
        
        # Register a test provider
        @CloudProviderFactory.register_provider("duplicate_test")
        class FirstProvider(CloudProvider):
            @property
            def provider_name(self) -> str:
                return "duplicate_test"
            
            def _validate_config(self, config):
                return ProviderConfig()
            
            async def sync_repository(self, repository, path_prefix=""):
                yield {"message": "first"}
            
            async def test_connection(self):
                return {"status": "first"}
            
            def get_connection_info(self):
                return {"provider": "first"}
            
            def _get_sensitive_fields(self):
                return []
        
        # Register another provider with same name
        @CloudProviderFactory.register_provider("duplicate_test")
        class SecondProvider(CloudProvider):
            @property
            def provider_name(self) -> str:
                return "duplicate_test"
            
            def _validate_config(self, config):
                return ProviderConfig()
            
            async def sync_repository(self, repository, path_prefix=""):
                yield {"message": "second"}
            
            async def test_connection(self):
                return {"status": "second"}
            
            def get_connection_info(self):
                return {"provider": "second"}
            
            def _get_sensitive_fields(self):
                return []
        
        # Should still have same number of providers (overwritten, not added)
        new_count = len(CloudProviderFactory.get_available_providers())
        assert new_count == original_count + 1
        
        # Should use the second provider
        provider = CloudProviderFactory.create_provider("duplicate_test", {})
        assert isinstance(provider, SecondProvider)
    
    def test_factory_isolation(self):
        """Test that factory state is properly isolated"""
        # Get initial state
        initial_providers = CloudProviderFactory.get_available_providers()
        
        # Register a temporary provider
        @CloudProviderFactory.register_provider("temp_provider")
        class TempProvider(CloudProvider):
            @property
            def provider_name(self) -> str:
                return "temp_provider"
            
            def _validate_config(self, config):
                return ProviderConfig()
            
            async def sync_repository(self, repository, path_prefix=""):
                yield {"type": "temp"}
            
            async def test_connection(self):
                return {"status": "temp"}
            
            def get_connection_info(self):
                return {"provider": "temp"}
            
            def _get_sensitive_fields(self):
                return []
        
        # Verify it was added
        assert "temp_provider" in CloudProviderFactory.get_available_providers()
        
        # After teardown, it should be removed (handled by teardown_method)
    
    def test_create_provider_with_invalid_config(self):
        """Test creating provider with invalid configuration"""
        invalid_config = {
            "bucket_name": "ab",  # Too short for S3
            "access_key": "invalid",
            "secret_key": "invalid"
        }
        
        with pytest.raises(ValueError):
            CloudProviderFactory.create_provider("s3", invalid_config)
    
    def test_multiple_dependency_injection(self):
        """Test injecting multiple dependencies"""
        config = {
            "host": "sftp.example.com",
            "username": "testuser",
            "password": "testpass",
            "remote_path": "/backups"
        }
        
        mock_rclone = MagicMock()
        mock_other = MagicMock()
        
        provider = CloudProviderFactory.create_provider(
            "sftp", 
            config,
            rclone_service=mock_rclone,
            other_service=mock_other  # This won't be used by current providers but tests the pattern
        )
        
        assert isinstance(provider, SFTPProvider)
        assert provider._rclone_service is mock_rclone
