"""
Comprehensive tests for cloud_providers/config_service.py

This test file ensures complete coverage of the config service layer with
proper DI patterns and real database usage where appropriate.
"""

import pytest
import json

from typing import Callable
from sqlalchemy.orm import Session
from borgitory.services.cloud_providers.config_service import (
    DatabaseConfigLoadService,
    MockConfigLoadService,
)
from borgitory.services.cloud_providers.types import CloudSyncConfig
from borgitory.models.database import CloudSyncConfig as DbCloudSyncConfig
from tests.conftest import create_s3_cloud_sync_config


class TestDatabaseConfigLoadService:
    """Test DatabaseConfigLoadService with real database operations"""

    @pytest.fixture
    def db_session_factory(self, test_db: Session) -> Callable[[], Session]:
        """Factory that returns test database session"""

        def factory() -> Session:
            return test_db

        return factory

    @pytest.fixture
    def service(
        self, db_session_factory: Callable[[], Session]
    ) -> DatabaseConfigLoadService:
        return DatabaseConfigLoadService(db_session_factory)

    @pytest.mark.asyncio
    async def test_load_config_success_with_json_config(
        self, service: DatabaseConfigLoadService, test_db: Session
    ) -> None:
        """Test loading config with new JSON-based configuration"""
        # Create config with JSON provider_config
        provider_config = {
            "bucket_name": "test-bucket",
            "access_key": "AKIA123",
            "secret_key": "secret456",
            "region": "us-east-1",
        }

        db_config = DbCloudSyncConfig()
        db_config.name = "test-s3"
        db_config.provider = "s3"
        db_config.provider_config = json.dumps(provider_config)
        db_config.path_prefix = "backups/"
        db_config.enabled = True
        test_db.add(db_config)
        test_db.commit()
        test_db.refresh(db_config)

        result = await service.load_config(db_config.id)

        assert result is not None
        assert isinstance(result, CloudSyncConfig)
        assert result.provider == "s3"
        assert result.config == provider_config
        assert result.path_prefix == "backups/"
        assert result.name == "test-s3"

    @pytest.mark.asyncio
    async def test_load_config_not_found(
        self, service: DatabaseConfigLoadService, test_db: Session
    ) -> None:
        """Test loading non-existent config"""
        result = await service.load_config(999)

        assert result is None

    @pytest.mark.asyncio
    async def test_load_config_disabled(
        self, service: DatabaseConfigLoadService, test_db: Session
    ) -> None:
        """Test loading disabled config returns None"""
        db_config = create_s3_cloud_sync_config(
            name="disabled-config",
            bucket_name="test-bucket",
            enabled=False,  # Disabled
        )
        test_db.add(db_config)
        test_db.commit()
        test_db.refresh(db_config)

        result = await service.load_config(db_config.id)

        assert result is None

    @pytest.mark.asyncio
    async def test_load_config_with_empty_path_prefix(
        self, service: DatabaseConfigLoadService, test_db: Session
    ) -> None:
        """Test loading config with empty path prefix"""
        provider_config = {
            "bucket_name": "test-bucket",
            "access_key": "key",
            "secret_key": "secret",
        }

        db_config = DbCloudSyncConfig()
        db_config.name = "no-prefix"
        db_config.provider = "s3"
        db_config.provider_config = json.dumps(provider_config)
        db_config.path_prefix = ""  # No prefix
        db_config.enabled = True
        test_db.add(db_config)
        test_db.commit()
        test_db.refresh(db_config)

        result = await service.load_config(db_config.id)

        assert result is not None
        assert result.path_prefix == ""  # Should default to empty string

    @pytest.mark.asyncio
    async def test_load_config_database_error(
        self, service: DatabaseConfigLoadService
    ) -> None:
        """Test handling database errors gracefully"""

        # Create a service with a broken session factory
        def broken_factory() -> None:
            raise Exception("Database connection failed")

        broken_service = DatabaseConfigLoadService(broken_factory)

        result = await broken_service.load_config(1)

        assert result is None  # Should handle error gracefully

    @pytest.mark.asyncio
    async def test_load_config_json_parse_error(
        self, service: DatabaseConfigLoadService, test_db: Session
    ) -> None:
        """Test handling invalid JSON in provider_config"""
        db_config = DbCloudSyncConfig()
        db_config.name = "invalid-json"
        db_config.provider = "s3"
        db_config.provider_config = "invalid json{"  # Malformed JSON
        db_config.enabled = True
        test_db.add(db_config)
        test_db.commit()
        test_db.refresh(db_config)

        result = await service.load_config(db_config.id)

        assert result is None  # Should handle JSON error gracefully

    @pytest.mark.asyncio
    async def test_load_config_with_all_fields(
        self, service: DatabaseConfigLoadService, test_db: Session
    ) -> None:
        """Test loading config with all possible fields populated"""
        provider_config = {
            "bucket_name": "comprehensive-bucket",
            "access_key": "AKIA123",
            "secret_key": "secret456",
            "region": "eu-west-1",
            "storage_class": "GLACIER",
        }

        db_config = DbCloudSyncConfig()
        db_config.name = "comprehensive-config"
        db_config.provider = "s3"
        db_config.provider_config = json.dumps(provider_config)
        db_config.path_prefix = "comprehensive/backups/"
        db_config.enabled = True

        test_db.add(db_config)
        test_db.commit()
        test_db.refresh(db_config)

        result = await service.load_config(db_config.id)

        assert result is not None
        assert result.provider == "s3"
        assert result.config == provider_config
        assert result.path_prefix == "comprehensive/backups/"
        assert result.name == "comprehensive-config"

    @pytest.mark.asyncio
    async def test_multiple_config_loads(
        self, service: DatabaseConfigLoadService, test_db: Session
    ) -> None:
        """Test loading multiple configs in sequence"""
        # Create multiple configs
        configs = []
        for i in range(3):
            provider_config = {
                "bucket_name": f"bucket-{i}",
                "access_key": "key",
                "secret_key": "secret",
            }
            db_config = DbCloudSyncConfig()
            db_config.name = f"config-{i}"
            db_config.provider = "s3"
            db_config.provider_config = json.dumps(provider_config)
            db_config.enabled = True
            test_db.add(db_config)
            configs.append(db_config)

        test_db.commit()
        for config in configs:
            test_db.refresh(config)

        # Load all configs
        results = []
        for config in configs:
            result = await service.load_config(config.id)
            results.append(result)

        # Verify all were loaded correctly
        assert len(results) == 3
        for i, result in enumerate(results):
            assert result is not None
            assert result.name == f"config-{i}"
            assert result.config["bucket_name"] == f"bucket-{i}"

    @pytest.mark.asyncio
    async def test_load_config_with_sftp_provider(
        self, service: DatabaseConfigLoadService, test_db: Session
    ) -> None:
        """Test loading SFTP config with JSON configuration"""
        provider_config = {
            "host": "sftp.example.com",
            "username": "testuser",
            "password": "testpass",
            "remote_path": "/backups",
            "port": 22,
            "host_key_checking": True,
        }

        db_config = DbCloudSyncConfig()
        db_config.name = "test-sftp"
        db_config.provider = "sftp"
        db_config.provider_config = json.dumps(provider_config)
        db_config.path_prefix = "sftp/backups/"
        db_config.enabled = True

        test_db.add(db_config)
        test_db.commit()
        test_db.refresh(db_config)

        result = await service.load_config(db_config.id)

        assert result is not None
        assert result.provider == "sftp"
        assert result.config == provider_config
        assert result.path_prefix == "sftp/backups/"
        assert result.name == "test-sftp"


class TestMockConfigLoadService:
    """Test MockConfigLoadService for testing scenarios"""

    @pytest.fixture
    def sample_configs(self) -> dict[int, CloudSyncConfig]:
        return {
            1: CloudSyncConfig(
                provider="s3",
                config={"bucket_name": "test-bucket-1"},
                name="test-config-1",
                path_prefix="test1/",
            ),
            2: CloudSyncConfig(
                provider="sftp",
                config={"host": "sftp.example.com"},
                name="test-config-2",
            ),
            5: CloudSyncConfig(
                provider="s3",
                config={"bucket_name": "prod-bucket", "region": "us-west-2"},
                name="production-config",
                path_prefix="prod/",
            ),
        }

    @pytest.fixture
    def service(
        self, sample_configs: dict[int, CloudSyncConfig]
    ) -> MockConfigLoadService:
        return MockConfigLoadService(sample_configs)

    @pytest.mark.asyncio
    async def test_load_existing_config(
        self, service: MockConfigLoadService, sample_configs: dict[int, CloudSyncConfig]
    ) -> None:
        """Test loading existing config from mock service"""
        result = await service.load_config(1)

        assert result is not None
        assert result == sample_configs[1]
        assert result.provider == "s3"
        assert result.name == "test-config-1"
        assert result.path_prefix == "test1/"

    @pytest.mark.asyncio
    async def test_load_different_configs(
        self, service: MockConfigLoadService, sample_configs: dict[int, CloudSyncConfig]
    ) -> None:
        """Test loading different configs by ID"""
        result1 = await service.load_config(1)
        result2 = await service.load_config(2)
        result5 = await service.load_config(5)

        assert result1 is not None
        assert result1.provider == "s3"
        assert result1.name == "test-config-1"

        assert result2 is not None
        assert result2.provider == "sftp"
        assert result2.name == "test-config-2"

        assert result5 is not None
        assert result5.provider == "s3"
        assert result5.name == "production-config"
        assert result5.path_prefix == "prod/"

    @pytest.mark.asyncio
    async def test_load_nonexistent_config(
        self, service: MockConfigLoadService
    ) -> None:
        """Test loading config that doesn't exist"""
        result = await service.load_config(999)

        assert result is None

    @pytest.mark.asyncio
    async def test_load_config_with_zero_id(
        self, service: MockConfigLoadService, sample_configs: dict[int, CloudSyncConfig]
    ) -> None:
        """Test loading config with ID 0 (edge case)"""
        # Add config with ID 0
        sample_configs[0] = CloudSyncConfig(
            provider="s3", config={"bucket_name": "zero-bucket"}, name="zero-config"
        )
        service_with_zero = MockConfigLoadService(sample_configs)

        result = await service_with_zero.load_config(0)

        assert result is not None
        assert result.name == "zero-config"

    def test_empty_configs(self) -> None:
        """Test mock service with no configs"""
        empty_service = MockConfigLoadService({})

        # Should work without error
        assert empty_service._configs == {}

    @pytest.mark.asyncio
    async def test_empty_configs_load(self) -> None:
        """Test loading from empty config service"""
        empty_service = MockConfigLoadService({})

        result = await empty_service.load_config(1)

        assert result is None

    @pytest.mark.asyncio
    async def test_mock_service_with_complex_configs(
        self, service: MockConfigLoadService
    ) -> None:
        """Test mock service with complex configuration data"""
        complex_configs = {
            100: CloudSyncConfig(
                provider="s3",
                config={
                    "bucket_name": "complex-bucket",
                    "access_key": "AKIA" + "X" * 16,
                    "secret_key": "secret" + "Y" * 35,
                    "region": "eu-central-1",
                    "storage_class": "INTELLIGENT_TIERING",
                    "server_side_encryption": "AES256",
                },
                name="complex-s3-config",
                path_prefix="complex/nested/path/",
            ),
            200: CloudSyncConfig(
                provider="sftp",
                config={
                    "host": "complex-sftp.example.com",
                    "port": 2222,
                    "username": "complex_user",
                    "password": "complex_password_123!@#",
                    "remote_path": "/complex/remote/path",
                    "host_key_checking": False,
                    "timeout": 60,
                    "max_connections": 5,
                },
                name="complex-sftp-config",
            ),
        }

        service = MockConfigLoadService(complex_configs)

        # Load complex S3 config
        s3_result = await service.load_config(100)
        assert s3_result is not None
        assert s3_result.provider == "s3"
        assert s3_result.config["storage_class"] == "INTELLIGENT_TIERING"
        assert s3_result.path_prefix == "complex/nested/path/"

        # Load complex SFTP config
        sftp_result = await service.load_config(200)
        assert sftp_result is not None
        assert sftp_result.provider == "sftp"
        assert sftp_result.config["port"] == 2222
        assert sftp_result.config["host_key_checking"] is False
        assert sftp_result.config["max_connections"] == 5

    @pytest.mark.asyncio
    async def test_mock_service_returns_same_reference(
        self, service: MockConfigLoadService, sample_configs: dict[int, CloudSyncConfig]
    ) -> None:
        """Test that mock service returns the same object reference"""
        result1 = await service.load_config(1)
        result2 = await service.load_config(1)

        # Should return the same object from the dictionary
        assert result1 is result2
        assert result1 is sample_configs[1]

    @pytest.mark.asyncio
    async def test_mock_service_with_different_provider_types(
        self, service: MockConfigLoadService
    ) -> None:
        """Test mock service handles different provider types correctly"""
        # Test S3 config
        s3_result = await service.load_config(1)
        assert s3_result is not None
        assert s3_result.provider == "s3"
        assert "bucket_name" in s3_result.config

        # Test SFTP config
        sftp_result = await service.load_config(2)
        assert sftp_result is not None
        assert sftp_result.provider == "sftp"
        assert "host" in sftp_result.config
