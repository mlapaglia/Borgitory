"""
Pruning Config Business Logic Service.
Handles all prune configuration-related business operations independent of HTTP concerns.
"""

import logging
from typing import List, Optional, Dict, Tuple, Union
from sqlalchemy.orm import Session

from borgitory.models.database import PruneConfig, Repository
from borgitory.models.schemas import PruneConfigCreate, PruneConfigUpdate
from borgitory.constants.retention import RetentionFieldHandler

logger = logging.getLogger(__name__)


class PruneService:
    """Service for prune configuration business logic operations."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def get_prune_configs(self, skip: int = 0, limit: int = 100) -> List[PruneConfig]:
        """Get all prune configurations with pagination."""
        return self.db.query(PruneConfig).offset(skip).limit(limit).all()

    def get_prune_config_by_id(self, config_id: int) -> Optional[PruneConfig]:
        """Get a prune configuration by ID."""
        config = self.db.query(PruneConfig).filter(PruneConfig.id == config_id).first()
        if not config:
            raise Exception(f"Prune configuration with id {config_id} not found")
        return config

    def create_prune_config(
        self, prune_config: PruneConfigCreate
    ) -> Tuple[bool, Optional[PruneConfig], Optional[str]]:
        """
        Create a new prune configuration.

        Returns:
            tuple: (success, config_or_none, error_message_or_none)
        """
        try:
            existing = (
                self.db.query(PruneConfig)
                .filter(PruneConfig.name == prune_config.name)
                .first()
            )
            if existing:
                return False, None, "A prune policy with this name already exists"

            db_config = PruneConfig()
            db_config.name = prune_config.name
            db_config.strategy = prune_config.strategy
            db_config.keep_within_days = prune_config.keep_within_days
            RetentionFieldHandler.copy_fields(prune_config, db_config)
            db_config.show_list = prune_config.show_list
            db_config.show_stats = prune_config.show_stats
            db_config.save_space = prune_config.save_space
            db_config.enabled = True

            self.db.add(db_config)
            self.db.commit()
            self.db.refresh(db_config)

            return True, db_config, None

        except Exception as e:
            self.db.rollback()
            return False, None, f"Failed to create prune configuration: {str(e)}"

    def update_prune_config(
        self, config_id: int, prune_config_update: PruneConfigUpdate
    ) -> Tuple[bool, Optional[PruneConfig], Optional[str]]:
        """
        Update an existing prune configuration.

        Returns:
            tuple: (success, config_or_none, error_message_or_none)
        """
        try:
            config = (
                self.db.query(PruneConfig).filter(PruneConfig.id == config_id).first()
            )
            if not config:
                return False, None, "Prune configuration not found"

            update_dict = prune_config_update.model_dump(exclude_unset=True)
            if "name" in update_dict and update_dict["name"] != config.name:
                existing = (
                    self.db.query(PruneConfig)
                    .filter(
                        PruneConfig.name == update_dict["name"],
                        PruneConfig.id != config_id,
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
            return False, None, f"Failed to update prune configuration: {str(e)}"

    def enable_prune_config(
        self, prune_config_id: int
    ) -> Tuple[bool, Optional[PruneConfig], Optional[str]]:
        """
        Enable a prune configuration.

        Returns:
            tuple: (success, config_or_none, error_message_or_none)
        """
        try:
            config = (
                self.db.query(PruneConfig)
                .filter(PruneConfig.id == prune_config_id)
                .first()
            )
            if not config:
                return False, None, "Prune configuration not found"

            config.enabled = True
            self.db.commit()
            self.db.refresh(config)

            return True, config, None

        except Exception as e:
            self.db.rollback()
            return False, None, f"Failed to enable prune configuration: {str(e)}"

    def disable_prune_config(
        self, prune_config_id: int
    ) -> Tuple[bool, Optional[PruneConfig], Optional[str]]:
        """
        Disable a prune configuration.

        Returns:
            tuple: (success, config_or_none, error_message_or_none)
        """
        try:
            config = (
                self.db.query(PruneConfig)
                .filter(PruneConfig.id == prune_config_id)
                .first()
            )
            if not config:
                return False, None, "Prune configuration not found"

            config.enabled = False
            self.db.commit()
            self.db.refresh(config)

            return True, config, None

        except Exception as e:
            self.db.rollback()
            return False, None, f"Failed to disable prune configuration: {str(e)}"

    def delete_prune_config(
        self, prune_config_id: int
    ) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Delete a prune configuration.

        Returns:
            tuple: (success, config_name_or_none, error_message_or_none)
        """
        try:
            config = (
                self.db.query(PruneConfig)
                .filter(PruneConfig.id == prune_config_id)
                .first()
            )
            if not config:
                return False, None, "Prune configuration not found"

            config_name = config.name
            self.db.delete(config)
            self.db.commit()

            return True, config_name, None

        except Exception as e:
            self.db.rollback()
            return False, None, f"Failed to delete prune configuration: {str(e)}"

    def get_configs_with_descriptions(
        self,
    ) -> List[Dict[str, Union[str, int, bool, None]]]:
        """
        Get all prune configurations with computed description fields.

        Returns:
            List of dictionaries with config data and computed fields
        """
        try:
            prune_configs_raw = self.get_prune_configs()

            processed_configs = []
            for config in prune_configs_raw:
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
        """Get data needed for prune form."""
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
