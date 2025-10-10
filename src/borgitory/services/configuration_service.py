"""
Configuration Business Logic Service.
Handles all configuration-related business operations for dropdowns and form data.
"""

import logging
from typing import List, Dict, TypedDict, cast
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from borgitory.models.database import (
    Repository,
    PruneConfig,
    CloudSyncConfig,
    NotificationConfig,
    RepositoryCheckConfig,
)

logger = logging.getLogger(__name__)


class ScheduleFormData(TypedDict):
    """Type definition for schedule form data"""

    repositories: List[Repository]
    prune_configs: List[PruneConfig]
    cloud_sync_configs: List[CloudSyncConfig]
    notification_configs: List[NotificationConfig]
    check_configs: List[RepositoryCheckConfig]


class CronFormContext(TypedDict):
    """Type definition for cron form context data"""

    preset: str
    is_custom: bool
    cron_expression: str
    description: str


class ConfigurationService:
    """Service for configuration and form data operations."""

    def __init__(self) -> None:
        """
        Initialize ConfigurationService.
        """

    async def get_schedule_form_data(self, db: AsyncSession) -> ScheduleFormData:
        """
        Get all configuration data needed for schedule forms.

        Returns:
            Dict containing lists of repositories and enabled configurations
        """
        repositories_result = await db.execute(select(Repository))
        repositories = list(repositories_result.scalars().all())

        prune_configs_result = await db.execute(
            select(PruneConfig).where(PruneConfig.enabled)
        )
        prune_configs = list(prune_configs_result.scalars().all())

        cloud_sync_configs_result = await db.execute(
            select(CloudSyncConfig).where(CloudSyncConfig.enabled)
        )
        cloud_sync_configs = list(cloud_sync_configs_result.scalars().all())

        notification_configs_result = await db.execute(
            select(NotificationConfig).where(NotificationConfig.enabled)
        )
        notification_configs = list(notification_configs_result.scalars().all())

        check_configs_result = await db.execute(
            select(RepositoryCheckConfig).where(RepositoryCheckConfig.enabled)
        )
        check_configs = list(check_configs_result.scalars().all())

        return {
            "repositories": repositories,
            "prune_configs": prune_configs,
            "cloud_sync_configs": cloud_sync_configs,
            "notification_configs": notification_configs,
            "check_configs": check_configs,
        }

    def get_cron_preset_descriptions(self) -> Dict[str, str]:
        """
        Get human-readable descriptions for cron presets.

        Returns:
            Dict mapping cron expressions to their descriptions
        """
        return {
            "0 2 * * *": "Daily at 2:00 AM",
            "0 2 * * 0": "Weekly on Sunday at 2:00 AM",
            "0 2 1 * *": "Monthly on 1st at 2:00 AM",
            "0 2 1,15 * *": "Twice monthly (1st and 15th) at 2:00 AM",
            "0 2 */2 * *": "Every 2 days at 2:00 AM",
        }

    def get_cron_form_context(self, preset: str = "") -> CronFormContext:
        """
        Get context data for cron expression form based on preset.

        Args:
            preset: The selected cron preset

        Returns:
            Dict containing form context data
        """
        context = {
            "preset": preset,
            "is_custom": preset == "custom",
            "cron_expression": preset if preset != "custom" and preset else "",
            "description": "",
        }

        # Get human readable description for preset
        if preset and preset != "custom":
            preset_descriptions = self.get_cron_preset_descriptions()
            context["description"] = preset_descriptions.get(preset, "")

        return cast(CronFormContext, context)
