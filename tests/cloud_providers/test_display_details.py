"""
Tests for provider display details functionality.

These tests verify that each storage provider correctly implements
the get_display_details method and returns properly formatted HTML.
"""

from borgitory.services.cloud_providers.storage.s3_storage import S3Storage
from borgitory.services.cloud_providers.storage.sftp_storage import SFTPStorage
from borgitory.services.cloud_providers.storage.smb_storage import SMBStorage


class TestS3DisplayDetails:
    """Test S3 display details functionality"""

    def test_s3_display_details_basic(self) -> None:
        """Test S3 display details with basic configuration"""
        storage = S3Storage(None, None)  # Mock dependencies not needed for this method
        config = {
            "bucket_name": "my-backup-bucket",
            "region": "us-west-2",
            "storage_class": "GLACIER",
        }

        result = storage.get_display_details(config)

        assert result["provider_name"] == "AWS S3"
        assert "my-backup-bucket" in result["provider_details"]
        assert "us-west-2" in result["provider_details"]
        assert "GLACIER" in result["provider_details"]
        assert "<div><strong>Bucket:</strong>" in result["provider_details"]

    def test_s3_display_details_defaults(self) -> None:
        """Test S3 display details with default values"""
        storage = S3Storage(None, None)
        config = {"bucket_name": "test-bucket"}  # Minimal config

        result = storage.get_display_details(config)

        assert result["provider_name"] == "AWS S3"
        assert "test-bucket" in result["provider_details"]
        assert "us-east-1" in result["provider_details"]  # Default region
        assert "STANDARD" in result["provider_details"]  # Default storage class

    def test_s3_display_details_missing_values(self) -> None:
        """Test S3 display details with missing values"""
        storage = S3Storage(None, None)
        config = {}  # Empty config

        result = storage.get_display_details(config)

        assert result["provider_name"] == "AWS S3"
        assert "Unknown" in result["provider_details"]


class TestSFTPDisplayDetails:
    """Test SFTP display details functionality"""

    def test_sftp_display_details_basic(self) -> None:
        """Test SFTP display details with basic configuration"""
        storage = SFTPStorage(None, None)
        config = {
            "host": "sftp.example.com",
            "port": 2222,
            "username": "backup-user",
            "remote_path": "/backups/borgitory",
            "password": "secret123",
        }

        result = storage.get_display_details(config)

        assert result["provider_name"] == "SFTP (SSH)"
        assert "sftp.example.com:2222" in result["provider_details"]
        assert "backup-user" in result["provider_details"]
        assert "/backups/borgitory" in result["provider_details"]
        assert "password" in result["provider_details"]  # Auth method

    def test_sftp_display_details_private_key_auth(self) -> None:
        """Test SFTP display details with private key authentication"""
        storage = SFTPStorage(None, None)
        config = {
            "host": "server.example.com",
            "port": 22,
            "username": "user",
            "remote_path": "/home/user/backups",
            "private_key": "-----BEGIN RSA PRIVATE KEY-----\n...",
        }

        result = storage.get_display_details(config)

        assert result["provider_name"] == "SFTP (SSH)"
        assert "server.example.com:22" in result["provider_details"]
        assert "private_key" in result["provider_details"]  # Auth method

    def test_sftp_display_details_defaults(self) -> None:
        """Test SFTP display details with default values"""
        storage = SFTPStorage(None, None)
        config = {"host": "test.example.com", "username": "testuser"}

        result = storage.get_display_details(config)

        assert result["provider_name"] == "SFTP (SSH)"
        assert "test.example.com:22" in result["provider_details"]  # Default port
        assert (
            "private_key" in result["provider_details"]
        )  # Default auth method when no password


class TestSMBDisplayDetails:
    """Test SMB display details functionality"""

    def test_smb_display_details_basic(self) -> None:
        """Test SMB display details with basic configuration"""
        storage = SMBStorage(None, None)
        config = {
            "host": "fileserver.company.com",
            "port": 445,
            "user": "backup-service",
            "domain": "COMPANY",
            "share_name": "backups",
            "pass": "secret123",
        }

        result = storage.get_display_details(config)

        assert result["provider_name"] == "SMB/CIFS"
        assert "fileserver.company.com:445" in result["provider_details"]
        assert "backups" in result["provider_details"]
        assert "COMPANY\\backup-service" in result["provider_details"]
        assert "password" in result["provider_details"]  # Auth method

    def test_smb_display_details_kerberos(self) -> None:
        """Test SMB display details with Kerberos authentication"""
        storage = SMBStorage(None, None)
        config = {
            "host": "server.domain.com",
            "port": 445,
            "user": "service-account",
            "domain": "DOMAIN",
            "share_name": "shared-folder",
            "use_kerberos": True,
        }

        result = storage.get_display_details(config)

        assert result["provider_name"] == "SMB/CIFS"
        assert "server.domain.com:445" in result["provider_details"]
        assert "shared-folder" in result["provider_details"]
        assert "DOMAIN\\service-account" in result["provider_details"]
        assert "kerberos" in result["provider_details"]  # Auth method

    def test_smb_display_details_defaults(self) -> None:
        """Test SMB display details with default values"""
        storage = SMBStorage(None, None)
        config = {"host": "nas.local", "user": "admin", "share_name": "backup"}

        result = storage.get_display_details(config)

        assert result["provider_name"] == "SMB/CIFS"
        assert "nas.local:445" in result["provider_details"]  # Default port
        assert "WORKGROUP\\admin" in result["provider_details"]  # Default domain
        assert "password" in result["provider_details"]  # Default auth method


class TestDisplayDetailsIntegration:
    """Test display details integration with the API helper function"""

    def test_get_provider_display_details_function(self) -> None:
        """Test the _get_provider_display_details function from cloud_sync.py"""
        from borgitory.api.cloud_sync import _get_provider_display_details
        from borgitory.services.cloud_providers.registry import get_registry

        registry = get_registry()

        # Test with S3
        s3_config = {"bucket_name": "test-bucket", "region": "eu-west-1"}
        result = _get_provider_display_details(registry, "s3", s3_config)

        assert result["provider_name"] == "AWS S3"
        assert "test-bucket" in result["provider_details"]
        assert "eu-west-1" in result["provider_details"]

    def test_get_provider_display_details_unknown_provider(self) -> None:
        """Test display details function with unknown provider"""
        from borgitory.api.cloud_sync import _get_provider_display_details
        from borgitory.services.cloud_providers.registry import get_registry

        registry = get_registry()
        result = _get_provider_display_details(registry, "unknown", {})

        assert result["provider_name"] == "UNKNOWN"
        assert "Unknown provider" in result["provider_details"]

    def test_get_provider_display_details_empty_provider(self) -> None:
        """Test display details function with empty provider"""
        from borgitory.api.cloud_sync import _get_provider_display_details
        from borgitory.services.cloud_providers.registry import get_registry

        registry = get_registry()
        result = _get_provider_display_details(registry, "", {})

        assert result["provider_name"] == "Unknown"  # Empty provider becomes "Unknown"
        assert "Unknown provider" in result["provider_details"]
