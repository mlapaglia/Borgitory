"""
Schedule Business Logic Service.
Handles all schedule-related business operations independent of HTTP concerns.
"""

import logging
from typing import List, Optional, Dict, Any, TYPE_CHECKING
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy.orm import Session

from borgitory.models.database import Schedule, Repository

if TYPE_CHECKING:
    from borgitory.services.scheduling.scheduler_service import SchedulerService

logger = logging.getLogger(__name__)


class ScheduleService:
    """Service for schedule business logic operations."""

    def __init__(self, db: Session, scheduler_service: "SchedulerService") -> None:
        self.db = db
        self.scheduler_service = scheduler_service

    def validate_cron_expression(
        self, cron_expression: str
    ) -> tuple[bool, Optional[str]]:
        """
        Validate a cron expression using APScheduler.

        Returns:
            tuple: (is_valid, error_message)
        """
        try:
            CronTrigger.from_crontab(cron_expression)
            return True, None
        except ValueError as e:
            return False, f"Invalid cron expression: {str(e)}"

    def get_schedule_by_id(self, schedule_id: int) -> Optional[Schedule]:
        """Get a schedule by ID."""
        return self.db.query(Schedule).filter(Schedule.id == schedule_id).first()

    def get_schedules(self, skip: int = 0, limit: int = 100) -> List[Schedule]:
        """Get a list of schedules with pagination."""
        return self.db.query(Schedule).offset(skip).limit(limit).all()

    def get_all_schedules(self) -> List[Schedule]:
        """Get all schedules."""
        return self.db.query(Schedule).all()

    async def create_schedule(
        self,
        name: str,
        repository_id: int,
        cron_expression: str,
        source_path: str,
        cloud_sync_config_id: Optional[int] = None,
        prune_config_id: Optional[int] = None,
        notification_config_id: Optional[int] = None,
        pre_job_hooks: Optional[str] = None,
        post_job_hooks: Optional[str] = None,
    ) -> tuple[bool, Optional[Schedule], Optional[str]]:
        """
        Create a new schedule.

        Returns:
            tuple: (success, schedule_or_none, error_message_or_none)
        """
        try:
            # Validate repository exists
            repository = (
                self.db.query(Repository).filter(Repository.id == repository_id).first()
            )
            if not repository:
                return False, None, "Repository not found"

            # Validate cron expression
            is_valid, error_msg = self.validate_cron_expression(cron_expression)
            if not is_valid:
                return False, None, error_msg

            # Create schedule
            db_schedule = Schedule()
            db_schedule.name = name
            db_schedule.repository_id = repository_id
            db_schedule.cron_expression = cron_expression
            db_schedule.source_path = source_path
            db_schedule.enabled = True
            db_schedule.cloud_sync_config_id = cloud_sync_config_id
            db_schedule.prune_config_id = prune_config_id
            db_schedule.notification_config_id = notification_config_id
            db_schedule.pre_job_hooks = pre_job_hooks
            db_schedule.post_job_hooks = post_job_hooks

            self.db.add(db_schedule)
            self.db.commit()
            self.db.refresh(db_schedule)

            # Add to scheduler
            try:
                await self.scheduler_service.add_schedule(
                    db_schedule.id, db_schedule.name, db_schedule.cron_expression
                )
                return True, db_schedule, None
            except Exception as e:
                # Rollback database changes if scheduler fails
                self.db.delete(db_schedule)
                self.db.commit()
                return False, None, f"Failed to schedule job: {str(e)}"

        except Exception as e:
            self.db.rollback()
            return False, None, f"Failed to create schedule: {str(e)}"

    async def update_schedule(
        self,
        schedule_id: int,
        update_data: Dict[str, Any],
    ) -> tuple[bool, Optional[Schedule], Optional[str]]:
        """
        Update an existing schedule.

        Returns:
            tuple: (success, schedule_or_none, error_message_or_none)
        """
        try:
            schedule = self.get_schedule_by_id(schedule_id)
            if not schedule:
                return False, None, "Schedule not found"

            # Update fields
            for field, value in update_data.items():
                setattr(schedule, field, value)

            self.db.commit()
            self.db.refresh(schedule)

            # Update the scheduler if enabled
            if schedule.enabled:
                try:
                    await self.scheduler_service.update_schedule(
                        schedule_id,
                        schedule.name,
                        schedule.cron_expression,
                        schedule.enabled,
                    )
                except Exception:
                    # If scheduler update fails, we still want to return the updated schedule
                    pass

            return True, schedule, None

        except Exception as e:
            self.db.rollback()
            return False, None, f"Failed to update schedule: {str(e)}"

    async def toggle_schedule(
        self, schedule_id: int
    ) -> tuple[bool, Optional[Schedule], Optional[str]]:
        """
        Toggle a schedule's enabled state.

        Returns:
            tuple: (success, schedule_or_none, error_message_or_none)
        """
        try:
            schedule = self.get_schedule_by_id(schedule_id)
            if not schedule:
                return False, None, "Schedule not found"

            schedule.enabled = not schedule.enabled
            self.db.commit()

            # Update scheduler
            try:
                await self.scheduler_service.update_schedule(
                    schedule.id,
                    schedule.name,
                    schedule.cron_expression,
                    schedule.enabled,
                )
                return True, schedule, None
            except Exception as e:
                return False, None, f"Failed to update schedule: {str(e)}"

        except Exception as e:
            self.db.rollback()
            return False, None, f"Failed to toggle schedule: {str(e)}"

    async def delete_schedule(
        self, schedule_id: int
    ) -> tuple[bool, Optional[str], Optional[str]]:
        """
        Delete a schedule.

        Returns:
            tuple: (success, schedule_name_or_none, error_message_or_none)
        """
        try:
            schedule = self.get_schedule_by_id(schedule_id)
            if not schedule:
                return False, None, "Schedule not found"

            schedule_name = schedule.name

            # Remove from scheduler
            try:
                await self.scheduler_service.remove_schedule(schedule_id)
            except Exception as e:
                return (
                    False,
                    None,
                    f"Failed to remove schedule from scheduler: {str(e)}",
                )

            # Delete from database
            self.db.delete(schedule)
            self.db.commit()

            return True, schedule_name, None

        except Exception as e:
            self.db.rollback()
            return False, None, f"Failed to delete schedule: {str(e)}"

    async def run_schedule_manually(
        self, schedule_id: int
    ) -> tuple[bool, Optional[str], Optional[str]]:
        """
        Manually run a schedule immediately by injecting a one-time job into APScheduler.

        Returns:
            tuple: (success, job_id_or_none, error_message_or_none)
        """
        try:
            schedule = self.get_schedule_by_id(schedule_id)
            if not schedule:
                return False, None, "Schedule not found"

            # Use the scheduler service to inject a one-time job
            job_id = await self.scheduler_service.run_schedule_once(
                schedule_id, schedule.name
            )

            logger.info(
                f"Successfully scheduled manual run for schedule {schedule_id} with job_id {job_id}"
            )
            return True, job_id, None

        except Exception as e:
            logger.error(f"Failed to run schedule manually: {str(e)}")
            return False, None, f"Failed to run schedule manually: {str(e)}"

    def validate_schedule_creation_data(
        self, json_data: Dict[str, Any]
    ) -> tuple[bool, Dict[str, Any], Optional[str]]:
        """
        Validate and process schedule creation data.

        Args:
            json_data: Raw JSON data from request

        Returns:
            tuple: (is_valid, processed_data, error_message)
        """
        try:
            # Validate cron expression
            cron_expression = json_data.get("cron_expression", "").strip()
            if not cron_expression:
                return False, {}, "Cron expression is required"

            # Check if cron expression has correct number of parts
            cron_parts = cron_expression.split()
            if len(cron_parts) != 5:
                return (
                    False,
                    {},
                    f"Cron expression must have 5 parts (minute hour day month weekday), but got {len(cron_parts)} parts: '{cron_expression}'",
                )

            # Validate repository ID
            repository_id = json_data.get("repository_id")
            if not repository_id:
                return False, {}, "Repository is required"

            try:
                repository_id = int(repository_id)
            except (ValueError, TypeError):
                return False, {}, "Invalid repository ID"

            # Validate name
            name = json_data.get("name", "").strip()
            if not name:
                return False, {}, "Schedule name is required"

            # Process optional fields
            def safe_int(value: Any) -> Optional[int]:
                if not value or value == "":
                    return None
                try:
                    return int(value)
                except (ValueError, TypeError):
                    return None

            processed_data = {
                "name": name,
                "repository_id": repository_id,
                "cron_expression": cron_expression,
                "source_path": json_data.get("source_path", ""),
                "cloud_sync_config_id": safe_int(json_data.get("cloud_sync_config_id")),
                "prune_config_id": safe_int(json_data.get("prune_config_id")),
                "notification_config_id": safe_int(
                    json_data.get("notification_config_id")
                ),
            }

            return True, processed_data, None

        except Exception as e:
            return False, {}, f"Invalid form data: {str(e)}"
