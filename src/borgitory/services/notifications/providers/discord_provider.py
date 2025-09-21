"""
Discord webhook notification provider implementation.
"""

import logging
from typing import Dict, List, Optional, Protocol, cast
import aiohttp
from pydantic import Field, field_validator

from .base import NotificationProvider, NotificationProviderConfig
from ..types import (
    NotificationMessage,
    NotificationResult,
    ConnectionInfo,
    NotificationType,
)
from ..registry import register_provider

logger = logging.getLogger(__name__)


class HttpClient(Protocol):
    """Protocol for HTTP client dependency injection"""

    async def post(
        self,
        url: str,
        json: Optional[Dict[str, object]] = None,
        data: Optional[Dict[str, object]] = None,
    ) -> "HttpResponse":
        """Make a POST request with JSON or form data payload"""
        ...

    async def close(self) -> None:
        """Close the HTTP client and cleanup resources"""
        ...


class HttpResponse(Protocol):
    """Protocol for HTTP response"""

    @property
    def status(self) -> int:
        """HTTP status code"""
        ...

    async def text(self) -> str:
        """Get response text"""
        ...

    async def json(self) -> Dict[str, object]:
        """Get response as JSON"""
        ...


class AiohttpClient:
    """Default HTTP client implementation using aiohttp"""

    def __init__(self, session: Optional[aiohttp.ClientSession] = None):
        """Initialize with optional existing session"""
        self._session = session
        self._owns_session = session is None

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session"""
        if self._session is None:
            self._session = aiohttp.ClientSession()
        return self._session

    async def post(
        self,
        url: str,
        json: Optional[Dict[str, object]] = None,
        data: Optional[Dict[str, object]] = None,
    ) -> "AiohttpResponse":
        """Make a POST request using aiohttp"""
        session = await self._get_session()
        if json is not None:
            async with session.post(url, json=json) as response:
                return await AiohttpResponse.create(response)
        elif data is not None:
            async with session.post(url, data=data) as response:
                return await AiohttpResponse.create(response)
        else:
            async with session.post(url) as response:
                return await AiohttpResponse.create(response)

    async def close(self) -> None:
        """Close the HTTP client session if we own it"""
        if self._session and self._owns_session:
            await self._session.close()
            self._session = None


class AiohttpResponse:
    """Wrapper for aiohttp response to match protocol"""

    def __init__(
        self, status: int, text_data: str, json_data: Optional[Dict[str, object]] = None
    ):
        self._status = status
        self._text_data = text_data
        self._json_data = json_data

    @classmethod
    async def create(cls, response: aiohttp.ClientResponse) -> "AiohttpResponse":
        """Create AiohttpResponse by reading data within the context manager"""
        text_data = await response.text()
        json_data = None

        # Try to parse JSON if the response looks like JSON
        if text_data.strip().startswith("{") or text_data.strip().startswith("["):
            try:
                json_data = await response.json()
            except Exception:
                # If JSON parsing fails, that's okay - we'll just have text
                pass

        return cls(response.status, text_data, json_data)

    @property
    def status(self) -> int:
        return self._status

    async def text(self) -> str:
        return self._text_data

    async def json(self) -> Dict[str, object]:
        if self._json_data is not None:
            return self._json_data

        # Fallback: try to parse the text as JSON
        import json

        try:
            return cast(Dict[str, object], json.loads(self._text_data))
        except json.JSONDecodeError:
            raise ValueError(f"Response is not valid JSON: {self._text_data}")


class DiscordConfig(NotificationProviderConfig):
    """Configuration for Discord webhook notifications"""

    webhook_url: str = Field(..., description="Discord webhook URL")
    username: str = Field(default="Borgitory", description="Bot username")
    avatar_url: str = Field(default="", description="Bot avatar URL (optional)")

    @field_validator("webhook_url")
    @classmethod
    def validate_webhook_url(cls, v: str) -> str:
        """Validate Discord webhook URL format"""
        if not v.startswith("https://discord.com/api/webhooks/") and not v.startswith(
            "https://discordapp.com/api/webhooks/"
        ):
            raise ValueError("Invalid Discord webhook URL format")
        return v


class DiscordProvider(NotificationProvider):
    """
    Discord webhook notification provider implementation.
    """

    config_class = DiscordConfig

    def __init__(
        self, config: DiscordConfig, http_client: Optional[HttpClient] = None
    ) -> None:
        super().__init__(config)
        self.config: DiscordConfig = config
        self.http_client = http_client or AiohttpClient()

    async def send_notification(
        self, message: NotificationMessage
    ) -> NotificationResult:
        """Send a notification via Discord webhook"""
        try:
            # Create Discord embed based on notification type
            embed_color = self._get_color_for_type(message.notification_type)

            embed = {
                "title": message.title,
                "description": message.message,
                "color": embed_color,
                "timestamp": None,  # Discord will use current time
                "footer": {"text": "Borgitory Backup System"},
            }

            # Add fields based on metadata
            if message.metadata:
                fields = []
                for key, value in message.metadata.items():
                    if key not in ["response", "status_code"]:  # Skip internal fields
                        fields.append(
                            {
                                "name": key.replace("_", " ").title(),
                                "value": str(value),
                                "inline": True,
                            }
                        )
                if fields:
                    embed["fields"] = fields

            payload = {"username": self.config.username, "embeds": [embed]}

            if self.config.avatar_url:
                payload["avatar_url"] = self.config.avatar_url

            response = await self.http_client.post(
                self.config.webhook_url, json=cast(Dict[str, object], payload)
            )
            response_text = await response.text()

            if response.status == 204:  # Discord webhooks return 204 on success
                logger.info(f"Discord notification sent: {message.title}")
                return NotificationResult(
                    success=True,
                    provider="discord",
                    message="Notification sent successfully",
                    metadata={"response": response_text},
                )
            else:
                logger.error(
                    f"Discord webhook error {response.status}: {response_text}"
                )
                return NotificationResult(
                    success=False,
                    provider="discord",
                    message=f"HTTP error {response.status}",
                    error=response_text,
                    metadata={"status_code": response.status},
                )

        except Exception as e:
            logger.error(f"Error sending Discord notification: {e}")
            return NotificationResult(
                success=False,
                provider="discord",
                message="Exception occurred",
                error=str(e),
            )

    async def test_connection(self) -> bool:
        """Test Discord webhook connection"""
        try:
            test_message = NotificationMessage(
                title="Borgitory Test",
                message="This is a test notification from Borgitory backup system.",
                notification_type=NotificationType.INFO,
            )

            result = await self.send_notification(test_message)
            return result.success

        except Exception as e:
            logger.error(f"Discord connection test failed: {e}")
            return False

    def get_connection_info(self) -> ConnectionInfo:
        """Get connection info for display"""
        webhook_id = (
            self.config.webhook_url.split("/")[-2]
            if "/" in self.config.webhook_url
            else "unknown"
        )
        return ConnectionInfo(
            provider="discord",
            endpoint=f"Webhook: {webhook_id[:8]}...",
            status="configured",
        )

    def get_sensitive_fields(self) -> List[str]:
        """Get list of fields that should be encrypted"""
        return ["webhook_url"]

    def get_display_details(self, config_dict: Dict[str, object]) -> Dict[str, object]:
        """Get provider-specific display details for the UI"""
        webhook_url = str(config_dict.get("webhook_url", ""))
        webhook_id = webhook_url.split("/")[-2] if "/" in webhook_url else "unknown"
        masked_webhook = f"{webhook_id[:8]}..." if len(webhook_id) >= 8 else "***"

        details = f"""
        <div class="space-y-2">
            <div><span class="font-medium">Webhook:</span> {masked_webhook}</div>
            <div><span class="font-medium">Username:</span> {config_dict.get("username", "Borgitory")}</div>
        </div>
        """

        return {"provider_name": "Discord", "provider_details": details.strip()}

    def _get_color_for_type(self, notification_type: NotificationType) -> int:
        """Get Discord embed color for notification type"""
        color_map = {
            NotificationType.SUCCESS: 0x00FF00,  # Green
            NotificationType.FAILURE: 0xFF0000,  # Red
            NotificationType.WARNING: 0xFFA500,  # Orange
            NotificationType.INFO: 0x0099FF,  # Blue
        }
        return color_map.get(notification_type, 0x0099FF)


# Register the provider directly
@register_provider(
    name="discord",
    label="Discord Webhook",
    description="Send notifications to Discord channel via webhook",
    supports_priority=False,
    supports_formatting=True,
    requires_credentials=True,
)
class DiscordProviderRegistered(DiscordProvider):
    """Registered Discord provider"""

    config_class = DiscordConfig
