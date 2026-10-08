"""Tests for schedule validation business logic in ScheduleService."""

import pytest
from unittest.mock import AsyncMock

from borgitory.services.scheduling.schedule_service import (
    NO_WORK_ERROR_MESSAGE,
    ScheduleService,
)


class TestScheduleValidationService:
    """Test suite for schedule validation business logic."""

    @pytest.fixture
    def mock_scheduler_service(self) -> AsyncMock:
        """Create a mock scheduler service."""
        mock = AsyncMock()
        mock.add_schedule.return_value = None
        mock.update_schedule.return_value = None
        mock.remove_schedule.return_value = None
        return mock

    @pytest.fixture
    def schedule_service(self, mock_scheduler_service: AsyncMock) -> ScheduleService:
        """Create a ScheduleService instance with mocked dependencies."""
        return ScheduleService(mock_scheduler_service)

    def test_validate_schedule_creation_data_manual_only(
        self, schedule_service: ScheduleService
    ) -> None:
        """manual_only clears the cron expression and skips cron validation."""
        is_valid, processed_data, error_msg = (
            schedule_service.validate_schedule_creation_data(
                {
                    "name": "Manual Backup",
                    "repository_id": "1",
                    "manual_only": "true",
                    "source_path": "/data",
                    "dry_run": "on",
                }
            )
        )

        assert is_valid is True
        assert error_msg is None
        assert processed_data["cron_expression"] is None
        assert processed_data["dry_run"] is True

    def test_validate_schedule_creation_data_missing_cron_not_manual(
        self, schedule_service: ScheduleService
    ) -> None:
        """Without manual_only, a missing cron expression is still an error."""
        is_valid, _, error_msg = schedule_service.validate_schedule_creation_data(
            {"name": "Backup", "repository_id": "1", "source_path": "/data"}
        )

        assert is_valid is False
        assert error_msg == "Cron expression is required"

    def test_validate_schedule_creation_data_valid_input(
        self, schedule_service: ScheduleService
    ) -> None:
        """Test validation with valid input data."""
        valid_data = {
            "name": "Daily Backup",
            "repository_id": "1",
            "cron_expression": "0 2 * * *",
            "source_path": "/data",
            "cloud_sync_config_id": "2",
            "prune_config_id": "3",
            "notification_config_id": "4",
        }

        is_valid, processed_data, error_msg = (
            schedule_service.validate_schedule_creation_data(valid_data)
        )

        assert is_valid is True
        assert error_msg is None
        assert processed_data == {
            "name": "Daily Backup",
            "repository_id": 1,
            "cron_expression": "0 2 * * *",
            "source_path": "/data",
            "cloud_sync_config_id": 2,
            "prune_config_id": 3,
            "check_config_id": None,
            "notification_config_id": 4,
            "pre_job_hooks": None,
            "post_job_hooks": None,
            "patterns": None,
            "dry_run": False,
        }

    def test_validate_schedule_creation_data_minimal_valid_input(
        self, schedule_service: ScheduleService
    ) -> None:
        """Test validation with minimal valid input data."""
        minimal_data = {
            "name": "Test Schedule",
            "repository_id": "1",
            "cron_expression": "*/5 * * * *",
            "source_path": "/data",
            "cloud_sync_config_id": "",
            "prune_config_id": "",
            "check_config_id": "",
            "notification_config_id": "",
        }

        is_valid, processed_data, error_msg = (
            schedule_service.validate_schedule_creation_data(minimal_data)
        )

        assert is_valid is True
        assert error_msg is None
        assert processed_data == {
            "name": "Test Schedule",
            "repository_id": 1,
            "cron_expression": "*/5 * * * *",
            "source_path": "/data",
            "cloud_sync_config_id": None,
            "prune_config_id": None,
            "check_config_id": None,
            "notification_config_id": None,
            "pre_job_hooks": None,
            "post_job_hooks": None,
            "patterns": None,
            "dry_run": False,
        }

    def test_validate_schedule_creation_data_check_only_schedule(
        self, schedule_service: ScheduleService
    ) -> None:
        """An empty source path is allowed when the schedule runs a check."""
        check_only_data = {
            "name": "Weekly Check",
            "repository_id": "1",
            "cron_expression": "0 2 * * 6",
            "source_path": "",
            "check_config_id": "5",
        }

        is_valid, processed_data, error_msg = (
            schedule_service.validate_schedule_creation_data(check_only_data)
        )

        assert is_valid is True
        assert error_msg is None
        assert processed_data["source_path"] == ""
        assert processed_data["check_config_id"] == 5

    def test_validate_schedule_creation_data_no_work_rejected(
        self, schedule_service: ScheduleService
    ) -> None:
        """An empty source path with no maintenance tasks is rejected."""
        no_work_data = {
            "name": "Empty Schedule",
            "repository_id": "1",
            "cron_expression": "0 2 * * *",
            "source_path": "   ",
            "notification_config_id": "4",
        }

        is_valid, processed_data, error_msg = (
            schedule_service.validate_schedule_creation_data(no_work_data)
        )

        assert is_valid is False
        assert processed_data == {}
        assert error_msg == NO_WORK_ERROR_MESSAGE

    def test_validate_schedule_creation_data_missing_name(
        self, schedule_service: ScheduleService
    ) -> None:
        """Test validation with missing name."""
        invalid_data = {
            "name": "",
            "repository_id": "1",
            "cron_expression": "0 2 * * *",
        }

        is_valid, processed_data, error_msg = (
            schedule_service.validate_schedule_creation_data(invalid_data)
        )

        assert is_valid is False
        assert processed_data == {}
        assert error_msg == "Schedule name is required"

    def test_validate_schedule_creation_data_missing_repository_id(
        self, schedule_service: ScheduleService
    ) -> None:
        """Test validation with missing repository ID."""
        invalid_data = {
            "name": "Test Schedule",
            "repository_id": "",
            "cron_expression": "0 2 * * *",
        }

        is_valid, processed_data, error_msg = (
            schedule_service.validate_schedule_creation_data(invalid_data)
        )

        assert is_valid is False
        assert processed_data == {}
        assert error_msg == "Repository is required"

    def test_validate_schedule_creation_data_invalid_repository_id(
        self, schedule_service: ScheduleService
    ) -> None:
        """Test validation with invalid repository ID."""
        invalid_data = {
            "name": "Test Schedule",
            "repository_id": "not-a-number",
            "cron_expression": "0 2 * * *",
        }

        is_valid, processed_data, error_msg = (
            schedule_service.validate_schedule_creation_data(invalid_data)
        )

        assert is_valid is False
        assert processed_data == {}
        assert error_msg == "Invalid repository ID"

    def test_validate_schedule_creation_data_missing_cron_expression(
        self, schedule_service: ScheduleService
    ) -> None:
        """Test validation with missing cron expression."""
        invalid_data = {
            "name": "Test Schedule",
            "repository_id": "1",
            "cron_expression": "",
        }

        is_valid, processed_data, error_msg = (
            schedule_service.validate_schedule_creation_data(invalid_data)
        )

        assert is_valid is False
        assert processed_data == {}
        assert error_msg == "Cron expression is required"

    def test_validate_schedule_creation_data_invalid_cron_expression_too_few_parts(
        self, schedule_service: ScheduleService
    ) -> None:
        """Test validation with cron expression having too few parts."""
        invalid_data = {
            "name": "Test Schedule",
            "repository_id": "1",
            "cron_expression": "0 2 * *",  # Only 4 parts
        }

        is_valid, processed_data, error_msg = (
            schedule_service.validate_schedule_creation_data(invalid_data)
        )

        assert is_valid is False
        assert processed_data == {}
        assert (
            error_msg
            == "Cron expression must have 5 parts (minute hour day month weekday), but got 4 parts: '0 2 * *'"
        )

    def test_validate_schedule_creation_data_invalid_cron_expression_too_many_parts(
        self, schedule_service: ScheduleService
    ) -> None:
        """Test validation with cron expression having too many parts."""
        invalid_data = {
            "name": "Test Schedule",
            "repository_id": "1",
            "cron_expression": "0 2 * * * *",  # 6 parts
        }

        is_valid, processed_data, error_msg = (
            schedule_service.validate_schedule_creation_data(invalid_data)
        )

        assert is_valid is False
        assert processed_data == {}
        assert (
            error_msg
            == "Cron expression must have 5 parts (minute hour day month weekday), but got 6 parts: '0 2 * * * *'"
        )

    def test_validate_schedule_creation_data_whitespace_handling(
        self, schedule_service: ScheduleService
    ) -> None:
        """Test validation properly handles whitespace in inputs."""
        data_with_whitespace = {
            "name": "  Test Schedule  ",
            "repository_id": "1",
            "cron_expression": "  0 2 * * *  ",
            "source_path": "  /data  ",
        }

        is_valid, processed_data, error_msg = (
            schedule_service.validate_schedule_creation_data(data_with_whitespace)
        )

        assert is_valid is True
        assert error_msg is None
        assert processed_data["name"] == "Test Schedule"
        assert processed_data["cron_expression"] == "0 2 * * *"
        assert processed_data["source_path"] == "/data"

    def test_validate_schedule_creation_data_complex_cron_expressions(
        self, schedule_service: ScheduleService
    ) -> None:
        """Test validation with complex but valid cron expressions."""
        test_cases = [
            "*/5 * * * *",  # Every 5 minutes
            "0 9-17 * * 1-5",  # Business hours weekdays
            "30 14 * * 0",  # Sunday afternoon
            "0 1 * * 7",  # Sunday via Unix alias
            "0 0 1 * *",  # First day of month
            "15,45 * * * *",  # At 15 and 45 minutes
        ]

        for cron_expr in test_cases:
            valid_data = {
                "name": "Test Schedule",
                "repository_id": "1",
                "cron_expression": cron_expr,
                "source_path": "/data",
            }

            is_valid, processed_data, error_msg = (
                schedule_service.validate_schedule_creation_data(valid_data)
            )

            assert is_valid is True, f"Failed for cron expression: {cron_expr}"
            assert error_msg is None
            assert processed_data["cron_expression"] == cron_expr

    def test_validate_schedule_creation_data_optional_field_type_conversion(
        self, schedule_service: ScheduleService
    ) -> None:
        """Test that optional fields are properly converted to integers or None."""
        test_cases = [
            ("", None),
            ("0", 0),
            ("123", 123),
            ("not-a-number", None),
            (None, None),
        ]

        for input_value, expected_output in test_cases:
            valid_data = {
                "name": "Test Schedule",
                "repository_id": "1",
                "cron_expression": "0 2 * * *",
                "source_path": "/data",
                "cloud_sync_config_id": input_value,
            }

            is_valid, processed_data, error_msg = (
                schedule_service.validate_schedule_creation_data(valid_data)
            )

            assert is_valid is True
            assert processed_data["cloud_sync_config_id"] == expected_output

    def test_validate_cron_expression_valid(
        self, schedule_service: ScheduleService
    ) -> None:
        """Test cron expression validation with valid expressions."""
        valid_expressions = [
            "0 2 * * *",
            "*/5 * * * *",
            "0 9-17 * * 1-5",
            "30 14 * * 0",
            "0 1 * * 7",  # Sunday via Unix cron alias
            "0 1 * * sun",
        ]

        for expr in valid_expressions:
            result = schedule_service.validate_cron_expression(expr)
            assert result.success is True, f"Expected '{expr}' to be valid"
            assert result.error_message is None

    def test_validate_cron_expression_invalid(
        self, schedule_service: ScheduleService
    ) -> None:
        """Test cron expression validation with invalid expressions."""
        invalid_expressions = [
            "60 * * * *",  # Invalid minute
            "* 25 * * *",  # Invalid hour
            "* * 32 * *",  # Invalid day
            "* * * 13 *",  # Invalid month
            "* * * * 8",  # Invalid weekday
        ]

        for expr in invalid_expressions:
            result = schedule_service.validate_cron_expression(expr)
            assert result.success is False, f"Expected '{expr}' to be invalid"
            assert result.error_message is not None
            assert "Invalid cron expression:" in result.error_message
