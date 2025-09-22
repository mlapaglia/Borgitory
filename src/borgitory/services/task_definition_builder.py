"""
TaskDefinitionBuilder - Centralized task definition creation for Borgitory

This class eliminates duplication between job_service.py and scheduler_service.py
by providing a consistent interface for building all task types.
"""

from typing import Dict, Optional
from sqlalchemy.orm import Session
from borgitory.models.database import (
    CleanupConfig,
    RepositoryCheckConfig,
    NotificationConfig,
)
from borgitory.models.schemas import PruneRequest, CheckRequest


class TaskDefinitionBuilder:
    """
    Builder class for creating task definitions with consistent structure and validation.

    Handles all task types: backup, prune, check, cloud_sync, and notification.
    Eliminates duplication between manual and scheduled job creation.
    """

    def __init__(self, db_session: Session) -> None:
        """
        Initialize the builder with a database session for configuration lookups.

        Args:
            db_session: SQLAlchemy session for accessing configurations
        """
        self.db_session = db_session

    def build_backup_task(
        self,
        repository_name: str,
        source_path: str = "/data",
        compression: str = "zstd",
        dry_run: bool = False,
    ) -> Dict[str, object]:
        """
        Build a backup task definition.

        Args:
            repository_name: Name of the repository for display
            source_path: Path to backup from
            compression: Compression algorithm to use
            dry_run: Whether this is a dry run

        Returns:
            Task definition dictionary
        """
        return {
            "type": "backup",
            "name": f"Backup {repository_name}",
            "source_path": source_path,
            "compression": compression,
            "dry_run": dry_run,
        }

    def build_prune_task_from_config(
        self, cleanup_config_id: int, repository_name: str
    ) -> Optional[Dict[str, object]]:
        """
        Build a prune task definition from a stored cleanup configuration.

        Args:
            cleanup_config_id: ID of the cleanup configuration
            repository_name: Name of the repository for display

        Returns:
            Task definition dictionary or None if config not found
        """
        cleanup_config = (
            self.db_session.query(CleanupConfig)
            .filter(CleanupConfig.id == cleanup_config_id)
            .first()
        )

        if not cleanup_config:
            return None

        task = {
            "type": "prune",
            "name": f"Prune {repository_name}",
            "dry_run": False,
            "show_list": cleanup_config.show_list,
            "show_stats": cleanup_config.show_stats,
            "save_space": cleanup_config.save_space,
        }

        # Add retention parameters based on strategy
        if cleanup_config.strategy == "simple" and cleanup_config.keep_within_days:
            task["keep_within"] = f"{cleanup_config.keep_within_days}d"
        elif cleanup_config.strategy == "advanced":
            task.update(
                {
                    "keep_secondly": cleanup_config.keep_secondly,
                    "keep_minutely": cleanup_config.keep_minutely,
                    "keep_hourly": cleanup_config.keep_hourly,
                    "keep_daily": cleanup_config.keep_daily,
                    "keep_weekly": cleanup_config.keep_weekly,
                    "keep_monthly": cleanup_config.keep_monthly,
                    "keep_yearly": cleanup_config.keep_yearly,
                }
            )

        return task

    def build_prune_task_from_request(
        self, prune_request: PruneRequest, repository_name: str
    ) -> Dict[str, object]:
        """
        Build a prune task definition from a manual prune request.

        Args:
            prune_request: Request object with prune parameters
            repository_name: Name of the repository for display

        Returns:
            Task definition dictionary
        """
        task = {
            "type": "prune",
            "name": f"Prune {repository_name}",
            "dry_run": prune_request.dry_run,
            "show_list": True,  # Default for manual requests
            "show_stats": True,  # Default for manual requests
            "save_space": getattr(prune_request, "save_space", True),
            "force_prune": getattr(prune_request, "force_prune", False),
        }

        # Add retention parameters based on strategy
        if prune_request.strategy == "simple" and prune_request.keep_within_days:
            task["keep_within"] = f"{prune_request.keep_within_days}d"
        elif prune_request.strategy == "advanced":
            task.update(
                {
                    "keep_secondly": prune_request.keep_secondly,
                    "keep_minutely": prune_request.keep_minutely,
                    "keep_hourly": prune_request.keep_hourly,
                    "keep_daily": prune_request.keep_daily,
                    "keep_weekly": prune_request.keep_weekly,
                    "keep_monthly": prune_request.keep_monthly,
                    "keep_yearly": prune_request.keep_yearly,
                }
            )

        return task

    def build_check_task_from_config(
        self, check_config_id: int, repository_name: str
    ) -> Optional[Dict[str, object]]:
        """
        Build a check task definition from a stored check configuration.

        Args:
            check_config_id: ID of the repository check configuration
            repository_name: Name of the repository for display

        Returns:
            Task definition dictionary or None if config not found
        """
        check_config = (
            self.db_session.query(RepositoryCheckConfig)
            .filter(RepositoryCheckConfig.id == check_config_id)
            .first()
        )

        if not check_config:
            return None

        task = {
            "type": "check",
            "name": f"Check {repository_name} ({check_config.name})",
            "check_type": check_config.check_type,
            "verify_data": check_config.verify_data,
            "repair_mode": check_config.repair_mode,
            "save_space": check_config.save_space,
            "max_duration": check_config.max_duration,
            "archive_prefix": check_config.archive_prefix,
            "archive_glob": check_config.archive_glob,
            "first_n_archives": check_config.first_n_archives,
            "last_n_archives": check_config.last_n_archives,
        }

        return task

    def build_check_task_from_request(
        self, check_request: CheckRequest, repository_name: str
    ) -> Dict[str, object]:
        """
        Build a check task definition from a manual check request.

        Args:
            check_request: Request object with check parameters
            repository_name: Name of the repository for display

        Returns:
            Task definition dictionary
        """
        task = {
            "type": "check",
            "name": f"Check {repository_name}",
            "check_type": check_request.check_type,
            "verify_data": getattr(check_request, "verify_data", False),
            "repair_mode": getattr(check_request, "repair_mode", False),
            "save_space": getattr(check_request, "save_space", False),
            "max_duration": getattr(check_request, "max_duration", None),
            "archive_prefix": getattr(check_request, "archive_prefix", None),
            "archive_glob": getattr(check_request, "archive_glob", None),
            "first_n_archives": getattr(check_request, "first_n_archives", None),
            "last_n_archives": getattr(check_request, "last_n_archives", None),
        }

        return task

    def build_cloud_sync_task(
        self,
        repository_name: Optional[str] = None,
        cloud_sync_config_id: Optional[int] = None,
    ) -> Dict[str, object]:
        """
        Build a cloud sync task definition.

        Args:
            repository_name: Optional repository name for display
            cloud_sync_config_id: ID of the cloud sync configuration

        Returns:
            Task definition dictionary
        """
        name = (
            f"Sync {repository_name} to Cloud" if repository_name else "Sync to Cloud"
        )

        return {
            "type": "cloud_sync",
            "name": name,
            "cloud_sync_config_id": cloud_sync_config_id,
        }

    def build_notification_task(
        self, notification_config_id: int, repository_name: str
    ) -> Optional[Dict[str, object]]:
        """
        Build a notification task definition from a stored notification configuration.

        Args:
            notification_config_id: ID of the notification configuration
            repository_name: Name of the repository for display

        Returns:
            Task definition dictionary or None if config not found
        """
        notification_config = (
            self.db_session.query(NotificationConfig)
            .filter(NotificationConfig.id == notification_config_id)
            .first()
        )

        if not notification_config:
            return None

        return {
            "type": "notification",
            "name": f"Send notification for {repository_name}",
            "provider": notification_config.provider,
            "config_id": notification_config_id,
        }

    def build_task_list(
        self,
        repository_name: str,
        include_backup: bool = True,
        backup_params: Optional[Dict[str, object]] = None,
        cleanup_config_id: Optional[int] = None,
        prune_request: Optional[PruneRequest] = None,
        check_config_id: Optional[int] = None,
        check_request: Optional[CheckRequest] = None,
        include_cloud_sync: bool = False,
        cloud_sync_config_id: Optional[int] = None,
        notification_config_id: Optional[int] = None,
    ) -> list[Dict[str, object]]:
        """
        Build a complete list of task definitions for a job.

        This is a convenience method that builds multiple tasks at once
        and handles the common patterns used in job creation.

        Args:
            repository_name: Name of the repository
            include_backup: Whether to include a backup task
            backup_params: Parameters for backup task (source_path, compression, etc.)
            cleanup_config_id: ID for prune task from borgitory.config
            prune_request: Request object for manual prune task
            check_config_id: ID for check task from borgitory.config
            check_request: Request object for manual check task
            include_cloud_sync: Whether to include cloud sync task
            notification_config_id: ID for notification task

        Returns:
            List of task definition dictionaries
        """
        tasks = []

        # Add backup task
        if include_backup:
            backup_params = backup_params or {}
            # Extract and cast parameters with defaults
            source_path = str(backup_params.get("source_path", "/data"))
            compression = str(backup_params.get("compression", "zstd"))
            dry_run = bool(backup_params.get("dry_run", False))
            tasks.append(
                self.build_backup_task(
                    repository_name, source_path, compression, dry_run
                )
            )

        # Add prune task (request takes precedence over config)
        if prune_request:
            tasks.append(
                self.build_prune_task_from_request(prune_request, repository_name)
            )
        elif cleanup_config_id:
            prune_task = self.build_prune_task_from_config(
                cleanup_config_id, repository_name
            )
            if prune_task:
                tasks.append(prune_task)

        # Add check task (request takes precedence over config)
        if check_request:
            tasks.append(
                self.build_check_task_from_request(check_request, repository_name)
            )
        elif check_config_id:
            check_task = self.build_check_task_from_config(
                check_config_id, repository_name
            )
            if check_task:
                tasks.append(check_task)

        # Add cloud sync task
        if include_cloud_sync:
            tasks.append(
                self.build_cloud_sync_task(repository_name, cloud_sync_config_id)
            )

        # Add notification task
        if notification_config_id:
            notification_task = self.build_notification_task(
                notification_config_id, repository_name
            )
            if notification_task:
                tasks.append(notification_task)

        return tasks
