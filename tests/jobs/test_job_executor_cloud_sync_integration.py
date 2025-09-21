"""
Tests for JobExecutor cloud sync integration with proper dependency injection.

This test module specifically ensures that:
1. Job executor uses proper DI for cloud sync operations
2. No hardcoded imports of deprecated classes like CloudProviderFactory
3. Generic rclone dispatchers are used correctly
4. Cloud sync works end-to-end with the registry pattern
"""

import pytest
import json
from unittest.mock import AsyncMock, MagicMock
from sqlalchemy.orm import Session

from borgitory.services.jobs.job_executor import JobExecutor
from borgitory.services.rclone_service import RcloneService
from borgitory.models.database import CloudSyncConfig

# Import registry fixtures


@pytest.fixture
def mock_rclone_service():
    """Mock RcloneService with the generic dispatcher methods"""
    service = MagicMock(spec=RcloneService)

    # Mock the generic dispatcher methods
    async def mock_sync_generator():
        yield {"type": "started", "command": "rclone sync", "pid": 12345}
        yield {
            "type": "progress",
            "percentage": 25,
            "transferred": "100MB",
            "speed": "10MB/s",
        }
        yield {
            "type": "progress",
            "percentage": 50,
            "transferred": "200MB",
            "speed": "10MB/s",
        }
        yield {
            "type": "progress",
            "percentage": 100,
            "transferred": "400MB",
            "speed": "10MB/s",
        }
        yield {"type": "completed", "return_code": 0, "status": "success"}

    # Mock should return the generator directly, not a coroutine
    service.sync_repository_to_provider = MagicMock(return_value=mock_sync_generator())
    service.test_provider_connection = AsyncMock(return_value={"status": "success"})

    return service


@pytest.fixture
def s3_cloud_sync_config(test_db: Session):
    """Create an S3 cloud sync configuration"""
    config = CloudSyncConfig(
        name="Test S3 Config",
        provider="s3",
        provider_config=json.dumps(
            {
                "access_key": "AKIAIOSFODNN7EXAMPLE",  # 20 chars, starts with AKIA
                "secret_key": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",  # 40 chars
                "bucket_name": "test-bucket",
                "region": "us-east-1",
            }
        ),
        enabled=True,
        path_prefix="backups/",
    )
    test_db.add(config)
    test_db.commit()
    test_db.refresh(config)
    return config


@pytest.fixture
def sftp_cloud_sync_config(test_db: Session):
    """Create an SFTP cloud sync configuration"""
    config = CloudSyncConfig(
        name="Test SFTP Config",
        provider="sftp",
        provider_config=json.dumps(
            {
                "host": "sftp.example.com",
                "username": "testuser",
                "password": "testpass",
                "remote_path": "/backup",
                "port": 22,
            }
        ),
        enabled=True,
        path_prefix="repos/",
    )
    test_db.add(config)
    test_db.commit()
    test_db.refresh(config)
    return config


@pytest.fixture
def invalid_s3_config(test_db: Session):
    """Create an invalid S3 configuration (empty provider_config to test error handling)"""
    config = CloudSyncConfig(
        name="Invalid S3 Config",
        provider="s3",
        provider_config="{}",  # Empty JSON to test error handling
        enabled=True,
    )
    test_db.add(config)
    test_db.commit()
    test_db.refresh(config)
    return config


@pytest.fixture
def missing_config_s3_config(test_db: Session):
    """Create an S3 configuration with no provider_config (null)"""
    config = CloudSyncConfig(
        name="Missing Config S3",
        provider="s3",
        provider_config="",  # Empty string to test null handling
        enabled=True,
    )
    test_db.add(config)
    test_db.commit()
    test_db.refresh(config)
    return config


@pytest.fixture
def mock_encryption_service():
    """Create mock encryption service for DI"""
    from unittest.mock import MagicMock

    mock_service = MagicMock()
    # Mock decryption to return the same config (simulating no encryption for tests)
    mock_service.decrypt_sensitive_fields.return_value = {
        "access_key": "AKIAIOSFODNN7EXAMPLE",
        "secret_key": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
        "bucket_name": "test-bucket",
        "region": "us-east-1",
    }
    return mock_service


@pytest.fixture
def mock_storage_factory():
    """Create mock storage factory for DI"""
    from unittest.mock import MagicMock

    return MagicMock()


@pytest.fixture
def job_executor():
    """Create JobExecutor instance"""
    return JobExecutor()


class TestCloudSyncDependencyInjection:
    """Test that cloud sync uses proper dependency injection"""

    async def _execute_cloud_sync_with_di(
        self,
        job_executor,
        config_id,
        test_db,
        mock_rclone_service,
        mock_encryption_service,
        mock_storage_factory,
        mock_provider_registry=None,
        output_callback=None,
    ):
        """Helper method to execute cloud sync with all DI parameters"""
        # Create a mock registry if not provided
        if mock_provider_registry is None:
            from unittest.mock import MagicMock

            mock_provider_registry = MagicMock()
            # Mock the get_metadata method to return a valid metadata object
            mock_metadata = MagicMock()
            mock_metadata.storage_class = MagicMock()
            mock_provider_registry.get_metadata.return_value = mock_metadata

        return await job_executor.execute_cloud_sync_task(
            repository_path="/test/repo/path",
            cloud_sync_config_id=config_id,
            db_session_factory=lambda: test_db,
            rclone_service=mock_rclone_service,
            encryption_service=mock_encryption_service,
            storage_factory=mock_storage_factory,
            provider_registry=mock_provider_registry,
            output_callback=output_callback,
        )

    @pytest.mark.asyncio
    async def test_cloud_sync_uses_injected_rclone_service(
        self,
        job_executor,
        mock_rclone_service,
        s3_cloud_sync_config,
        test_db,
        mock_encryption_service,
        mock_storage_factory,
    ) -> None:
        """Test that cloud sync uses the injected RcloneService, not hardcoded imports"""

        output_messages = []

        def output_callback(message: str) -> None:
            output_messages.append(message)

        # Execute cloud sync with injected dependencies
        result = await self._execute_cloud_sync_with_di(
            job_executor,
            s3_cloud_sync_config.id,
            test_db,
            mock_rclone_service,
            mock_encryption_service,
            mock_storage_factory,
            output_callback=output_callback,
        )

        # Verify the result
        assert result.return_code == 0
        assert result.error is None

        # Verify output messages
        assert "Starting cloud sync..." in output_messages
        assert "Syncing to Test S3 Config (S3)" in output_messages
        assert "Cloud sync completed successfully" in output_messages

        # Verify the generic dispatcher was called correctly
        mock_rclone_service.sync_repository_to_provider.assert_called_once()
        call_args = mock_rclone_service.sync_repository_to_provider.call_args

        # Check provider argument
        assert call_args[1]["provider"] == "s3"

        # Check repository argument
        repository_arg = call_args[1]["repository"]
        assert hasattr(repository_arg, "path")
        assert repository_arg.path == "/test/repo/path"

        # Check provider config arguments
        assert call_args[1]["access_key"] == "AKIAIOSFODNN7EXAMPLE"
        assert call_args[1]["secret_key"] == "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
        assert call_args[1]["bucket_name"] == "test-bucket"
        assert call_args[1]["region"] == "us-east-1"
        assert call_args[1]["path_prefix"] == "backups/"

    @pytest.mark.asyncio
    async def test_cloud_sync_works_with_sftp_provider(
        self,
        job_executor,
        mock_rclone_service,
        sftp_cloud_sync_config,
        test_db,
        mock_encryption_service,
        mock_storage_factory,
    ) -> None:
        """Test cloud sync works with SFTP provider using generic dispatcher"""

        # Update mock to return SFTP config
        mock_encryption_service.decrypt_sensitive_fields.return_value = {
            "host": "sftp.example.com",
            "username": "testuser",
            "password": "testpass",
            "remote_path": "/backup",
            "port": 22,
        }

        result = await self._execute_cloud_sync_with_di(
            job_executor,
            sftp_cloud_sync_config.id,
            test_db,
            mock_rclone_service,
            mock_encryption_service,
            mock_storage_factory,
        )

        assert result.return_code == 0

        # Verify SFTP-specific parameters were passed
        call_args = mock_rclone_service.sync_repository_to_provider.call_args
        assert call_args[1]["provider"] == "sftp"
        assert call_args[1]["host"] == "sftp.example.com"
        assert call_args[1]["username"] == "testuser"
        assert call_args[1]["password"] == "testpass"
        assert call_args[1]["remote_path"] == "/backup"
        assert call_args[1]["port"] == 22
        assert call_args[1]["path_prefix"] == "repos/"

    @pytest.mark.asyncio
    async def test_cloud_sync_handles_invalid_provider_config(
        self,
        job_executor,
        mock_rclone_service,
        invalid_s3_config,
        test_db,
        mock_encryption_service,
        mock_storage_factory,
    ) -> None:
        """Test that configurations with invalid provider_config are handled with clear error messages"""

        result = await self._execute_cloud_sync_with_di(
            job_executor,
            invalid_s3_config.id,
            test_db,
            mock_rclone_service,
            mock_encryption_service,
            mock_storage_factory,
        )

        # Should fail with clear error message about missing configuration
        assert result.return_code == 1
        assert "empty or invalid provider_config" in result.error
        assert "update the configuration through the web UI" in result.error

    @pytest.mark.asyncio
    async def test_cloud_sync_handles_missing_provider_config(
        self,
        job_executor,
        mock_rclone_service,
        missing_config_s3_config,
        test_db,
        mock_encryption_service,
        mock_storage_factory,
    ) -> None:
        """Test that configurations with missing provider_config are handled with clear error messages"""

        result = await self._execute_cloud_sync_with_di(
            job_executor,
            missing_config_s3_config.id,
            test_db,
            mock_rclone_service,
            mock_encryption_service,
            mock_storage_factory,
        )

        # Should fail with clear error message about missing provider_config
        assert result.return_code == 1
        assert "has no provider_config" in result.error
        assert "update the configuration through the web UI" in result.error

    @pytest.mark.asyncio
    async def test_cloud_sync_handles_rclone_service_exception(
        self,
        job_executor,
        s3_cloud_sync_config,
        test_db,
        mock_encryption_service,
        mock_storage_factory,
    ) -> None:
        """Test proper error handling when rclone service throws exception"""

        # Mock rclone service that throws exception
        mock_rclone_service = MagicMock(spec=RcloneService)
        mock_rclone_service.sync_repository_to_provider.side_effect = Exception(
            "Rclone sync failed"
        )

        result = await self._execute_cloud_sync_with_di(
            job_executor,
            s3_cloud_sync_config.id,
            test_db,
            mock_rclone_service,
            mock_encryption_service,
            mock_storage_factory,
        )

        # Should handle the exception gracefully
        assert result.return_code == 1
        assert "Rclone sync failed" in result.error

    # NOTE: The "skip when no config" test has been removed because the skip logic
    # has been moved to the JobManager level. The JobExecutor now requires a valid
    # config_id parameter. Skip logic should be tested at the JobManager level.

    @pytest.mark.asyncio
    async def test_cloud_sync_skips_when_config_disabled(
        self,
        job_executor,
        mock_rclone_service,
        s3_cloud_sync_config,
        test_db,
        mock_encryption_service,
        mock_storage_factory,
    ) -> None:
        """Test that cloud sync is skipped when config is disabled"""

        # Disable the configuration
        s3_cloud_sync_config.enabled = False
        test_db.commit()

        result = await self._execute_cloud_sync_with_di(
            job_executor,
            s3_cloud_sync_config.id,
            test_db,
            mock_rclone_service,
            mock_encryption_service,
            mock_storage_factory,
        )

        assert result.return_code == 0
        assert b"Cloud sync skipped - configuration disabled" in result.stdout

        # RcloneService should not be called
        mock_rclone_service.sync_repository_to_provider.assert_not_called()


class TestNoDeprecatedImports:
    """Test that deprecated imports are not used"""

    def test_no_cloud_provider_factory_import(self) -> None:
        """Test that CloudProviderFactory is not imported anywhere in job executor"""

        # Read the job executor file
        with open("src/borgitory/services/jobs/job_executor.py", "r") as f:
            content = f.read()

        # Ensure CloudProviderFactory is not imported
        assert "CloudProviderFactory" not in content, (
            "JobExecutor should not import CloudProviderFactory - use dependency injection instead"
        )

        # Ensure the new pattern is used
        assert "sync_repository_to_provider" in content, (
            "JobExecutor should use the generic rclone dispatcher methods"
        )

    def test_proper_rclone_service_usage(self) -> None:
        """Test that RcloneService is used via dependency injection"""

        with open("src/borgitory/services/jobs/job_executor.py", "r") as f:
            content = f.read()

        # Should use the injected rclone_service parameter
        assert "rclone_service.sync_repository_to_provider" in content, (
            "Should use injected rclone_service, not create new instance"
        )

    @pytest.mark.asyncio
    async def test_registry_integration_works(self, production_registry) -> None:
        """Test that the registry system is properly integrated"""
        # Use isolated registry fixture instead of global registry
        providers = production_registry.get_supported_providers()
        expected_providers = ["s3", "sftp", "smb"]

        for provider in expected_providers:
            assert provider in providers, f"Provider {provider} should be registered"

    def test_rclone_service_has_generic_dispatchers(self) -> None:
        """Test that RcloneService has the required generic dispatcher methods"""
        from borgitory.services.rclone_service import RcloneService

        service = RcloneService()

        # Should have the generic dispatcher methods
        assert hasattr(service, "sync_repository_to_provider"), (
            "RcloneService should have sync_repository_to_provider method"
        )
        assert hasattr(service, "test_provider_connection"), (
            "RcloneService should have test_provider_connection method"
        )

        # Methods should be callable
        assert callable(service.sync_repository_to_provider)
        assert callable(service.test_provider_connection)


class TestCloudSyncProgressHandling:
    """Test progress handling in cloud sync"""

    async def _execute_cloud_sync_with_di(
        self,
        job_executor,
        config_id,
        test_db,
        mock_rclone_service,
        mock_encryption_service,
        mock_storage_factory,
        mock_provider_registry=None,
        output_callback=None,
    ):
        """Helper method to execute cloud sync with all DI parameters"""
        # Create a mock registry if not provided
        if mock_provider_registry is None:
            from unittest.mock import MagicMock

            mock_provider_registry = MagicMock()
            # Mock the get_metadata method to return a valid metadata object
            mock_metadata = MagicMock()
            mock_metadata.storage_class = MagicMock()
            mock_provider_registry.get_metadata.return_value = mock_metadata

        return await job_executor.execute_cloud_sync_task(
            repository_path="/test/repo/path",
            cloud_sync_config_id=config_id,
            db_session_factory=lambda: test_db,
            rclone_service=mock_rclone_service,
            encryption_service=mock_encryption_service,
            storage_factory=mock_storage_factory,
            provider_registry=mock_provider_registry,
            output_callback=output_callback,
        )

    @pytest.mark.asyncio
    async def test_progress_streaming_works(
        self,
        job_executor,
        s3_cloud_sync_config,
        test_db,
        mock_encryption_service,
        mock_storage_factory,
    ) -> None:
        """Test that progress is properly streamed from rclone service"""

        # Create a mock rclone service with detailed progress
        mock_rclone_service = MagicMock(spec=RcloneService)

        async def detailed_progress_generator():
            yield {"type": "started", "command": "rclone sync", "pid": 12345}
            yield {"type": "progress", "percentage": 10, "transferred": "50MB"}
            yield {"type": "progress", "percentage": 25, "transferred": "125MB"}
            yield {"type": "progress", "percentage": 50, "transferred": "250MB"}
            yield {"type": "progress", "percentage": 75, "transferred": "375MB"}
            yield {"type": "progress", "percentage": 100, "transferred": "500MB"}
            yield {"type": "completed", "return_code": 0, "status": "success"}

        mock_rclone_service.sync_repository_to_provider = MagicMock(
            return_value=detailed_progress_generator()
        )

        progress_events = []

        def progress_callback(message: str) -> None:
            progress_events.append((message, {}))

        result = await self._execute_cloud_sync_with_di(
            job_executor,
            s3_cloud_sync_config.id,
            test_db,
            mock_rclone_service,
            mock_encryption_service,
            mock_storage_factory,
            output_callback=progress_callback,
        )

        assert result.return_code == 0

        # Should have received progress events
        assert len(progress_events) >= 3  # At least start, progress, complete

        # Check that we got meaningful progress messages
        messages = [event[0] for event in progress_events]
        assert any("Starting cloud sync" in msg for msg in messages)
        assert any("Syncing to" in msg for msg in messages)
        assert any("completed successfully" in msg for msg in messages)

    @pytest.mark.asyncio
    async def test_handles_rclone_failure_gracefully(
        self,
        job_executor,
        s3_cloud_sync_config,
        test_db,
        mock_encryption_service,
        mock_storage_factory,
    ) -> None:
        """Test handling when rclone process fails"""

        mock_rclone_service = MagicMock(spec=RcloneService)

        async def failing_generator():
            yield {"type": "started", "command": "rclone sync", "pid": 12345}
            yield {"type": "progress", "percentage": 25, "transferred": "100MB"}
            yield {"type": "error", "message": "Network connection failed"}
            yield {"type": "completed", "return_code": 1, "status": "failed"}

        mock_rclone_service.sync_repository_to_provider = MagicMock(
            return_value=failing_generator()
        )

        result = await self._execute_cloud_sync_with_di(
            job_executor,
            s3_cloud_sync_config.id,
            test_db,
            mock_rclone_service,
            mock_encryption_service,
            mock_storage_factory,
        )

        # Should handle failure properly
        assert result.return_code == 1
        assert "Network connection failed" in result.error
