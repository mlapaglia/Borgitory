"""
Repository Check Config Business Logic Service.
Handles all repository check configuration-related business operations independent of HTTP concerns.
"""

import logging
from typing import List, Optional, Dict, Union, Tuple
from sqlalchemy.orm import Session

from borgitory.models.database import RepositoryCheckConfig, Repository

logger = logging.getLogger(__name__)


class RepositoryCheckConfigService:
    """Service for repository check configuration business logic operations."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def get_all_configs(
        self, order_by_name: bool = True
    ) -> List[RepositoryCheckConfig]:
        """Get all repository check configurations."""
        query = self.db.query(RepositoryCheckConfig)
        if order_by_name:
            query = query.order_by(RepositoryCheckConfig.name)
        return query.all()

    def get_enabled_configs(self) -> List[RepositoryCheckConfig]:
        """Get all enabled repository check configurations."""
        return (
            self.db.query(RepositoryCheckConfig)
            .filter(RepositoryCheckConfig.enabled)
            .order_by(RepositoryCheckConfig.name)
            .all()
        )

    def get_config_by_id(self, config_id: int) -> Optional[RepositoryCheckConfig]:
        """Get a repository check configuration by ID."""
        return (
            self.db.query(RepositoryCheckConfig)
            .filter(RepositoryCheckConfig.id == config_id)
            .first()
        )

    def get_config_by_name(self, name: str) -> Optional[RepositoryCheckConfig]:
        """Get a repository check configuration by name."""
        return (
            self.db.query(RepositoryCheckConfig)
            .filter(RepositoryCheckConfig.name == name)
            .first()
        )

    def create_config(
        self,
        name: str,
        description: Optional[str] = None,
        check_type: str = "full",
        verify_data: bool = False,
        repair_mode: bool = False,
        save_space: bool = False,
        max_duration: Optional[int] = None,
        archive_prefix: Optional[str] = None,
        archive_glob: Optional[str] = None,
        first_n_archives: Optional[int] = None,
        last_n_archives: Optional[int] = None,
    ) -> Tuple[bool, Optional[RepositoryCheckConfig], Optional[str]]:
        """
        Create a new repository check configuration.

        Returns:
            tuple: (success, config_or_none, error_message_or_none)
        """
        try:
            # Check if name already exists
            existing = self.get_config_by_name(name)
            if existing:
                return False, None, "A check policy with this name already exists"

            # Create new configuration
            db_config = RepositoryCheckConfig()
            db_config.name = name
            db_config.description = description
            db_config.check_type = check_type
            db_config.verify_data = verify_data
            db_config.repair_mode = repair_mode
            db_config.save_space = save_space
            db_config.max_duration = max_duration
            db_config.archive_prefix = archive_prefix
            db_config.archive_glob = archive_glob
            db_config.first_n_archives = first_n_archives
            db_config.last_n_archives = last_n_archives

            self.db.add(db_config)
            self.db.commit()
            self.db.refresh(db_config)

            return True, db_config, None

        except Exception as e:
            self.db.rollback()
            return False, None, f"Failed to create check policy: {str(e)}"

    def update_config(
        self, config_id: int, update_data: Dict[str, Union[str, int, bool, None]]
    ) -> Tuple[bool, Optional[RepositoryCheckConfig], Optional[str]]:
        """
        Update an existing repository check configuration.

        Returns:
            tuple: (success, config_or_none, error_message_or_none)
        """
        try:
            config = self.get_config_by_id(config_id)
            if not config:
                return False, None, "Check policy not found"

            # Check for name conflicts if name is being updated
            if "name" in update_data and update_data["name"] != config.name:
                existing = (
                    self.db.query(RepositoryCheckConfig)
                    .filter(
                        RepositoryCheckConfig.name == update_data["name"],
                        RepositoryCheckConfig.id != config_id,
                    )
                    .first()
                )
                if existing:
                    return False, None, "A check policy with this name already exists"

            # Update fields that were provided
            for field, value in update_data.items():
                if hasattr(config, field):
                    setattr(config, field, value)

            self.db.commit()
            self.db.refresh(config)

            return True, config, None

        except Exception as e:
            self.db.rollback()
            return False, None, f"Failed to update check policy: {str(e)}"

    def enable_config(
        self, config_id: int
    ) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Enable a repository check configuration.

        Returns:
            tuple: (success, success_message_or_none, error_message_or_none)
        """
        try:
            config = self.get_config_by_id(config_id)
            if not config:
                return False, None, "Check policy not found"

            config.enabled = True
            self.db.commit()

            return True, f"Check policy '{config.name}' enabled successfully!", None

        except Exception as e:
            self.db.rollback()
            return False, None, f"Failed to enable check policy: {str(e)}"

    def disable_config(
        self, config_id: int
    ) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Disable a repository check configuration.

        Returns:
            tuple: (success, success_message_or_none, error_message_or_none)
        """
        try:
            config = self.get_config_by_id(config_id)
            if not config:
                return False, None, "Check policy not found"

            config.enabled = False
            self.db.commit()

            return True, f"Check policy '{config.name}' disabled successfully!", None

        except Exception as e:
            self.db.rollback()
            return False, None, f"Failed to disable check policy: {str(e)}"

    def delete_config(
        self, config_id: int
    ) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Delete a repository check configuration.

        Returns:
            tuple: (success, config_name_or_none, error_message_or_none)
        """
        try:
            config = self.get_config_by_id(config_id)
            if not config:
                return False, None, "Check policy not found"

            config_name = config.name
            self.db.delete(config)
            self.db.commit()

            return True, config_name, None

        except Exception as e:
            self.db.rollback()
            return False, None, f"Failed to delete check policy: {str(e)}"

    def get_form_data(
        self,
    ) -> Dict[str, Union[List[Repository], List[RepositoryCheckConfig]]]:
        """Get data needed for repository check form."""
        try:
            repositories = self.db.query(Repository).all()
            check_configs = self.get_enabled_configs()

            return {
                "repositories": repositories,
                "check_configs": check_configs,
            }
        except Exception as e:
            logger.error(f"Error getting form data: {str(e)}")
            return {
                "repositories": [],
                "check_configs": [],
            }
