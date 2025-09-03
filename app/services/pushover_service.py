"""
Pushover notification service for sending backup status notifications
"""
import asyncio
import logging
from typing import Optional
import aiohttp

logger = logging.getLogger(__name__)


class PushoverService:
    """Service to send notifications via Pushover"""
    
    PUSHOVER_API_URL = "https://api.pushover.net/1/messages.json"
    
    async def send_notification(
        self,
        user_key: str,
        app_token: str,
        title: str,
        message: str,
        priority: int = 0,
        sound: str = "default"
    ) -> bool:
        """
        Send a notification via Pushover
        
        Args:
            user_key: Pushover user key
            app_token: Pushover application token
            title: Notification title
            message: Notification message
            priority: -2 (lowest) to 2 (emergency)
            sound: Notification sound
        """
        try:
            payload = {
                "token": app_token,
                "user": user_key,
                "title": title,
                "message": message,
                "priority": priority,
                "sound": sound
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(self.PUSHOVER_API_URL, data=payload) as response:
                    if response.status == 200:
                        result = await response.json()
                        if result.get("status") == 1:
                            logger.info(f"✅ Pushover notification sent: {title}")
                            return True
                        else:
                            logger.error(f"❌ Pushover API error: {result.get('errors', 'Unknown error')}")
                            return False
                    else:
                        error_text = await response.text()
                        logger.error(f"❌ Pushover HTTP error {response.status}: {error_text}")
                        return False
                        
        except Exception as e:
            logger.error(f"❌ Error sending Pushover notification: {e}")
            return False
    
    async def send_backup_success_notification(
        self,
        user_key: str,
        app_token: str,
        repository_name: str,
        job_type: str,
        duration: Optional[str] = None,
        archive_count: Optional[int] = None
    ) -> bool:
        """Send a backup success notification"""
        
        title = f"✅ Backup Complete - {repository_name}"
        
        parts = [f"{job_type.replace('_', ' ').title()} completed successfully"]
        if duration:
            parts.append(f"Duration: {duration}")
        if archive_count:
            parts.append(f"Archive count: {archive_count}")
        
        message = "\n".join(parts)
        
        return await self.send_notification(
            user_key=user_key,
            app_token=app_token,
            title=title,
            message=message,
            priority=0,  # Normal priority
            sound="default"
        )
    
    async def send_backup_failure_notification(
        self,
        user_key: str,
        app_token: str,
        repository_name: str,
        job_type: str,
        error_message: Optional[str] = None
    ) -> bool:
        """Send a backup failure notification"""
        
        title = f"❌ Backup Failed - {repository_name}"
        
        parts = [f"{job_type.replace('_', ' ').title()} failed"]
        if error_message:
            # Truncate long error messages
            if len(error_message) > 200:
                error_message = error_message[:200] + "..."
            parts.append(f"Error: {error_message}")
        
        message = "\n".join(parts)
        
        return await self.send_notification(
            user_key=user_key,
            app_token=app_token,
            title=title,
            message=message,
            priority=1,  # High priority for failures
            sound="siren"  # Alert sound for failures
        )
    
    async def test_pushover_connection(self, user_key: str, app_token: str) -> dict:
        """Test Pushover connection and validate credentials"""
        try:
            success = await self.send_notification(
                user_key=user_key,
                app_token=app_token,
                title="Borgitory Test",
                message="This is a test notification from Borgitory backup system.",
                priority=0,
                sound="default"
            )
            
            if success:
                return {
                    "status": "success",
                    "message": "Test notification sent successfully!"
                }
            else:
                return {
                    "status": "error",
                    "message": "Failed to send test notification. Check your credentials."
                }
                
        except Exception as e:
            return {
                "status": "error",
                "message": f"Connection test failed: {str(e)}"
            }


# Global instance
pushover_service = PushoverService()