"""
Tests for manual schedule run functionality using APScheduler one-time jobs.
"""

import pickle

from apscheduler.executors.asyncio import AsyncIOExecutor
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.schedulers.base import MemoryJobStore
from apscheduler.triggers.date import DateTrigger
from httpx import AsyncClient
import pytest
import uuid
from unittest.mock import Mock, AsyncMock, patch
from sqlalchemy.ext.asyncio import AsyncSession

from borgitory.main import app
from borgitory.models.database import Schedule, Repository
from borgitory.models.enums import JobType
from borgitory.models.job_results import JobCreationResult
from borgitory.services.scheduling.schedule_service import ScheduleService
from borgitory.services.scheduling.scheduler_service import (
    SchedulerService,
    execute_scheduled_backup,
)
from borgitory.dependencies import get_schedule_service, get_scheduler_service_singleton
from borgitory.protocols.job_protocols import JobManagerProtocol

def create_test_scheduler_service(
    job_manager: Mock, job_service_factory: Mock
) -> SchedulerService:
    """Create a scheduler service with in-memory job store for testing"""
    scheduler_service = SchedulerService(job_manager, job_service_factory)

    jobstores = {"default": MemoryJobStore()}
    executors = {"default": AsyncIOExecutor()}
    job_defaults = {"coalesce": False, "max_instances": 1}

    scheduler_service.scheduler = AsyncIOScheduler(
        jobstores=jobstores, executors=executors, job_defaults=job_defaults
    )
    scheduler_service._running = False

    return scheduler_service


class TestManualRunAPScheduler:
    """Test manual schedule run functionality using APScheduler one-time jobs"""

    @pytest.fixture
    def mock_job_manager(self) -> Mock:
        """Mock job manager"""
        mock = Mock(spec=JobManagerProtocol)
        return mock

    @pytest.fixture
    def mock_job_service_factory(self) -> Mock:
        """Mock job service factory"""
        return Mock()

    @pytest.fixture
    def scheduler_service(
        self, mock_job_manager: Mock, mock_job_service_factory: Mock
    ) -> SchedulerService:
        """Create scheduler service with mocked dependencies and in-memory job store"""
        return create_test_scheduler_service(mock_job_manager, mock_job_service_factory)

    @pytest.fixture
    def mock_scheduler_service(self) -> AsyncMock:
        """Mock scheduler service for schedule service tests"""
        mock = AsyncMock()
        mock.add_schedule = AsyncMock()
        mock.update_schedule = AsyncMock()
        mock.remove_schedule = AsyncMock()
        mock.run_schedule_once = AsyncMock()
        return mock

    @pytest.fixture
    def schedule_service(self, mock_scheduler_service: AsyncMock) -> ScheduleService:
        """Create schedule service with mocked scheduler service"""
        return ScheduleService(mock_scheduler_service)

    @pytest.fixture
    async def test_repository(self, test_db: AsyncSession) -> Repository:
        """Create test repository"""
        repo = Repository()
        repo.name = "test_repo"
        repo.path = "/test/path"
        repo.set_passphrase("test_pass")
        test_db.add(repo)
        await test_db.commit()
        await test_db.refresh(repo)
        return repo

    @pytest.fixture
    async def test_schedule(
        self, test_db: AsyncSession, test_repository: Repository
    ) -> Schedule:
        """Create test schedule"""
        schedule = Schedule()
        schedule.name = "Test Schedule"
        schedule.repository_id = test_repository.id
        schedule.cron_expression = "0 2 * * *"
        schedule.source_path = "/test/source"
        schedule.enabled = True
        test_db.add(schedule)
        await test_db.commit()
        await test_db.refresh(schedule)
        return schedule

    async def test_scheduler_service_run_schedule_once_success(
        self, scheduler_service: SchedulerService
    ) -> None:
        """Test SchedulerService.run_schedule_once creates one-time job successfully"""
        # Start the scheduler
        await scheduler_service.start()

        try:
            schedule_id = 123
            schedule_name = "Test Schedule"

            # Call run_schedule_once
            job_id = await scheduler_service.run_schedule_once(
                schedule_id, schedule_name
            )

            # Verify job was added to scheduler
            job = scheduler_service.scheduler.get_job(job_id)
            assert job is not None
            assert job.name == f"Manual run: {schedule_name}"
            assert job.max_instances == 1
            assert job.misfire_grace_time == 60

        finally:
            await scheduler_service.stop()

    async def test_scheduler_service_run_schedule_once_scheduler_not_running(
        self, scheduler_service: SchedulerService
    ) -> None:
        """Test SchedulerService.run_schedule_once fails when scheduler not running"""
        schedule_id = 123
        schedule_name = "Test Schedule"

        # Don't start the scheduler
        with pytest.raises(RuntimeError, match="Scheduler is not running"):
            await scheduler_service.run_schedule_once(schedule_id, schedule_name)

    async def test_scheduler_service_run_schedule_once_unique_job_ids(
        self, scheduler_service: SchedulerService
    ) -> None:
        """Test that multiple manual runs create unique job IDs"""
        await scheduler_service.start()

        try:
            schedule_id = 123
            schedule_name = "Test Schedule"

            # Create first manual run
            job_id_1 = await scheduler_service.run_schedule_once(
                schedule_id, schedule_name
            )

            # Create second manual run immediately (should have different microseconds)
            job_id_2 = await scheduler_service.run_schedule_once(
                schedule_id, schedule_name
            )

            # Verify they're different (microseconds should make them unique)
            assert job_id_1 != job_id_2

            # Verify both jobs exist in scheduler
            job_1 = scheduler_service.scheduler.get_job(job_id_1)
            job_2 = scheduler_service.scheduler.get_job(job_id_2)
            assert job_1 is not None
            assert job_2 is not None

        finally:
            await scheduler_service.stop()

    async def test_schedule_service_run_schedule_manually_success(
        self,
        schedule_service: ScheduleService,
        test_schedule: Schedule,
        mock_scheduler_service: AsyncMock,
        test_db: AsyncSession,
    ) -> None:
        """Test ScheduleService.run_schedule_manually calls scheduler service correctly"""
        expected_job_id = uuid.uuid4()
        mock_scheduler_service.run_schedule_once.return_value = expected_job_id

        result = await schedule_service.run_schedule_manually(
            test_schedule.id, db=test_db
        )

        assert result.success is True
        assert result.job_details is not None
        assert result.job_details.get("job_id") == expected_job_id
        assert result.error_message is None

        # Verify scheduler service was called correctly
        mock_scheduler_service.run_schedule_once.assert_called_once_with(
            test_schedule.id, test_schedule.name
        )

    async def test_schedule_service_run_schedule_manually_not_found(
        self,
        schedule_service: ScheduleService,
        mock_scheduler_service: AsyncMock,
        test_db: AsyncSession,
    ) -> None:
        """Test ScheduleService.run_schedule_manually with non-existent schedule"""
        result = await schedule_service.run_schedule_manually(999, db=test_db)

        assert result.success is False
        assert result.job_details is not None
        assert result.job_details.get("job_id") is None
        assert result.error_message == "Schedule not found"

        # Verify scheduler service was not called
        mock_scheduler_service.run_schedule_once.assert_not_called()

    async def test_schedule_service_run_schedule_manually_scheduler_error(
        self,
        schedule_service: ScheduleService,
        test_schedule: Schedule,
        mock_scheduler_service: AsyncMock,
        test_db: AsyncSession,
    ) -> None:
        """Test ScheduleService.run_schedule_manually with scheduler service error"""
        mock_scheduler_service.run_schedule_once.side_effect = RuntimeError(
            "Scheduler not running"
        )

        result = await schedule_service.run_schedule_manually(
            test_schedule.id, db=test_db
        )

        assert result.success is False
        assert result.job_details is not None
        assert result.job_details.get("job_id") is None
        assert result.error_message is not None
        assert (
            "Failed to run schedule manually: Scheduler not running"
            in result.error_message
        )

        # Verify scheduler service was called
        mock_scheduler_service.run_schedule_once.assert_called_once_with(
            test_schedule.id, test_schedule.name
        )

    async def test_manual_run_api_endpoint_success(
        self,
        test_schedule: Schedule,
        mock_scheduler_service: AsyncMock,
        test_db: AsyncSession,
        async_client: AsyncClient
    ) -> None:
        """Test the API endpoint for manual run with APScheduler approach"""
        # Setup dependency override
        mock_scheduler_service = AsyncMock()
        expected_job_id = uuid.uuid4()
        mock_scheduler_service.run_schedule_once.return_value = expected_job_id

        schedule_service = ScheduleService(mock_scheduler_service)
        app.dependency_overrides[get_schedule_service] = lambda: schedule_service

        try:
            response = await async_client.post(f"/api/schedules/{test_schedule.id}/run")

            assert response.status_code == 200
            assert "Test Schedule" in response.text

            # Verify scheduler service was called
            mock_scheduler_service.run_schedule_once.assert_called_once_with(
                test_schedule.id, test_schedule.name
            )
        finally:
            app.dependency_overrides.clear()

    async def test_manual_run_api_endpoint_scheduler_error(
        self,
        test_schedule: Schedule,
        mock_scheduler_service: AsyncMock,
        test_db: AsyncSession,
        async_client: AsyncClient
    ) -> None:
        """Test the API endpoint with scheduler service error"""
        # Setup dependency override
        mock_scheduler_service = AsyncMock()
        mock_scheduler_service.run_schedule_once.side_effect = RuntimeError(
            "Scheduler not running"
        )

        schedule_service = ScheduleService(mock_scheduler_service)
        app.dependency_overrides[get_schedule_service] = lambda: schedule_service

        try:
            response = await async_client.post(f"/api/schedules/{test_schedule.id}/run")

            assert response.status_code == 500
            assert (
                "Failed to run schedule manually: Scheduler not running"
                in response.text
            )
        finally:
            app.dependency_overrides.clear()

    async def test_scheduler_service_job_execution_flow(
        self, scheduler_service: SchedulerService
    ) -> None:
        """Test that one-time jobs are properly configured for immediate execution"""
        await scheduler_service.start()

        try:
            schedule_id = 123
            schedule_name = "Test Schedule"

            # Create the job first
            job_id = await scheduler_service.run_schedule_once(
                schedule_id, schedule_name
            )

            # Get the job from scheduler
            job = scheduler_service.scheduler.get_job(job_id)
            assert job is not None

            assert len(job.args) == 1
            assert job.args[0] == schedule_id
            assert job.name == f"Manual run: {schedule_name}"
            assert job.max_instances == 1
            assert job.misfire_grace_time == 60

            # Verify the job has a DateTrigger (one-time execution)
            from apscheduler.triggers.date import DateTrigger

            assert isinstance(job.trigger, DateTrigger)

            # The run_date should be very close to now (within a few seconds)
            from borgitory.utils.datetime_utils import now_utc

            assert job.trigger.run_date is not None
            time_diff = abs((job.trigger.run_date - now_utc()).total_seconds())
            assert time_diff < 5  # Should be within 5 seconds of now

        finally:
            await scheduler_service.stop()

    async def test_scheduler_service_job_cleanup(
        self, scheduler_service: SchedulerService
    ) -> None:
        """Test that one-time jobs are cleaned up after execution"""
        await scheduler_service.start()

        try:
            schedule_id = 123
            schedule_name = "Test Schedule"

            # Create the job
            job_id = await scheduler_service.run_schedule_once(
                schedule_id, schedule_name
            )

            # Job should exist initially
            job = scheduler_service.scheduler.get_job(job_id)
            assert job is not None

            # Verify job configuration is set up for proper cleanup
            assert job.max_instances == 1  # Only one instance allowed

            # Verify it's a one-time job (DateTrigger)
            from apscheduler.triggers.date import DateTrigger

            assert isinstance(job.trigger, DateTrigger)

            # One-time jobs should not have a next run time after execution
            # (APScheduler automatically removes them)
            assert job.trigger.run_date is not None

        finally:
            await scheduler_service.stop()

    async def test_scheduler_service_with_mock_dependencies(self) -> None:
        """Test scheduler service with properly mocked dependencies"""
        # Create a mock job manager that tracks calls
        mock_job_manager = Mock(spec=JobManagerProtocol)
        test_job_id = uuid.uuid4()
        mock_job_manager.create_composite_job.return_value = test_job_id

        # Create a mock job service factory
        mock_job_service = Mock()
        mock_job_service.create_backup_job = AsyncMock(
            return_value={"job_id": test_job_id}
        )
        mock_job_service_factory = Mock(return_value=mock_job_service)

        # Create scheduler service with mocked dependencies and in-memory job store
        scheduler_service = create_test_scheduler_service(
            mock_job_manager, mock_job_service_factory
        )

        await scheduler_service.start()

        try:
            schedule_id = 456
            schedule_name = "Mock Test Schedule"

            # Create the job
            job_id = await scheduler_service.run_schedule_once(
                schedule_id, schedule_name
            )

            # Verify job was created in scheduler
            job = scheduler_service.scheduler.get_job(job_id)
            assert job is not None
            assert job.name == f"Manual run: {schedule_name}"
            # args should be (schedule_id, job_service) - two arguments
            assert len(job.args) == 1
            assert job.args[0] == schedule_id

            assert isinstance(job.trigger, DateTrigger)
            assert job.func == execute_scheduled_backup

        finally:
            await scheduler_service.stop()

    def test_scheduler_singleton_injects_resolved_job_manager_not_depends(self) -> None:
        """Singleton path must build JobService with resolved job_manager, not get_job_service().

        If the singleton called get_job_service(), job_manager would be a Depends object
        when called outside FastAPI, causing AttributeError on create_composite_job.
        """
        scheduler = get_scheduler_service_singleton()
        job_manager = scheduler.job_service.job_manager

        assert hasattr(job_manager, "create_composite_job"), (
            "job_manager must be a resolved JobManager with create_composite_job; "
            "if it were from get_job_service() called directly, it would be a Depends object."
        )
        assert callable(job_manager.create_composite_job)


class TestExecuteScheduledBackup:
    """Tests for execute_scheduled_backup() behavior (DB lookup, last_run, job creation)."""

    @pytest.fixture
    def mock_schedule(self) -> Mock:
        schedule = Mock(spec=Schedule)
        schedule.id = 1
        schedule.name = "Test Schedule"
        schedule.repository_id = 10
        schedule.source_path = "/data/backup"
        schedule.cloud_sync_config_id = None
        schedule.prune_config_id = 2
        schedule.check_config_id = 3
        schedule.notification_config_id = None
        schedule.pre_job_hooks = None
        schedule.post_job_hooks = None
        schedule.patterns = None
        schedule.last_run = None
        return schedule

    @pytest.fixture
    def mock_repository(self) -> Mock:
        repo = Mock()
        repo.id = 10
        repo.name = "test_repo"
        return repo

    def _make_mock_db_session(
        self,
        schedule_or_none: Mock | None,
    ) -> Mock:
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = schedule_or_none
        mock_db = Mock()
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_db.commit = AsyncMock()
        mock_db.__aenter__ = AsyncMock(return_value=mock_db)
        mock_db.__aexit__ = AsyncMock(return_value=None)
        return mock_db

    @pytest.mark.asyncio
    async def test_execute_scheduled_backup_success(
        self,
        mock_schedule: Mock,
        mock_repository: Mock,
    ) -> None:
        mock_schedule.repository = mock_repository
        mock_db = self._make_mock_db_session(mock_schedule)
        job_id = uuid.uuid4()
        mock_job_service = Mock()
        mock_job_service.create_backup_job = AsyncMock(
            return_value=JobCreationResult(job_id=job_id, status="started")
        )
        mock_scheduler = Mock()
        mock_scheduler.job_service = mock_job_service

        with (
            patch(
                "borgitory.dependencies.get_scheduler_service_singleton",
                return_value=mock_scheduler,
            ),
            patch(
                "borgitory.models.database.async_session_maker",
            ) as mock_session_maker,
            patch(
                "borgitory.services.scheduling.scheduler_service.now_utc",
            ) as mock_now_utc,
        ):
            from datetime import datetime, UTC

            fixed_now = datetime.now(UTC)
            mock_now_utc.return_value = fixed_now
            mock_session_maker.return_value = mock_db

            await execute_scheduled_backup(1)

        assert mock_schedule.last_run == fixed_now
        mock_db.commit.assert_called_once()
        mock_job_service.create_backup_job.assert_called_once()
        call_args = mock_job_service.create_backup_job.call_args
        assert call_args.args[0] is mock_db
        backup_request = call_args.args[1]
        assert backup_request.repository_id == 10
        assert backup_request.source_path == "/data/backup"
        assert backup_request.prune_config_id == 2
        assert backup_request.check_config_id == 3
        assert call_args.args[2] == JobType.SCHEDULED_BACKUP

    @pytest.mark.asyncio
    async def test_execute_scheduled_backup_schedule_not_found(self) -> None:
        mock_db = self._make_mock_db_session(None)
        mock_job_service = Mock()
        mock_job_service.create_backup_job = AsyncMock()
        mock_scheduler = Mock()
        mock_scheduler.job_service = mock_job_service

        with (
            patch(
                "borgitory.dependencies.get_scheduler_service_singleton",
                return_value=mock_scheduler,
            ),
            patch(
                "borgitory.models.database.async_session_maker",
            ) as mock_session_maker,
        ):
            mock_session_maker.return_value = mock_db

            await execute_scheduled_backup(999)

        mock_job_service.create_backup_job.assert_not_called()

    @pytest.mark.asyncio
    async def test_execute_scheduled_backup_repository_not_found(
        self,
        mock_schedule: Mock,
    ) -> None:
        mock_schedule.repository = None
        mock_db = self._make_mock_db_session(mock_schedule)
        mock_job_service = Mock()
        mock_job_service.create_backup_job = AsyncMock()
        mock_scheduler = Mock()
        mock_scheduler.job_service = mock_job_service

        with (
            patch(
                "borgitory.dependencies.get_scheduler_service_singleton",
                return_value=mock_scheduler,
            ),
            patch(
                "borgitory.models.database.async_session_maker",
            ) as mock_session_maker,
        ):
            mock_session_maker.return_value = mock_db

            await execute_scheduled_backup(1)

        mock_job_service.create_backup_job.assert_not_called()

    @pytest.mark.asyncio
    async def test_execute_scheduled_backup_create_job_returns_error(
        self,
        mock_schedule: Mock,
        mock_repository: Mock,
    ) -> None:
        mock_schedule.repository = mock_repository
        mock_db = self._make_mock_db_session(mock_schedule)
        mock_job_service = Mock()
        error_result = Mock()
        error_result.error = "Backup creation failed"
        mock_job_service.create_backup_job = AsyncMock(return_value=error_result)
        mock_scheduler = Mock()
        mock_scheduler.job_service = mock_job_service

        with (
            patch(
                "borgitory.dependencies.get_scheduler_service_singleton",
                return_value=mock_scheduler,
            ),
            patch(
                "borgitory.models.database.async_session_maker",
            ) as mock_session_maker,
        ):
            mock_session_maker.return_value = mock_db

            await execute_scheduled_backup(1)

        mock_job_service.create_backup_job.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_scheduled_backup_create_job_raises(
        self,
        mock_schedule: Mock,
        mock_repository: Mock,
    ) -> None:
        mock_schedule.repository = mock_repository
        mock_db = self._make_mock_db_session(mock_schedule)
        mock_job_service = Mock()
        mock_job_service.create_backup_job = AsyncMock(
            side_effect=RuntimeError("DB error")
        )
        mock_scheduler = Mock()
        mock_scheduler.job_service = mock_job_service

        with (
            patch(
                "borgitory.dependencies.get_scheduler_service_singleton",
                return_value=mock_scheduler,
            ),
            patch(
                "borgitory.models.database.async_session_maker",
            ) as mock_session_maker,
        ):
            mock_session_maker.return_value = mock_db

            with pytest.raises(RuntimeError, match="DB error"):
                await execute_scheduled_backup(1)
