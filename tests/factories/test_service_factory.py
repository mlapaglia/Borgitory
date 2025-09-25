"""
Tests for protocol-based service factories.

These tests verify that our factory system correctly creates services
based on protocols and manages different implementations.
"""

import pytest
from unittest.mock import Mock

from borgitory.factories.service_factory import (
    ServiceFactory,
    NotificationServiceFactory,
    CloudProviderServiceFactory,
)

from borgitory.protocols.notification_protocols import NotificationServiceProtocol


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
        # Create factory with injected dependency - no more service locator!
        mock_http_client = Mock()
        factory = NotificationServiceFactory(http_client=mock_http_client)

        implementations = factory.list_implementations()
        assert "provider_based" in implementations
        assert factory.get_default_implementation() == "provider_based"

    def test_create_notification_service(self):
        """Test creating a notification service."""
        # Create factory with injected dependency - clean and simple!
        mock_http_client = Mock()
        factory = NotificationServiceFactory(http_client=mock_http_client)

        service = factory.create_notification_service("provider_based")

        assert service is not None
        # Should have the methods from NotificationServiceProtocol
        assert hasattr(service, "send_notification")
        assert hasattr(service, "test_connection")
        assert hasattr(service, "prepare_config_for_storage")
        assert hasattr(service, "load_config_from_storage")

    def test_create_default_service(self):
        """Test creating default notification service."""
        # Create factory with injected dependency - no more service locator!
        mock_http_client = Mock()
        factory = NotificationServiceFactory(http_client=mock_http_client)

        service = factory.create_notification_service()

        assert service is not None
        assert hasattr(service, "send_notification")
        assert service.__class__.__name__ == "NotificationService"


class TestCloudProviderServiceFactory:
    """Test the CloudProviderServiceFactory."""

    def test_factory_has_default_implementations(self):
        """Test that factory comes with default implementations."""
        # Create factory with injected dependencies - clean and simple!
        mock_rclone = Mock()
        mock_storage = Mock()
        mock_encryption = Mock()
        mock_metadata = Mock()

        factory = CloudProviderServiceFactory(
            rclone_service=mock_rclone,
            storage_factory=mock_storage,
            encryption_service=mock_encryption,
            metadata_func=mock_metadata,
        )

        implementations = factory.list_implementations()
        assert "default" in implementations
        assert factory.get_default_implementation() == "default"

    def test_create_cloud_sync_service(self):
        """Test creating a cloud sync service."""
        # Create factory with injected dependencies - no more complex patching!
        mock_db = Mock()
        mock_rclone = Mock()
        mock_storage = Mock()
        mock_encryption = Mock()
        mock_metadata = Mock()

        factory = CloudProviderServiceFactory(
            rclone_service=mock_rclone,
            storage_factory=mock_storage,
            encryption_service=mock_encryption,
            metadata_func=mock_metadata,
        )

        service = factory.create_cloud_sync_service(mock_db, "default")

        assert service is not None
        # Should satisfy the CloudSyncConfigServiceProtocol
        assert hasattr(service, "create_cloud_sync_config")
        assert hasattr(service, "get_cloud_sync_configs")
        assert hasattr(service, "update_cloud_sync_config")
        assert hasattr(service, "delete_cloud_sync_config")

    def test_create_cloud_sync_service_with_db_session(self):
        """Test creating cloud sync service with proper database session injection."""
        # This tests the DI pattern - db session is injected, dependencies are pre-injected
        mock_db = Mock()
        mock_rclone = Mock()
        mock_storage = Mock()
        mock_encryption = Mock()
        mock_metadata = Mock()

        factory = CloudProviderServiceFactory(
            rclone_service=mock_rclone,
            storage_factory=mock_storage,
            encryption_service=mock_encryption,
            metadata_func=mock_metadata,
        )

        service = factory.create_cloud_sync_service(
            mock_db
        )  # Using default implementation

        assert service is not None
        # Dependencies are already injected - no need to verify function calls!


class TestFactoryIntegration:
    """Integration tests for factory system."""

    def test_notification_factory_creates_protocol_compliant_services(self):
        """Test that notification factory creates protocol-compliant services."""
        # Create factory with injected dependency - clean and simple!
        mock_http_client = Mock()
        factory = NotificationServiceFactory(http_client=mock_http_client)
        service = factory.create_notification_service()

        # Test that service satisfies the protocol interface
        assert hasattr(service, "send_notification")
        assert hasattr(service, "test_connection")
        assert hasattr(service, "prepare_config_for_storage")
        assert hasattr(service, "load_config_from_storage")

    def test_cloud_sync_factory_creates_protocol_compliant_services(self):
        """Test that cloud sync factory creates protocol-compliant services."""
        # Create factory with injected dependencies - no more complex patching!
        mock_db = Mock()
        mock_rclone = Mock()
        mock_storage = Mock()
        mock_encryption = Mock()
        mock_metadata = Mock()

        factory = CloudProviderServiceFactory(
            rclone_service=mock_rclone,
            storage_factory=mock_storage,
            encryption_service=mock_encryption,
            metadata_func=mock_metadata,
        )
        service = factory.create_cloud_sync_service(mock_db)

        # Test that service satisfies the CloudSyncConfigServiceProtocol
        assert hasattr(service, "create_cloud_sync_config")
        assert hasattr(service, "get_cloud_sync_configs")
        assert hasattr(service, "get_cloud_sync_config_by_id")
        assert hasattr(service, "update_cloud_sync_config")
        assert hasattr(service, "delete_cloud_sync_config")
        assert hasattr(service, "enable_cloud_sync_config")
        assert hasattr(service, "disable_cloud_sync_config")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
