"""Tests for schedule validation business logic in ScheduleService."""

import pytest
from unittest.mock import Mock, AsyncMock

from borgitory.services.scheduling.schedule_service import ScheduleService


class TestScheduleValidationService:
    """Test suite for schedule validation business logic."""

    @pytest.fixture
    def mock_db(self) -> Mock:
        """Create a mock database session."""
        return Mock()

    @pytest.fixture
    def mock_scheduler_service(self) -> AsyncMock:
        """Create a mock scheduler service."""
        mock = AsyncMock()
        mock.add_schedule.return_value = None
        mock.update_schedule.return_value = None
        mock.remove_schedule.return_value = None
        return mock

    @pytest.fixture
    def schedule_service(
        self, mock_db: Mock, mock_scheduler_service: AsyncMock
    ) -> ScheduleService:
        """Create a ScheduleService instance with mocked dependencies."""
        return ScheduleService(mock_db, mock_scheduler_service)

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
            "notification_config_id": 4,
        }

    def test_validate_schedule_creation_data_minimal_valid_input(
        self, schedule_service: ScheduleService
    ) -> None:
        """Test validation with minimal valid input data."""
        minimal_data = {
            "name": "Test Schedule",
            "repository_id": "1",
            "cron_expression": "*/5 * * * *",
            "source_path": "",
            "cloud_sync_config_id": "",
            "prune_config_id": "",
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
            "source_path": "",
            "cloud_sync_config_id": None,
            "prune_config_id": None,
            "notification_config_id": None,
        }

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
        }

        is_valid, processed_data, error_msg = (
            schedule_service.validate_schedule_creation_data(data_with_whitespace)
        )

        assert is_valid is True
        assert error_msg is None
        assert processed_data["name"] == "Test Schedule"
        assert processed_data["cron_expression"] == "0 2 * * *"

    def test_validate_schedule_creation_data_complex_cron_expressions(
        self, schedule_service: ScheduleService
    ) -> None:
        """Test validation with complex but valid cron expressions."""
        test_cases = [
            "*/5 * * * *",  # Every 5 minutes
            "0 9-17 * * 1-5",  # Business hours weekdays
            "30 14 * * 0",  # Sunday afternoon
            "0 0 1 * *",  # First day of month
            "15,45 * * * *",  # At 15 and 45 minutes
        ]

        for cron_expr in test_cases:
            valid_data = {
                "name": "Test Schedule",
                "repository_id": "1",
                "cron_expression": cron_expr,
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
        ]

        for expr in valid_expressions:
            is_valid, error_msg = schedule_service.validate_cron_expression(expr)
            assert is_valid is True, f"Expected '{expr}' to be valid"
            assert error_msg is None

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
            is_valid, error_msg = schedule_service.validate_cron_expression(expr)
            assert is_valid is False, f"Expected '{expr}' to be invalid"
            assert error_msg is not None
            assert "Invalid cron expression:" in error_msg
