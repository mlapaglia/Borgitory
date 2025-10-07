"""
Tests for FastAPI dependency providers
"""

from unittest.mock import Mock

from borgitory.dependencies import (
    get_simple_command_runner,
    get_command_runner_config,
    get_job_manager_env_config,
    get_job_manager_config,
    get_configuration_service,
    get_registry_factory,
    get_provider_registry,
    get_file_system,
)
from borgitory.services.simple_command_runner import SimpleCommandRunner
from borgitory.config.command_runner_config import CommandRunnerConfig
from borgitory.config.job_manager_config import JobManagerEnvironmentConfig
from borgitory.services.jobs.job_models import JobManagerConfig
from borgitory.services.configuration_service import ConfigurationService
from borgitory.services.cloud_providers.registry_factory import RegistryFactory
from borgitory.services.cloud_providers.registry import ProviderRegistry
from borgitory.services.volumes.file_system_interface import FileSystemInterface
from borgitory.services.volumes.os_file_system import OsFileSystem
from borgitory.protocols.command_protocols import CommandRunnerProtocol


class TestDependencies:
    """Test class for dependency providers."""

    def test_get_command_runner_config(self) -> None:
        """Test CommandRunnerConfig dependency provider."""
        config = get_command_runner_config()

        assert isinstance(config, CommandRunnerConfig)
        assert config.timeout == 300  # Default timeout
        assert config.max_retries == 3
        assert config.log_commands is True

    def test_get_simple_command_runner(self) -> None:
        """Test SimpleCommandRunner dependency provider."""
        config = get_command_runner_config()
        runner = get_simple_command_runner(config)

        assert isinstance(runner, SimpleCommandRunner)
        assert isinstance(runner, CommandRunnerProtocol)
        assert runner.timeout == 300  # Default timeout from config
        assert runner.max_retries == 3
        assert runner.log_commands is True

    def test_get_simple_command_runner_custom_config(self) -> None:
        """Test SimpleCommandRunner with custom configuration."""
        custom_config = CommandRunnerConfig(
            timeout=120, max_retries=5, log_commands=False
        )
        runner = get_simple_command_runner(custom_config)

        assert isinstance(runner, SimpleCommandRunner)
        assert runner.timeout == 120
        assert runner.max_retries == 5
        assert runner.log_commands is False

    def test_get_job_manager_env_config(self) -> None:
        """Test JobManagerEnvironmentConfig dependency provider."""
        env_config = get_job_manager_env_config()

        assert isinstance(env_config, JobManagerEnvironmentConfig)
        assert env_config.max_concurrent_backups == 5  # Default value
        assert env_config.max_output_lines_per_job == 1000
        assert env_config.max_concurrent_operations == 10
        assert env_config.queue_poll_interval == 0.1
        assert env_config.sse_keepalive_timeout == 30.0
        assert env_config.sse_max_queue_size == 100
        assert env_config.max_concurrent_cloud_uploads == 3

    def test_get_job_manager_config(self) -> None:
        """Test JobManagerConfig dependency provider."""
        env_config = get_job_manager_env_config()
        config = get_job_manager_config(env_config)

        assert isinstance(config, JobManagerConfig)
        assert config.max_concurrent_backups == 5
        assert config.max_output_lines_per_job == 1000
        assert config.max_concurrent_operations == 10
        assert config.queue_poll_interval == 0.1
        assert config.sse_keepalive_timeout == 30.0
        assert config.sse_max_queue_size == 100
        assert config.max_concurrent_cloud_uploads == 3

    def test_get_job_manager_config_custom_env(self) -> None:
        """Test JobManagerConfig with custom environment configuration."""
        custom_env_config = JobManagerEnvironmentConfig(
            max_concurrent_backups=10,
            max_output_lines_per_job=2000,
            max_concurrent_operations=20,
            queue_poll_interval=0.05,
            sse_keepalive_timeout=60.0,
            sse_max_queue_size=200,
            max_concurrent_cloud_uploads=5,
        )
        config = get_job_manager_config(custom_env_config)

        assert isinstance(config, JobManagerConfig)
        assert config.max_concurrent_backups == 10
        assert config.max_output_lines_per_job == 2000
        assert config.max_concurrent_operations == 20
        assert config.queue_poll_interval == 0.05
        assert config.sse_keepalive_timeout == 60.0
        assert config.sse_max_queue_size == 200
        assert config.max_concurrent_cloud_uploads == 5

    def test_get_configuration_service(self) -> None:
        """Test ConfigurationService dependency provider."""
        # Create a mock database session
        mock_db = Mock()
        config_service = get_configuration_service(mock_db)

        assert isinstance(config_service, ConfigurationService)
        assert config_service.db is mock_db

    def test_get_registry_factory(self) -> None:
        """Test RegistryFactory dependency provider."""
        registry_factory = get_registry_factory()

        assert isinstance(registry_factory, RegistryFactory)

    def test_get_provider_registry(self) -> None:
        """Test ProviderRegistry dependency provider."""
        registry_factory = get_registry_factory()
        provider_registry = get_provider_registry(registry_factory)

        assert isinstance(provider_registry, ProviderRegistry)

    def test_get_provider_registry_with_mock_factory(self) -> None:
        """Test ProviderRegistry with mock factory for testing."""
        # Create a mock factory
        mock_factory = Mock(spec=RegistryFactory)
        mock_registry = Mock(spec=ProviderRegistry)
        mock_factory.create_production_registry.return_value = mock_registry

        # Test the dependency function
        result = get_provider_registry(mock_factory)

        assert result is mock_registry
        mock_factory.create_production_registry.assert_called_once()

    def test_get_file_system(self) -> None:
        """Test FileSystemInterface dependency provider."""
        filesystem = get_file_system()

        assert isinstance(filesystem, FileSystemInterface)
        assert isinstance(filesystem, OsFileSystem)
