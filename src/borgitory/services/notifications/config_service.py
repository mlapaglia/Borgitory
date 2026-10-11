"""
Notification configuration service layer.

This module provides the high-level service interface for notification configuration
CRUD operations, following the project's service layer patterns.
"""

import logging
from typing import List, Optional, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from fastapi import HTTPException

from borgitory.models.database import NotificationConfig
from borgitory.services.notifications.apprise_storage import (
    APPRISE_PROVIDER,
    AppriseSubmission,
    StoredAppriseConfig,
)
from borgitory.services.notifications.service import (
    NotificationEditView,
    NotificationService,
)
from borgitory.services.notifications.types import NotificationResult

logger = logging.getLogger(__name__)


class NotificationConfigService:
    """Service class for notification configuration operations."""

    def __init__(
        self,
        notification_service: Optional[NotificationService] = None,
    ):
        """
        Initialize notification config service.

        Args:
            notification_service: Notification service for building and sending configs
        """
        if notification_service is None:
            from borgitory.dependencies import get_notification_service_singleton

            notification_service = get_notification_service_singleton()
        self._notification_service = notification_service

    async def get_all_configs(
        self, db: AsyncSession, skip: int = 0, limit: int = 100
    ) -> List[NotificationConfig]:
        """Get all notification configurations."""
        result = await db.execute(select(NotificationConfig).offset(skip).limit(limit))
        return list(result.scalars().all())

    async def get_config_by_id(
        self, db: AsyncSession, config_id: int
    ) -> Optional[NotificationConfig]:
        """Get notification configuration by ID."""
        result = await db.execute(
            select(NotificationConfig).where(NotificationConfig.id == config_id)
        )
        return result.scalar_one_or_none()

    async def _get_config_or_404(
        self, db: AsyncSession, config_id: int
    ) -> NotificationConfig:
        config = await self.get_config_by_id(db, config_id)
        if not config:
            raise HTTPException(
                status_code=404, detail="Notification configuration not found"
            )
        return config

    async def _ensure_unique_name(
        self, db: AsyncSession, name: str, exclude_id: Optional[int] = None
    ) -> None:
        query = select(NotificationConfig).where(NotificationConfig.name == name)
        if exclude_id is not None:
            query = query.where(NotificationConfig.id != exclude_id)
        result = await db.execute(query)
        if result.scalar_one_or_none():
            raise HTTPException(
                status_code=400,
                detail=f"Notification configuration with name '{name}' already exists",
            )

    def _load_stored(self, config: NotificationConfig) -> Optional[StoredAppriseConfig]:
        try:
            return self._notification_service.load_config_from_storage(
                config.provider, config.provider_config
            )
        except ValueError:
            return None

    def build_config(
        self,
        submission: AppriseSubmission,
        existing: Optional[StoredAppriseConfig] = None,
    ) -> StoredAppriseConfig:
        """
        Validate a submission and build the configuration to store.

        Raises:
            HTTPException: If the submission is invalid
        """
        try:
            return self._notification_service.build_config(submission, existing)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

    async def create_config(
        self,
        db: AsyncSession,
        name: str,
        submission: AppriseSubmission,
    ) -> NotificationConfig:
        """
        Create a new notification configuration.

        Raises:
            HTTPException: If validation fails or name already exists
        """
        await self._ensure_unique_name(db, name)
        stored = self.build_config(submission)

        db_config = NotificationConfig()
        db_config.name = name
        db_config.provider = APPRISE_PROVIDER
        db_config.provider_config = (
            self._notification_service.prepare_config_for_storage(stored)
        )
        db_config.enabled = True

        db.add(db_config)
        await db.commit()
        await db.refresh(db_config)

        return db_config

    async def update_config(
        self,
        db: AsyncSession,
        config_id: int,
        name: str,
        submission: AppriseSubmission,
    ) -> NotificationConfig:
        """
        Update an existing notification configuration.

        Blank secret fields keep their stored values.

        Raises:
            HTTPException: If config not found or validation fails
        """
        config = await self._get_config_or_404(db, config_id)

        if name != config.name:
            await self._ensure_unique_name(db, name, exclude_id=config_id)

        stored = self.build_config(submission, self._load_stored(config))

        config.name = name
        config.provider = APPRISE_PROVIDER
        config.provider_config = self._notification_service.prepare_config_for_storage(
            stored
        )

        await db.commit()
        await db.refresh(config)
        return config

    async def delete_config(self, db: AsyncSession, config_id: int) -> Tuple[bool, str]:
        """
        Delete a notification configuration.

        Returns:
            Tuple of (success, config_name)

        Raises:
            HTTPException: If config not found
        """
        config = await self._get_config_or_404(db, config_id)

        config_name = config.name
        await db.delete(config)
        await db.commit()

        return True, config_name

    async def enable_config(self, db: AsyncSession, config_id: int) -> Tuple[bool, str]:
        """
        Enable a notification configuration.

        Raises:
            HTTPException: If config not found or it must be re-configured first
        """
        config = await self._get_config_or_404(db, config_id)

        stored = self._load_stored(config)
        if stored is None or stored.migration_error:
            raise HTTPException(
                status_code=400,
                detail=f"Notification '{config.name}' must be edited and saved before it can be enabled",
            )

        config.enabled = True
        await db.commit()

        return True, f"Notification '{config.name}' enabled successfully!"

    async def disable_config(
        self, db: AsyncSession, config_id: int
    ) -> Tuple[bool, str]:
        """
        Disable a notification configuration.

        Raises:
            HTTPException: If config not found
        """
        config = await self._get_config_or_404(db, config_id)

        config.enabled = False
        await db.commit()

        return True, f"Notification '{config.name}' disabled successfully!"

    async def test_config_with_service(
        self,
        db: AsyncSession,
        config_id: int,
        notification_service: NotificationService,
    ) -> Tuple[bool, str]:
        """
        Send a test notification for a saved configuration.

        Returns:
            Tuple of (success, message)
        """
        config = await self._get_config_or_404(db, config_id)

        if not config.enabled:
            raise HTTPException(
                status_code=400, detail="Notification configuration is disabled"
            )

        try:
            stored = notification_service.load_config_from_storage(
                config.provider, config.provider_config
            )
            result = await notification_service.send_test(stored)
        except Exception as e:
            logger.error(f"Error testing notification config {config_id}: {e}")
            return False, f"Test failed: {str(e)}"

        return self._describe_test_result(result, config.name)

    async def test_submission(
        self,
        db: AsyncSession,
        submission: AppriseSubmission,
        config_id: Optional[int] = None,
    ) -> Tuple[bool, str]:
        """
        Send a test notification for unsaved form values.

        When editing, blank secret fields fall back to the stored configuration.

        Returns:
            Tuple of (success, message)

        Raises:
            HTTPException: If the submission is invalid
        """
        existing = None
        if config_id is not None:
            config = await self._get_config_or_404(db, config_id)
            existing = self._load_stored(config)

        stored = self.build_config(submission, existing)
        result = await self._notification_service.send_test(stored)
        return self._describe_test_result(result, stored.service_name)

    @staticmethod
    def _describe_test_result(
        result: NotificationResult, target: str
    ) -> Tuple[bool, str]:
        if result.success:
            return True, f"Test notification sent successfully to {target}"
        return False, f"Test failed: {result.error or result.message}"

    async def get_config_for_edit(
        self, db: AsyncSession, config_id: int
    ) -> Tuple[NotificationConfig, NotificationEditView]:
        """
        Get a configuration and the non-secret details needed to edit it.

        Raises:
            HTTPException: If config not found
        """
        config = await self._get_config_or_404(db, config_id)

        stored = self._load_stored(config)
        if stored is None:
            return config, NotificationEditView(
                mode="manual",
                service=None,
                service_name=config.provider,
                migration_error="This notification uses an unsupported format and must be re-configured",
            )

        return config, self._notification_service.get_edit_view(stored)
