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
            TelegramConfig(
                bot_token="abc:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijk",
                chat_id="12345678",
            )

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
            metadata={"backup_id": "test-123", "duration": "5 minutes"},
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
        expected_base = (
            f"https://api.telegram.org/bot{telegram_provider.config.bot_token}"
        )
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
            },
        )

        formatted = telegram_provider._format_message(message)

        # Should include user-visible metadata
        assert "backup_id" in formatted or "Backup Id" in formatted
        assert "duration" in formatted or "Duration" in formatted

        # Should NOT include internal metadata
        assert "response" not in formatted
        assert "status_code" not in formatted

    # ===== SEND_NOTIFICATION TESTS =====

    @pytest.mark.asyncio
    async def test_send_notification_success(
        self, telegram_config, mock_http_client, sample_message
    ):
        """Test successful notification sending"""
        # Setup mock response
        mock_response = Mock()
        mock_response.status = 200
        mock_response.text = AsyncMock(
            return_value='{"ok": true, "result": {"message_id": 123}}'
        )
        mock_response.json = AsyncMock(
            return_value={"ok": True, "result": {"message_id": 123}}
        )
        mock_http_client.post.return_value = mock_response

        provider = TelegramProvider(telegram_config, mock_http_client)
        result = await provider.send_notification(sample_message)

        # Verify result
        assert result.success is True
        assert result.provider == "telegram"
        assert result.message == "Notification sent successfully"
        assert result.error is None
        assert "response" in result.metadata

        # Verify HTTP call
        mock_http_client.post.assert_called_once()
        call_args = mock_http_client.post.call_args
        assert (
            call_args[0][0]
            == f"https://api.telegram.org/bot{telegram_config.bot_token}/sendMessage"
        )

        # Verify payload
        payload = call_args[1]["json"]
        assert payload["chat_id"] == telegram_config.chat_id
        assert payload["disable_notification"] == telegram_config.disable_notification
        assert "text" in payload
        assert payload["parse_mode"] == telegram_config.parse_mode

    @pytest.mark.asyncio
    async def test_send_notification_api_error(
        self, telegram_config, mock_http_client, sample_message
    ):
        """Test handling of Telegram API errors (200 status but ok=false)"""
        # Setup mock response with API error
        mock_response = Mock()
        mock_response.status = 200
        mock_response.text = AsyncMock(
            return_value='{"ok": false, "description": "Bad Request: chat not found"}'
        )
        mock_response.json = AsyncMock(
            return_value={"ok": False, "description": "Bad Request: chat not found"}
        )
        mock_http_client.post.return_value = mock_response

        provider = TelegramProvider(telegram_config, mock_http_client)
        result = await provider.send_notification(sample_message)

        # Verify result
        assert result.success is False
        assert result.provider == "telegram"
        assert result.message == "API returned error"
        assert result.error == "Bad Request: chat not found"
        assert "response" in result.metadata

    @pytest.mark.asyncio
    async def test_send_notification_http_error(
        self, telegram_config, mock_http_client, sample_message
    ):
        """Test handling of HTTP errors (non-200 status)"""
        # Setup mock response with HTTP error
        mock_response = Mock()
        mock_response.status = 401
        mock_response.text = AsyncMock(return_value="Unauthorized")
        mock_http_client.post.return_value = mock_response

        provider = TelegramProvider(telegram_config, mock_http_client)
        result = await provider.send_notification(sample_message)

        # Verify result
        assert result.success is False
        assert result.provider == "telegram"
        assert result.message == "HTTP error 401"
        assert result.error == "Unauthorized"
        assert result.metadata["status_code"] == 401

    @pytest.mark.asyncio
    async def test_send_notification_json_parse_error_but_200(
        self, telegram_config, mock_http_client, sample_message
    ):
        """Test handling when JSON parsing fails but HTTP status is 200 (consider success)"""
        # Setup mock response that returns 200 but invalid JSON
        mock_response = Mock()
        mock_response.status = 200
        mock_response.text = AsyncMock(return_value="Invalid JSON response")
        mock_response.json = AsyncMock(side_effect=ValueError("Invalid JSON"))
        mock_http_client.post.return_value = mock_response

        provider = TelegramProvider(telegram_config, mock_http_client)
        result = await provider.send_notification(sample_message)

        # Should still consider it success since status is 200
        assert result.success is True
        assert result.provider == "telegram"
        assert result.message == "Notification sent successfully"
        assert result.error is None
        assert "response" in result.metadata

    @pytest.mark.asyncio
    async def test_send_notification_network_exception(
        self, telegram_config, mock_http_client, sample_message
    ):
        """Test handling of network exceptions"""
        # Setup mock to raise exception
        mock_http_client.post.side_effect = Exception("Network error")

        provider = TelegramProvider(telegram_config, mock_http_client)
        result = await provider.send_notification(sample_message)

        # Verify result
        assert result.success is False
        assert result.provider == "telegram"
        assert result.message == "Exception occurred"
        assert result.error == "Network error"
        assert result.metadata == {}

    @pytest.mark.asyncio
    async def test_send_notification_payload_construction(
        self, mock_http_client, sample_message
    ):
        """Test that notification payload is constructed correctly for different configurations"""
        # Test with parse_mode = None (should not include parse_mode in payload)
        config_no_parse = TelegramConfig(
            bot_token="123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijk",
            chat_id="@test",
            parse_mode="None",
            disable_notification=True,
        )

        mock_response = Mock()
        mock_response.status = 200
        mock_response.text = AsyncMock(return_value='{"ok": true}')
        mock_response.json = AsyncMock(return_value={"ok": True})
        mock_http_client.post.return_value = mock_response

        provider = TelegramProvider(config_no_parse, mock_http_client)
        await provider.send_notification(sample_message)

        # Check that parse_mode is not in payload when set to "None"
        call_args = mock_http_client.post.call_args
        payload = call_args[1]["json"]
        assert "parse_mode" not in payload
        assert payload["disable_notification"] is True

    @pytest.mark.asyncio
    async def test_send_notification_empty_parse_mode(
        self, mock_http_client, sample_message
    ):
        """Test notification with empty parse_mode (plain text)"""
        config_empty_parse = TelegramConfig(
            bot_token="123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijk",
            chat_id="@test",
            parse_mode="",
            disable_notification=False,
        )

        mock_response = Mock()
        mock_response.status = 200
        mock_response.text = AsyncMock(return_value='{"ok": true}')
        mock_response.json = AsyncMock(return_value={"ok": True})
        mock_http_client.post.return_value = mock_response

        provider = TelegramProvider(config_empty_parse, mock_http_client)
        await provider.send_notification(sample_message)

        # Check that parse_mode is not in payload when empty string
        call_args = mock_http_client.post.call_args
        payload = call_args[1]["json"]
        assert "parse_mode" not in payload

    @pytest.mark.asyncio
    async def test_send_notification_with_metadata(
        self, telegram_config, mock_http_client
    ):
        """Test notification sending with metadata in message"""
        message_with_metadata = NotificationMessage(
            title="Backup Complete",
            message="Daily backup finished successfully",
            notification_type=NotificationType.SUCCESS,
            metadata={
                "backup_size": "2.5 GB",
                "duration": "45 minutes",
                "files_backed_up": 1250,
            },
        )

        mock_response = Mock()
        mock_response.status = 200
        mock_response.text = AsyncMock(return_value='{"ok": true}')
        mock_response.json = AsyncMock(return_value={"ok": True})
        mock_http_client.post.return_value = mock_response

        provider = TelegramProvider(telegram_config, mock_http_client)
        result = await provider.send_notification(message_with_metadata)

        assert result.success is True

        # Verify the formatted message includes metadata
        call_args = mock_http_client.post.call_args
        payload = call_args[1]["json"]
        message_text = payload["text"]

        # Should contain title, message, and metadata
        assert "Backup Complete" in message_text
        assert "Daily backup finished successfully" in message_text
        assert "Details:" in message_text
        assert "Backup Size" in message_text  # metadata keys are formatted
        assert "2.5 GB" in message_text

    @pytest.mark.asyncio
    async def test_send_notification_different_notification_types(
        self, telegram_config, mock_http_client
    ):
        """Test that different notification types get appropriate emoji formatting"""
        mock_response = Mock()
        mock_response.status = 200
        mock_response.text = AsyncMock(return_value='{"ok": true}')
        mock_response.json = AsyncMock(return_value={"ok": True})
        mock_http_client.post.return_value = mock_response

        provider = TelegramProvider(telegram_config, mock_http_client)

        # Test different notification types
        notification_types = [
            (NotificationType.SUCCESS, "✅"),
            (NotificationType.FAILURE, "❌"),
            (NotificationType.WARNING, "⚠️"),
            (NotificationType.INFO, "ℹ️"),
        ]

        for notification_type, expected_emoji in notification_types:
            mock_http_client.post.reset_mock()

            message = NotificationMessage(
                title="Test",
                message="Test message",
                notification_type=notification_type,
            )

            await provider.send_notification(message)

            # Check that the correct emoji is used
            call_args = mock_http_client.post.call_args
            payload = call_args[1]["json"]
            message_text = payload["text"]
            assert expected_emoji in message_text

    @pytest.mark.asyncio
    async def test_send_notification_api_url_construction(
        self, telegram_config, mock_http_client, sample_message
    ):
        """Test that the correct API URL is constructed"""
        mock_response = Mock()
        mock_response.status = 200
        mock_response.text = AsyncMock(return_value='{"ok": true}')
        mock_response.json = AsyncMock(return_value={"ok": True})
        mock_http_client.post.return_value = mock_response

        provider = TelegramProvider(telegram_config, mock_http_client)
        await provider.send_notification(sample_message)

        # Verify the correct URL was called
        expected_url = (
            f"https://api.telegram.org/bot{telegram_config.bot_token}/sendMessage"
        )
        mock_http_client.post.assert_called_once()
        call_args = mock_http_client.post.call_args
        assert call_args[0][0] == expected_url

    @pytest.mark.asyncio
    async def test_send_notification_unknown_api_error(
        self, telegram_config, mock_http_client, sample_message
    ):
        """Test handling of API errors without description"""
        # Setup mock response with API error but no description
        mock_response = Mock()
        mock_response.status = 200
        mock_response.text = AsyncMock(return_value='{"ok": false}')
        mock_response.json = AsyncMock(return_value={"ok": False})
        mock_http_client.post.return_value = mock_response

        provider = TelegramProvider(telegram_config, mock_http_client)
        result = await provider.send_notification(sample_message)

        # Verify result handles missing description gracefully
        assert result.success is False
        assert result.provider == "telegram"
        assert result.message == "API returned error"
        assert result.error == "Unknown error"  # Default when description is missing

    # ===== TEST_CONNECTION TESTS =====

    @pytest.mark.asyncio
    async def test_test_connection_success(self, telegram_config, mock_http_client):
        """Test successful connection test"""
        # Setup mock responses for both getMe and test notification
        getme_response = Mock()
        getme_response.status = 200
        getme_response.json = AsyncMock(
            return_value={
                "ok": True,
                "result": {"id": 123456789, "is_bot": True, "first_name": "TestBot"},
            }
        )

        test_notification_response = Mock()
        test_notification_response.status = 200
        test_notification_response.text = AsyncMock(
            return_value='{"ok": true, "result": {"message_id": 456}}'
        )
        test_notification_response.json = AsyncMock(
            return_value={"ok": True, "result": {"message_id": 456}}
        )

        # Mock HTTP client to return different responses for different calls
        mock_http_client.post.side_effect = [getme_response, test_notification_response]

        provider = TelegramProvider(telegram_config, mock_http_client)
        result = await provider.test_connection()

        # Verify result
        assert result is True

        # Verify both API calls were made
        assert mock_http_client.post.call_count == 2

        # Verify getMe call
        getme_call = mock_http_client.post.call_args_list[0]
        expected_getme_url = (
            f"https://api.telegram.org/bot{telegram_config.bot_token}/getMe"
        )
        assert getme_call[0][0] == expected_getme_url

        # Verify test message call
        test_call = mock_http_client.post.call_args_list[1]
        expected_send_url = (
            f"https://api.telegram.org/bot{telegram_config.bot_token}/sendMessage"
        )
        assert test_call[0][0] == expected_send_url

        # Verify test message payload
        test_payload = test_call[1]["json"]
        assert test_payload["chat_id"] == telegram_config.chat_id
        assert "Borgitory Test" in test_payload["text"]
        assert "test notification" in test_payload["text"]

    @pytest.mark.asyncio
    async def test_test_connection_getme_http_error(
        self, telegram_config, mock_http_client
    ):
        """Test connection test when getMe API returns HTTP error"""
        # Setup mock response for getMe with HTTP error
        getme_response = Mock()
        getme_response.status = 401
        mock_http_client.post.return_value = getme_response

        provider = TelegramProvider(telegram_config, mock_http_client)
        result = await provider.test_connection()

        # Verify result
        assert result is False

        # Verify only getMe was called (test notification should not be attempted)
        assert mock_http_client.post.call_count == 1

    @pytest.mark.asyncio
    async def test_test_connection_getme_api_error(
        self, telegram_config, mock_http_client
    ):
        """Test connection test when getMe API returns ok=false"""
        # Setup mock response for getMe with API error
        getme_response = Mock()
        getme_response.status = 200
        getme_response.json = AsyncMock(
            return_value={"ok": False, "description": "Unauthorized"}
        )
        mock_http_client.post.return_value = getme_response

        provider = TelegramProvider(telegram_config, mock_http_client)
        result = await provider.test_connection()

        # Verify result
        assert result is False

        # Verify only getMe was called
        assert mock_http_client.post.call_count == 1

    @pytest.mark.asyncio
    async def test_test_connection_getme_success_but_notification_fails(
        self, telegram_config, mock_http_client
    ):
        """Test connection test when getMe succeeds but test notification fails"""
        # Setup mock responses
        getme_response = Mock()
        getme_response.status = 200
        getme_response.json = AsyncMock(
            return_value={"ok": True, "result": {"id": 123456789, "is_bot": True}}
        )

        # Test notification fails
        test_notification_response = Mock()
        test_notification_response.status = 200
        test_notification_response.text = AsyncMock(
            return_value='{"ok": false, "description": "Chat not found"}'
        )
        test_notification_response.json = AsyncMock(
            return_value={"ok": False, "description": "Chat not found"}
        )

        mock_http_client.post.side_effect = [getme_response, test_notification_response]

        provider = TelegramProvider(telegram_config, mock_http_client)
        result = await provider.test_connection()

        # Verify result - should be False because test notification failed
        assert result is False

        # Verify both calls were made
        assert mock_http_client.post.call_count == 2

    @pytest.mark.asyncio
    async def test_test_connection_network_exception_on_getme(
        self, telegram_config, mock_http_client
    ):
        """Test connection test when getMe raises network exception"""
        # Setup mock to raise exception on getMe
        mock_http_client.post.side_effect = Exception("Network timeout")

        provider = TelegramProvider(telegram_config, mock_http_client)
        result = await provider.test_connection()

        # Verify result
        assert result is False

    @pytest.mark.asyncio
    async def test_test_connection_network_exception_on_test_notification(
        self, telegram_config, mock_http_client
    ):
        """Test connection test when getMe succeeds but test notification raises exception"""
        # Setup successful getMe response
        getme_response = Mock()
        getme_response.status = 200
        getme_response.json = AsyncMock(
            return_value={"ok": True, "result": {"id": 123456789, "is_bot": True}}
        )

        # First call (getMe) succeeds, second call (test notification) raises exception
        mock_http_client.post.side_effect = [getme_response, Exception("Network error")]

        provider = TelegramProvider(telegram_config, mock_http_client)
        result = await provider.test_connection()

        # Verify result - should be False because test notification failed
        assert result is False

        # Verify both calls were attempted
        assert mock_http_client.post.call_count == 2

    @pytest.mark.asyncio
    async def test_test_connection_getme_json_parse_error(
        self, telegram_config, mock_http_client
    ):
        """Test connection test when getMe returns invalid JSON"""
        # Setup mock response with invalid JSON
        getme_response = Mock()
        getme_response.status = 200
        getme_response.json = AsyncMock(side_effect=ValueError("Invalid JSON"))
        mock_http_client.post.return_value = getme_response

        provider = TelegramProvider(telegram_config, mock_http_client)
        result = await provider.test_connection()

        # Verify result
        assert result is False

    @pytest.mark.asyncio
    async def test_test_connection_uses_correct_test_message(
        self, telegram_config, mock_http_client
    ):
        """Test that connection test uses the correct test message format"""
        # Setup successful responses
        getme_response = Mock()
        getme_response.status = 200
        getme_response.json = AsyncMock(
            return_value={"ok": True, "result": {"id": 123456789, "is_bot": True}}
        )

        test_notification_response = Mock()
        test_notification_response.status = 200
        test_notification_response.text = AsyncMock(return_value='{"ok": true}')
        test_notification_response.json = AsyncMock(return_value={"ok": True})

        mock_http_client.post.side_effect = [getme_response, test_notification_response]

        provider = TelegramProvider(telegram_config, mock_http_client)
        await provider.test_connection()

        # Verify test message payload
        test_call = mock_http_client.post.call_args_list[1]
        test_payload = test_call[1]["json"]

        # Verify test message content
        assert "Borgitory Test" in test_payload["text"]
        assert (
            "This is a test notification from Borgitory backup system."
            in test_payload["text"]
        )
        assert test_payload["chat_id"] == telegram_config.chat_id
        assert (
            test_payload["disable_notification"] == telegram_config.disable_notification
        )

        # Should include parse_mode if configured
        if telegram_config.parse_mode and telegram_config.parse_mode != "None":
            assert test_payload["parse_mode"] == telegram_config.parse_mode

    @pytest.mark.asyncio
    async def test_test_connection_with_different_configs(self, mock_http_client):
        """Test connection test works with different configuration options"""
        configs_to_test = [
            # Different parse modes
            TelegramConfig(
                bot_token="123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijk",
                chat_id="@test",
                parse_mode="Markdown",
                disable_notification=True,
            ),
            TelegramConfig(
                bot_token="987654321:ZYXWVUTSRQPONMLKJIHGFEDCBAzyxwvuts",
                chat_id="-123456789",
                parse_mode="",
                disable_notification=False,
            ),
        ]

        for config in configs_to_test:
            # Reset mock for each config
            mock_http_client.post.reset_mock()

            # Setup successful responses
            getme_response = Mock()
            getme_response.status = 200
            getme_response.json = AsyncMock(
                return_value={"ok": True, "result": {"id": 123456789, "is_bot": True}}
            )

            test_notification_response = Mock()
            test_notification_response.status = 200
            test_notification_response.text = AsyncMock(return_value='{"ok": true}')
            test_notification_response.json = AsyncMock(return_value={"ok": True})

            mock_http_client.post.side_effect = [
                getme_response,
                test_notification_response,
            ]

            provider = TelegramProvider(config, mock_http_client)
            result = await provider.test_connection()

            # Should succeed for all valid configs
            assert result is True

            # Verify correct configuration was used
            test_call = mock_http_client.post.call_args_list[1]
            test_payload = test_call[1]["json"]
            assert test_payload["chat_id"] == config.chat_id
            assert test_payload["disable_notification"] == config.disable_notification
