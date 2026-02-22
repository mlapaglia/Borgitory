"""
Regression tests for schedule next_run staleness bugs.

Bug 1: execute_scheduled_backup updates last_run but never updates next_run,
        causing next_run to become stale and appear before last_run.

Bug 2: _reload_schedules uses persist=False, so stale next_run values in the
        database are never corrected on application restart.

Bug 3: _update_next_run_time stores APScheduler's timezone-aware datetime
        directly without normalizing to UTC, causing display mismatches.
"""

import uuid
from datetime import datetime, UTC, timezone, timedelta
from unittest.mock import Mock, AsyncMock, MagicMock, patch

import pytest

from borgitory.models.database import Schedule
from borgitory.models.enums import JobType
from borgitory.models.job_results import JobCreationResult
from borgitory.services.scheduling.scheduler_service import (
    SchedulerService,
    execute_scheduled_backup,
)


class TestNextRunUpdatedAfterExecution:
    """execute_scheduled_backup must update next_run so it doesn't go stale."""

    @pytest.fixture
    def mock_schedule(self) -> Mock:
        schedule = Mock(spec=Schedule)
        schedule.id = 1
        schedule.name = "Test Schedule"
        schedule.repository_id = 10
        schedule.source_path = "/data/backup"
        schedule.cloud_sync_config_id = None
        schedule.prune_config_id = None
        schedule.check_config_id = None
        schedule.notification_config_id = None
        schedule.pre_job_hooks = None
        schedule.post_job_hooks = None
        schedule.patterns = None
        schedule.last_run = None
        schedule.next_run = datetime(2025, 11, 3, 15, 0, 0, tzinfo=UTC)
        return schedule

    @pytest.fixture
    def mock_repository(self) -> Mock:
        repo = Mock()
        repo.id = 10
        repo.name = "test_repo"
        return repo

    def _make_mock_db_session(self, schedule_or_none: Mock | None) -> Mock:
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = schedule_or_none
        mock_db = Mock()
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_db.commit = AsyncMock()
        mock_db.__aenter__ = AsyncMock(return_value=mock_db)
        mock_db.__aexit__ = AsyncMock(return_value=None)
        return mock_db

    @pytest.mark.asyncio
    async def test_next_run_is_updated_after_backup_execution(
        self,
        mock_schedule: Mock,
        mock_repository: Mock,
    ) -> None:
        """After a scheduled backup executes, next_run must advance past last_run.

        Currently fails because execute_scheduled_backup only sets last_run
        and never updates next_run from the APScheduler job.
        """
        mock_schedule.repository = mock_repository
        old_next_run = mock_schedule.next_run
        mock_db = self._make_mock_db_session(mock_schedule)

        job_id = uuid.uuid4()
        mock_job_service = Mock()
        mock_job_service.create_backup_job = AsyncMock(
            return_value=JobCreationResult(job_id=job_id, status="started")
        )

        future_next_run = datetime(2025, 11, 8, 15, 0, 0, tzinfo=UTC)
        mock_apscheduler_job = Mock()
        mock_apscheduler_job.next_run_time = future_next_run

        mock_scheduler_svc = Mock()
        mock_scheduler_svc.job_service = mock_job_service
        mock_scheduler_svc.scheduler = Mock()
        mock_scheduler_svc.scheduler.get_job.return_value = mock_apscheduler_job

        fixed_now = datetime(2025, 11, 7, 14, 0, 0, tzinfo=UTC)

        with (
            patch(
                "borgitory.dependencies.get_scheduler_service_singleton",
                return_value=mock_scheduler_svc,
            ),
            patch(
                "borgitory.models.database.async_session_maker",
            ) as mock_session_maker,
            patch(
                "borgitory.services.scheduling.scheduler_service.now_utc",
                return_value=fixed_now,
            ),
        ):
            mock_session_maker.return_value = mock_db
            await execute_scheduled_backup(1)

        assert mock_schedule.last_run == fixed_now, "last_run should be updated"
        assert mock_schedule.next_run != old_next_run, (
            "next_run should have been updated after execution"
        )
        assert mock_schedule.next_run > mock_schedule.last_run, (
            f"next_run ({mock_schedule.next_run}) must be after "
            f"last_run ({mock_schedule.last_run})"
        )


class TestReloadSchedulesUpdatesNextRun:
    """_reload_schedules must refresh stale next_run values in the database."""

    def setup_method(self) -> None:
        mock_job_manager = Mock()
        mock_job_service = Mock()
        self.scheduler_service = SchedulerService(
            job_manager=mock_job_manager, job_service=mock_job_service
        )

    @pytest.mark.asyncio
    async def test_reload_schedules_persists_next_run(self) -> None:
        """On startup, _reload_schedules should update next_run in the database.

        Currently fails because _reload_schedules passes persist=False,
        which skips _update_next_run_time entirely.
        """
        mock_schedule = Mock()
        mock_schedule.id = 1
        mock_schedule.name = "Schedule 1"
        mock_schedule.cron_expression = "0 14 1-31 1-12 *"

        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [mock_schedule]
        mock_result = Mock()
        mock_result.scalars.return_value = mock_scalars

        mock_db = Mock()
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_db.__aenter__ = AsyncMock(return_value=mock_db)
        mock_db.__aexit__ = AsyncMock(return_value=None)

        with (
            patch(
                "borgitory.models.database.async_session_maker"
            ) as mock_session_maker,
            patch.object(
                self.scheduler_service,
                "_add_schedule_internal",
                new_callable=AsyncMock,
            ) as mock_add,
            patch.object(
                self.scheduler_service,
                "_update_next_run_time",
                new_callable=AsyncMock,
            ) as mock_update_next_run,
        ):
            mock_session_maker.return_value = mock_db
            mock_add.return_value = "backup_schedule_1"

            await self.scheduler_service._reload_schedules()

            mock_add.assert_called_once()
            mock_update_next_run.assert_called_once_with(1, "backup_schedule_1"), (
                "_update_next_run_time must be called during reload "
                "to correct stale next_run values"
            )


class TestNextRunTimezoneNormalization:
    """_update_next_run_time must store UTC-normalized datetimes."""

    def setup_method(self) -> None:
        mock_job_manager = Mock()
        mock_job_service = Mock()
        self.scheduler_service = SchedulerService(
            job_manager=mock_job_manager, job_service=mock_job_service
        )

    @pytest.mark.asyncio
    async def test_next_run_stored_as_utc(self) -> None:
        """next_run must be stored as UTC regardless of APScheduler's timezone.

        APScheduler's CronTrigger.from_crontab() uses the local timezone,
        so job.next_run_time may be in a non-UTC timezone. Storing it directly
        into a non-timezone-aware DB column causes display mismatches because
        the display layer assumes naive datetimes are UTC.
        """
        schedule_id = 1
        job_id = "backup_schedule_1"

        # Simulate APScheduler returning a time in US Eastern (UTC-5)
        eastern = timezone(timedelta(hours=-5))
        eastern_time = datetime(2025, 11, 7, 8, 0, 0, tzinfo=eastern)
        expected_utc = datetime(2025, 11, 7, 13, 0, 0, tzinfo=UTC)

        mock_job = Mock()
        mock_job.next_run_time = eastern_time

        mock_schedule = Mock()
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = mock_schedule

        mock_db = Mock()
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_db.__aenter__ = AsyncMock(return_value=mock_db)
        mock_db.__aexit__ = AsyncMock(return_value=None)

        with (
            patch.object(
                self.scheduler_service.scheduler, "get_job"
            ) as mock_get_job,
            patch(
                "borgitory.models.database.async_session_maker"
            ) as mock_session_maker,
        ):
            mock_get_job.return_value = mock_job
            mock_session_maker.return_value = mock_db

            await self.scheduler_service._update_next_run_time(schedule_id, job_id)

        stored_value = mock_schedule.next_run
        if stored_value.tzinfo is not None:
            stored_utc = stored_value.astimezone(UTC)
        else:
            stored_utc = stored_value.replace(tzinfo=UTC)

        assert stored_utc == expected_utc, (
            f"Expected UTC time {expected_utc}, but got {stored_value}. "
            f"The value should be normalized to UTC before storage."
        )
