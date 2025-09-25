"""
Notification configuration service layer.

This module provides the high-level service interface for notification configuration
CRUD operations, following the project's service layer patterns.
"""

import logging
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass
from sqlalchemy.orm import Session
from fastapi import HTTPException

from borgitory.models.database import NotificationConfig
from borgitory.services.notifications.service import NotificationService
from borgitory.services.notifications.registry import get_all_provider_info
from borgitory.services.notifications.types import (
    NotificationConfig as NotificationConfigType,
)

logger = logging.getLogger(__name__)


@dataclass
class SupportedProvider:
    """Represents a supported notification provider."""

    value: str
    label: str
    description: str


class NotificationConfigService:
    """Service class for notification configuration operations."""

    def __init__(
        self,
        db: Session,
        notification_service: Optional[NotificationService] = None,
    ):
        """
        Initialize notification config service.

        Args:
            db: Database session
            notification_service: Notification service for provider operations
        """
        self.db = db
        if notification_service is None:
            # Create a basic notification service with default factory
            from .service import NotificationProviderFactory
            from borgitory.dependencies import get_http_client

            http_client = get_http_client()
            factory = NotificationProviderFactory(http_client)
            self._notification_service = NotificationService(factory)
        else:
            self._notification_service = notification_service

    def get_all_configs(
        self, skip: int = 0, limit: int = 100
    ) -> List[NotificationConfig]:
        """Get all notification configurations."""
        return self.db.query(NotificationConfig).offset(skip).limit(limit).all()

    def get_config_by_id(self, config_id: int) -> Optional[NotificationConfig]:
        """Get notification configuration by ID."""
        return (
            self.db.query(NotificationConfig)
            .filter(NotificationConfig.id == config_id)
            .first()
        )

    def get_supported_providers(self) -> List[SupportedProvider]:
        """Get supported notification providers from the registry."""
        provider_info = get_all_provider_info()
        supported_providers = []

        for provider_name, info in provider_info.items():
            supported_providers.append(
                SupportedProvider(
                    value=provider_name,
                    label=info.label,
                    description=info.description,
                )
            )

        # Sort by provider name for consistent ordering
        return sorted(supported_providers, key=lambda x: x.value)

    def create_config(
        self, name: str, provider: str, provider_config: Dict[str, Any]
    ) -> NotificationConfig:
        """
        Create a new notification configuration.

        Args:
            name: Configuration name
            provider: Provider type (e.g., 'pushover', 'discord')
            provider_config: Provider-specific configuration

        Returns:
            Created NotificationConfig

        Raises:
            HTTPException: If validation fails or name already exists
        """
        # Check if name already exists
        existing = (
            self.db.query(NotificationConfig)
            .filter(NotificationConfig.name == name)
            .first()
        )
        if existing:
            raise HTTPException(
                status_code=400,
                detail=f"Notification configuration with name '{name}' already exists",
            )

        # Validate and prepare configuration for storage
        try:
            provider_config_json = (
                self._notification_service.prepare_config_for_storage(
                    provider, provider_config
                )
            )
        except Exception as e:
            raise HTTPException(
                status_code=400, detail=f"Invalid configuration: {str(e)}"
            )

        # Create database record
        db_config = NotificationConfig()
        db_config.name = name
        db_config.provider = provider
        db_config.provider_config = provider_config_json
        db_config.enabled = True

        self.db.add(db_config)
        self.db.commit()
        self.db.refresh(db_config)

        return db_config

    def update_config(
        self,
        config_id: int,
        name: Optional[str] = None,
        provider: Optional[str] = None,
        provider_config: Optional[Dict[str, Any]] = None,
        enabled: Optional[bool] = None,
    ) -> NotificationConfig:
        """
        Update an existing notification configuration.

        Args:
            config_id: Configuration ID to update
            name: New name (optional)
            provider: New provider (optional)
            provider_config: New provider config (optional)
            enabled: New enabled status (optional)

        Returns:
            Updated NotificationConfig

        Raises:
            HTTPException: If config not found or validation fails
        """
        config = self.get_config_by_id(config_id)
        if not config:
            raise HTTPException(
                status_code=404, detail="Notification configuration not found"
            )

        # Check name uniqueness if changing name
        if name and name != config.name:
            existing = (
                self.db.query(NotificationConfig)
                .filter(
                    NotificationConfig.name == name, NotificationConfig.id != config_id
                )
                .first()
            )
            if existing:
                raise HTTPException(
                    status_code=400,
                    detail=f"Notification configuration with name '{name}' already exists",
                )

        # Update fields
        if name is not None:
            config.name = name
        if provider is not None:
            config.provider = provider
        if enabled is not None:
            config.enabled = enabled

        # Update provider config if provided
        if provider_config is not None:
            try:
                provider_config_json = (
                    self._notification_service.prepare_config_for_storage(
                        provider or config.provider, provider_config
                    )
                )
                config.provider_config = provider_config_json
            except Exception as e:
                raise HTTPException(
                    status_code=400, detail=f"Invalid configuration: {str(e)}"
                )

        self.db.commit()
        self.db.refresh(config)
        return config

    def delete_config(self, config_id: int) -> Tuple[bool, str]:
        """
        Delete a notification configuration.

        Args:
            config_id: Configuration ID to delete

        Returns:
            Tuple of (success, config_name)

        Raises:
            HTTPException: If config not found
        """
        config = self.get_config_by_id(config_id)
        if not config:
            raise HTTPException(
                status_code=404, detail="Notification configuration not found"
            )

        config_name = config.name
        self.db.delete(config)
        self.db.commit()

        return True, config_name

    def enable_config(self, config_id: int) -> Tuple[bool, str]:
        """
        Enable a notification configuration.

        Args:
            config_id: Configuration ID to enable

        Returns:
            Tuple of (success, message)

        Raises:
            HTTPException: If config not found
        """
        config = self.get_config_by_id(config_id)
        if not config:
            raise HTTPException(
                status_code=404, detail="Notification configuration not found"
            )

        config.enabled = True
        self.db.commit()

        return True, f"Notification '{config.name}' enabled successfully!"

    def disable_config(self, config_id: int) -> Tuple[bool, str]:
        """
        Disable a notification configuration.

        Args:
            config_id: Configuration ID to disable

        Returns:
            Tuple of (success, message)

        Raises:
            HTTPException: If config not found
        """
        config = self.get_config_by_id(config_id)
        if not config:
            raise HTTPException(
                status_code=404, detail="Notification configuration not found"
            )

        config.enabled = False
        self.db.commit()

        return True, f"Notification '{config.name}' disabled successfully!"

    async def test_config(self, config_id: int) -> Tuple[bool, str]:
        """
        Test a notification configuration.

        Args:
            config_id: Configuration ID to test

        Returns:
            Tuple of (success, message)

        Raises:
            HTTPException: If config not found or disabled
        """
        config = self.get_config_by_id(config_id)
        if not config:
            raise HTTPException(
                status_code=404, detail="Notification configuration not found"
            )

        if not config.enabled:
            raise HTTPException(
                status_code=400, detail="Notification configuration is disabled"
            )

        try:
            # Load and decrypt configuration
            decrypted_config = self._notification_service.load_config_from_storage(
                config.provider, config.provider_config
            )

            # Create notification config object
            notification_config = NotificationConfigType(
                provider=config.provider,
                config=decrypted_config,
                name=config.name,
                enabled=config.enabled,
            )

            # Test the connection
            test_success = await self._notification_service.test_connection(
                notification_config
            )

            if test_success:
                return True, f"Test notification sent successfully to {config.name}"
            else:
                return False, "Failed to send test notification"

        except Exception as e:
            logger.error(f"Error testing notification config {config_id}: {e}")
            return False, f"Test failed: {str(e)}"

    async def test_config_with_service(
        self, config_id: int, notification_service: NotificationService
    ) -> Tuple[bool, str]:
        """
        Test notification configuration with provided notification service.

        This method follows the same pattern as cloud sync service where
        the encryption service is passed from the API layer.

        Args:
            config_id: Configuration ID to test
            notification_service: NotificationService with proper encryption setup

        Returns:
            Tuple of (success, message)
        """
        config = self.get_config_by_id(config_id)
        if not config:
            raise HTTPException(
                status_code=404, detail="Notification configuration not found"
            )

        if not config.enabled:
            raise HTTPException(
                status_code=400, detail="Notification configuration is disabled"
            )

        try:
            # Load and decrypt configuration using the provided service
            decrypted_config = notification_service.load_config_from_storage(
                config.provider, config.provider_config
            )

            # Create notification config object
            notification_config = NotificationConfigType(
                provider=config.provider,
                config=decrypted_config,
                name=config.name,
                enabled=config.enabled,
            )

            # Test the connection
            test_success = await notification_service.test_connection(
                notification_config
            )

            if test_success:
                return True, f"Test notification sent successfully to {config.name}"
            else:
                return False, "Failed to send test notification"

        except Exception as e:
            logger.error(f"Error testing notification config {config_id}: {e}")
            return False, f"Test failed: {str(e)}"

    def get_config_with_decrypted_data(
        self, config_id: int
    ) -> Tuple[NotificationConfig, Dict[str, Any]]:
        """
        Get configuration with decrypted provider data for editing.

        Args:
            config_id: Configuration ID

        Returns:
            Tuple of (config, decrypted_config_dict)

        Raises:
            HTTPException: If config not found
        """
        config = self.get_config_by_id(config_id)
        if not config:
            raise HTTPException(
                status_code=404, detail="Notification configuration not found"
            )

        try:
            decrypted_config = self._notification_service.load_config_from_storage(
                config.provider, config.provider_config
            )
            return config, decrypted_config
        except Exception as e:
            logger.error(f"Failed to decrypt config for editing: {e}")
            return config, {}
