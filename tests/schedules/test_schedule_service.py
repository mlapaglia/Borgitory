"""
Tests for ScheduleService - Business logic tests
"""

import pytest
from unittest.mock import AsyncMock

from sqlalchemy.orm import Session

from borgitory.services.scheduling.schedule_service import ScheduleService
from borgitory.models.database import Schedule, Repository


@pytest.fixture
def mock_scheduler_service() -> AsyncMock:
    """Mock scheduler service for testing."""
    mock = AsyncMock()
    mock.add_schedule.return_value = None
    mock.update_schedule.return_value = None
    mock.remove_schedule.return_value = None
    return mock


@pytest.fixture
def service(test_db: Session, mock_scheduler_service: AsyncMock) -> ScheduleService:
    """ScheduleService instance with real database session."""
    return ScheduleService(test_db, mock_scheduler_service)


@pytest.fixture
def sample_repository(test_db: Session) -> Repository:
    """Create a sample repository for testing."""
    repository = Repository(
        name="test-repo",
        path="/tmp/test-repo",
        encrypted_passphrase="test-encrypted-passphrase",
    )
    test_db.add(repository)
    test_db.commit()
    test_db.refresh(repository)
    return repository


class TestScheduleService:
    """Test class for ScheduleService business logic."""

    def test_validate_cron_expression_valid(self, service: ScheduleService) -> None:
        """Test valid cron expression validation."""
        is_valid, error = service.validate_cron_expression("0 2 * * *")
        assert is_valid is True
        assert error is None

    def test_validate_cron_expression_invalid(self, service: ScheduleService) -> None:
        """Test invalid cron expression validation."""
        is_valid, error = service.validate_cron_expression("invalid cron")
        assert is_valid is False
        assert error is not None
        assert "Invalid cron expression" in error

    def test_get_schedule_by_id_success(
        self, service: ScheduleService, test_db: Session, sample_repository: Repository
    ) -> None:
        """Test getting schedule by ID successfully."""
        schedule = Schedule(
            name="test-schedule",
            repository_id=sample_repository.id,
            cron_expression="0 2 * * *",
            source_path="/data",
        )
        test_db.add(schedule)
        test_db.commit()
        test_db.refresh(schedule)

        result = service.get_schedule_by_id(schedule.id)
        assert result is not None
        assert result.name == "test-schedule"
        assert result.id == schedule.id

    def test_get_schedule_by_id_not_found(self, service: ScheduleService) -> None:
        """Test getting non-existent schedule."""
        result = service.get_schedule_by_id(999)
        assert result is None

    def test_get_schedules_empty(self, service: ScheduleService) -> None:
        """Test getting schedules when none exist."""
        result = service.get_schedules()
        assert result == []

    def test_get_schedules_with_data(
        self, service: ScheduleService, test_db: Session, sample_repository: Repository
    ) -> None:
        """Test getting schedules with data."""
        schedule1 = Schedule(
            name="schedule-1",
            repository_id=sample_repository.id,
            cron_expression="0 2 * * *",
            source_path="/data1",
        )
        schedule2 = Schedule(
            name="schedule-2",
            repository_id=sample_repository.id,
            cron_expression="0 3 * * *",
            source_path="/data2",
        )
        test_db.add(schedule1)
        test_db.add(schedule2)
        test_db.commit()

        result = service.get_schedules()
        assert len(result) == 2
        names = [s.name for s in result]
        assert "schedule-1" in names
        assert "schedule-2" in names

    def test_get_schedules_with_pagination(
        self, service: ScheduleService, test_db: Session, sample_repository: Repository
    ) -> None:
        """Test getting schedules with pagination."""
        for i in range(5):
            schedule = Schedule(
                name=f"schedule-{i}",
                repository_id=sample_repository.id,
                cron_expression="0 2 * * *",
                source_path=f"/data{i}",
            )
            test_db.add(schedule)
        test_db.commit()

        result = service.get_schedules(skip=2, limit=2)
        assert len(result) == 2

    def test_get_all_schedules(
        self, service: ScheduleService, test_db: Session, sample_repository: Repository
    ) -> None:
        """Test getting all schedules."""
        schedule = Schedule(
            name="test-schedule",
            repository_id=sample_repository.id,
            cron_expression="0 2 * * *",
            source_path="/data",
        )
        test_db.add(schedule)
        test_db.commit()

        result = service.get_all_schedules()
        assert len(result) == 1
        assert result[0].name == "test-schedule"

    @pytest.mark.asyncio
    async def test_create_schedule_success(
        self,
        service: ScheduleService,
        test_db: Session,
        sample_repository: Repository,
        mock_scheduler_service: AsyncMock,
    ) -> None:
        """Test successful schedule creation."""
        success, schedule, error = await service.create_schedule(
            name="new-schedule",
            repository_id=sample_repository.id,
            cron_expression="0 2 * * *",
            source_path="/backup",
        )

        assert success is True
        assert error is None
        assert schedule is not None
        assert schedule.name == "new-schedule"
        assert schedule.repository_id == sample_repository.id
        assert schedule.enabled is True

        # Verify saved to database
        saved_schedule = (
            test_db.query(Schedule).filter(Schedule.name == "new-schedule").first()
        )
        assert saved_schedule is not None
        assert saved_schedule.cron_expression == "0 2 * * *"

        # Verify scheduler was called
        mock_scheduler_service.add_schedule.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_schedule_repository_not_found(
        self, service: ScheduleService
    ) -> None:
        """Test schedule creation with non-existent repository."""
        success, schedule, error = await service.create_schedule(
            name="test-schedule",
            repository_id=999,
            cron_expression="0 2 * * *",
            source_path="/data",
        )

        assert success is False
        assert schedule is None
        assert error is not None
        assert "Repository not found" in error

    @pytest.mark.asyncio
    async def test_create_schedule_invalid_cron(
        self, service: ScheduleService, sample_repository: Repository
    ) -> None:
        """Test schedule creation with invalid cron expression."""
        success, schedule, error = await service.create_schedule(
            name="test-schedule",
            repository_id=sample_repository.id,
            cron_expression="invalid cron",
            source_path="/data",
        )

        assert success is False
        assert schedule is None
        assert error is not None
        assert "Invalid cron expression" in error

    @pytest.mark.asyncio
    async def test_create_schedule_scheduler_failure(
        self,
        service: ScheduleService,
        test_db: Session,
        sample_repository: Repository,
        mock_scheduler_service: AsyncMock,
    ) -> None:
        """Test schedule creation when scheduler fails."""
        mock_scheduler_service.add_schedule.side_effect = Exception("Scheduler error")

        success, schedule, error = await service.create_schedule(
            name="test-schedule",
            repository_id=sample_repository.id,
            cron_expression="0 2 * * *",
            source_path="/data",
        )

        assert success is False
        assert schedule is None
        assert error is not None
        assert "Failed to schedule job" in error

        # Verify database rollback - schedule should not exist
        saved_schedule = (
            test_db.query(Schedule).filter(Schedule.name == "test-schedule").first()
        )
        assert saved_schedule is None

    @pytest.mark.asyncio
    async def test_update_schedule_success(
        self,
        service: ScheduleService,
        test_db: Session,
        sample_repository: Repository,
        mock_scheduler_service: AsyncMock,
    ) -> None:
        """Test successful schedule update."""
        # Create initial schedule
        schedule = Schedule(
            name="original-name",
            repository_id=sample_repository.id,
            cron_expression="0 2 * * *",
            source_path="/data",
            enabled=True,
        )
        test_db.add(schedule)
        test_db.commit()
        test_db.refresh(schedule)

        update_data = {"name": "updated-name", "cron_expression": "0 3 * * *"}

        success, updated_schedule, error = await service.update_schedule(
            schedule.id, update_data
        )

        assert success is True
        assert error is None
        assert updated_schedule is not None
        assert updated_schedule.name == "updated-name"
        assert updated_schedule.cron_expression == "0 3 * * *"

        # Verify scheduler was updated
        mock_scheduler_service.update_schedule.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_schedule_not_found(self, service: ScheduleService) -> None:
        """Test updating non-existent schedule."""
        success, schedule, error = await service.update_schedule(
            999, {"name": "new-name"}
        )

        assert success is False
        assert schedule is None
        assert error is not None
        assert "Schedule not found" in error

    @pytest.mark.asyncio
    async def test_toggle_schedule_enable(
        self,
        service: ScheduleService,
        test_db: Session,
        sample_repository: Repository,
        mock_scheduler_service: AsyncMock,
    ) -> None:
        """Test enabling a disabled schedule."""
        schedule = Schedule(
            name="test-schedule",
            repository_id=sample_repository.id,
            cron_expression="0 2 * * *",
            source_path="/data",
            enabled=False,
        )
        test_db.add(schedule)
        test_db.commit()
        test_db.refresh(schedule)

        success, updated_schedule, error = await service.toggle_schedule(schedule.id)

        assert success is True
        assert error is None
        assert updated_schedule is not None
        assert updated_schedule.enabled is True

        # Verify scheduler was updated
        mock_scheduler_service.update_schedule.assert_called_once()

    @pytest.mark.asyncio
    async def test_toggle_schedule_disable(
        self,
        service: ScheduleService,
        test_db: Session,
        sample_repository: Repository,
        mock_scheduler_service: AsyncMock,
    ) -> None:
        """Test disabling an enabled schedule."""
        schedule = Schedule(
            name="test-schedule",
            repository_id=sample_repository.id,
            cron_expression="0 2 * * *",
            source_path="/data",
            enabled=True,
        )
        test_db.add(schedule)
        test_db.commit()
        test_db.refresh(schedule)

        success, updated_schedule, error = await service.toggle_schedule(schedule.id)

        assert success is True
        assert error is None
        assert updated_schedule is not None
        assert updated_schedule.enabled is False

        # Verify scheduler was updated
        mock_scheduler_service.update_schedule.assert_called_once()

    @pytest.mark.asyncio
    async def test_toggle_schedule_not_found(self, service: ScheduleService) -> None:
        """Test toggling non-existent schedule."""
        success, schedule, error = await service.toggle_schedule(999)

        assert success is False
        assert schedule is None
        assert error is not None
        assert "Schedule not found" in error

    @pytest.mark.asyncio
    async def test_toggle_schedule_scheduler_error(
        self,
        service: ScheduleService,
        test_db: Session,
        sample_repository: Repository,
        mock_scheduler_service: AsyncMock,
    ) -> None:
        """Test toggle schedule when scheduler fails."""
        schedule = Schedule(
            name="test-schedule",
            repository_id=sample_repository.id,
            cron_expression="0 2 * * *",
            source_path="/data",
            enabled=False,
        )
        test_db.add(schedule)
        test_db.commit()
        test_db.refresh(schedule)

        mock_scheduler_service.update_schedule.side_effect = Exception(
            "Scheduler error"
        )

        success, updated_schedule, error = await service.toggle_schedule(schedule.id)

        assert success is False
        assert updated_schedule is None
        assert error is not None
        assert "Failed to update schedule" in error

    @pytest.mark.asyncio
    async def test_delete_schedule_success(
        self,
        service: ScheduleService,
        test_db: Session,
        sample_repository: Repository,
        mock_scheduler_service: AsyncMock,
    ) -> None:
        """Test successful schedule deletion."""
        schedule = Schedule(
            name="test-schedule",
            repository_id=sample_repository.id,
            cron_expression="0 2 * * *",
            source_path="/data",
        )
        test_db.add(schedule)
        test_db.commit()
        test_db.refresh(schedule)
        schedule_id = schedule.id

        success, schedule_name, error = await service.delete_schedule(schedule_id)

        assert success is True
        assert schedule_name == "test-schedule"
        assert error is None

        # Verify removed from database
        deleted_schedule = (
            test_db.query(Schedule).filter(Schedule.id == schedule_id).first()
        )
        assert deleted_schedule is None

        # Verify scheduler was called
        mock_scheduler_service.remove_schedule.assert_called_once_with(schedule_id)

    @pytest.mark.asyncio
    async def test_delete_schedule_not_found(self, service: ScheduleService) -> None:
        """Test deleting non-existent schedule."""
        success, schedule_name, error = await service.delete_schedule(999)

        assert success is False
        assert schedule_name is None
        assert error is not None
        assert "Schedule not found" in error

    @pytest.mark.asyncio
    async def test_delete_schedule_scheduler_error(
        self,
        service: ScheduleService,
        test_db: Session,
        sample_repository: Repository,
        mock_scheduler_service: AsyncMock,
    ) -> None:
        """Test delete schedule when scheduler fails."""
        schedule = Schedule(
            name="test-schedule",
            repository_id=sample_repository.id,
            cron_expression="0 2 * * *",
            source_path="/data",
        )
        test_db.add(schedule)
        test_db.commit()
        test_db.refresh(schedule)

        mock_scheduler_service.remove_schedule.side_effect = Exception(
            "Scheduler error"
        )

        success, schedule_name, error = await service.delete_schedule(schedule.id)

        assert success is False
        assert schedule_name is None
        assert error is not None
        assert "Failed to remove schedule from scheduler" in error

    @pytest.mark.asyncio
    async def test_schedule_lifecycle(
        self,
        service: ScheduleService,
        test_db: Session,
        sample_repository: Repository,
        mock_scheduler_service: AsyncMock,
    ) -> None:
        """Test complete schedule lifecycle: create, update, toggle, delete."""
        # Create
        success, created_schedule, error = await service.create_schedule(
            name="lifecycle-test",
            repository_id=sample_repository.id,
            cron_expression="0 2 * * *",
            source_path="/data",
        )
        assert success is True
        assert created_schedule is not None
        schedule_id = created_schedule.id

        # Update
        success, updated_schedule, error = await service.update_schedule(
            schedule_id, {"cron_expression": "0 3 * * *"}
        )
        assert success is True
        assert updated_schedule is not None
        assert updated_schedule.cron_expression == "0 3 * * *"

        # Toggle (disable)
        success, toggled_schedule, error = await service.toggle_schedule(schedule_id)
        assert success is True
        assert toggled_schedule is not None
        assert toggled_schedule.enabled is False

        # Toggle (enable)
        success, toggled_schedule, error = await service.toggle_schedule(schedule_id)
        assert success is True
        assert toggled_schedule is not None
        assert toggled_schedule.enabled is True

        # Delete
        success, schedule_name, error = await service.delete_schedule(schedule_id)
        assert success is True
        assert schedule_name == "lifecycle-test"

        # Verify completely removed
        deleted_schedule = (
            test_db.query(Schedule).filter(Schedule.id == schedule_id).first()
        )
        assert deleted_schedule is None
