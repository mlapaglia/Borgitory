"""
Tests for Discord notification provider with dependency injection.
"""

import pytest
from unittest.mock import AsyncMock
from typing import Dict, Any, Optional

from borgitory.services.notifications.providers.discord_provider import (
    DiscordProvider,
    DiscordConfig,
)
from borgitory.services.notifications.types import (
    NotificationMessage,
    NotificationType,
)


class MockHttpResponse:
    """Mock HTTP response for testing"""

    def __init__(self, status: int, text: str = "", json_data: Dict[str, Any] = None):
        self.status = status
        self._text = text
        self._json_data = json_data or {}

    async def text(self) -> str:
        return self._text

    async def json(self) -> Dict[str, Any]:
        return self._json_data


class MockHttpClient:
    """Mock HTTP client for testing"""

    def __init__(self):
        self.post = AsyncMock()
        self.close = AsyncMock()

    async def post(
        self,
        url: str,
        json: Optional[Dict[str, Any]] = None,
        data: Optional[Dict[str, Any]] = None,
    ) -> MockHttpResponse:
        return await self.post(url, json, data)

    async def close(self) -> None:
        return await self.close()


@pytest.fixture
def discord_config() -> DiscordConfig:
    """Create a test Discord configuration"""
    return DiscordConfig(
        webhook_url="https://discord.com/api/webhooks/123456789/test-webhook-token",
        username="TestBot",
        avatar_url="https://example.com/avatar.png",
    )


@pytest.fixture
def mock_http_client() -> MockHttpClient:
    """Create a mock HTTP client"""
    return MockHttpClient()


@pytest.fixture
def discord_provider(discord_config, mock_http_client) -> DiscordProvider:
    """Create Discord provider with injected mock HTTP client"""
    return DiscordProvider(discord_config, http_client=mock_http_client)


class TestDiscordProvider:
    """Test Discord notification provider"""

    def test_provider_initialization(self, discord_config, mock_http_client):
        """Test provider initializes correctly with injected dependencies"""
        provider = DiscordProvider(discord_config, http_client=mock_http_client)

        assert provider.config == discord_config
        assert provider.http_client == mock_http_client

    def test_provider_initialization_with_defaults(self, discord_config):
        """Test provider initializes with default HTTP client when none provided"""
        provider = DiscordProvider(discord_config)

        assert provider.config == discord_config
        assert provider.http_client is not None
        # Should use default AiohttpClient
        assert provider.http_client.__class__.__name__ == "AiohttpClient"

    @pytest.mark.asyncio
    async def test_send_notification_success(self, discord_provider, mock_http_client):
        """Test successful notification sending"""
        # Setup mock response
        mock_response = MockHttpResponse(status=204, text="")
        mock_http_client.post.return_value = mock_response

        # Create test message
        message = NotificationMessage(
            title="Test Notification",
            message="This is a test message",
            notification_type=NotificationType.SUCCESS,
            metadata={"job_id": "test-123"},
        )

        # Send notification
        result = await discord_provider.send_notification(message)

        # Verify result
        assert result.success is True
        assert result.provider == "discord"
        assert result.message == "Notification sent successfully"

        # Verify HTTP client was called correctly
        mock_http_client.post.assert_called_once()
        call_args = mock_http_client.post.call_args
        assert call_args[0][0] == discord_provider.config.webhook_url

        # Verify payload structure
        payload = call_args[1]["json"]
        assert payload["username"] == "TestBot"
        assert payload["avatar_url"] == "https://example.com/avatar.png"
        assert len(payload["embeds"]) == 1

        embed = payload["embeds"][0]
        assert embed["title"] == "Test Notification"
        assert embed["description"] == "This is a test message"
        assert embed["color"] == 0x00FF00  # Green for success
        assert len(embed["fields"]) == 1
        assert embed["fields"][0]["name"] == "Job Id"
        assert embed["fields"][0]["value"] == "test-123"

    @pytest.mark.asyncio
    async def test_send_notification_http_error(
        self, discord_provider, mock_http_client
    ):
        """Test notification sending with HTTP error"""
        # Setup mock error response
        mock_response = MockHttpResponse(status=400, text="Bad Request")
        mock_http_client.post.return_value = mock_response

        # Create test message
        message = NotificationMessage(
            title="Test Notification",
            message="This is a test message",
            notification_type=NotificationType.FAILURE,
        )

        # Send notification
        result = await discord_provider.send_notification(message)

        # Verify error result
        assert result.success is False
        assert result.provider == "discord"
        assert result.message == "HTTP error 400"
        assert result.error == "Bad Request"
        assert result.metadata["status_code"] == 400

    @pytest.mark.asyncio
    async def test_send_notification_exception(
        self, discord_provider, mock_http_client
    ):
        """Test notification sending with exception"""
        # Setup mock to raise exception
        mock_http_client.post.side_effect = Exception("Network error")

        # Create test message
        message = NotificationMessage(
            title="Test Notification",
            message="This is a test message",
            notification_type=NotificationType.INFO,
        )

        # Send notification
        result = await discord_provider.send_notification(message)

        # Verify error result
        assert result.success is False
        assert result.provider == "discord"
        assert result.message == "Exception occurred"
        assert result.error == "Network error"

    @pytest.mark.asyncio
    async def test_test_connection_success(self, discord_provider, mock_http_client):
        """Test successful connection test"""
        # Setup mock response
        mock_response = MockHttpResponse(status=204, text="")
        mock_http_client.post.return_value = mock_response

        # Test connection
        result = await discord_provider.test_connection()

        # Verify success
        assert result is True
        mock_http_client.post.assert_called_once()

    @pytest.mark.asyncio
    async def test_test_connection_failure(self, discord_provider, mock_http_client):
        """Test failed connection test"""
        # Setup mock error response
        mock_response = MockHttpResponse(status=401, text="Unauthorized")
        mock_http_client.post.return_value = mock_response

        # Test connection
        result = await discord_provider.test_connection()

        # Verify failure
        assert result is False

    def test_get_connection_info(self, discord_provider):
        """Test connection info generation"""
        info = discord_provider.get_connection_info()

        assert info.provider == "discord"
        assert "Webhook:" in info.endpoint
        assert info.status == "configured"

    def test_get_sensitive_fields(self, discord_provider):
        """Test sensitive fields identification"""
        fields = discord_provider.get_sensitive_fields()

        assert fields == ["webhook_url"]

    def test_get_display_details(self, discord_provider):
        """Test display details generation"""
        config_dict = {
            "webhook_url": "https://discord.com/api/webhooks/123456789/test-webhook-token",
            "username": "TestBot",
        }

        details = discord_provider.get_display_details(config_dict)

        assert details["provider_name"] == "Discord"
        assert "TestBot" in details["provider_details"]
        assert "12345678..." in details["provider_details"]  # Masked webhook ID

    def test_color_mapping(self, discord_provider):
        """Test notification type to color mapping"""
        assert (
            discord_provider._get_color_for_type(NotificationType.SUCCESS) == 0x00FF00
        )
        assert (
            discord_provider._get_color_for_type(NotificationType.FAILURE) == 0xFF0000
        )
        assert (
            discord_provider._get_color_for_type(NotificationType.WARNING) == 0xFFA500
        )
        assert discord_provider._get_color_for_type(NotificationType.INFO) == 0x0099FF


class TestDiscordConfig:
    """Test Discord configuration validation"""

    def test_valid_discord_webhook_url(self):
        """Test valid Discord webhook URLs"""
        valid_urls = [
            "https://discord.com/api/webhooks/123/token",
            "https://discordapp.com/api/webhooks/456/another-token",
        ]

        for url in valid_urls:
            config = DiscordConfig(webhook_url=url)
            assert config.webhook_url == url

    def test_invalid_discord_webhook_url(self):
        """Test invalid Discord webhook URLs"""
        invalid_urls = [
            "https://example.com/webhook",
            "https://discord.com/api/other/123/token",
            "http://discord.com/api/webhooks/123/token",  # HTTP not HTTPS
            "not-a-url-at-all",
        ]

        for url in invalid_urls:
            with pytest.raises(ValueError, match="Invalid Discord webhook URL format"):
                DiscordConfig(webhook_url=url)

    def test_default_values(self):
        """Test default configuration values"""
        config = DiscordConfig(webhook_url="https://discord.com/api/webhooks/123/token")

        assert config.username == "Borgitory"
        assert config.avatar_url == ""
