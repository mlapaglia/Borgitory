"""
Pushover notification provider implementation.
"""

import logging
from typing import Dict, List, Optional
from pydantic import Field, field_validator

# Import HttpClient protocol from discord_provider for consistency
from .discord_provider import HttpClient, AiohttpClient

from .base import NotificationProvider, NotificationProviderConfig
from ..types import (
    NotificationMessage,
    NotificationResult,
    ConnectionInfo,
    NotificationType,
)
from ..registry import register_provider

logger = logging.getLogger(__name__)


class PushoverConfig(NotificationProviderConfig):
    """Configuration for Pushover notifications"""

    user_key: str = Field(
        ..., min_length=30, max_length=30, description="Pushover user key"
    )
    app_token: str = Field(
        ..., min_length=30, max_length=30, description="Pushover application token"
    )
    priority: int = Field(
        default=0, ge=-2, le=2, description="Default notification priority"
    )
    sound: str = Field(default="default", description="Default notification sound")
    device: Optional[str] = Field(
        default=None, description="Target device name (optional)"
    )

    @field_validator("user_key")
    @classmethod
    def validate_user_key(cls, v: str) -> str:
        """Validate Pushover user key format"""
        if not v or len(v) != 30:
            raise ValueError("Pushover user key must be exactly 30 characters long")
        return v

    @field_validator("app_token")
    @classmethod
    def validate_app_token(cls, v: str) -> str:
        """Validate Pushover app token format"""
        if not v or len(v) != 30:
            raise ValueError("Pushover app token must be exactly 30 characters long")
        return v


class PushoverProvider(NotificationProvider):
    """
    Pushover notification provider implementation.
    """

    config_class = PushoverConfig
    PUSHOVER_API_URL = "https://api.pushover.net/1/messages.json"

    def __init__(
        self, config: PushoverConfig, http_client: Optional[HttpClient] = None
    ) -> None:
        super().__init__(config)
        self.config: PushoverConfig = config
        self.http_client = http_client or AiohttpClient()

    async def send_notification(
        self, message: NotificationMessage
    ) -> NotificationResult:
        """Send a notification via Pushover"""
        try:
            # Map notification type to Pushover priority
            priority = self._get_priority_for_type(
                message.notification_type, message.priority.value
            )
            sound = self._get_sound_for_type(message.notification_type)

            payload = {
                "token": self.config.app_token,
                "user": self.config.user_key,
                "title": message.title,
                "message": message.message,
                "priority": priority,
                "sound": sound,
            }

            response = await self.http_client.post(self.PUSHOVER_API_URL, data=payload)
            response_text = await response.text()

            if response.status == 200:
                try:
                    result = await response.json()
                    if result.get("status") == 1:
                        logger.info(f"Pushover notification sent: {message.title}")
                        return NotificationResult(
                            success=True,
                            provider="pushover",
                            message="Notification sent successfully",
                            metadata={"response": response_text},
                        )
                    else:
                        error_msg = result.get("errors", ["Unknown error"])
                        logger.error(f"Pushover API error: {error_msg}")
                        return NotificationResult(
                            success=False,
                            provider="pushover",
                            message="API returned error",
                            error=str(error_msg),
                            metadata={"response": response_text},
                        )
                except Exception as e:
                    # Even if JSON parsing fails, if status is 200, consider it success
                    logger.info(
                        f"Pushover notification sent (JSON parse error): {message.title} - {e}"
                    )
                    return NotificationResult(
                        success=True,
                        provider="pushover",
                        message="Notification sent successfully",
                        metadata={"response": response_text},
                    )
            else:
                logger.error(f"Pushover HTTP error {response.status}: {response_text}")
                return NotificationResult(
                    success=False,
                    provider="pushover",
                    message=f"HTTP error {response.status}",
                    error=response_text,
                    metadata={"status_code": response.status},
                )

        except Exception as e:
            logger.error(f"Error sending Pushover notification: {e}")
            return NotificationResult(
                success=False,
                provider="pushover",
                message="Exception occurred",
                error=str(e),
            )

    async def test_connection(self) -> bool:
        """Test Pushover connection and validate credentials"""
        try:
            test_message = NotificationMessage(
                title="Borgitory Test",
                message="This is a test notification from Borgitory backup system.",
                notification_type=NotificationType.INFO,
            )

            result = await self.send_notification(test_message)
            return result.success

        except Exception as e:
            logger.error(f"Pushover connection test failed: {e}")
            return False

    def get_connection_info(self) -> ConnectionInfo:
        """Get connection info for display"""
        return ConnectionInfo(
            provider="pushover",
            endpoint=f"User: {self.config.user_key[:6]}...",
            status="configured",
        )

    def get_sensitive_fields(self) -> List[str]:
        """Get list of fields that should be encrypted"""
        return ["user_key", "app_token"]

    def get_display_details(self, config_dict: Dict[str, object]) -> Dict[str, object]:
        """Get provider-specific display details for the UI"""
        user_key = str(config_dict.get("user_key", ""))
        masked_key = f"{user_key[:6]}..." if len(user_key) >= 6 else "***"

        details = f"""
        <div class="space-y-2">
            <div><span class="font-medium">User:</span> {masked_key}</div>
            <div><span class="font-medium">Priority:</span> {config_dict.get("priority", 0)}</div>
            <div><span class="font-medium">Sound:</span> {config_dict.get("sound", "default")}</div>
        </div>
        """

        return {"provider_name": "Pushover", "provider_details": details.strip()}

    def _get_priority_for_type(
        self, notification_type: NotificationType, requested_priority: int
    ) -> int:
        """Map notification type to appropriate Pushover priority"""
        if notification_type == NotificationType.FAILURE:
            return max(requested_priority, 1)  # At least high priority for failures
        elif notification_type == NotificationType.WARNING:
            return max(requested_priority, 0)  # At least normal priority for warnings
        else:
            return requested_priority

    def _get_sound_for_type(self, notification_type: NotificationType) -> str:
        """Get appropriate sound for notification type"""
        if notification_type == NotificationType.FAILURE:
            return "siren"  # Alert sound for failures
        elif notification_type == NotificationType.WARNING:
            return "intermission"  # Warning sound
        else:
            return self.config.sound  # Use configured default


# Register the provider directly
@register_provider(
    name="pushover",
    label="Pushover",
    description="Push notifications via Pushover service",
    supports_priority=True,
    supports_formatting=False,
    requires_credentials=True,
)
class PushoverProviderRegistered(PushoverProvider):
    """Registered Pushover provider"""

    config_class = PushoverConfig
