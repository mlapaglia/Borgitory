"""
Notification service implementation following clean architecture and FastAPI best practices.

This service handles sending notifications via various providers (starting with Pushover).
"""

import logging
import aiohttp
from typing import Optional

from app.models.repository import NotificationConfig
from app.models.enums import NotificationProvider, JobStatus
from app.services.interfaces import NotificationService

logger = logging.getLogger(__name__)


class PushoverNotificationService:
    """
    Pushover notification service implementation.
    
    Demonstrates external service integration with clean architecture.
    """
    
    PUSHOVER_API_URL = "https://api.pushover.net/1/messages.json"
    
    async def send_notification(
        self,
        user_key: str,
        app_token: str,
        title: str,
        message: str,
        priority: int = 0
    ) -> bool:
        """Send notification via Pushover API."""
        try:
            payload = {
                "token": app_token,
                "user": user_key,
                "title": title,
                "message": message,
                "priority": priority
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(self.PUSHOVER_API_URL, data=payload) as response:
                    if response.status == 200:
                        logger.info(f"Pushover notification sent successfully: {title}")
                        return True
                    else:
                        error_text = await response.text()
                        logger.error(f"Pushover API error {response.status}: {error_text}")
                        return False
                        
        except Exception as e:
            logger.exception(f"Failed to send Pushover notification: {e}")
            return False


class NotificationServiceImpl:
    """
    Notification service implementation following clean architecture.
    
    Delegates to provider-specific services based on configuration.
    """
    
    def __init__(self):
        self.pushover_service = PushoverNotificationService()
    
    async def send_backup_notification(
        self,
        notification_config: NotificationConfig,
        repository_name: str,
        backup_success: bool,
        job_details: str = ""
    ) -> bool:
        """Send backup completion notification."""
        if not notification_config.enabled:
            logger.info("Notification config disabled, skipping notification")
            return True
        
        try:
            # Create notification content
            status_emoji = "✅" if backup_success else "❌"
            status_text = "completed successfully" if backup_success else "failed"
            
            title = f"{status_emoji} Backup {status_text.title()}"
            message = f"Repository '{repository_name}' backup {status_text}"
            
            if job_details:
                message += f"\n\nDetails: {job_details}"
            
            # Send based on provider
            if notification_config.provider == NotificationProvider.PUSHOVER:
                user_key, app_token = notification_config.get_pushover_credentials()
                if not user_key or not app_token:
                    logger.error("Missing Pushover credentials")
                    return False
                
                return await self.pushover_service.send_notification(
                    user_key=user_key,
                    app_token=app_token,
                    title=title,
                    message=message,
                    priority=1 if not backup_success else 0  # High priority for failures
                )
            else:
                logger.warning(f"Unsupported notification provider: {notification_config.provider}")
                return False
                
        except Exception as e:
            logger.exception(f"Notification service error: {e}")
            return False
    
    async def test_notification_config(
        self,
        notification_config: NotificationConfig
    ) -> bool:
        """Test notification configuration with a test message."""
        return await self.send_backup_notification(
            notification_config=notification_config,
            repository_name="Test Repository",
            backup_success=True,
            job_details="This is a test notification from your backup system."
        )