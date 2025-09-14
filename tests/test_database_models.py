"""
Tests for database models - CRITICAL for data integrity and encryption security
"""
import pytest
from unittest.mock import Mock, patch
from cryptography.fernet import Fernet, InvalidToken

from models.database import (
    Repository, User, CloudSyncConfig, NotificationConfig,
    get_cipher_suite
)
import models.database


class TestCipherSuite:
    """Test encryption cipher suite functionality."""
    
    def test_get_cipher_suite_creates_instance(self):
        """Test that cipher suite is created properly."""
        with patch('config.get_secret_key', return_value='test_secret_key_32_characters_long!'):
            cipher = get_cipher_suite()
            assert cipher is not None
            assert isinstance(cipher, Fernet)
    
    def test_get_cipher_suite_caches_instance(self):
        """Test that cipher suite is cached and reused."""
        with patch('config.get_secret_key', return_value='test_secret_key_32_characters_long!'):
            # Clear any existing cached instance
            models.database._cipher_suite = None
            
            cipher1 = get_cipher_suite()
            cipher2 = get_cipher_suite()
            assert cipher1 is cipher2  # Should be the same instance

    def test_cipher_suite_key_derivation(self):
        """Test that cipher suite properly derives key from secret."""
        test_secret = 'test_secret_key_for_derivation'
        
        with patch('config.get_secret_key', return_value=test_secret):
            # Clear cached instance to force recreation
            models.database._cipher_suite = None
            
            cipher = get_cipher_suite()
            # The Fernet instance should be created with the derived key
            assert isinstance(cipher, Fernet)

    def test_cipher_suite_with_invalid_key(self):
        """Test cipher suite behavior with invalid key."""
        # Fernet keys must be 32 URL-safe base64-encoded bytes
        with patch('config.get_secret_key', return_value='short'):
            # Clear cached instance
            models.database._cipher_suite = None
            
            # This should work because we hash the secret to get proper length
            cipher = get_cipher_suite()
            assert isinstance(cipher, Fernet)


class TestRepositoryModel:
    """Test Repository model encryption and data integrity."""
    
    def setup_method(self):
        """Set up test fixtures."""
        # Mock the cipher suite to avoid config dependencies
        self.mock_cipher = Mock()
        self.mock_cipher.encrypt.return_value = b'encrypted_data'
        self.mock_cipher.decrypt.return_value = b'decrypted_data'
        
        with patch('models.database.get_cipher_suite', return_value=self.mock_cipher):
            self.repository = Repository(
                name="test-repo",
                path="/path/to/repo"
            )

    def test_repository_creation(self):
        """Test basic repository creation."""
        repo = Repository(name="test", path="/test/path")
        assert repo.name == "test"
        assert repo.path == "/test/path"
        assert repo.created_at is None  # Not set until added to session

    def test_set_passphrase_encryption(self):
        """Test that passphrase is properly encrypted."""
        test_passphrase = "my_secret_passphrase_123!"
        
        with patch('models.database.get_cipher_suite', return_value=self.mock_cipher):
            self.repository.set_passphrase(test_passphrase)
            
            # Should call encrypt with encoded passphrase
            self.mock_cipher.encrypt.assert_called_once_with(test_passphrase.encode())
            # Should store the decoded result
            assert self.repository.encrypted_passphrase == 'encrypted_data'

    def test_get_passphrase_decryption(self):
        """Test that passphrase is properly decrypted."""
        self.repository.encrypted_passphrase = "stored_encrypted_data"
        
        with patch('models.database.get_cipher_suite', return_value=self.mock_cipher):
            result = self.repository.get_passphrase()
            
            # Should call decrypt with encoded encrypted data
            self.mock_cipher.decrypt.assert_called_once_with(b"stored_encrypted_data")
            # Should return the decoded result
            assert result == 'decrypted_data'

    def test_passphrase_roundtrip_encryption(self):
        """Test complete encryption/decryption cycle."""
        original_passphrase = "test_passphrase_with_special_chars!@#$%"
        
        # Use real cipher for full test
        with patch('config.get_secret_key', return_value='test_key_32_chars_long_for_test!'):
            # Clear cached cipher
            models.database._cipher_suite = None
            
            repo = Repository(name="test", path="/test")
            repo.set_passphrase(original_passphrase)
            
            # Verify passphrase was encrypted (not stored in plain text)
            assert repo.encrypted_passphrase != original_passphrase
            assert len(repo.encrypted_passphrase) > len(original_passphrase)
            
            # Verify we can decrypt it back
            decrypted = repo.get_passphrase()
            assert decrypted == original_passphrase

    def test_passphrase_encryption_with_unicode(self):
        """Test passphrase encryption with unicode characters."""
        unicode_passphrase = "pässwörd_with_ünicöde_çhars_日本語"
        
        with patch('config.get_secret_key', return_value='test_key_32_chars_long_for_test!'):
            models.database._cipher_suite = None
            
            repo = Repository(name="test", path="/test")
            repo.set_passphrase(unicode_passphrase)
            decrypted = repo.get_passphrase()
            
            assert decrypted == unicode_passphrase

    def test_passphrase_encryption_empty_string(self):
        """Test passphrase encryption with empty string."""
        with patch('config.get_secret_key', return_value='test_key_32_chars_long_for_test!'):
            models.database._cipher_suite = None
            
            repo = Repository(name="test", path="/test")
            repo.set_passphrase("")
            decrypted = repo.get_passphrase()
            
            assert decrypted == ""

    def test_passphrase_decryption_invalid_data(self):
        """Test handling of invalid encrypted data."""
        repo = Repository(name="test", path="/test")
        repo.encrypted_passphrase = "invalid_encrypted_data"
        
        mock_cipher = Mock()
        mock_cipher.decrypt.side_effect = InvalidToken("Invalid token")
        
        with patch('models.database.get_cipher_suite', return_value=mock_cipher):
            with pytest.raises(InvalidToken):
                repo.get_passphrase()

    def test_passphrase_encryption_with_long_passphrase(self):
        """Test encryption with very long passphrase."""
        long_passphrase = "a" * 1000  # 1000 character passphrase
        
        with patch('config.get_secret_key', return_value='test_key_32_chars_long_for_test!'):
            models.database._cipher_suite = None
            
            repo = Repository(name="test", path="/test")
            repo.set_passphrase(long_passphrase)
            decrypted = repo.get_passphrase()
            
            assert decrypted == long_passphrase


class TestUserModel:
    """Test User model password hashing and authentication."""
    
    def test_user_creation(self):
        """Test basic user creation."""
        user = User(username="testuser")
        assert user.username == "testuser"
        assert user.password_hash is None
        assert user.created_at is None  # Not set until added to session

    def test_set_password_hashing(self):
        """Test that password is properly hashed."""
        user = User(username="testuser")
        password = "my_secure_password_123!"
        
        user.set_password(password)
        
        # Password should be hashed, not stored in plain text
        assert user.password_hash != password
        assert user.password_hash is not None
        assert len(user.password_hash) > 20  # Bcrypt hashes are long
        assert user.password_hash.startswith('$2b$')  # Bcrypt identifier

    def test_verify_password_correct(self):
        """Test password verification with correct password."""
        user = User(username="testuser")
        password = "my_secure_password_123!"
        
        user.set_password(password)
        assert user.verify_password(password) is True

    def test_verify_password_incorrect(self):
        """Test password verification with incorrect password."""
        user = User(username="testuser")
        password = "my_secure_password_123!"
        wrong_password = "wrong_password"
        
        user.set_password(password)
        assert user.verify_password(wrong_password) is False

    def test_password_hashing_consistency(self):
        """Test that same password produces different hashes (due to salt)."""
        user1 = User(username="user1")
        user2 = User(username="user2")
        same_password = "identical_password"
        
        user1.set_password(same_password)
        user2.set_password(same_password)
        
        # Hashes should be different due to salt
        assert user1.password_hash != user2.password_hash
        
        # But both should verify correctly
        assert user1.verify_password(same_password) is True
        assert user2.verify_password(same_password) is True

    def test_password_with_unicode_characters(self):
        """Test password hashing with unicode characters."""
        user = User(username="testuser")
        unicode_password = "pässwörd_ünicöde_日本語"
        
        user.set_password(unicode_password)
        assert user.verify_password(unicode_password) is True
        assert user.verify_password("wrong_password") is False

    def test_empty_password_handling(self):
        """Test handling of empty password."""
        user = User(username="testuser")
        
        user.set_password("")
        assert user.password_hash != ""
        assert user.verify_password("") is True
        assert user.verify_password("not_empty") is False

    def test_very_long_password(self):
        """Test password hashing with very long password."""
        user = User(username="testuser")
        long_password = "a" * 1000  # 1000 character password
        
        user.set_password(long_password)
        assert user.verify_password(long_password) is True

    def test_password_with_special_characters(self):
        """Test password with various special characters."""
        user = User(username="testuser")
        special_password = "!@#$%^&*()_+-=[]{}|;:'\",.<>?/`~"
        
        user.set_password(special_password)
        assert user.verify_password(special_password) is True


class TestCloudSyncConfigModel:
    """Test CloudSyncConfig model credential encryption."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.mock_cipher = Mock()
        self.mock_cipher.encrypt.side_effect = lambda x: f"encrypted_{x.decode()}".encode()
        self.mock_cipher.decrypt.side_effect = lambda x: x.decode().replace("encrypted_", "").encode()

    def test_s3_credentials_encryption(self):
        """Test S3 credentials are properly encrypted."""
        config = CloudSyncConfig(
            name="test-s3",
            provider="s3",
            bucket_name="test-bucket"
        )
        
        access_key = "AKIAIOSFODNN7EXAMPLE"
        secret_key = "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
        
        with patch('models.database.get_cipher_suite', return_value=self.mock_cipher):
            config.set_credentials(access_key, secret_key)
            
            # Should encrypt both keys
            assert config.encrypted_access_key == "encrypted_AKIAIOSFODNN7EXAMPLE"
            assert config.encrypted_secret_key == "encrypted_wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"

    def test_s3_credentials_decryption(self):
        """Test S3 credentials are properly decrypted."""
        config = CloudSyncConfig(name="test-s3", provider="s3")
        config.encrypted_access_key = "encrypted_AKIAIOSFODNN7EXAMPLE"
        config.encrypted_secret_key = "encrypted_wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
        
        with patch('models.database.get_cipher_suite', return_value=self.mock_cipher):
            access_key, secret_key = config.get_credentials()
            
            assert access_key == "AKIAIOSFODNN7EXAMPLE"
            assert secret_key == "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"

    def test_sftp_credentials_encryption(self):
        """Test SFTP credentials are properly encrypted."""
        config = CloudSyncConfig(
            name="test-sftp",
            provider="sftp",
            host="example.com",
            username="testuser"
        )
        
        password = "secure_password_123"
        private_key = "-----BEGIN PRIVATE KEY-----\nMIIEvgIBADANBgkqhkiG9w0BA...\n-----END PRIVATE KEY-----"
        
        with patch('models.database.get_cipher_suite', return_value=self.mock_cipher):
            config.set_sftp_credentials(password=password, private_key=private_key)
            
            assert config.encrypted_password == "encrypted_secure_password_123"
            assert "encrypted_-----BEGIN PRIVATE KEY-----" in config.encrypted_private_key

    def test_sftp_credentials_decryption(self):
        """Test SFTP credentials are properly decrypted."""
        config = CloudSyncConfig(name="test-sftp", provider="sftp")
        config.encrypted_password = "encrypted_secure_password_123"
        config.encrypted_private_key = "encrypted_-----BEGIN PRIVATE KEY-----\ntest_key\n-----END PRIVATE KEY-----"
        
        with patch('models.database.get_cipher_suite', return_value=self.mock_cipher):
            password, private_key = config.get_sftp_credentials()
            
            assert password == "secure_password_123"
            assert "-----BEGIN PRIVATE KEY-----" in private_key

    def test_sftp_credentials_partial_encryption(self):
        """Test SFTP credentials with only password or only key."""
        config = CloudSyncConfig(name="test-sftp", provider="sftp")
        
        with patch('models.database.get_cipher_suite', return_value=self.mock_cipher):
            # Set only password
            config.set_sftp_credentials(password="test_password")
            assert config.encrypted_password == "encrypted_test_password"
            assert config.encrypted_private_key is None
            
            # Set only private key
            config2 = CloudSyncConfig(name="test-sftp2", provider="sftp")
            config2.set_sftp_credentials(private_key="test_key")
            assert config2.encrypted_password is None
            assert config2.encrypted_private_key == "encrypted_test_key"

    def test_sftp_credentials_empty_decryption(self):
        """Test SFTP credentials decryption when fields are empty."""
        config = CloudSyncConfig(name="test-sftp", provider="sftp")
        # Leave encrypted fields as None
        
        with patch('models.database.get_cipher_suite', return_value=self.mock_cipher):
            password, private_key = config.get_sftp_credentials()
            
            assert password == ""
            assert private_key == ""

    def test_credentials_roundtrip_encryption(self):
        """Test complete credential encryption/decryption cycle."""
        original_access = "AKIATEST123EXAMPLE"
        original_secret = "secretKeyExample123!@#"
        
        with patch('config.get_secret_key', return_value='test_key_32_chars_long_for_test!'):
            models.database._cipher_suite = None
            
            config = CloudSyncConfig(name="test", provider="s3")
            config.set_credentials(original_access, original_secret)
            
            # Verify credentials were encrypted
            assert config.encrypted_access_key != original_access
            assert config.encrypted_secret_key != original_secret
            
            # Verify we can decrypt them back
            decrypted_access, decrypted_secret = config.get_credentials()
            assert decrypted_access == original_access
            assert decrypted_secret == original_secret


class TestNotificationConfigModel:
    """Test NotificationConfig model credential encryption."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.mock_cipher = Mock()
        self.mock_cipher.encrypt.side_effect = lambda x: f"encrypted_{x.decode()}".encode()
        self.mock_cipher.decrypt.side_effect = lambda x: x.decode().replace("encrypted_", "").encode()

    def test_pushover_credentials_encryption(self):
        """Test Pushover credentials are properly encrypted."""
        config = NotificationConfig(
            name="test-pushover",
            provider="pushover"
        )
        
        user_key = "u4t8z5j2k9x7m1n3q6r8s4v2w9y5z7a2"
        app_token = "a3g7h2j5k8l4m9n6p1q4r7s2t5v8w3x6"
        
        with patch('models.database.get_cipher_suite', return_value=self.mock_cipher):
            config.set_pushover_credentials(user_key, app_token)
            
            assert config.encrypted_user_key == f"encrypted_{user_key}"
            assert config.encrypted_app_token == f"encrypted_{app_token}"

    def test_pushover_credentials_decryption(self):
        """Test Pushover credentials are properly decrypted."""
        config = NotificationConfig(name="test-pushover", provider="pushover")
        config.encrypted_user_key = "encrypted_u4t8z5j2k9x7m1n3q6r8s4v2w9y5z7a2"
        config.encrypted_app_token = "encrypted_a3g7h2j5k8l4m9n6p1q4r7s2t5v8w3x6"
        
        with patch('models.database.get_cipher_suite', return_value=self.mock_cipher):
            user_key, app_token = config.get_pushover_credentials()
            
            assert user_key == "u4t8z5j2k9x7m1n3q6r8s4v2w9y5z7a2"
            assert app_token == "a3g7h2j5k8l4m9n6p1q4r7s2t5v8w3x6"

    def test_pushover_credentials_roundtrip(self):
        """Test complete Pushover credential encryption/decryption cycle."""
        original_user_key = "test_user_key_12345"
        original_app_token = "test_app_token_67890"
        
        with patch('config.get_secret_key', return_value='test_key_32_chars_long_for_test!'):
            models.database._cipher_suite = None
            
            config = NotificationConfig(name="test", provider="pushover")
            config.set_pushover_credentials(original_user_key, original_app_token)
            
            # Verify credentials were encrypted
            assert config.encrypted_user_key != original_user_key
            assert config.encrypted_app_token != original_app_token
            
            # Verify we can decrypt them back
            decrypted_user_key, decrypted_app_token = config.get_pushover_credentials()
            assert decrypted_user_key == original_user_key
            assert decrypted_app_token == original_app_token


class TestEncryptionSecurity:
    """Test encryption security aspects and edge cases."""
    
    def test_encryption_with_different_keys(self):
        """Test that different keys produce different encrypted data."""
        test_data = "sensitive_information"
        
        with patch('config.get_secret_key', return_value='key1_32_chars_long_for_testing!'):
            models.database._cipher_suite = None
            
            repo1 = Repository(name="test1", path="/test1")
            repo1.set_passphrase(test_data)
            encrypted1 = repo1.encrypted_passphrase
        
        with patch('config.get_secret_key', return_value='key2_32_chars_long_for_testing!'):
            models.database._cipher_suite = None
            
            repo2 = Repository(name="test2", path="/test2")
            repo2.set_passphrase(test_data)
            encrypted2 = repo2.encrypted_passphrase
        
        # Different keys should produce different encrypted data
        assert encrypted1 != encrypted2

    def test_encryption_with_same_data_different_instances(self):
        """Test that same data produces different encrypted results (due to randomness)."""
        test_data = "identical_data"
        
        with patch('config.get_secret_key', return_value='test_key_32_chars_long_for_test!'):
            models.database._cipher_suite = None
            
            repo1 = Repository(name="test1", path="/test1")
            repo1.set_passphrase(test_data)
            
            repo2 = Repository(name="test2", path="/test2")
            repo2.set_passphrase(test_data)
            
            # Fernet includes random IV, so encrypted data should be different
            assert repo1.encrypted_passphrase != repo2.encrypted_passphrase
            
            # But both should decrypt to the same value
            assert repo1.get_passphrase() == test_data
            assert repo2.get_passphrase() == test_data

    def test_encryption_invalid_token_handling(self):
        """Test handling of corrupted encrypted data."""
        repo = Repository(name="test", path="/test")
        
        with patch('config.get_secret_key', return_value='test_key_32_chars_long_for_test!'):
            models.database._cipher_suite = None
            
            # Set valid encrypted data first
            repo.set_passphrase("test_data")
            
            # Corrupt the encrypted data
            repo.encrypted_passphrase = "corrupted_invalid_token_data"
            
            # Should raise InvalidToken exception
            with pytest.raises(InvalidToken):
                repo.get_passphrase()

    def test_encryption_with_binary_data(self):
        """Test encryption with data containing binary characters."""
        binary_like_data = "data_with_\x00_null_\xff_bytes"
        
        with patch('config.get_secret_key', return_value='test_key_32_chars_long_for_test!'):
            models.database._cipher_suite = None
            
            repo = Repository(name="test", path="/test")
            repo.set_passphrase(binary_like_data)
            decrypted = repo.get_passphrase()
            
            assert decrypted == binary_like_data


class TestModelRelationships:
    """Test database model relationships and constraints."""
    
    def test_repository_model_fields(self):
        """Test Repository model has all required fields."""
        repo = Repository(name="test", path="/test")
        
        # Test required fields exist
        assert hasattr(repo, 'id')
        assert hasattr(repo, 'name')
        assert hasattr(repo, 'path')
        assert hasattr(repo, 'encrypted_passphrase')
        assert hasattr(repo, 'created_at')
        
        # Test relationships exist
        assert hasattr(repo, 'jobs')
        assert hasattr(repo, 'schedules')

    def test_user_model_fields(self):
        """Test User model has all required fields."""
        user = User(username="test")
        
        # Test required fields exist
        assert hasattr(user, 'id')
        assert hasattr(user, 'username')
        assert hasattr(user, 'password_hash')
        assert hasattr(user, 'created_at')
        assert hasattr(user, 'last_login')
        
        # Test relationships exist
        assert hasattr(user, 'sessions')

    def test_cloud_sync_config_model_fields(self):
        """Test CloudSyncConfig model has all required fields."""
        config = CloudSyncConfig(name="test", provider="s3")
        
        # Test required fields exist
        assert hasattr(config, 'id')
        assert hasattr(config, 'name')
        assert hasattr(config, 'provider')
        assert hasattr(config, 'bucket_name')
        assert hasattr(config, 'encrypted_access_key')
        assert hasattr(config, 'encrypted_secret_key')
        
        # Test SFTP fields exist
        assert hasattr(config, 'host')
        assert hasattr(config, 'port')
        assert hasattr(config, 'username')
        assert hasattr(config, 'encrypted_password')
        assert hasattr(config, 'encrypted_private_key')
        assert hasattr(config, 'remote_path')

    def test_notification_config_model_fields(self):
        """Test NotificationConfig model has all required fields."""
        config = NotificationConfig(name="test", provider="pushover")
        
        # Test required fields exist
        assert hasattr(config, 'id')
        assert hasattr(config, 'name')
        assert hasattr(config, 'provider')
        assert hasattr(config, 'encrypted_user_key')
        assert hasattr(config, 'encrypted_app_token')
        assert hasattr(config, 'notify_on_success')
        assert hasattr(config, 'notify_on_failure')
        assert hasattr(config, 'enabled')