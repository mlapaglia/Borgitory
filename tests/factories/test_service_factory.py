"""
Tests for protocol-based service factories.

These tests verify that our factory system correctly creates services
based on protocols and manages different implementations.
"""

import pytest
from unittest.mock import Mock, patch

from borgitory.factories.service_factory import (
    ServiceFactory,
    NotificationServiceFactory,
    CommandRunnerFactory,
    BackupServiceFactory,
    ServiceRegistry,
    get_service_registry,
    create_notification_service,
    create_command_runner,
    create_backup_service,
)

from borgitory.protocols.notification_protocols import NotificationServiceProtocol
from borgitory.protocols.command_protocols import CommandRunnerProtocol


class MockNotificationService:
    """Mock notification service for testing."""

    def __init__(self, config_value: str = "default"):
        self.config_value = config_value

    async def send_notification(self, title: str, message: str, **kwargs) -> bool:
        return True

    def is_configured(self) -> bool:
        return True

    def get_service_name(self) -> str:
        return f"MockNotificationService({self.config_value})"


class MockCommandRunner:
    """Mock command runner for testing."""

    def __init__(self, timeout: int = 30):
        self.timeout = timeout

    async def run_command(self, command, env=None):
        return Mock(success=True, stdout=b"mock output", stderr=b"")


class TestServiceFactory:
    """Test the base ServiceFactory class."""

    def test_factory_initialization(self):
        """Test that factory initializes correctly."""
        factory = ServiceFactory[NotificationServiceProtocol]()

        assert len(factory._implementations) == 0
        assert len(factory._configurations) == 0
        assert factory._default_implementation is None

    def test_register_implementation(self):
        """Test registering service implementations."""
        factory = ServiceFactory[NotificationServiceProtocol]()
        config = {"api_key": "test_key"}

        factory.register_implementation(
            "mock", MockNotificationService, config=config, set_as_default=True
        )

        assert "mock" in factory._implementations
        assert factory._implementations["mock"] == MockNotificationService
        assert factory._configurations["mock"] == config
        assert factory._default_implementation == "mock"

    def test_create_service_with_default(self):
        """Test creating service with default implementation."""
        factory = ServiceFactory[NotificationServiceProtocol]()
        factory.register_implementation(
            "mock", MockNotificationService, set_as_default=True
        )

        service = factory.create_service()

        assert isinstance(service, MockNotificationService)
        assert service.config_value == "default"

    def test_create_service_with_specific_implementation(self):
        """Test creating service with specific implementation."""
        factory = ServiceFactory[NotificationServiceProtocol]()
        factory.register_implementation("mock1", MockNotificationService)
        factory.register_implementation("mock2", MockNotificationService)

        service = factory.create_service("mock2", config_value="custom")

        assert isinstance(service, MockNotificationService)
        assert service.config_value == "custom"

    def test_create_service_with_nonexistent_implementation(self):
        """Test creating service with nonexistent implementation raises error."""
        factory = ServiceFactory[NotificationServiceProtocol]()

        with pytest.raises(ValueError) as exc_info:
            factory.create_service("nonexistent")

        assert "Implementation 'nonexistent' not found" in str(exc_info.value)

    def test_list_implementations(self):
        """Test listing registered implementations."""
        factory = ServiceFactory[NotificationServiceProtocol]()
        factory.register_implementation("mock1", MockNotificationService)
        factory.register_implementation("mock2", MockNotificationService)

        implementations = factory.list_implementations()

        assert len(implementations) == 2
        assert "mock1" in implementations
        assert "mock2" in implementations
        assert implementations["mock1"] == MockNotificationService


class TestNotificationServiceFactory:
    """Test the NotificationServiceFactory."""

    def test_factory_has_default_implementations(self):
        """Test that factory comes with default implementations."""
        factory = NotificationServiceFactory()

        implementations = factory.list_implementations()
        assert "provider_based" in implementations
        assert factory.get_default_implementation() == "provider_based"

    def test_create_notification_service(self):
        """Test creating a notification service."""
        factory = NotificationServiceFactory()

        service = factory.create_notification_service("provider_based")

        assert service is not None
        # Should have the methods from NotificationService
        assert hasattr(service, "send_notification")
        assert hasattr(service, "test_connection")
        assert hasattr(service, "prepare_config_for_storage")

    def test_create_default_service(self):
        """Test creating default notification service."""
        factory = NotificationServiceFactory()

        service = factory.create_notification_service()

        assert service is not None
        assert hasattr(service, "send_notification")
        assert service.__class__.__name__ == "NotificationService"


class TestCommandRunnerFactory:
    """Test the CommandRunnerFactory."""

    def test_factory_has_default_implementations(self):
        """Test that factory comes with default implementations."""
        factory = CommandRunnerFactory()

        implementations = factory.list_implementations()
        assert "simple" in implementations
        assert factory.get_default_implementation() == "simple"

    def test_create_simple_command_runner(self):
        """Test creating a SimpleCommandRunner."""
        factory = CommandRunnerFactory()

        runner = factory.create_command_runner("simple")

        assert runner is not None
        # Should satisfy the protocol
        assert hasattr(runner, "run_command")

    def test_create_command_runner_with_config(self):
        """Test creating command runner with configuration."""
        factory = CommandRunnerFactory()

        runner = factory.create_command_runner("simple", timeout=60)

        assert runner is not None
        assert runner.timeout == 60


class TestBackupServiceFactory:
    """Test the BackupServiceFactory."""

    def test_factory_has_default_implementations(self):
        """Test that factory comes with default implementations."""
        factory = BackupServiceFactory()

        implementations = factory.list_implementations()
        assert "borg" in implementations
        assert factory.get_default_implementation() == "borg"

    @patch("borgitory.dependencies.get_simple_command_runner")
    @patch("borgitory.dependencies.get_volume_service")
    @patch("borgitory.dependencies.get_job_manager_dependency")
    def test_create_borg_service(
        self, mock_job_manager, mock_volume_service, mock_command_runner
    ):
        """Test creating a BorgService through the factory."""
        # Setup mocks
        mock_command_runner.return_value = Mock()
        mock_volume_service.return_value = Mock()
        mock_job_manager.return_value = Mock()

        factory = BackupServiceFactory()

        service = factory.create_backup_service("borg")

        assert service is not None
        # Should satisfy the protocol
        assert hasattr(service, "create_backup")
        assert hasattr(service, "list_archives")
        assert hasattr(service, "get_repo_info")


class TestServiceRegistry:
    """Test the ServiceRegistry."""

    def test_registry_initialization(self):
        """Test that registry initializes with default factories."""
        registry = ServiceRegistry()

        factories = registry.list_factories()
        assert "notifications" in factories
        assert "command_runners" in factories
        assert "backup_services" in factories

    def test_get_notification_factory(self):
        """Test getting notification factory."""
        registry = ServiceRegistry()

        factory = registry.get_notification_factory()

        assert isinstance(factory, NotificationServiceFactory)

    def test_get_command_runner_factory(self):
        """Test getting command runner factory."""
        registry = ServiceRegistry()

        factory = registry.get_command_runner_factory()

        assert isinstance(factory, CommandRunnerFactory)

    def test_get_backup_service_factory(self):
        """Test getting backup service factory."""
        registry = ServiceRegistry()

        factory = registry.get_backup_service_factory()

        assert isinstance(factory, BackupServiceFactory)

    def test_get_nonexistent_factory(self):
        """Test getting nonexistent factory raises error."""
        registry = ServiceRegistry()

        with pytest.raises(ValueError) as exc_info:
            registry.get_factory("nonexistent")

        assert "Factory 'nonexistent' not found" in str(exc_info.value)


class TestConvenienceFunctions:
    """Test the convenience functions."""

    def test_create_notification_service_function(self):
        """Test the create_notification_service convenience function."""
        service = create_notification_service("provider_based")

        assert service is not None
        assert hasattr(service, "send_notification")

    def test_create_command_runner_function(self):
        """Test the create_command_runner convenience function."""
        runner = create_command_runner("simple")

        assert runner is not None
        assert hasattr(runner, "run_command")

    @patch("borgitory.dependencies.get_simple_command_runner")
    @patch("borgitory.dependencies.get_volume_service")
    @patch("borgitory.dependencies.get_job_manager_dependency")
    def test_create_backup_service_function(
        self, mock_job_manager, mock_volume_service, mock_command_runner
    ):
        """Test the create_backup_service convenience function."""
        # Setup mocks
        mock_command_runner.return_value = Mock()
        mock_volume_service.return_value = Mock()
        mock_job_manager.return_value = Mock()

        service = create_backup_service("borg")

        assert service is not None
        assert hasattr(service, "create_backup")


class TestFactoryIntegration:
    """Integration tests for factory system."""

    def test_factory_creates_protocol_compliant_services(self):
        """Test that all factory-created services satisfy their protocols."""
        registry = get_service_registry()

        # Test notification service
        notification_factory = registry.get_notification_factory()
        notification_service = notification_factory.create_notification_service()

        def use_notification_service(service) -> str:
            # Use actual service interface instead of protocol
            return service.__class__.__name__

        result = use_notification_service(notification_service)
        assert result == "NotificationService"

        # Test command runner
        command_factory = registry.get_command_runner_factory()
        command_runner = command_factory.create_command_runner()

        def use_command_runner(runner: CommandRunnerProtocol) -> bool:
            return hasattr(runner, "run_command")

        assert use_command_runner(command_runner) is True

    def test_global_registry_singleton(self):
        """Test that get_service_registry returns the same instance."""
        registry1 = get_service_registry()
        registry2 = get_service_registry()

        assert registry1 is registry2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
