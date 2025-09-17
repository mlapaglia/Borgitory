"""
Notification Config Business Logic Service.
Handles all notification configuration-related business operations independent of HTTP concerns.
"""

import logging
from typing import List, Optional, Dict, Any, Tuple
from sqlalchemy.orm import Session

from borgitory.models.database import NotificationConfig

logger = logging.getLogger(__name__)


class NotificationConfigService:
    """Service for notification configuration business logic operations."""

    def __init__(self, db: Session):
        self.db = db

    def get_all_configs(
        self, skip: int = 0, limit: int = 100
    ) -> List[NotificationConfig]:
        """Get all notification configurations with pagination."""
        return self.db.query(NotificationConfig).offset(skip).limit(limit).all()

    def get_config_by_id(self, config_id: int) -> Optional[NotificationConfig]:
        """Get a notification configuration by ID."""
        return (
            self.db.query(NotificationConfig)
            .filter(NotificationConfig.id == config_id)
            .first()
        )

    def create_config(
        self,
        name: str,
        provider: str,
        notify_on_success: bool,
        notify_on_failure: bool,
        user_key: str,
        app_token: str,
    ) -> Tuple[bool, Optional[NotificationConfig], Optional[str]]:
        """
        Create a new notification configuration.

        Returns:
            tuple: (success, config_or_none, error_message_or_none)
        """
        try:
            db_notification_config = NotificationConfig(
                name=name,
                provider=provider,
                notify_on_success=notify_on_success,
                notify_on_failure=notify_on_failure,
                enabled=True,
            )

            # Encrypt and store credentials
            db_notification_config.set_pushover_credentials(user_key, app_token)

            self.db.add(db_notification_config)
            self.db.commit()
            self.db.refresh(db_notification_config)

            return True, db_notification_config, None

        except Exception as e:
            self.db.rollback()
            return False, None, f"Failed to create notification configuration: {str(e)}"

    def update_config(
        self,
        config_id: int,
        name: str,
        provider: str,
        notify_on_success: bool,
        notify_on_failure: bool,
        user_key: str,
        app_token: str,
    ) -> Tuple[bool, Optional[NotificationConfig], Optional[str]]:
        """
        Update an existing notification configuration.

        Returns:
            tuple: (success, config_or_none, error_message_or_none)
        """
        try:
            existing_config = self.get_config_by_id(config_id)
            if not existing_config:
                return False, None, "Notification configuration not found"

            # Update basic fields
            existing_config.name = name
            existing_config.provider = provider
            existing_config.notify_on_success = notify_on_success
            existing_config.notify_on_failure = notify_on_failure

            # Update credentials
            existing_config.set_pushover_credentials(user_key, app_token)

            self.db.commit()
            self.db.refresh(existing_config)

            return True, existing_config, None

        except Exception as e:
            self.db.rollback()
            return False, None, f"Failed to update notification configuration: {str(e)}"

    def enable_config(
        self, config_id: int
    ) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Enable a notification configuration.

        Returns:
            tuple: (success, success_message_or_none, error_message_or_none)
        """
        try:
            config = self.get_config_by_id(config_id)
            if not config:
                return False, None, "Notification configuration not found"

            config.enabled = True
            self.db.commit()

            return True, f"Notification '{config.name}' enabled successfully!", None

        except Exception as e:
            self.db.rollback()
            return False, None, f"Failed to enable notification: {str(e)}"

    def disable_config(
        self, config_id: int
    ) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Disable a notification configuration.

        Returns:
            tuple: (success, success_message_or_none, error_message_or_none)
        """
        try:
            config = self.get_config_by_id(config_id)
            if not config:
                return False, None, "Notification configuration not found"

            config.enabled = False
            self.db.commit()

            return True, f"Notification '{config.name}' disabled successfully!", None

        except Exception as e:
            self.db.rollback()
            return False, None, f"Failed to disable notification: {str(e)}"

    def delete_config(
        self, config_id: int
    ) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Delete a notification configuration.

        Returns:
            tuple: (success, config_name_or_none, error_message_or_none)
        """
        try:
            config = self.get_config_by_id(config_id)
            if not config:
                return False, None, "Notification configuration not found"

            config_name = config.name
            self.db.delete(config)
            self.db.commit()

            return True, config_name, None

        except Exception as e:
            self.db.rollback()
            return False, None, f"Failed to delete notification: {str(e)}"

    def get_configs_with_descriptions(self) -> List[Dict[str, Any]]:
        """
        Get all notification configurations with computed description fields.

        Returns:
            List of dictionaries with config data and computed fields
        """
        try:
            notification_configs_raw = self.get_all_configs()

            # Process configs to add computed fields for template
            processed_configs = []
            for config in notification_configs_raw:
                # Build notification description
                notify_types = []
                if config.notify_on_success:
                    notify_types.append("Success")
                if config.notify_on_failure:
                    notify_types.append("Failures")

                notification_desc = (
                    ", ".join(notify_types) if notify_types else "No notifications"
                )

                processed_config = config.__dict__.copy()
                processed_config["notification_desc"] = notification_desc
                processed_configs.append(processed_config)

            return processed_configs

        except Exception as e:
            logger.error(f"Error getting configs with descriptions: {str(e)}")
            return []

    def get_config_credentials(
        self, config_id: int
    ) -> Tuple[bool, Optional[str], Optional[str], Optional[str]]:
        """
        Get decrypted credentials for a notification configuration.

        Returns:
            tuple: (success, user_key_or_none, app_token_or_none, error_message_or_none)
        """
        try:
            config = self.get_config_by_id(config_id)
            if not config:
                return False, None, None, "Notification configuration not found"

            if config.provider == "pushover":
                user_key, app_token = config.get_pushover_credentials()
                return True, user_key, app_token, None
            else:
                return False, None, None, "Unsupported notification provider"

        except Exception as e:
            return False, None, None, f"Failed to get credentials: {str(e)}"
