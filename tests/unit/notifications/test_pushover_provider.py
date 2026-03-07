"""
Unit tests for PushoverProvider class - business logic only, no HTTP mocking.
HTTP/API integration tests should be separate integration tests.
"""

import pytest
from unittest.mock import Mock, AsyncMock
from urllib.parse import urlparse

from borgitory.services.notifications.providers.pushover_provider import (
    PushoverProvider,
    PushoverConfig,
)
from borgitory.services.notifications.providers.discord_provider import HttpClient
from borgitory.services.notifications.types import (
    NotificationMessage,
    NotificationResult,
    NotificationType,
    NotificationPriority,
    ConnectionInfo,
)


@pytest.fixture
def pushover_config():
    """Create a valid Pushover configuration for testing."""
    return PushoverConfig(
        user_key="u" + "x" * 29,  # 30 chars total
        app_token="a" + "x" * 29,  # 30 chars total
        priority=0,
        sound="default",
    )


@pytest.fixture
def pushover_provider(pushover_config):
    """Create a PushoverProvider instance for testing."""
    return PushoverProvider(pushover_config)


@pytest.fixture
def mock_http_client():
    """Create a mock HTTP client for testing DI."""
    mock = Mock(spec=HttpClient)
    mock.post = AsyncMock()
    mock.close = AsyncMock()
    return mock


@pytest.fixture
def sample_message():
    """Create a sample notification message for testing."""
    return NotificationMessage(
        title="Test Title",
        message="Test message content",
        notification_type=NotificationType.INFO,
        priority=NotificationPriority.NORMAL,
    )


class TestPushoverProvider:
    """Unit tests for PushoverProvider class - business logic focus"""

    def test_provider_initialization_with_http_client_injection(
        self, pushover_config, mock_http_client
    ):
        """Test that PushoverProvider accepts HTTP client injection."""
        provider = PushoverProvider(pushover_config, http_client=mock_http_client)

        assert provider.config == pushover_config
        assert provider.http_client == mock_http_client

    def test_provider_initialization_with_default_http_client(self, pushover_config):
        """Test that PushoverProvider creates default HTTP client when none provided."""
        provider = PushoverProvider(pushover_config)

        assert provider.config == pushover_config
        assert provider.http_client is not None
        # Should be AiohttpClient instance
        assert hasattr(provider.http_client, "post")
        assert hasattr(provider.http_client, "close")

    # ===== CONFIGURATION TESTS =====

    def test_config_validation_valid(self) -> None:
        """Test valid configuration passes validation"""
        config = PushoverConfig(
            user_key="u" + "x" * 29,  # 30 chars total
            app_token="a" + "x" * 29,  # 30 chars total
        )
        provider = PushoverProvider(config)
        assert provider.config.user_key.startswith("u")
        assert provider.config.app_token.startswith("a")

    def test_config_validation_invalid_short_keys(self) -> None:
        """Test invalid configuration (too short keys) raises validation error"""
        with pytest.raises(Exception):  # Pydantic validation error
            PushoverConfig(user_key="short", app_token="short")

    def test_config_validation_invalid_long_keys(self) -> None:
        """Test invalid configuration (too long keys) raises validation error"""
        with pytest.raises(Exception):  # Pydantic validation error
            PushoverConfig(
                user_key="u" + "x" * 50,  # Too long
                app_token="a" + "x" * 50,  # Too long
            )

    def test_optional_config_fields(self) -> None:
        """Test optional configuration fields"""
        config = PushoverConfig(
            user_key="u" + "x" * 29,  # 30 chars total
            app_token="a" + "x" * 29,  # 30 chars total
            sound="cosmic",
            device="test-device",
            priority=1,
        )

        provider = PushoverProvider(config)
        assert provider.config.sound == "cosmic"
        assert provider.config.device == "test-device"
        assert provider.config.priority == 1

    def test_config_priority_bounds(self) -> None:
        """Test priority field validation bounds"""
        # Test valid priority values
        for priority in [-2, -1, 0, 1, 2]:
            config = PushoverConfig(
                user_key="u" + "x" * 29, app_token="a" + "x" * 29, priority=priority
            )
            assert config.priority == priority

        # Test invalid priority values
        with pytest.raises(Exception):  # Pydantic validation error
            PushoverConfig(
                user_key="u" + "x" * 29,
                app_token="a" + "x" * 29,
                priority=3,  # Too high
            )

    # ===== PROVIDER INTERFACE TESTS =====

    def test_get_connection_info(self, pushover_provider) -> None:
        """Test getting connection information"""
        info = pushover_provider.get_connection_info()

        assert isinstance(info, ConnectionInfo)
        assert info.provider == "pushover"
        assert info.status == "configured"
        assert "ux" in info.endpoint  # Should show truncated user key

        # Test string representation
        info_str = str(info)
        assert "Pushover API" in info_str
        assert "configured" in info_str

    def test_get_sensitive_fields(self, pushover_provider) -> None:
        """Test getting sensitive field names"""
        sensitive_fields = pushover_provider.get_sensitive_fields()

        assert isinstance(sensitive_fields, list)
        assert "user_key" in sensitive_fields
        assert "app_token" in sensitive_fields
        assert len(sensitive_fields) == 2

    def test_provider_instantiation(self, pushover_config) -> None:
        """Test provider can be instantiated correctly"""
        provider = PushoverProvider(pushover_config)

        assert provider.config == pushover_config
        assert provider.config.user_key.startswith("u")
        assert provider.config.app_token.startswith("a")

    # ===== NOTIFICATION MESSAGE TESTS =====

    def test_notification_message_creation(self) -> None:
        """Test NotificationMessage creation and defaults"""
        # Test with minimal fields
        message = NotificationMessage(title="Test", message="Test message")

        assert message.title == "Test"
        assert message.message == "Test message"
        assert message.notification_type == NotificationType.INFO
        assert message.priority == NotificationPriority.NORMAL
        assert message.metadata == {}

        # Test with all fields
        message = NotificationMessage(
            title="Error Alert",
            message="Something went wrong",
            notification_type=NotificationType.ERROR,
            priority=NotificationPriority.HIGH,
            metadata={"source": "test"},
        )

        assert message.title == "Error Alert"
        assert message.notification_type == NotificationType.ERROR
        assert message.priority == NotificationPriority.HIGH
        assert message.metadata == {"source": "test"}

    def test_notification_types_available(self) -> None:
        """Test all notification types are available"""
        # Test all enum values exist
        assert NotificationType.SUCCESS == "success"
        assert NotificationType.FAILURE == "failure"
        assert NotificationType.ERROR == "error"
        assert NotificationType.WARNING == "warning"
        assert NotificationType.INFO == "info"

    def test_notification_priorities_available(self) -> None:
        """Test all priority levels are available"""
        assert NotificationPriority.LOWEST == -2
        assert NotificationPriority.LOW == -1
        assert NotificationPriority.NORMAL == 0
        assert NotificationPriority.HIGH == 1
        assert NotificationPriority.EMERGENCY == 2

    def test_message_length_handling(self) -> None:
        """Test handling of long messages"""
        long_message = NotificationMessage(
            title="Test" * 100,  # Very long title
            message="Content" * 200,  # Very long message
            notification_type=NotificationType.INFO,
        )

        # Should not raise an exception during creation
        assert len(long_message.title) > 100
        assert len(long_message.message) > 100

    # ===== NOTIFICATION RESULT TESTS =====

    def test_notification_result_structure(self) -> None:
        """Test NotificationResult structure and creation"""
        # Test successful result
        result = NotificationResult(
            success=True,
            provider="pushover",
            message="Notification sent successfully",
            error=None,
            metadata={"request_id": "test-123"},
        )

        assert result.success is True
        assert result.provider == "pushover"
        assert result.message == "Notification sent successfully"
        assert result.error is None
        assert result.metadata == {"request_id": "test-123"}

        # Test failed result
        result = NotificationResult(
            success=False,
            provider="pushover",
            message="Failed to send notification",
            error="Invalid user key",
            metadata={},
        )

        assert result.success is False
        assert result.error == "Invalid user key"
        assert result.metadata == {}

    def test_notification_result_defaults(self) -> None:
        """Test NotificationResult default values"""
        result = NotificationResult(
            success=True, provider="pushover", message="Test message"
        )

        assert result.error is None
        assert result.metadata == {}

    # ===== BUSINESS LOGIC TESTS =====

    def test_priority_mapping_logic(self) -> None:
        """Test that different notification types can have different priorities"""
        # Create messages with different types and priorities
        error_message = NotificationMessage(
            title="Error",
            message="Something went wrong",
            notification_type=NotificationType.ERROR,
            priority=NotificationPriority.HIGH,
        )

        info_message = NotificationMessage(
            title="Info",
            message="Just FYI",
            notification_type=NotificationType.INFO,
            priority=NotificationPriority.LOW,
        )

        success_message = NotificationMessage(
            title="Success",
            message="Everything worked",
            notification_type=NotificationType.SUCCESS,
            priority=NotificationPriority.NORMAL,
        )

        assert error_message.notification_type == NotificationType.ERROR
        assert error_message.priority == NotificationPriority.HIGH

        assert info_message.notification_type == NotificationType.INFO
        assert info_message.priority == NotificationPriority.LOW

        assert success_message.notification_type == NotificationType.SUCCESS
        assert success_message.priority == NotificationPriority.NORMAL

    def test_sound_configuration(self, pushover_provider) -> None:
        """Test sound configuration options"""
        # Test default sound
        assert pushover_provider.config.sound == "default"

        # Test custom sound
        config = PushoverConfig(
            user_key="u" + "x" * 29, app_token="a" + "x" * 29, sound="bike"
        )
        provider = PushoverProvider(config)
        assert provider.config.sound == "bike"

    def test_device_configuration(self) -> None:
        """Test device configuration options"""
        # Test no device (default)
        config = PushoverConfig(user_key="u" + "x" * 29, app_token="a" + "x" * 29)
        provider = PushoverProvider(config)
        assert provider.config.device is None

        # Test specific device
        config = PushoverConfig(
            user_key="u" + "x" * 29, app_token="a" + "x" * 29, device="my-phone"
        )
        provider = PushoverProvider(config)
        assert provider.config.device == "my-phone"

    def test_provider_constants(self, pushover_provider) -> None:
        """Test provider has correct constants"""
        # Test API URL is set
        assert hasattr(pushover_provider, "PUSHOVER_API_URL")
        url = urlparse(pushover_provider.PUSHOVER_API_URL)
        assert url.hostname is not None
        # Allow root domain or any subdomain
        assert url.hostname == "pushover.net" or url.hostname.endswith(".pushover.net")

    # ===== EDGE CASES =====

    def test_empty_message_handling(self) -> None:
        """Test handling of empty or minimal messages"""
        # Test empty strings (should be allowed)
        message = NotificationMessage(title="", message="")
        assert message.title == ""
        assert message.message == ""

    def test_unicode_message_handling(self) -> None:
        """Test handling of unicode characters in messages"""
        message = NotificationMessage(
            title="🚨 Alert 🚨",
            message="测试消息 with émojis 🎉",
            notification_type=NotificationType.WARNING,
        )

        assert "🚨" in message.title
        assert "测试消息" in message.message
        assert "🎉" in message.message
        assert message.notification_type == NotificationType.WARNING
