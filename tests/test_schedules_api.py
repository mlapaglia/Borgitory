import pytest
from datetime import datetime
from unittest.mock import Mock, AsyncMock, patch
from fastapi import HTTPException

from app.api.schedules import (
    get_schedules_form,
    create_schedule,
    get_schedules_html,
    get_upcoming_backups_html,
    get_cron_expression_form,
    list_schedules,
    get_schedule,
    toggle_schedule,
    delete_schedule,
    get_active_scheduled_jobs,
    format_cron_trigger,
    format_hour,
    get_day_name,
    format_time_until,
)


class TestSchedulesAPI:
    """Test the Schedules API endpoints"""

    @pytest.fixture
    def mock_db(self):
        """Mock database session"""
        return Mock()

    @pytest.fixture
    def mock_scheduler_service(self):
        """Mock scheduler service"""
        return AsyncMock()

    @pytest.fixture
    def mock_request(self):
        """Mock FastAPI request"""
        request = Mock()
        request.headers = {}
        return request

    @pytest.mark.asyncio
    async def test_get_schedules_form(self, mock_request, mock_db):
        """Test getting schedules form"""
        # Setup mock database queries
        mock_repositories = [Mock(name="repo1"), Mock(name="repo2")]
        mock_cleanup_configs = [Mock(name="cleanup1")]
        mock_cloud_sync_configs = [Mock(name="cloud1")]
        mock_notification_configs = [Mock(name="notif1")]
        mock_check_configs = [Mock(name="check1")]

        # Setup query chains
        mock_db.query.return_value.all.return_value = mock_repositories
        mock_db.query.return_value.filter.return_value.all.side_effect = [
            mock_cleanup_configs,
            mock_cloud_sync_configs,
            mock_notification_configs,
            mock_check_configs,
        ]

        with patch("app.api.schedules.templates") as mock_templates:
            mock_templates.TemplateResponse.return_value = "form_template"

            # Execute
            result = await get_schedules_form(mock_request, mock_db)

            # Verify
            assert result == "form_template"
            mock_templates.TemplateResponse.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_schedule_success_htmx(self, mock_request, mock_db, mock_scheduler_service):
        """Test successful schedule creation with HTMX request"""
        # Setup
        mock_request.headers = {"hx-request": "true"}
        schedule_data = Mock()
        schedule_data.name = "Test Schedule"
        schedule_data.repository_id = 1
        schedule_data.cron_expression = "0 2 * * *"
        schedule_data.source_path = "/data"
        schedule_data.cloud_sync_config_id = None
        schedule_data.cleanup_config_id = None
        schedule_data.notification_config_id = None

        # Mock repository query
        mock_repository = Mock()
        mock_db.query.return_value.filter.return_value.first.return_value = mock_repository

        # Mock database operations
        mock_db_schedule = Mock()
        mock_db_schedule.id = 123
        mock_db_schedule.name = "Test Schedule"
        mock_db_schedule.cron_expression = "0 2 * * *"
        mock_db.refresh.return_value = None

        with patch("app.api.schedules.Schedule") as mock_schedule_class:
            mock_schedule_class.return_value = mock_db_schedule
            with patch("app.api.schedules.scheduler_service", mock_scheduler_service):
                mock_scheduler_service.add_schedule.return_value = None
                with patch("app.api.schedules.templates") as mock_templates:
                    mock_templates.TemplateResponse.return_value = Mock(headers={})

                    # Execute
                    await create_schedule(mock_request, schedule_data, mock_db)

                    # Verify
                    mock_db.add.assert_called_once()
                    mock_db.commit.assert_called()
                    mock_scheduler_service.add_schedule.assert_called_once_with(123, "Test Schedule", "0 2 * * *")

    @pytest.mark.asyncio
    async def test_create_schedule_success_non_htmx(self, mock_request, mock_db, mock_scheduler_service):
        """Test successful schedule creation with non-HTMX request"""
        # Setup
        mock_request.headers = {}
        schedule_data = Mock()
        schedule_data.name = "Test Schedule"
        schedule_data.repository_id = 1
        schedule_data.cron_expression = "0 2 * * *"
        schedule_data.source_path = "/data"
        schedule_data.cloud_sync_config_id = None
        schedule_data.cleanup_config_id = None
        schedule_data.notification_config_id = None

        # Mock repository query
        mock_repository = Mock()
        mock_db.query.return_value.filter.return_value.first.return_value = mock_repository

        # Mock database operations
        mock_db_schedule = Mock()
        mock_db_schedule.id = 123
        mock_db_schedule.name = "Test Schedule"
        mock_db_schedule.cron_expression = "0 2 * * *"  # Ensure this is set

        with patch("app.api.schedules.Schedule") as mock_schedule_class:
            mock_schedule_class.return_value = mock_db_schedule
            with patch("app.api.schedules.scheduler_service", mock_scheduler_service):
                mock_scheduler_service.add_schedule.return_value = None

                # Execute
                result = await create_schedule(mock_request, schedule_data, mock_db)

                # Verify
                assert result == mock_db_schedule
                mock_scheduler_service.add_schedule.assert_called_once_with(123, "Test Schedule", "0 2 * * *")

    @pytest.mark.asyncio
    async def test_create_schedule_repository_not_found(self, mock_request, mock_db):
        """Test schedule creation when repository not found"""
        # Setup
        mock_request.headers = {"hx-request": "true"}
        schedule_data = Mock()
        schedule_data.repository_id = 999

        # Mock repository query to return None
        mock_db.query.return_value.filter.return_value.first.return_value = None

        with patch("app.api.schedules.templates") as mock_templates:
            mock_templates.TemplateResponse.return_value = "error_template"

            # Execute
            result = await create_schedule(mock_request, schedule_data, mock_db)

            # Verify
            assert result == "error_template"

    @pytest.mark.asyncio
    async def test_create_schedule_invalid_cron(self, mock_request, mock_db):
        """Test schedule creation with invalid cron expression"""
        # Setup
        mock_request.headers = {"hx-request": "true"}
        schedule_data = Mock()
        schedule_data.repository_id = 1
        schedule_data.cron_expression = "invalid cron"

        # Mock repository query
        mock_repository = Mock()
        mock_db.query.return_value.filter.return_value.first.return_value = mock_repository

        with patch("app.api.schedules.templates") as mock_templates:
            mock_templates.TemplateResponse.return_value = "error_template"
            with patch("apscheduler.triggers.cron.CronTrigger") as mock_cron:
                mock_cron.from_crontab.side_effect = ValueError("Invalid cron expression")

                # Execute
                result = await create_schedule(mock_request, schedule_data, mock_db)

                # Verify
                assert result == "error_template"

    @pytest.mark.asyncio
    async def test_create_schedule_scheduler_failure(self, mock_request, mock_db, mock_scheduler_service):
        """Test schedule creation when scheduler service fails"""
        # Setup
        mock_request.headers = {"hx-request": "true"}
        schedule_data = Mock()
        schedule_data.name = "Test Schedule"
        schedule_data.repository_id = 1
        schedule_data.cron_expression = "0 2 * * *"
        schedule_data.source_path = "/data"
        schedule_data.cloud_sync_config_id = None
        schedule_data.cleanup_config_id = None
        schedule_data.notification_config_id = None

        # Mock repository query
        mock_repository = Mock()
        mock_db.query.return_value.filter.return_value.first.return_value = mock_repository

        # Mock database operations
        mock_db_schedule = Mock()
        mock_db_schedule.id = 123

        with patch("app.api.schedules.Schedule") as mock_schedule_class:
            mock_schedule_class.return_value = mock_db_schedule
            with patch("app.api.schedules.scheduler_service", mock_scheduler_service):
                mock_scheduler_service.add_schedule.side_effect = Exception("Scheduler error")
                with patch("app.api.schedules.templates") as mock_templates:
                    mock_templates.TemplateResponse.return_value = "error_template"

                    # Execute
                    result = await create_schedule(mock_request, schedule_data, mock_db)

                    # Verify
                    assert result == "error_template"
                    mock_db.delete.assert_called_once_with(mock_db_schedule)

    def test_get_schedules_html(self, mock_db):
        """Test getting schedules as HTML"""
        # Setup
        mock_schedules = [Mock(name="schedule1"), Mock(name="schedule2")]
        mock_db.query.return_value.offset.return_value.limit.return_value.all.return_value = mock_schedules

        with patch("app.api.schedules.templates") as mock_templates:
            mock_template = Mock()
            mock_template.render.return_value = "<div>Schedules HTML</div>"
            mock_templates.get_template.return_value = mock_template

            # Execute
            result = get_schedules_html(skip=5, limit=10, db=mock_db)

            # Verify
            assert result == "<div>Schedules HTML</div>"
            mock_db.query.return_value.offset.assert_called_once_with(5)
            mock_db.query.return_value.offset.return_value.limit.assert_called_once_with(10)

    @pytest.mark.asyncio
    async def test_get_upcoming_backups_html_success(self, mock_scheduler_service):
        """Test getting upcoming backups HTML successfully"""
        # Setup
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

        with patch("app.api.schedules.scheduler_service", mock_scheduler_service):
            mock_scheduler_service.get_scheduled_jobs.return_value = mock_jobs
            with patch("app.api.schedules.templates") as mock_templates:
                mock_template = Mock()
                mock_template.render.return_value = "<div>Upcoming Backups</div>"
                mock_templates.get_template.return_value = mock_template

                # Execute
                result = await get_upcoming_backups_html()

                # Verify
                assert result == "<div>Upcoming Backups</div>"
                mock_scheduler_service.get_scheduled_jobs.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_upcoming_backups_html_error(self, mock_scheduler_service):
        """Test getting upcoming backups HTML with error"""
        # Setup
        with patch("app.api.schedules.scheduler_service", mock_scheduler_service):
            mock_scheduler_service.get_scheduled_jobs.side_effect = Exception("Scheduler error")
            with patch("app.api.schedules.templates") as mock_templates:
                mock_template = Mock()
                mock_template.render.return_value = "<div>Error loading backups</div>"
                mock_templates.get_template.return_value = mock_template

                # Execute
                result = await get_upcoming_backups_html()

                # Verify
                assert result == "<div>Error loading backups</div>"

    @pytest.mark.asyncio
    async def test_get_cron_expression_form(self, mock_request):
        """Test getting cron expression form"""
        # Setup
        with patch("app.api.schedules.templates") as mock_templates:
            mock_templates.TemplateResponse.return_value = "cron_form_template"

            # Execute
            result = await get_cron_expression_form(mock_request, preset="0 2 * * *")

            # Verify
            assert result == "cron_form_template"

    def test_list_schedules(self, mock_db):
        """Test listing schedules"""
        # Setup
        mock_schedules = [Mock(name="schedule1"), Mock(name="schedule2")]
        mock_db.query.return_value.offset.return_value.limit.return_value.all.return_value = mock_schedules

        # Execute
        result = list_schedules(skip=0, limit=50, db=mock_db)

        # Verify
        assert result == mock_schedules

    def test_get_schedule_success(self, mock_db):
        """Test getting schedule successfully"""
        # Setup
        mock_schedule = Mock(name="schedule1")
        mock_db.query.return_value.filter.return_value.first.return_value = mock_schedule

        # Execute
        result = get_schedule(1, mock_db)

        # Verify
        assert result == mock_schedule

    def test_get_schedule_not_found(self, mock_db):
        """Test getting non-existent schedule"""
        # Setup
        mock_db.query.return_value.filter.return_value.first.return_value = None

        # Execute & Verify
        with pytest.raises(HTTPException) as exc_info:
            get_schedule(999, mock_db)

        assert exc_info.value.status_code == 404
        assert "Schedule not found" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    async def test_toggle_schedule_success(self, mock_db, mock_scheduler_service):
        """Test successfully toggling schedule"""
        # Setup
        mock_schedule = Mock()
        mock_schedule.id = 1
        mock_schedule.name = "Test Schedule"
        mock_schedule.cron_expression = "0 2 * * *"
        mock_schedule.enabled = False
        mock_db.query.return_value.filter.return_value.first.return_value = mock_schedule

        with patch("app.api.schedules.scheduler_service", mock_scheduler_service):
            mock_scheduler_service.update_schedule.return_value = None

            # Execute
            result = await toggle_schedule(1, None, mock_db)

            # Verify
            assert result == {"message": "Schedule enabled"}
            assert mock_schedule.enabled is True
            mock_db.commit.assert_called_once()
            mock_scheduler_service.update_schedule.assert_called_once_with(1, "Test Schedule", "0 2 * * *", True)

    @pytest.mark.asyncio
    async def test_toggle_schedule_not_found(self, mock_db):
        """Test toggling non-existent schedule"""
        # Setup
        mock_db.query.return_value.filter.return_value.first.return_value = None

        # Execute & Verify
        with pytest.raises(HTTPException) as exc_info:
            await toggle_schedule(999, None, mock_db)

        assert exc_info.value.status_code == 404
        assert "Schedule not found" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    async def test_toggle_schedule_service_error(self, mock_db, mock_scheduler_service):
        """Test toggling schedule with scheduler service error"""
        # Setup
        mock_schedule = Mock()
        mock_schedule.enabled = False
        mock_db.query.return_value.filter.return_value.first.return_value = mock_schedule

        with patch("app.api.schedules.scheduler_service", mock_scheduler_service):
            mock_scheduler_service.update_schedule.side_effect = Exception("Scheduler error")

            # Execute & Verify
            with pytest.raises(HTTPException) as exc_info:
                await toggle_schedule(1, None, mock_db)

            assert exc_info.value.status_code == 500
            assert "Failed to update schedule" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    async def test_delete_schedule_success(self, mock_db, mock_scheduler_service):
        """Test successfully deleting schedule"""
        # Setup
        mock_schedule = Mock()
        mock_schedule.id = 1
        mock_db.query.return_value.filter.return_value.first.return_value = mock_schedule

        with patch("app.api.schedules.scheduler_service", mock_scheduler_service):
            mock_scheduler_service.remove_schedule.return_value = None

            # Execute
            result = await delete_schedule(1, None, mock_db)

            # Verify
            assert result == {"message": "Schedule deleted successfully"}
            mock_scheduler_service.remove_schedule.assert_called_once_with(1)
            mock_db.delete.assert_called_once_with(mock_schedule)
            mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_schedule_not_found(self, mock_db):
        """Test deleting non-existent schedule"""
        # Setup
        mock_db.query.return_value.filter.return_value.first.return_value = None

        # Execute & Verify
        with pytest.raises(HTTPException) as exc_info:
            await delete_schedule(999, None, mock_db)

        assert exc_info.value.status_code == 404
        assert "Schedule not found" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    async def test_get_active_scheduled_jobs(self, mock_scheduler_service):
        """Test getting active scheduled jobs"""
        # Setup
        mock_jobs = [{"name": "job1"}, {"name": "job2"}]
        with patch("app.api.schedules.scheduler_service", mock_scheduler_service):
            mock_scheduler_service.get_scheduled_jobs.return_value = mock_jobs

            # Execute
            result = await get_active_scheduled_jobs()

            # Verify
            assert result == {"jobs": mock_jobs}
            mock_scheduler_service.get_scheduled_jobs.assert_called_once()


class TestScheduleUtilityFunctions:
    """Test utility functions for schedule processing"""

    def test_format_cron_trigger_daily(self):
        """Test formatting daily cron trigger"""
        trigger_str = "cron[minute='0', hour='14', day='*', month='*', day_of_week='*']"
        result = format_cron_trigger(trigger_str)
        assert result == "Daily at 2:00 PM"

    def test_format_cron_trigger_weekly(self):
        """Test formatting weekly cron trigger"""
        trigger_str = "cron[minute='0', hour='9', day='*', month='*', day_of_week='1']"
        result = format_cron_trigger(trigger_str)
        assert result == "Weekly on Monday at 9:00 AM"

    def test_format_cron_trigger_monthly(self):
        """Test formatting monthly cron trigger"""
        trigger_str = "cron[minute='0', hour='2', day='15', month='*', day_of_week='*']"
        result = format_cron_trigger(trigger_str)
        assert result == "Monthly on 15 at 2:00 AM"

    def test_format_cron_trigger_twice_monthly(self):
        """Test formatting twice monthly cron trigger"""
        trigger_str = "cron[minute='0', hour='2', day='1,15', month='*', day_of_week='*']"
        result = format_cron_trigger(trigger_str)
        assert result == "Twice monthly (1,15) at 2:00 AM"

    def test_format_cron_trigger_every_n_days(self):
        """Test formatting every N days cron trigger"""
        trigger_str = "cron[minute='0', hour='2', day='*/3', month='*', day_of_week='*']"
        result = format_cron_trigger(trigger_str)
        assert result == "Every 3 days at 2:00 AM"

    def test_format_cron_trigger_invalid(self):
        """Test formatting invalid cron trigger"""
        trigger_str = "invalid trigger format"
        result = format_cron_trigger(trigger_str)
        assert result == "invalid trigger format"

    def test_format_hour_morning(self):
        """Test formatting morning hours"""
        assert format_hour("0") == "12:00 AM"
        assert format_hour("9") == "9:00 AM"
        assert format_hour("11") == "11:00 AM"

    def test_format_hour_afternoon(self):
        """Test formatting afternoon hours"""
        assert format_hour("12") == "12:00 PM"
        assert format_hour("13") == "1:00 PM"
        assert format_hour("23") == "11:00 PM"

    def test_format_hour_invalid(self):
        """Test formatting invalid hour"""
        assert format_hour("invalid") == "invalid"

    def test_get_day_name_valid(self):
        """Test getting valid day names"""
        assert get_day_name("0") == "Sunday"
        assert get_day_name("1") == "Monday"
        assert get_day_name("6") == "Saturday"

    def test_get_day_name_invalid(self):
        """Test getting invalid day names"""
        assert get_day_name("7") == "Unknown"
        assert get_day_name("invalid") == "Unknown"

    def test_format_time_until_days(self):
        """Test formatting time until in days"""
        ms = 2 * 24 * 60 * 60 * 1000 + 3 * 60 * 60 * 1000  # 2 days 3 hours
        result = format_time_until(ms)
        assert result == "2d 3h"

    def test_format_time_until_hours(self):
        """Test formatting time until in hours"""
        ms = 5 * 60 * 60 * 1000 + 30 * 60 * 1000  # 5 hours 30 minutes
        result = format_time_until(ms)
        assert result == "5h 30m"

    def test_format_time_until_minutes(self):
        """Test formatting time until in minutes"""
        ms = 15 * 60 * 1000 + 45 * 1000  # 15 minutes 45 seconds
        result = format_time_until(ms)
        assert result == "15m 45s"

    def test_format_time_until_seconds(self):
        """Test formatting time until in seconds"""
        ms = 30 * 1000  # 30 seconds
        result = format_time_until(ms)
        assert result == "30s"

    def test_format_time_until_overdue(self):
        """Test formatting overdue time"""
        ms = -1000  # Negative time
        result = format_time_until(ms)
        assert result == "Overdue"