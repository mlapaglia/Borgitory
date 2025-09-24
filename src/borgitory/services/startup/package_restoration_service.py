"""
Package Restoration Service for ensuring user-installed packages persist across container restarts.
This service runs on application startup to reinstall packages that were previously installed by users.
"""

import logging
from sqlalchemy.orm import Session
from borgitory.services.package_manager_service import PackageManagerService
from borgitory.services.simple_command_runner import SimpleCommandRunner

logger = logging.getLogger(__name__)


class PackageRestorationService:
    """Service to restore user-installed packages on startup."""

    def __init__(self, db_session: Session):
        self.db_session = db_session
        self.package_manager = PackageManagerService(
            command_runner=SimpleCommandRunner(), db_session=db_session
        )

    async def restore_user_packages(self) -> None:
        """Restore all user-installed packages from database."""
        try:
            logger.info("Starting package restoration on startup...")
            (
                success,
                message,
            ) = await self.package_manager.ensure_user_packages_installed()

            if success:
                logger.info(f"Package restoration completed: {message}")
            else:
                logger.error(f"Package restoration failed: {message}")

        except Exception as e:
            logger.error(f"Error during package restoration: {e}")
