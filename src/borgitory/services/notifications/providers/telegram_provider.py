"""
Telegram bot notification provider implementation.
"""

import logging
from typing import Dict, List, Optional
from pydantic import Field, field_validator

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


class TelegramConfig(NotificationProviderConfig):
    """Configuration for Telegram bot notifications"""

    bot_token: str = Field(..., min_length=10, description="Telegram bot token")
    chat_id: str = Field(
        ...,
        description="Telegram chat ID (can be user ID, group ID, or channel username)",
    )
    parse_mode: str = Field(
        default="HTML",
        description="Message parse mode (HTML, Markdown, MarkdownV2, or None for plain text)",
    )
    disable_notification: bool = Field(
        default=False, description="Send message silently (no notification sound)"
    )

    @field_validator("bot_token")
    @classmethod
    def validate_bot_token(cls, v: str) -> str:
        """Validate Telegram bot token format"""
        if not v or ":" not in v:
            raise ValueError("Telegram bot token must contain ':' separator")
        parts = v.split(":")
        if len(parts) != 2 or not parts[0].isdigit() or len(parts[1]) < 10:
            raise ValueError("Invalid Telegram bot token format")
        return v

    @field_validator("parse_mode")
    @classmethod
    def validate_parse_mode(cls, v: str) -> str:
        """Validate parse mode"""
        valid_modes = ["HTML", "Markdown", "MarkdownV2", "None", ""]
        if v not in valid_modes:
            raise ValueError(
                "Parse mode must be one of: HTML, Markdown, MarkdownV2, None, or empty string for plain text"
            )
        return v


class TelegramProvider(NotificationProvider):
    """
    Telegram bot notification provider implementation.
    """

    config_class = TelegramConfig
    TELEGRAM_API_BASE = "https://api.telegram.org"

    def __init__(
        self, config: TelegramConfig, http_client: Optional[HttpClient] = None
    ) -> None:
        super().__init__(config)
        self.config: TelegramConfig = config
        self.http_client = http_client or AiohttpClient()

    async def send_notification(
        self, message: NotificationMessage
    ) -> NotificationResult:
        """Send a notification via Telegram bot API"""
        try:
            formatted_message = self._format_message(message)

            api_url = f"{self.TELEGRAM_API_BASE}/bot{self.config.bot_token}/sendMessage"

            payload = {
                "chat_id": self.config.chat_id,
                "text": formatted_message,
                "disable_notification": self.config.disable_notification,
            }

            if self.config.parse_mode and self.config.parse_mode != "None":
                payload["parse_mode"] = self.config.parse_mode

            response = await self.http_client.post(api_url, json=payload)
            response_text = await response.text()

            if response.status == 200:
                try:
                    result = await response.json()
                    if result.get("ok"):
                        logger.info(f"Telegram notification sent: {message.title}")
                        return NotificationResult(
                            success=True,
                            provider="telegram",
                            message="Notification sent successfully",
                            metadata={"response": response_text},
                        )
                    else:
                        error_msg = result.get("description", "Unknown error")
                        logger.error(f"Telegram API error: {error_msg}")
                        return NotificationResult(
                            success=False,
                            provider="telegram",
                            message="API returned error",
                            error=str(error_msg),
                            metadata={"response": response_text},
                        )
                except Exception as e:
                    # Even if JSON parsing fails, if status is 200, consider it success
                    logger.info(
                        f"Telegram notification sent (JSON parse error): {message.title} - {e}"
                    )
                    return NotificationResult(
                        success=True,
                        provider="telegram",
                        message="Notification sent successfully",
                        metadata={"response": response_text},
                    )
            else:
                logger.error(f"Telegram HTTP error {response.status}: {response_text}")
                return NotificationResult(
                    success=False,
                    provider="telegram",
                    message=f"HTTP error {response.status}",
                    error=response_text,
                    metadata={"status_code": response.status},
                )

        except Exception as e:
            logger.error(f"Error sending Telegram notification: {e}")
            return NotificationResult(
                success=False,
                provider="telegram",
                message="Exception occurred",
                error=str(e),
            )

    async def test_connection(self) -> bool:
        """Test Telegram bot connection and validate credentials"""
        try:
            api_url = f"{self.TELEGRAM_API_BASE}/bot{self.config.bot_token}/getMe"
            response = await self.http_client.post(api_url)

            if response.status != 200:
                logger.error("Telegram bot token validation failed")
                return False

            getme_result = await response.json()
            if not getme_result.get("ok"):
                logger.error(
                    f"Telegram getMe failed: {getme_result.get('description')}"
                )
                return False

            test_message = NotificationMessage(
                title="Borgitory Test",
                message="This is a test notification from Borgitory backup system.",
                notification_type=NotificationType.INFO,
            )

            notification_result = await self.send_notification(test_message)
            return notification_result.success

        except Exception as e:
            logger.error(f"Telegram connection test failed: {e}")
            return False

    def get_connection_info(self) -> ConnectionInfo:
        """Get connection info for display"""
        bot_id = (
            self.config.bot_token.split(":")[0]
            if ":" in self.config.bot_token
            else "unknown"
        )
        return ConnectionInfo(
            provider="telegram",
            endpoint=f"Bot: {bot_id}, Chat: {self.config.chat_id}",
            status="configured",
        )

    def get_sensitive_fields(self) -> List[str]:
        """Get list of fields that should be encrypted"""
        return ["bot_token"]

    def get_display_details(self, config_dict: Dict[str, object]) -> Dict[str, object]:
        """Get provider-specific display details for the UI"""
        bot_token = str(config_dict.get("bot_token", ""))
        bot_id = bot_token.split(":")[0] if ":" in bot_token else "unknown"

        details = f"""
        <div class="space-y-2">
            <div><span class="font-medium">Bot ID:</span> {bot_id}</div>
            <div><span class="font-medium">Chat ID:</span> {config_dict.get("chat_id", "")}</div>
            <div><span class="font-medium">Parse Mode:</span> {config_dict.get("parse_mode", "HTML")}</div>
            <div><span class="font-medium">Silent:</span> {"Yes" if config_dict.get("disable_notification", False) else "No"}</div>
        </div>
        """

        return {"provider_name": "Telegram", "provider_details": details.strip()}

    def _format_message(self, message: NotificationMessage) -> str:
        """Format message for Telegram with appropriate styling"""
        # Get emoji for notification type
        emoji = self._get_emoji_for_type(message.notification_type)

        if self.config.parse_mode == "HTML":
            formatted = f"{emoji} <b>{message.title}</b>\n\n{message.message}"

            # Add metadata if present
            if message.metadata:
                formatted += "\n\n<b>Details:</b>"
                for key, value in message.metadata.items():
                    if key not in ["response", "status_code"]:  # Skip internal fields
                        clean_key = key.replace("_", " ").title()
                        formatted += f"\n• <i>{clean_key}:</i> {value}"

        elif self.config.parse_mode in ["Markdown", "MarkdownV2"]:
            # Use Markdown formatting
            if self.config.parse_mode == "MarkdownV2":
                # MarkdownV2 requires escaping special characters
                title = (
                    message.title.replace("_", "\\_")
                    .replace("*", "\\*")
                    .replace("[", "\\[")
                    .replace("]", "\\]")
                    .replace("(", "\\(")
                    .replace(")", "\\)")
                    .replace("~", "\\~")
                    .replace("`", "\\`")
                    .replace(">", "\\>")
                    .replace("#", "\\#")
                    .replace("+", "\\+")
                    .replace("-", "\\-")
                    .replace("=", "\\=")
                    .replace("|", "\\|")
                    .replace("{", "\\{")
                    .replace("}", "\\}")
                    .replace(".", "\\.")
                    .replace("!", "\\!")
                )
                msg_text = (
                    message.message.replace("_", "\\_")
                    .replace("*", "\\*")
                    .replace("[", "\\[")
                    .replace("]", "\\]")
                    .replace("(", "\\(")
                    .replace(")", "\\)")
                    .replace("~", "\\~")
                    .replace("`", "\\`")
                    .replace(">", "\\>")
                    .replace("#", "\\#")
                    .replace("+", "\\+")
                    .replace("-", "\\-")
                    .replace("=", "\\=")
                    .replace("|", "\\|")
                    .replace("{", "\\{")
                    .replace("}", "\\}")
                    .replace(".", "\\.")
                    .replace("!", "\\!")
                )
                formatted = f"{emoji} *{title}*\n\n{msg_text}"
            else:
                formatted = f"{emoji} *{message.title}*\n\n{message.message}"

            # Add metadata if present
            if message.metadata:
                formatted += "\n\n*Details:*"
                for key, value in message.metadata.items():
                    if key not in ["response", "status_code"]:  # Skip internal fields
                        clean_key = key.replace("_", " ").title()
                        formatted += f"\n• _{clean_key}_: {value}"
        else:
            # Plain text mode (empty string, "None", or other)
            formatted = f"{emoji} {message.title}\n\n{message.message}"

            # Add metadata if present
            if message.metadata:
                formatted += "\n\nDetails:"
                for key, value in message.metadata.items():
                    if key not in ["response", "status_code"]:  # Skip internal fields
                        clean_key = key.replace("_", " ").title()
                        formatted += f"\n• {clean_key}: {value}"

        return formatted

    def _get_emoji_for_type(self, notification_type: NotificationType) -> str:
        """Get appropriate emoji for notification type"""
        emoji_map = {
            NotificationType.SUCCESS: "✅",
            NotificationType.FAILURE: "❌",
            NotificationType.WARNING: "⚠️",
            NotificationType.INFO: "ℹ️",
        }
        return emoji_map.get(notification_type, "📢")


# Register the provider directly
@register_provider(
    name="telegram",
    label="Telegram Bot",
    description="Send notifications via Telegram bot",
    supports_priority=False,
    supports_formatting=True,
    requires_credentials=True,
)
class TelegramProviderRegistered(TelegramProvider):
    """Registered Telegram provider"""

    config_class = TelegramConfig
