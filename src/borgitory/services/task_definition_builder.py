"""
TaskDefinitionBuilder - Centralized task definition creation for Borgitory

This class eliminates duplication between job_service.py and scheduler_service.py
by providing a consistent interface for building all task types.
"""

import logging
from typing import Dict, List, Optional, cast
from sqlalchemy.orm import Session
from borgitory.models.database import (
    CleanupConfig,
    RepositoryCheckConfig,
    NotificationConfig,
)
from borgitory.models.schemas import PruneRequest, CheckRequest
from borgitory.constants.retention import RetentionConfigProtocol, RetentionFieldHandler
from borgitory.services.hooks.hook_config import HookConfigParser


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
        ignore_lock: bool = False,
    ) -> Dict[str, object]:
        """
        Build a backup task definition.

        Args:
            repository_name: Name of the repository for display
            source_path: Path to backup from
            compression: Compression algorithm to use
            dry_run: Whether this is a dry run
            ignore_lock: Whether to run 'borg break-lock' before backup

        Returns:
            Task definition dictionary
        """
        return {
            "type": "backup",
            "name": f"Backup {repository_name}",
            "source_path": source_path,
            "compression": compression,
            "dry_run": dry_run,
            "ignore_lock": ignore_lock,
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
            retention_config = cast(RetentionConfigProtocol, cleanup_config)
            retention_dict = RetentionFieldHandler.to_dict(retention_config)
            task.update(retention_dict)

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
            retention_dict = RetentionFieldHandler.to_dict(prune_request)
            task.update(retention_dict)

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

    def build_hook_task(
        self,
        hook_name: str,
        hook_command: str,
        hook_type: str,
        repository_name: Optional[str] = None,
    ) -> Dict[str, object]:
        """
        Build a hook task definition.

        Args:
            hook_name: Name of the hook
            hook_command: Command to execute
            hook_type: Type of hook ("pre" or "post")
            repository_name: Optional repository name for display

        Returns:
            Task definition dictionary
        """
        display_name = f"{hook_type.title()}-job hook: {hook_name}"
        if repository_name:
            display_name += f" ({repository_name})"

        return {
            "type": "hook",
            "name": display_name,
            "hook_name": hook_name,
            "hook_command": hook_command,
            "hook_type": hook_type,
        }

    def build_hooks_from_json(
        self,
        hooks_json: Optional[str],
        hook_type: str,
        repository_name: Optional[str] = None,
    ) -> List[Dict[str, object]]:
        """
        Build hook task definitions from JSON configuration.

        Args:
            hooks_json: JSON string containing hook configurations
            hook_type: Type of hooks ("pre" or "post")
            repository_name: Optional repository name for display

        Returns:
            List containing a single hook task definition with all hooks bundled
        """
        if not hooks_json:
            return []

        try:
            hooks = HookConfigParser.parse_hooks_json(hooks_json)
            if not hooks:
                return []

            display_name = f"{hook_type.title()}-job hooks"
            if repository_name:
                display_name += f" ({repository_name})"

            return [
                {
                    "type": "hook",
                    "name": display_name,
                    "hook_type": hook_type,
                    "hooks": hooks_json,
                }
            ]
        except ValueError as e:
            logger = logging.getLogger(__name__)
            logger.error(f"Failed to parse {hook_type}-job hooks: {e}")
            return []

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
        pre_job_hooks: Optional[str] = None,
        post_job_hooks: Optional[str] = None,
    ) -> List[Dict[str, object]]:
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
            pre_job_hooks: JSON string of pre-job hook configurations
            post_job_hooks: JSON string of post-job hook configurations

        Returns:
            List of task definition dictionaries
        """
        tasks = []

        pre_hook_tasks = self.build_hooks_from_json(
            pre_job_hooks, "pre", repository_name
        )
        tasks.extend(pre_hook_tasks)

        if include_backup:
            backup_params = backup_params or {}
            source_path = str(backup_params.get("source_path", "/data"))
            compression = str(backup_params.get("compression", "zstd"))
            dry_run = bool(backup_params.get("dry_run", False))
            ignore_lock = bool(backup_params.get("ignore_lock", False))
            tasks.append(
                self.build_backup_task(
                    repository_name, source_path, compression, dry_run, ignore_lock
                )
            )

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

        if include_cloud_sync:
            tasks.append(
                self.build_cloud_sync_task(repository_name, cloud_sync_config_id)
            )

        if notification_config_id:
            notification_task = self.build_notification_task(
                notification_config_id, repository_name
            )
            if notification_task:
                tasks.append(notification_task)

        post_hook_tasks = self.build_hooks_from_json(
            post_job_hooks, "post", repository_name
        )
        tasks.extend(post_hook_tasks)

        return tasks
