"""
Unit tests for TelegramProvider class - business logic only, no HTTP mocking.
HTTP/API integration tests should be separate integration tests.
"""

import pytest
from unittest.mock import Mock, AsyncMock
from urllib.parse import urlparse

from borgitory.services.notifications.providers.telegram_provider import (
    TelegramProvider,
    TelegramConfig,
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
def telegram_config():
    """Create a valid Telegram configuration for testing."""
    return TelegramConfig(
        bot_token="123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijk",
        chat_id="@test_channel",
        parse_mode="HTML",
        disable_notification=False,
    )


@pytest.fixture
def telegram_provider(telegram_config):
    """Create a TelegramProvider instance for testing."""
    return TelegramProvider(telegram_config)


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


class TestTelegramProvider:
    """Unit tests for TelegramProvider class - business logic focus"""

    def test_provider_initialization_with_http_client_injection(
        self, telegram_config, mock_http_client
    ):
        """Test that TelegramProvider accepts HTTP client injection."""
        provider = TelegramProvider(telegram_config, http_client=mock_http_client)

        assert provider.config == telegram_config
        assert provider.http_client == mock_http_client

    def test_provider_initialization_with_default_http_client(self, telegram_config):
        """Test that TelegramProvider creates default HTTP client when none provided."""
        provider = TelegramProvider(telegram_config)

        assert provider.config == telegram_config
        assert provider.http_client is not None
        # Should be AiohttpClient instance
        assert hasattr(provider.http_client, "post")
        assert hasattr(provider.http_client, "close")

    # ===== CONFIGURATION TESTS =====

    def test_config_validation_valid(self) -> None:
        """Test valid configuration passes validation"""
        config = TelegramConfig(
            bot_token="123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijk",
            chat_id="12345678",
        )
        provider = TelegramProvider(config)
        assert provider.config.bot_token.startswith("123456789:")
        assert provider.config.chat_id == "12345678"

    def test_config_validation_invalid_bot_token_no_colon(self) -> None:
        """Test invalid bot token (no colon) raises validation error"""
        with pytest.raises(Exception):  # Pydantic validation error
            TelegramConfig(bot_token="invalidtoken", chat_id="12345678")

    def test_config_validation_invalid_bot_token_short(self) -> None:
        """Test invalid bot token (too short) raises validation error"""
        with pytest.raises(Exception):  # Pydantic validation error
            TelegramConfig(bot_token="123:short", chat_id="12345678")

    def test_config_validation_invalid_bot_token_non_numeric_id(self) -> None:
        """Test invalid bot token (non-numeric bot ID) raises validation error"""
        with pytest.raises(Exception):  # Pydantic validation error
            TelegramConfig(bot_token="abc:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijk", chat_id="12345678")

    def test_config_validation_various_chat_id_formats(self) -> None:
        """Test various valid chat ID formats"""
        # Numeric user/group ID
        config1 = TelegramConfig(
            bot_token="123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijk",
            chat_id="12345678",
        )
        assert config1.chat_id == "12345678"

        # Negative group ID
        config2 = TelegramConfig(
            bot_token="123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijk",
            chat_id="-987654321",
        )
        assert config2.chat_id == "-987654321"

        # Channel username
        config3 = TelegramConfig(
            bot_token="123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijk",
            chat_id="@mychannel",
        )
        assert config3.chat_id == "@mychannel"

    def test_config_parse_mode_validation(self) -> None:
        """Test parse mode validation"""
        # Valid parse modes
        for mode in ["HTML", "Markdown", "MarkdownV2"]:
            config = TelegramConfig(
                bot_token="123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijk",
                chat_id="12345678",
                parse_mode=mode,
            )
            assert config.parse_mode == mode

        # Invalid parse mode
        with pytest.raises(Exception):  # Pydantic validation error
            TelegramConfig(
                bot_token="123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijk",
                chat_id="12345678",
                parse_mode="InvalidMode",
            )

    def test_optional_config_fields(self) -> None:
        """Test optional configuration fields"""
        config = TelegramConfig(
            bot_token="123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijk",
            chat_id="12345678",
            parse_mode="Markdown",
            disable_notification=True,
        )

        provider = TelegramProvider(config)
        assert provider.config.parse_mode == "Markdown"
        assert provider.config.disable_notification is True

    # ===== PROVIDER INTERFACE TESTS =====

    def test_get_connection_info(self, telegram_provider) -> None:
        """Test getting connection information"""
        info = telegram_provider.get_connection_info()

        assert isinstance(info, ConnectionInfo)
        assert info.provider == "telegram"
        assert info.status == "configured"
        assert "123456789" in info.endpoint  # Should show bot ID
        assert "@test_channel" in info.endpoint  # Should show chat ID

        # Test string representation
        info_str = str(info)
        assert "Telegram API" in info_str
        assert "configured" in info_str

    def test_get_sensitive_fields(self, telegram_provider) -> None:
        """Test getting sensitive field names"""
        sensitive_fields = telegram_provider.get_sensitive_fields()

        assert isinstance(sensitive_fields, list)
        assert "bot_token" in sensitive_fields
        assert len(sensitive_fields) == 1

    def test_get_display_details(self, telegram_provider) -> None:
        """Test getting display details for UI"""
        config_dict = {
            "bot_token": "123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijk",
            "chat_id": "@test_channel",
            "parse_mode": "HTML",
            "disable_notification": False,
        }
        
        details = telegram_provider.get_display_details(config_dict)
        
        assert details["provider_name"] == "Telegram"
        assert "123456789" in details["provider_details"]  # Bot ID shown
        assert "@test_channel" in details["provider_details"]  # Chat ID shown
        assert "HTML" in details["provider_details"]  # Parse mode shown
        assert "No" in details["provider_details"]  # Silent mode shown

    def test_provider_instantiation(self, telegram_config) -> None:
        """Test provider can be instantiated correctly"""
        provider = TelegramProvider(telegram_config)

        assert provider.config == telegram_config
        assert provider.config.bot_token.startswith("123456789:")
        assert provider.config.chat_id == "@test_channel"

    # ===== MESSAGE FORMATTING TESTS =====

    def test_message_formatting_html_mode(self) -> None:
        """Test message formatting in HTML mode"""
        config = TelegramConfig(
            bot_token="123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijk",
            chat_id="12345678",
            parse_mode="HTML",
        )
        provider = TelegramProvider(config)

        message = NotificationMessage(
            title="Test Alert",
            message="This is a test message",
            notification_type=NotificationType.WARNING,
            metadata={"backup_id": "test-123", "duration": "5 minutes"}
        )

        formatted = provider._format_message(message)
        
        assert "⚠️" in formatted  # Warning emoji
        assert "<b>Test Alert</b>" in formatted  # Bold title
        assert "This is a test message" in formatted
        assert "<b>Details:</b>" in formatted
        assert "<i>Backup Id:</i> test-123" in formatted
        assert "<i>Duration:</i> 5 minutes" in formatted

    def test_message_formatting_markdown_mode(self) -> None:
        """Test message formatting in Markdown mode"""
        config = TelegramConfig(
            bot_token="123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijk",
            chat_id="12345678",
            parse_mode="Markdown",
        )
        provider = TelegramProvider(config)

        message = NotificationMessage(
            title="Success",
            message="Backup completed successfully",
            notification_type=NotificationType.SUCCESS,
        )

        formatted = provider._format_message(message)
        
        assert "✅" in formatted  # Success emoji
        assert "*Success*" in formatted  # Bold title
        assert "Backup completed successfully" in formatted

    def test_message_formatting_markdownv2_mode(self) -> None:
        """Test message formatting in MarkdownV2 mode with escaping"""
        config = TelegramConfig(
            bot_token="123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijk",
            chat_id="12345678",
            parse_mode="MarkdownV2",
        )
        provider = TelegramProvider(config)

        message = NotificationMessage(
            title="Error: Backup Failed!",
            message="Failed to backup: /path/to/file (permission denied)",
            notification_type=NotificationType.FAILURE,
        )

        formatted = provider._format_message(message)
        
        assert "❌" in formatted  # Failure emoji
        assert "*Error: Backup Failed\\!*" in formatted  # Escaped title
        assert "\\(permission denied\\)" in formatted  # Escaped parentheses

    def test_message_formatting_plain_text(self) -> None:
        """Test message formatting in plain text mode"""
        config = TelegramConfig(
            bot_token="123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijk",
            chat_id="12345678",
            parse_mode="",  # Empty string should fall back to plain text
        )
        provider = TelegramProvider(config)

        message = NotificationMessage(
            title="Info",
            message="Just some information",
            notification_type=NotificationType.INFO,
        )

        formatted = provider._format_message(message)
        
        assert "ℹ️" in formatted  # Info emoji
        assert "Info" in formatted  # Plain title
        assert "Just some information" in formatted
        # Should not contain HTML or Markdown formatting
        assert "<b>" not in formatted
        assert "*" not in formatted

    def test_emoji_mapping_for_notification_types(self, telegram_provider) -> None:
        """Test emoji mapping for different notification types"""
        assert telegram_provider._get_emoji_for_type(NotificationType.SUCCESS) == "✅"
        assert telegram_provider._get_emoji_for_type(NotificationType.FAILURE) == "❌"
        assert telegram_provider._get_emoji_for_type(NotificationType.WARNING) == "⚠️"
        assert telegram_provider._get_emoji_for_type(NotificationType.INFO) == "ℹ️"
        # Test unknown type falls back to default
        assert "📢" in telegram_provider._get_emoji_for_type("unknown_type")

    # ===== BUSINESS LOGIC TESTS =====

    def test_api_url_construction(self, telegram_provider) -> None:
        """Test API URL construction"""
        # Test that the provider constructs correct API URLs
        assert hasattr(telegram_provider, "TELEGRAM_API_BASE")
        assert telegram_provider.TELEGRAM_API_BASE == "https://api.telegram.org"
        
        # Test URL construction in send_notification would use bot token
        expected_base = f"https://api.telegram.org/bot{telegram_provider.config.bot_token}"
        assert telegram_provider.config.bot_token in expected_base

    def test_provider_constants(self, telegram_provider) -> None:
        """Test provider has correct constants"""
        # Test API base URL is set
        assert hasattr(telegram_provider, "TELEGRAM_API_BASE")
        url = urlparse(telegram_provider.TELEGRAM_API_BASE)
        assert url.hostname == "api.telegram.org"
        assert url.scheme == "https"

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

    def test_long_message_handling(self) -> None:
        """Test handling of long messages"""
        long_message = NotificationMessage(
            title="Test" * 100,  # Very long title
            message="Content" * 200,  # Very long message
            notification_type=NotificationType.INFO,
        )

        # Should not raise an exception during creation
        assert len(long_message.title) > 100
        assert len(long_message.message) > 100

    def test_special_characters_in_markdownv2_escaping(self) -> None:
        """Test that MarkdownV2 properly escapes special characters"""
        config = TelegramConfig(
            bot_token="123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijk",
            chat_id="12345678",
            parse_mode="MarkdownV2",
        )
        provider = TelegramProvider(config)

        message = NotificationMessage(
            title="Test_with*special[chars](and)more!",
            message="Message with. special+ chars= here| too{}",
            notification_type=NotificationType.INFO,
        )

        formatted = provider._format_message(message)
        
        # Check that special characters are properly escaped
        assert "Test\\_with\\*special\\[chars\\]\\(and\\)more\\!" in formatted
        assert "Message with\\. special\\+ chars\\= here\\| too\\{\\}" in formatted

    def test_metadata_filtering(self, telegram_provider) -> None:
        """Test that internal metadata fields are filtered out"""
        message = NotificationMessage(
            title="Test",
            message="Test message",
            notification_type=NotificationType.INFO,
            metadata={
                "backup_id": "test-123",
                "response": "internal response data",  # Should be filtered
                "status_code": 200,  # Should be filtered
                "duration": "5 minutes",
            }
        )

        formatted = telegram_provider._format_message(message)
        
        # Should include user-visible metadata
        assert "backup_id" in formatted or "Backup Id" in formatted
        assert "duration" in formatted or "Duration" in formatted
        
        # Should NOT include internal metadata
        assert "response" not in formatted
        assert "status_code" not in formatted
