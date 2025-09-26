"""
Tests for manual schedule run functionality using APScheduler one-time jobs.
"""

import pytest
import uuid
from unittest.mock import Mock, AsyncMock
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from borgitory.main import app
from borgitory.models.database import Schedule, Repository
from borgitory.services.scheduling.schedule_service import ScheduleService
from borgitory.services.scheduling.scheduler_service import SchedulerService
from borgitory.dependencies import get_schedule_service
from borgitory.protocols.job_protocols import JobManagerProtocol

client = TestClient(app)


def create_test_scheduler_service(
    job_manager: Mock, job_service_factory: Mock
) -> SchedulerService:
    """Create a scheduler service with in-memory job store for testing"""
    scheduler_service = SchedulerService(job_manager, job_service_factory)

    # Override to use in-memory job store to avoid CI database issues
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    from apscheduler.jobstores.memory import MemoryJobStore
    from apscheduler.executors.asyncio import AsyncIOExecutor

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
    def schedule_service(
        self, test_db: Session, mock_scheduler_service: AsyncMock
    ) -> ScheduleService:
        """Create schedule service with mocked scheduler service"""
        return ScheduleService(test_db, mock_scheduler_service)

    @pytest.fixture
    def test_repository(self, test_db: Session) -> Repository:
        """Create test repository"""
        repo = Repository()
        repo.name = "test_repo"
        repo.path = "/test/path"
        repo.set_passphrase("test_pass")
        test_db.add(repo)
        test_db.commit()
        test_db.refresh(repo)
        return repo

    @pytest.fixture
    def test_schedule(self, test_db: Session, test_repository: Repository) -> Schedule:
        """Create test schedule"""
        schedule = Schedule()
        schedule.name = "Test Schedule"
        schedule.repository_id = test_repository.id
        schedule.cron_expression = "0 2 * * *"
        schedule.source_path = "/test/source"
        schedule.enabled = True
        test_db.add(schedule)
        test_db.commit()
        test_db.refresh(schedule)
        return schedule

    @pytest.mark.asyncio
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

    @pytest.mark.asyncio
    async def test_scheduler_service_run_schedule_once_scheduler_not_running(
        self, scheduler_service: SchedulerService
    ) -> None:
        """Test SchedulerService.run_schedule_once fails when scheduler not running"""
        schedule_id = 123
        schedule_name = "Test Schedule"

        # Don't start the scheduler
        with pytest.raises(RuntimeError, match="Scheduler is not running"):
            await scheduler_service.run_schedule_once(schedule_id, schedule_name)

    @pytest.mark.asyncio
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

    @pytest.mark.asyncio
    async def test_schedule_service_run_schedule_manually_success(
        self,
        schedule_service: ScheduleService,
        test_schedule: Schedule,
        mock_scheduler_service: AsyncMock,
    ) -> None:
        """Test ScheduleService.run_schedule_manually calls scheduler service correctly"""
        expected_job_id = str(uuid.uuid4())
        mock_scheduler_service.run_schedule_once.return_value = expected_job_id

        success, job_id, error_msg = await schedule_service.run_schedule_manually(
            test_schedule.id
        )

        assert success is True
        assert job_id == expected_job_id
        assert error_msg is None

        # Verify scheduler service was called correctly
        mock_scheduler_service.run_schedule_once.assert_called_once_with(
            test_schedule.id, test_schedule.name
        )

    @pytest.mark.asyncio
    async def test_schedule_service_run_schedule_manually_not_found(
        self, schedule_service: ScheduleService, mock_scheduler_service: AsyncMock
    ) -> None:
        """Test ScheduleService.run_schedule_manually with non-existent schedule"""
        success, job_id, error_msg = await schedule_service.run_schedule_manually(999)

        assert success is False
        assert job_id is None
        assert error_msg == "Schedule not found"

        # Verify scheduler service was not called
        mock_scheduler_service.run_schedule_once.assert_not_called()

    @pytest.mark.asyncio
    async def test_schedule_service_run_schedule_manually_scheduler_error(
        self,
        schedule_service: ScheduleService,
        test_schedule: Schedule,
        mock_scheduler_service: AsyncMock,
    ) -> None:
        """Test ScheduleService.run_schedule_manually with scheduler service error"""
        mock_scheduler_service.run_schedule_once.side_effect = RuntimeError(
            "Scheduler not running"
        )

        success, job_id, error_msg = await schedule_service.run_schedule_manually(
            test_schedule.id
        )

        assert success is False
        assert job_id is None
        assert error_msg is not None
        assert "Failed to run schedule manually: Scheduler not running" in error_msg

        # Verify scheduler service was called
        mock_scheduler_service.run_schedule_once.assert_called_once_with(
            test_schedule.id, test_schedule.name
        )

    def test_manual_run_api_endpoint_success(
        self, test_db: Session, test_schedule: Schedule
    ) -> None:
        """Test the API endpoint for manual run with APScheduler approach"""
        # Setup dependency override
        mock_scheduler_service = AsyncMock()
        expected_job_id = str(uuid.uuid4())
        mock_scheduler_service.run_schedule_once.return_value = expected_job_id

        schedule_service = ScheduleService(test_db, mock_scheduler_service)
        app.dependency_overrides[get_schedule_service] = lambda: schedule_service

        try:
            response = client.post(f"/api/schedules/{test_schedule.id}/run")

            assert response.status_code == 200
            assert "Test Schedule" in response.text

            # Verify scheduler service was called
            mock_scheduler_service.run_schedule_once.assert_called_once_with(
                test_schedule.id, test_schedule.name
            )
        finally:
            app.dependency_overrides.clear()

    def test_manual_run_api_endpoint_scheduler_error(
        self, test_db: Session, test_schedule: Schedule
    ) -> None:
        """Test the API endpoint with scheduler service error"""
        # Setup dependency override
        mock_scheduler_service = AsyncMock()
        mock_scheduler_service.run_schedule_once.side_effect = RuntimeError(
            "Scheduler not running"
        )

        schedule_service = ScheduleService(test_db, mock_scheduler_service)
        app.dependency_overrides[get_schedule_service] = lambda: schedule_service

        try:
            response = client.post(f"/api/schedules/{test_schedule.id}/run")

            assert response.status_code == 500
            assert (
                "Failed to run schedule manually: Scheduler not running"
                in response.text
            )
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
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

            # Verify job configuration
            assert job.args == (schedule_id,)
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

    @pytest.mark.asyncio
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

    @pytest.mark.asyncio
    async def test_scheduler_service_with_mock_dependencies(self) -> None:
        """Test scheduler service with properly mocked dependencies (no patching)"""
        # Create a mock job manager that tracks calls
        mock_job_manager = Mock(spec=JobManagerProtocol)
        mock_job_manager.create_composite_job = AsyncMock(return_value="test-job-123")

        # Create a mock job service factory
        mock_job_service = Mock()
        mock_job_service.create_backup_job = AsyncMock(
            return_value={"job_id": "test-job-123"}
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
            assert job.args == (schedule_id,)

            # Verify it's configured as a one-time job
            from apscheduler.triggers.date import DateTrigger

            assert isinstance(job.trigger, DateTrigger)

            # The job function should be execute_scheduled_backup
            from borgitory.services.scheduling.scheduler_service import (
                execute_scheduled_backup,
            )

            assert job.func == execute_scheduled_backup

        finally:
            await scheduler_service.stop()
