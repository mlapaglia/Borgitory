"""
Tests for SFTP Cloud Provider

These tests verify that the SFTPProvider correctly implements the CloudProvider interface
and handles SFTP-specific configuration and operations.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from types import SimpleNamespace
from services.cloud_providers.sftp_provider import SFTPProvider, SFTPConfig
from services.cloud_providers.base import CloudProvider


class TestSFTPConfig:
    """Test SFTP configuration validation"""
    
    def test_valid_sftp_config_with_password(self):
        """Test valid SFTP configuration with password"""
        config = SFTPConfig(
            host="sftp.example.com",
            username="testuser",
            password="testpass",
            remote_path="/backups",
            port=22,
            host_key_checking=True
        )
        
        assert config.host == "sftp.example.com"
        assert config.username == "testuser"
        assert config.password == "testpass"
        assert config.remote_path == "/backups"
        assert config.port == 22
        assert config.host_key_checking is True
    
    def test_valid_sftp_config_with_private_key(self):
        """Test valid SFTP configuration with private key"""
        private_key = "-----BEGIN RSA PRIVATE KEY-----\ntest-key-content\n-----END RSA PRIVATE KEY-----"
        
        config = SFTPConfig(
            host="sftp.example.com",
            username="testuser",
            private_key=private_key,
            remote_path="/backups"
        )
        
        assert config.host == "sftp.example.com"
        assert config.private_key == private_key
        assert config.password is None
    
    def test_remote_path_normalization(self):
        """Test remote path normalization"""
        # Should add leading slash
        config = SFTPConfig(
            host="sftp.example.com",
            username="testuser",
            password="testpass",
            remote_path="backups/data"
        )
        assert config.remote_path == "/backups/data"
        
        # Should remove trailing slash
        config = SFTPConfig(
            host="sftp.example.com",
            username="testuser",
            password="testpass",
            remote_path="/backups/data/"
        )
        assert config.remote_path == "/backups/data"
    
    def test_missing_authentication(self):
        """Test configuration without authentication method"""
        with pytest.raises(ValueError, match="Either password or private_key must be provided"):
            SFTPConfig(
                host="sftp.example.com",
                username="testuser",
                remote_path="/backups"
                # No password or private_key
            )
    
    def test_port_validation(self):
        """Test port number validation"""
        config = SFTPConfig(
            host="sftp.example.com",
            username="testuser",
            password="testpass",
            remote_path="/backups",
            port=2222
        )
        assert config.port == 2222


class TestSFTPProvider:
    """Test SFTPProvider implementation"""
    
    @pytest.fixture
    def sftp_config_password(self):
        """Valid SFTP configuration with password"""
        return {
            "host": "sftp.example.com",
            "username": "testuser",
            "password": "testpass",
            "remote_path": "/backups",
            "port": 22,
            "host_key_checking": True
        }
    
    @pytest.fixture
    def sftp_config_key(self):
        """Valid SFTP configuration with private key"""
        return {
            "host": "sftp.example.com",
            "username": "testuser",
            "private_key": "-----BEGIN RSA PRIVATE KEY-----\ntest-key\n-----END RSA PRIVATE KEY-----",
            "remote_path": "/backups",
            "port": 22,
            "host_key_checking": True
        }
    
    @pytest.fixture
    def mock_rclone_service(self):
        """Mock RcloneService for testing"""
        return AsyncMock()
    
    @pytest.fixture
    def sftp_provider_password(self, sftp_config_password, mock_rclone_service):
        """SFTPProvider instance with password auth and mocked dependencies"""
        return SFTPProvider(sftp_config_password, rclone_service=mock_rclone_service)
    
    @pytest.fixture
    def sftp_provider_key(self, sftp_config_key, mock_rclone_service):
        """SFTPProvider instance with key auth and mocked dependencies"""
        return SFTPProvider(sftp_config_key, rclone_service=mock_rclone_service)
    
    def test_provider_initialization(self, sftp_config_password):
        """Test SFTPProvider initialization"""
        provider = SFTPProvider(sftp_config_password)
        
        assert provider.provider_name == "sftp"
        assert isinstance(provider.config, SFTPConfig)
        assert provider.config.host == "sftp.example.com"
        assert provider.config.username == "testuser"
    
    def test_provider_implements_interface(self, sftp_provider_password):
        """Test that SFTPProvider implements CloudProvider interface"""
        assert isinstance(sftp_provider_password, CloudProvider)
        assert hasattr(sftp_provider_password, 'sync_repository')
        assert hasattr(sftp_provider_password, 'test_connection')
        assert hasattr(sftp_provider_password, 'get_connection_info')
    
    def test_get_connection_info_password(self, sftp_provider_password):
        """Test connection info with password auth"""
        info = sftp_provider_password.get_connection_info()
        
        assert info["provider"] == "sftp"
        assert info["host"] == "sftp.example.com"
        assert info["port"] == 22
        assert info["username"] == "testuser"
        assert info["remote_path"] == "/backups"
        assert info["auth_method"] == "password"
        assert info["host_key_checking"] is True
    
    def test_get_connection_info_private_key(self, sftp_provider_key):
        """Test connection info with private key auth"""
        info = sftp_provider_key.get_connection_info()
        
        assert info["auth_method"] == "private_key"
    
    def test_get_sensitive_fields(self, sftp_provider_password):
        """Test sensitive fields identification"""
        sensitive_fields = sftp_provider_password._get_sensitive_fields()
        
        assert "password" in sensitive_fields
        assert "private_key" in sensitive_fields
        assert len(sensitive_fields) == 2
    
    @pytest.mark.asyncio
    async def test_sync_repository_success_password(self, sftp_provider_password, mock_rclone_service):
        """Test successful repository sync with password auth"""
        repository = SimpleNamespace(path="/test/repo/path")
        
        # Setup mock progress generator
        mock_progress = [
            {"type": "started", "command": "rclone sync", "pid": 12345},
            {"type": "progress", "transferred": "100MB", "percentage": 50},
            {"type": "completed", "return_code": 0, "status": "success"}
        ]
        
        async def mock_sync_generator(*args, **kwargs):
            for progress in mock_progress:
                yield progress
        
        mock_rclone_service.sync_repository_to_sftp.return_value = mock_sync_generator()
        
        # Execute sync
        progress_list = []
        async for progress in sftp_provider_password.sync_repository(repository, "backups/"):
            progress_list.append(progress)
        
        # Verify rclone service was called correctly
        mock_rclone_service.sync_repository_to_sftp.assert_called_once_with(
            repository=repository,
            host="sftp.example.com",
            username="testuser",
            remote_path="/backups",
            port=22,
            password="testpass",
            private_key=None,
            path_prefix="backups/",
        )
        
        # Verify progress was yielded correctly
        assert len(progress_list) == 3
        assert progress_list[0]["type"] == "started"
        assert progress_list[2]["type"] == "completed"
    
    @pytest.mark.asyncio
    async def test_sync_repository_success_private_key(self, sftp_provider_key, mock_rclone_service):
        """Test successful repository sync with private key auth"""
        repository = SimpleNamespace(path="/test/repo/path")
        
        mock_progress = [
            {"type": "completed", "return_code": 0, "status": "success"}
        ]
        
        async def mock_sync_generator(*args, **kwargs):
            for progress in mock_progress:
                yield progress
        
        mock_rclone_service.sync_repository_to_sftp.return_value = mock_sync_generator()
        
        # Execute sync
        progress_list = []
        async for progress in sftp_provider_key.sync_repository(repository):
            progress_list.append(progress)
        
        # Verify rclone service was called with private key
        call_args = mock_rclone_service.sync_repository_to_sftp.call_args
        assert call_args.kwargs["password"] is None
        assert "test-key" in call_args.kwargs["private_key"]
    
    @pytest.mark.asyncio
    async def test_sync_repository_error(self, sftp_provider_password, mock_rclone_service):
        """Test repository sync with error"""
        repository = SimpleNamespace(path="/test/repo/path")
        
        # Setup mock to raise exception
        mock_rclone_service.sync_repository_to_sftp.side_effect = Exception("SSH connection failed")
        
        # Execute sync
        progress_list = []
        async for progress in sftp_provider_password.sync_repository(repository):
            progress_list.append(progress)
        
        # Verify error was handled
        assert len(progress_list) == 1
        assert progress_list[0]["type"] == "error"
        assert "SFTP sync failed" in progress_list[0]["message"]
        assert "SSH connection failed" in progress_list[0]["message"]
    
    @pytest.mark.asyncio
    async def test_test_connection_success(self, sftp_provider_password, mock_rclone_service):
        """Test successful connection test"""
        expected_result = {
            "status": "success",
            "message": "SFTP connection successful",
            "details": {
                "read_test": "passed",
                "write_test": "passed",
                "host": "sftp.example.com",
                "port": 22
            }
        }
        mock_rclone_service.test_sftp_connection.return_value = expected_result
        
        result = await sftp_provider_password.test_connection()
        
        # Verify rclone service was called correctly
        mock_rclone_service.test_sftp_connection.assert_called_once_with(
            host="sftp.example.com",
            username="testuser",
            remote_path="/backups",
            port=22,
            password="testpass",
            private_key=None,
        )
        
        assert result == expected_result
    
    @pytest.mark.asyncio
    async def test_test_connection_error(self, sftp_provider_password, mock_rclone_service):
        """Test connection test with error"""
        mock_rclone_service.test_sftp_connection.side_effect = Exception("Connection refused")
        
        result = await sftp_provider_password.test_connection()
        
        assert result["status"] == "error"
        assert "Connection test failed" in result["message"]
        assert "Connection refused" in result["message"]
    
    def test_encrypt_decrypt_password(self, sftp_provider_password):
        """Test encryption/decryption of password"""
        test_data = {
            "host": "sftp.example.com",
            "username": "testuser",
            "password": "secret123",
            "remote_path": "/backups"
        }
        
        # Encrypt
        encrypted_data = sftp_provider_password.encrypt_sensitive_fields(test_data)
        
        # Non-sensitive fields should remain
        assert encrypted_data["host"] == "sftp.example.com"
        assert encrypted_data["username"] == "testuser"
        
        # Password should be encrypted
        assert "password" not in encrypted_data
        assert "encrypted_password" in encrypted_data
        assert encrypted_data["encrypted_password"] != "secret123"
        
        # Decrypt
        decrypted_data = sftp_provider_password.decrypt_sensitive_fields(encrypted_data)
        assert decrypted_data["password"] == "secret123"
        assert "encrypted_password" not in decrypted_data
    
    def test_encrypt_decrypt_private_key(self, sftp_provider_key):
        """Test encryption/decryption of private key"""
        test_key = "-----BEGIN RSA PRIVATE KEY-----\nsecret-key-data\n-----END RSA PRIVATE KEY-----"
        test_data = {
            "host": "sftp.example.com",
            "username": "testuser",
            "private_key": test_key,
            "remote_path": "/backups"
        }
        
        # Encrypt
        encrypted_data = sftp_provider_key.encrypt_sensitive_fields(test_data)
        
        # Private key should be encrypted
        assert "private_key" not in encrypted_data
        assert "encrypted_private_key" in encrypted_data
        assert encrypted_data["encrypted_private_key"] != test_key
        
        # Decrypt
        decrypted_data = sftp_provider_key.decrypt_sensitive_fields(encrypted_data)
        assert decrypted_data["private_key"] == test_key
        assert "encrypted_private_key" not in decrypted_data
    
    def test_dependency_injection(self, sftp_config_password):
        """Test that dependencies are properly injected"""
        mock_service = MagicMock()
        provider = SFTPProvider(sftp_config_password, rclone_service=mock_service)
        
        assert provider._rclone_service is mock_service
        assert provider._get_rclone_service() is mock_service
    
    def test_invalid_config(self):
        """Test provider with invalid configuration"""
        invalid_config = {
            "host": "sftp.example.com",
            "username": "testuser",
            "remote_path": "/backups"
            # Missing authentication method
        }
        
        with pytest.raises(ValueError, match="Either password or private_key must be provided"):
            SFTPProvider(invalid_config)
