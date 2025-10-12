"""
Package Restoration Service for ensuring user-installed packages persist across container restarts.
This service runs on application startup to reinstall packages that were previously installed by users.
"""

import logging
from borgitory.services.package_manager_service import PackageManagerService
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class PackageRestorationService:
    """Service to restore user-installed packages on startup."""

    def __init__(self, package_manager: PackageManagerService):
        self.package_manager = package_manager

    async def restore_user_packages(self, session: AsyncSession) -> None:
        """Restore all user-installed packages from database."""
        try:
            logger.info("Starting package restoration on startup...")
            (
                success,
                message,
            ) = await self.package_manager.ensure_user_packages_installed(session)

            if success:
                logger.info(f"Package restoration completed: {message}")
            else:
                logger.error(f"Package restoration failed: {message}")

        except Exception as e:
            logger.error(f"Error during package restoration: {e}")
