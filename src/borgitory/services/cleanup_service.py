"""
Cleanup Config Business Logic Service.
Handles all cleanup configuration-related business operations independent of HTTP concerns.
"""

import logging
from typing import List, Optional, Dict, Tuple, Union
from sqlalchemy.orm import Session

from borgitory.models.database import CleanupConfig, Repository
from borgitory.models.schemas import CleanupConfigCreate, CleanupConfigUpdate
from borgitory.constants.retention import RetentionFieldHandler

logger = logging.getLogger(__name__)


class CleanupService:
    """Service for cleanup configuration business logic operations."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def get_cleanup_configs(
        self, skip: int = 0, limit: int = 100
    ) -> List[CleanupConfig]:
        """Get all cleanup configurations with pagination."""
        return self.db.query(CleanupConfig).offset(skip).limit(limit).all()

    def get_cleanup_config_by_id(self, config_id: int) -> Optional[CleanupConfig]:
        """Get a cleanup configuration by ID."""
        config = (
            self.db.query(CleanupConfig).filter(CleanupConfig.id == config_id).first()
        )
        if not config:
            raise Exception(f"Cleanup configuration with id {config_id} not found")
        return config

    def create_cleanup_config(
        self, cleanup_config: CleanupConfigCreate
    ) -> Tuple[bool, Optional[CleanupConfig], Optional[str]]:
        """
        Create a new cleanup configuration.

        Returns:
            tuple: (success, config_or_none, error_message_or_none)
        """
        try:
            existing = (
                self.db.query(CleanupConfig)
                .filter(CleanupConfig.name == cleanup_config.name)
                .first()
            )
            if existing:
                return False, None, "A prune policy with this name already exists"

            db_config = CleanupConfig()
            db_config.name = cleanup_config.name
            db_config.strategy = cleanup_config.strategy
            db_config.keep_within_days = cleanup_config.keep_within_days
            RetentionFieldHandler.copy_fields(cleanup_config, db_config)
            db_config.show_list = cleanup_config.show_list
            db_config.show_stats = cleanup_config.show_stats
            db_config.save_space = cleanup_config.save_space
            db_config.enabled = True

            self.db.add(db_config)
            self.db.commit()
            self.db.refresh(db_config)

            return True, db_config, None

        except Exception as e:
            self.db.rollback()
            return False, None, f"Failed to create cleanup configuration: {str(e)}"

    def update_cleanup_config(
        self, config_id: int, config_update: CleanupConfigUpdate
    ) -> Tuple[bool, Optional[CleanupConfig], Optional[str]]:
        """
        Update an existing cleanup configuration.

        Returns:
            tuple: (success, config_or_none, error_message_or_none)
        """
        try:
            config = (
                self.db.query(CleanupConfig)
                .filter(CleanupConfig.id == config_id)
                .first()
            )
            if not config:
                return False, None, "Cleanup configuration not found"

            update_dict = config_update.model_dump(exclude_unset=True)
            if "name" in update_dict and update_dict["name"] != config.name:
                existing = (
                    self.db.query(CleanupConfig)
                    .filter(
                        CleanupConfig.name == update_dict["name"],
                        CleanupConfig.id != config_id,
                    )
                    .first()
                )
                if existing:
                    return False, None, "A prune policy with this name already exists"

            for field, value in update_dict.items():
                if hasattr(config, field):
                    setattr(config, field, value)

            self.db.commit()
            self.db.refresh(config)

            return True, config, None

        except Exception as e:
            self.db.rollback()
            return False, None, f"Failed to update cleanup configuration: {str(e)}"

    def enable_cleanup_config(
        self, config_id: int
    ) -> Tuple[bool, Optional[CleanupConfig], Optional[str]]:
        """
        Enable a cleanup configuration.

        Returns:
            tuple: (success, config_or_none, error_message_or_none)
        """
        try:
            config = (
                self.db.query(CleanupConfig)
                .filter(CleanupConfig.id == config_id)
                .first()
            )
            if not config:
                return False, None, "Cleanup configuration not found"

            config.enabled = True
            self.db.commit()
            self.db.refresh(config)

            return True, config, None

        except Exception as e:
            self.db.rollback()
            return False, None, f"Failed to enable cleanup configuration: {str(e)}"

    def disable_cleanup_config(
        self, config_id: int
    ) -> Tuple[bool, Optional[CleanupConfig], Optional[str]]:
        """
        Disable a cleanup configuration.

        Returns:
            tuple: (success, config_or_none, error_message_or_none)
        """
        try:
            config = (
                self.db.query(CleanupConfig)
                .filter(CleanupConfig.id == config_id)
                .first()
            )
            if not config:
                return False, None, "Cleanup configuration not found"

            config.enabled = False
            self.db.commit()
            self.db.refresh(config)

            return True, config, None

        except Exception as e:
            self.db.rollback()
            return False, None, f"Failed to disable cleanup configuration: {str(e)}"

    def delete_cleanup_config(
        self, config_id: int
    ) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Delete a cleanup configuration.

        Returns:
            tuple: (success, config_name_or_none, error_message_or_none)
        """
        try:
            config = (
                self.db.query(CleanupConfig)
                .filter(CleanupConfig.id == config_id)
                .first()
            )
            if not config:
                return False, None, "Cleanup configuration not found"

            config_name = config.name
            self.db.delete(config)
            self.db.commit()

            return True, config_name, None

        except Exception as e:
            self.db.rollback()
            return False, None, f"Failed to delete cleanup configuration: {str(e)}"

    def get_configs_with_descriptions(
        self,
    ) -> List[Dict[str, Union[str, int, bool, None]]]:
        """
        Get all cleanup configurations with computed description fields.

        Returns:
            List of dictionaries with config data and computed fields
        """
        try:
            cleanup_configs_raw = self.get_cleanup_configs()

            processed_configs = []
            for config in cleanup_configs_raw:
                if config.strategy == "simple":
                    description = f"Keep archives within {config.keep_within_days} days"
                else:
                    description = RetentionFieldHandler.build_description(config)

                processed_config = config.__dict__.copy()
                processed_config["description"] = description
                processed_configs.append(processed_config)

            return processed_configs

        except Exception as e:
            logger.error(f"Error getting configs with descriptions: {str(e)}")
            return []

    def get_form_data(self) -> Dict[str, List[Repository]]:
        """Get data needed for cleanup form."""
        try:
            repositories = self.db.query(Repository).all()

            return {
                "repositories": repositories,
            }
        except Exception as e:
            logger.error(f"Error getting form data: {str(e)}")
            return {
                "repositories": [],
            }
