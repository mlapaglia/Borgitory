import pytest
from datetime import datetime
from unittest.mock import AsyncMock
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from borgitory.main import app
from borgitory.models.database import (
    Schedule,
    Repository,
    CloudSyncConfig,
    PruneConfig,
    NotificationConfig,
)
from borgitory.dependencies import (
    get_schedule_service,
    get_configuration_service,
    get_scheduler_service_dependency,
)
from borgitory.services.scheduling.schedule_service import ScheduleService
from borgitory.services.configuration_service import ConfigurationService
from borgitory.services.upcoming_backups_service import format_time_until
from borgitory.services.cron_description_service import CronDescriptionService

client = TestClient(app)


class TestSchedulesAPI:
    """Test the Schedules API endpoints - HTMX/HTTP behavior"""

    @pytest.fixture(scope="function")
    def setup_test_dependencies(self, test_db: Session):
        """Setup dependency overrides for each test."""
        # Create mock scheduler service
        mock_scheduler_service = AsyncMock()
        mock_scheduler_service.add_schedule.return_value = None
        mock_scheduler_service.update_schedule.return_value = None
        mock_scheduler_service.remove_schedule.return_value = None
        mock_scheduler_service.get_scheduled_jobs.return_value = []

        # Create real services with test database
        schedule_service = ScheduleService(test_db, mock_scheduler_service)
        configuration_service = ConfigurationService(test_db)

        # Override dependencies
        app.dependency_overrides[get_schedule_service] = lambda: schedule_service
        app.dependency_overrides[get_configuration_service] = (
            lambda: configuration_service
        )
        app.dependency_overrides[get_scheduler_service_dependency] = (
            lambda: mock_scheduler_service
        )

        yield {
            "schedule_service": schedule_service,
            "configuration_service": configuration_service,
            "scheduler_service": mock_scheduler_service,
        }

        # Clean up overrides after test
        app.dependency_overrides.clear()

    @pytest.fixture
    def sample_repository(self, test_db: Session) -> Repository:
        """Create a sample repository for testing."""
        repository = Repository()
        repository.name = "test-repo"
        repository.path = "/tmp/test-repo"
        repository.encrypted_passphrase = "test-encrypted-passphrase"
        test_db.add(repository)
        test_db.commit()
        test_db.refresh(repository)
        return repository

    def test_get_schedules_form(
        self, setup_test_dependencies, test_db, sample_repository
    ) -> None:
        """Test getting schedules form returns HTML template."""
        # Create some test configurations with required fields
        prune_config = PruneConfig()
        prune_config.name = "test-prune"
        prune_config.strategy = "simple"
        prune_config.keep_daily = 7
        prune_config.enabled = True
        import json

        cloud_config = CloudSyncConfig()
        cloud_config.name = "test-cloud"
        cloud_config.provider = "s3"
        cloud_config.provider_config = json.dumps(
            {
                "bucket_name": "test",
                "access_key": "test-access-key",
                "secret_key": "test-secret-key",
            }
        )
        cloud_config.enabled = True
        notification_config = NotificationConfig()
        notification_config.name = "test-notif"
        notification_config.provider = "pushover"
        notification_config.provider_config = (
            '{"user_key": "'
            + "u"
            + "x" * 29
            + '", "app_token": "'
            + "a"
            + "x" * 29
            + '"}'
        )
        notification_config.enabled = True

        test_db.add_all([prune_config, cloud_config, notification_config])
        test_db.commit()

        response = client.get("/api/schedules/form")

        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")
        # Verify it contains form elements
        assert "schedule" in response.text.lower() or "form" in response.text.lower()

    def test_create_schedule_success(
        self, setup_test_dependencies, test_db, sample_repository
    ) -> None:
        """Test successful schedule creation returns success template."""
        schedule_data = {
            "name": "Test Schedule",
            "repository_id": sample_repository.id,
            "cron_expression": "0 2 * * *",
            "source_path": "/data",
        }

        response = client.post("/api/schedules/", json=schedule_data)

        assert response.status_code == 200  # TemplateResponse returns 200 by default
        assert "text/html" in response.headers.get("content-type", "")
        # Verify HX-Trigger header for frontend updates
        assert "HX-Trigger" in response.headers
        assert "scheduleUpdate" in response.headers["HX-Trigger"]

        # Verify schedule was created in database
        created_schedule = (
            test_db.query(Schedule).filter(Schedule.name == "Test Schedule").first()
        )
        assert created_schedule is not None
        assert created_schedule.repository_id == sample_repository.id

    def test_create_schedule_repository_not_found(
        self, setup_test_dependencies, test_db
    ) -> None:
        """Test schedule creation with non-existent repository returns error template."""
        schedule_data = {
            "name": "Test Schedule",
            "repository_id": 999,  # Non-existent repository
            "cron_expression": "0 2 * * *",
            "source_path": "/data",
        }

        response = client.post("/api/schedules/", json=schedule_data)

        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")
        # Should contain error message
        assert "repository" in response.text.lower() or "error" in response.text.lower()

    def test_create_schedule_invalid_cron(
        self, setup_test_dependencies, test_db, sample_repository
    ) -> None:
        """Test schedule creation with invalid cron expression returns error template."""
        schedule_data = {
            "name": "Test Schedule",
            "repository_id": sample_repository.id,
            "cron_expression": "invalid cron",
            "source_path": "/data",
        }

        response = client.post("/api/schedules/", json=schedule_data)

        assert response.status_code == 200  # Returns error template
        assert "text/html" in response.headers.get("content-type", "")
        # Should contain error info
        assert "cron" in response.text.lower() or "error" in response.text.lower()

    def test_get_schedules_html(
        self, setup_test_dependencies, test_db, sample_repository
    ) -> None:
        """Test getting schedules as HTML."""
        # Create test schedules
        schedule1 = Schedule()
        schedule1.name = "schedule-1"
        schedule1.repository_id = sample_repository.id
        schedule1.cron_expression = "0 2 * * *"
        schedule1.source_path = "/data1"

        schedule2 = Schedule()
        schedule2.name = "schedule-2"
        schedule2.repository_id = sample_repository.id
        schedule2.cron_expression = "0 3 * * *"
        schedule2.source_path = "/data2"
        test_db.add_all([schedule1, schedule2])
        test_db.commit()

        response = client.get("/api/schedules/html")

        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")
        # Should contain schedule names
        response_text = response.text.lower()
        assert "schedule-1" in response_text or "schedule-2" in response_text

    def test_get_schedules_html_pagination(
        self, setup_test_dependencies, test_db, sample_repository
    ) -> None:
        """Test getting schedules with pagination parameters."""
        # Create multiple schedules
        for i in range(5):
            schedule = Schedule()
            schedule.name = f"schedule-{i}"
            schedule.repository_id = sample_repository.id
            schedule.cron_expression = "0 2 * * *"
            schedule.source_path = f"/data{i}"
            test_db.add(schedule)
        test_db.commit()

        response = client.get("/api/schedules/html?skip=2&limit=2")

        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")

    def test_get_upcoming_backups_html(self, setup_test_dependencies) -> None:
        """Test getting upcoming backups as HTML."""
        # Setup mock jobs with different datetime formats
        mock_jobs = [
            {
                "name": "Daily Backup",
                "next_run": "2023-12-01T02:00:00Z",
                "trigger": "cron[minute='0', hour='2', day='*', month='*', day_of_week='*']",
            },
            {
                "name": "Weekly Backup",
                "next_run": datetime(2023, 12, 1, 2, 0, 0),
                "trigger": "cron[minute='0', hour='2', day='*', month='*', day_of_week='0']",
            },
        ]
        setup_test_dependencies[
            "scheduler_service"
        ].get_scheduled_jobs.return_value = mock_jobs

        response = client.get("/api/schedules/upcoming/html")

        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")

    def test_get_upcoming_backups_html_error(self, setup_test_dependencies) -> None:
        """Test getting upcoming backups HTML with scheduler error."""
        setup_test_dependencies[
            "scheduler_service"
        ].get_scheduled_jobs.side_effect = Exception("Scheduler error")

        response = client.get("/api/schedules/upcoming/html")

        assert response.status_code == 200  # Should still return HTML error state
        assert "text/html" in response.headers.get("content-type", "")
        # Should contain error message
        assert "error" in response.text.lower()

    def test_get_cron_expression_form(self, setup_test_dependencies) -> None:
        """Test getting cron expression form."""
        response = client.get(
            "/api/schedules/cron-expression-form?preset=0%202%20*%20*%20*"
        )

        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")

    def test_list_schedules(
        self, setup_test_dependencies, test_db, sample_repository
    ) -> None:
        """Test listing schedules."""
        # Create test schedules
        schedule1 = Schedule()
        schedule1.name = "schedule-1"
        schedule1.repository_id = sample_repository.id
        schedule1.cron_expression = "0 2 * * *"
        schedule1.source_path = "/data1"
        test_db.add(schedule1)
        test_db.commit()

        response = client.get("/api/schedules/")

        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")

    @pytest.mark.skip(
        reason="Template path issues in test environment - service layer is tested separately"
    )
    def test_get_schedule_success(
        self, setup_test_dependencies, test_db, sample_repository
    ) -> None:
        """Test getting specific schedule successfully."""
        pass

    def test_get_schedule_not_found(self, setup_test_dependencies) -> None:
        """Test getting non-existent schedule."""
        response = client.get("/api/schedules/999")

        assert response.status_code == 200  # Returns HTML error template
        assert "text/html" in response.headers.get("content-type", "")
        assert "error" in response.text.lower() or "not found" in response.text.lower()

    def test_get_schedule_edit_form(
        self, setup_test_dependencies, test_db, sample_repository
    ) -> None:
        """Test getting schedule edit form."""
        schedule = Schedule()
        schedule.name = "test-schedule"
        schedule.repository_id = sample_repository.id
        schedule.cron_expression = "0 2 * * *"
        schedule.source_path = "/data"
        test_db.add(schedule)
        test_db.commit()
        test_db.refresh(schedule)

        response = client.get(f"/api/schedules/{schedule.id}/edit")

        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")
        # Should contain form elements for editing
        assert "form" in response.text.lower() or "edit" in response.text.lower()

    def test_update_schedule_success(
        self, setup_test_dependencies, test_db, sample_repository
    ) -> None:
        """Test successful schedule update."""
        schedule = Schedule()
        schedule.name = "original-schedule"
        schedule.repository_id = sample_repository.id
        schedule.cron_expression = "0 2 * * *"
        schedule.source_path = "/data"
        test_db.add(schedule)
        test_db.commit()
        test_db.refresh(schedule)

        update_data = {"name": "updated-schedule", "cron_expression": "0 3 * * *"}

        response = client.put(f"/api/schedules/{schedule.id}", json=update_data)

        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")
        assert "HX-Trigger" in response.headers

        # Verify update in database
        updated_schedule = (
            test_db.query(Schedule).filter(Schedule.id == schedule.id).first()
        )
        assert updated_schedule.name == "updated-schedule"
        assert updated_schedule.cron_expression == "0 3 * * *"

    def test_toggle_schedule_success(
        self, setup_test_dependencies, test_db, sample_repository
    ) -> None:
        """Test successfully toggling schedule."""
        schedule = Schedule()
        schedule.name = "test-schedule"
        schedule.repository_id = sample_repository.id
        schedule.cron_expression = "0 2 * * *"
        schedule.source_path = "/data"
        schedule.enabled = False
        test_db.add(schedule)
        test_db.commit()
        test_db.refresh(schedule)

        response = client.put(f"/api/schedules/{schedule.id}/toggle")

        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")

        # Verify toggle in database
        toggled_schedule = (
            test_db.query(Schedule).filter(Schedule.id == schedule.id).first()
        )
        assert toggled_schedule.enabled is True

    def test_toggle_schedule_not_found(self, setup_test_dependencies) -> None:
        """Test toggling non-existent schedule."""
        response = client.put("/api/schedules/999/toggle")

        assert response.status_code == 404
        assert "text/html" in response.headers.get("content-type", "")
        assert "error" in response.text.lower() or "not found" in response.text.lower()

    def test_delete_schedule_success(
        self, setup_test_dependencies, test_db, sample_repository
    ) -> None:
        """Test successfully deleting schedule."""
        schedule = Schedule()
        schedule.name = "test-schedule"
        schedule.repository_id = sample_repository.id
        schedule.cron_expression = "0 2 * * *"
        schedule.source_path = "/data"
        test_db.add(schedule)
        test_db.commit()
        test_db.refresh(schedule)
        schedule_id = schedule.id

        response = client.delete(f"/api/schedules/{schedule_id}")

        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")
        assert "HX-Trigger" in response.headers

        # Verify deletion from database
        deleted_schedule = (
            test_db.query(Schedule).filter(Schedule.id == schedule_id).first()
        )
        assert deleted_schedule is None

    def test_delete_schedule_not_found(self, setup_test_dependencies) -> None:
        """Test deleting non-existent schedule."""
        response = client.delete("/api/schedules/999")

        assert response.status_code == 404
        assert "text/html" in response.headers.get("content-type", "")
        assert "error" in response.text.lower() or "not found" in response.text.lower()

    @pytest.mark.skip(
        reason="Template missing in test environment - functionality tested in service layer"
    )
    def test_get_active_scheduled_jobs(self, setup_test_dependencies) -> None:
        """Test getting active scheduled jobs."""
        pass


class TestScheduleUtilityFunctions:
    """Test utility functions for schedule processing"""

    @pytest.fixture
    def cron_description_service(self) -> CronDescriptionService:
        """Provide CronDescriptionService instance for tests"""
        return CronDescriptionService()

    def test_format_cron_trigger_daily(self, cron_description_service) -> None:
        """Test formatting daily cron trigger"""
        trigger_str = "cron[minute='0', hour='14', day='*', month='*', day_of_week='*']"
        result = cron_description_service.format_cron_trigger(trigger_str)
        assert result == "At 14:00"

    def test_format_cron_trigger_weekly(self, cron_description_service) -> None:
        """Test formatting weekly cron trigger"""
        trigger_str = "cron[minute='0', hour='9', day='*', month='*', day_of_week='1']"
        result = cron_description_service.format_cron_trigger(trigger_str)
        assert result == "At 09:00, only on Monday"

    def test_format_cron_trigger_monthly(self, cron_description_service) -> None:
        """Test formatting monthly cron trigger"""
        trigger_str = "cron[minute='0', hour='2', day='15', month='*', day_of_week='*']"
        result = cron_description_service.format_cron_trigger(trigger_str)
        assert result == "At 02:00, on day 15 of the month"

    def test_format_cron_trigger_twice_monthly(self, cron_description_service) -> None:
        """Test formatting twice monthly cron trigger"""
        trigger_str = (
            "cron[minute='0', hour='2', day='1,15', month='*', day_of_week='*']"
        )
        result = cron_description_service.format_cron_trigger(trigger_str)
        assert result == "At 02:00, on day 1 and 15 of the month"

    def test_format_cron_trigger_every_n_days(self, cron_description_service) -> None:
        """Test formatting every N days cron trigger"""
        trigger_str = (
            "cron[minute='0', hour='2', day='*/3', month='*', day_of_week='*']"
        )
        result = cron_description_service.format_cron_trigger(trigger_str)
        assert result == "At 02:00, every 3 days"

    def test_format_cron_trigger_invalid(self, cron_description_service) -> None:
        """Test formatting invalid cron trigger"""
        trigger_str = "invalid trigger format"
        result = cron_description_service.format_cron_trigger(trigger_str)
        assert result == "invalid trigger format"

    def test_format_time_until_days(self) -> None:
        """Test formatting time until in days"""
        ms = 2 * 24 * 60 * 60 * 1000 + 3 * 60 * 60 * 1000  # 2 days 3 hours
        result = format_time_until(ms)
        assert result == "2d 3h"

    def test_format_time_until_hours(self) -> None:
        """Test formatting time until in hours"""
        ms = 5 * 60 * 60 * 1000 + 30 * 60 * 1000  # 5 hours 30 minutes
        result = format_time_until(ms)
        assert result == "5h 30m"

    def test_format_time_until_minutes(self) -> None:
        """Test formatting time until in minutes"""
        ms = 15 * 60 * 1000 + 45 * 1000  # 15 minutes 45 seconds
        result = format_time_until(ms)
        assert result == "15m 45s"

    def test_format_time_until_seconds(self) -> None:
        """Test formatting time until in seconds"""
        ms = 30 * 1000  # 30 seconds
        result = format_time_until(ms)
        assert result == "30s"

    def test_format_time_until_overdue(self) -> None:
        """Test formatting overdue time"""
        ms = -1000  # Negative time
        result = format_time_until(ms)
        assert result == "Overdue"
