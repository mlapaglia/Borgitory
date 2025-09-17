"""
Tests for registry-based schema validation functionality.

These tests verify that the new validate_provider_config function
correctly validates configurations using the registry pattern.
"""

import pytest
from pydantic import ValidationError
from borgitory.services.cloud_providers.registry import validate_provider_config
from borgitory.models.schemas import CloudSyncConfigCreate, CloudSyncConfigUpdate


class TestRegistryValidation:
    """Test the validate_provider_config function directly"""

    def setup_method(self) -> None:
        """Import storage modules to ensure providers are registered"""

    def test_validate_s3_config_valid(self) -> None:
        """Test validating a valid S3 configuration"""
        config = {
            "bucket_name": "my-backup-bucket",
            "access_key": "AKIAIOSFODNN7EXAMPLE",
            "secret_key": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
        }

        # Should not raise any exception
        validate_provider_config("s3", config)

    def test_validate_s3_config_missing_required_field(self) -> None:
        """Test validating S3 config with missing required field"""
        config = {
            "access_key": "AKIAIOSFODNN7EXAMPLE",
            "secret_key": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
            # Missing bucket_name
        }

        with pytest.raises(ValueError, match="Invalid s3 configuration"):
            validate_provider_config("s3", config)

    def test_validate_sftp_config_valid(self) -> None:
        """Test validating a valid SFTP configuration"""
        config = {
            "host": "sftp.example.com",
            "username": "backup-user",
            "password": "secret123",
            "remote_path": "/backups",
        }

        # Should not raise any exception
        validate_provider_config("sftp", config)

    def test_validate_sftp_config_missing_required_field(self) -> None:
        """Test validating SFTP config with missing required field"""
        config = {
            "username": "backup-user",
            "password": "secret123",
            "remote_path": "/backups",
            # Missing host
        }

        with pytest.raises(ValueError, match="Invalid sftp configuration"):
            validate_provider_config("sftp", config)

    def test_validate_smb_config_valid(self) -> None:
        """Test validating a valid SMB configuration"""
        config = {
            "host": "fileserver.company.com",
            "user": "backup-service",
            "share_name": "backups",
            "pass": "secret123",
        }

        # Should not raise any exception
        validate_provider_config("smb", config)

    def test_validate_unknown_provider(self) -> None:
        """Test validating config for unknown provider"""
        config = {"some_field": "some_value"}

        with pytest.raises(ValueError, match="Unknown provider: unknown"):
            validate_provider_config("unknown", config)

    def test_validate_empty_provider(self) -> None:
        """Test validating config with empty provider"""
        config = {"some_field": "some_value"}

        with pytest.raises(ValueError, match="Provider is required"):
            validate_provider_config("", config)

    def test_validate_empty_config(self) -> None:
        """Test validating with empty config"""
        with pytest.raises(ValueError, match="Configuration is required"):
            validate_provider_config("s3", {})

    def test_validate_none_config(self) -> None:
        """Test validating with None config"""
        with pytest.raises(ValueError, match="Configuration is required"):
            validate_provider_config("s3", None)


class TestCloudSyncConfigCreateValidation:
    """Test CloudSyncConfigCreate schema validation using registry"""

    def setup_method(self) -> None:
        """Import storage modules to ensure providers are registered"""

    def test_create_config_valid_s3(self) -> None:
        """Test creating valid S3 config"""
        config_data = {
            "name": "My S3 Backup",
            "provider": "s3",
            "provider_config": {
                "bucket_name": "my-backup-bucket",
                "access_key": "AKIAIOSFODNN7EXAMPLE",
                "secret_key": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
            },
        }

        # Should not raise any exception
        config = CloudSyncConfigCreate(**config_data)
        assert config.name == "My S3 Backup"
        assert config.provider == "s3"

    def test_create_config_valid_sftp(self) -> None:
        """Test creating valid SFTP config"""
        config_data = {
            "name": "My SFTP Backup",
            "provider": "sftp",
            "provider_config": {
                "host": "sftp.example.com",
                "username": "backup-user",
                "password": "secret123",
                "remote_path": "/backups",
            },
        }

        # Should not raise any exception
        config = CloudSyncConfigCreate(**config_data)
        assert config.name == "My SFTP Backup"
        assert config.provider == "sftp"

    def test_create_config_valid_smb(self) -> None:
        """Test creating valid SMB config"""
        config_data = {
            "name": "My SMB Backup",
            "provider": "smb",
            "provider_config": {
                "host": "fileserver.company.com",
                "user": "backup-service",
                "share_name": "backups",
                "pass": "secret123",
            },
        }

        # Should not raise any exception
        config = CloudSyncConfigCreate(**config_data)
        assert config.name == "My SMB Backup"
        assert config.provider == "smb"

    def test_create_config_invalid_s3(self) -> None:
        """Test creating invalid S3 config"""
        config_data = {
            "name": "My S3 Backup",
            "provider": "s3",
            "provider_config": {
                "access_key": "AKIAIOSFODNN7EXAMPLE",
                "secret_key": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
                # Missing bucket_name
            },
        }

        with pytest.raises(ValidationError, match="Invalid s3 configuration"):
            CloudSyncConfigCreate(**config_data)

    def test_create_config_empty_provider_config(self) -> None:
        """Test creating config with empty provider_config"""
        config_data = {"name": "My Backup", "provider": "s3", "provider_config": {}}

        with pytest.raises(ValidationError, match="provider_config is required"):
            CloudSyncConfigCreate(**config_data)

    def test_create_config_missing_provider_config(self) -> None:
        """Test creating config with missing provider_config"""
        config_data = {
            "name": "My Backup",
            "provider": "s3",
            # Missing provider_config
        }

        with pytest.raises(ValidationError, match="provider_config is required"):
            CloudSyncConfigCreate(**config_data)


class TestCloudSyncConfigUpdateValidation:
    """Test CloudSyncConfigUpdate schema validation using registry"""

    def setup_method(self) -> None:
        """Import storage modules to ensure providers are registered"""

    def test_update_config_valid_s3(self) -> None:
        """Test updating with valid S3 config"""
        config_data = {
            "name": "Updated S3 Backup",
            "provider": "s3",
            "provider_config": {
                "bucket_name": "updated-backup-bucket",
                "access_key": "AKIAIOSFODNN7EXAMPLE",
                "secret_key": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
            },
        }

        # Should not raise any exception
        config = CloudSyncConfigUpdate(**config_data)
        assert config.name == "Updated S3 Backup"
        assert config.provider == "s3"

    def test_update_config_partial_update(self) -> None:
        """Test partial update (name only)"""
        config_data = {"name": "Updated Name Only"}

        # Should not raise any exception (no validation needed)
        config = CloudSyncConfigUpdate(**config_data)
        assert config.name == "Updated Name Only"
        assert config.provider is None
        assert config.provider_config is None

    def test_update_config_provider_only(self) -> None:
        """Test updating provider only (should not validate)"""
        config_data = {"provider": "sftp"}

        # Should not raise any exception (validation only runs when both are provided)
        config = CloudSyncConfigUpdate(**config_data)
        assert config.provider == "sftp"
        assert config.provider_config is None

    def test_update_config_invalid_when_both_provided(self) -> None:
        """Test update validation when both provider and config are provided"""
        config_data = {
            "provider": "s3",
            "provider_config": {
                "access_key": "AKIAIOSFODNN7EXAMPLE",
                "secret_key": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
                # Missing bucket_name
            },
        }

        with pytest.raises(ValidationError, match="Invalid s3 configuration"):
            CloudSyncConfigUpdate(**config_data)

    def test_update_config_empty_provider_config(self) -> None:
        """Test update with empty provider_config (should pass since it's optional)"""
        config_data = {"name": "Updated Name", "provider": "s3", "provider_config": {}}

        # Should not validate since provider_config is empty
        config = CloudSyncConfigUpdate(**config_data)
        assert config.name == "Updated Name"
        assert config.provider == "s3"
        assert config.provider_config == {}
