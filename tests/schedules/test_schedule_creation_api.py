"""Tests for schedule creation API with cron validation."""

import pytest
from typing import Any, Dict, Generator
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock
from urllib.parse import unquote

from sqlalchemy.orm import Session

from borgitory.main import app
from borgitory.models.database import Repository, User
from borgitory.dependencies import (
    get_schedule_service,
    get_configuration_service,
    get_scheduler_service_dependency,
)
from borgitory.services.scheduling.schedule_service import ScheduleService
from borgitory.services.configuration_service import ConfigurationService


def extract_error_message(html_content: str) -> str:
    """Extract and decode error message from HTMX notification trigger."""
    import re

    match = re.search(r"message=([^&]+)", html_content)
    if match:
        return unquote(match.group(1))
    return html_content


class TestScheduleCreationAPI:
    """Test suite for schedule creation API with validation."""

    @pytest.fixture
    def client(self) -> TestClient:
        """Create test client."""
        return TestClient(app)

    @pytest.fixture(scope="function")
    def setup_dependencies(
        self, test_db: Session
    ) -> Generator[Dict[str, Any], None, None]:
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

        # Create test data
        user = User()
        user.username = "testuser"
        user.set_password("testpass")
        test_db.add(user)

        repository = Repository()
        repository.name = "test-repo"
        repository.path = "/tmp/test-repo"
        repository.set_passphrase("test-passphrase")
        test_db.add(repository)
        test_db.commit()

        yield {
            "schedule_service": schedule_service,
            "configuration_service": configuration_service,
            "scheduler_service": mock_scheduler_service,
            "repository": repository,
            "user": user,
        }

        # Clean up overrides after test
        app.dependency_overrides.clear()

    def test_create_schedule_valid_data(
        self, client: TestClient, setup_dependencies: Dict[str, Any]
    ) -> None:
        """Test creating a schedule with valid data."""
        valid_data = {
            "name": "Daily Backup",
            "repository_id": 1,
            "cron_expression": "0 2 * * *",
            "source_path": "/data",
            "cloud_sync_config_id": None,
            "prune_config_id": None,
            "notification_config_id": None,
        }

        response = client.post("/api/schedules/", json=valid_data)

        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/html")

        html_content = response.text
        assert (
            "Schedule created successfully" in html_content
            or "Daily Backup" in html_content
        )

    def test_create_schedule_missing_name(
        self, client: TestClient, setup_dependencies: Dict[str, Any]
    ) -> None:
        """Test creating a schedule without a name."""
        invalid_data = {
            "name": "",
            "repository_id": 1,
            "cron_expression": "0 2 * * *",
            "source_path": "/data",
        }

        response = client.post("/api/schedules/", json=invalid_data)

        assert response.status_code == 200  # Returns 200 with error template
        html_content = response.text
        error_message = extract_error_message(html_content)
        assert "Schedule name is required" in error_message

    def test_create_schedule_missing_repository(
        self, client: TestClient, setup_dependencies: Dict[str, Any]
    ) -> None:
        """Test creating a schedule without a repository."""
        invalid_data = {
            "name": "Test Schedule",
            "repository_id": "",
            "cron_expression": "0 2 * * *",
            "source_path": "/data",
        }

        response = client.post("/api/schedules/", json=invalid_data)

        assert response.status_code == 200
        html_content = response.text
        error_message = extract_error_message(html_content)
        assert "Repository is required" in error_message

    def test_create_schedule_invalid_repository_id(
        self, client: TestClient, setup_dependencies: Dict[str, Any]
    ) -> None:
        """Test creating a schedule with invalid repository ID."""
        invalid_data = {
            "name": "Test Schedule",
            "repository_id": "not-a-number",
            "cron_expression": "0 2 * * *",
            "source_path": "/data",
        }

        response = client.post("/api/schedules/", json=invalid_data)

        assert response.status_code == 200
        html_content = response.text
        error_message = extract_error_message(html_content)
        assert "Invalid repository ID" in error_message

    def test_create_schedule_missing_cron_expression(
        self, client: TestClient, setup_dependencies: Dict[str, Any]
    ) -> None:
        """Test creating a schedule without cron expression."""
        invalid_data = {
            "name": "Test Schedule",
            "repository_id": 1,
            "cron_expression": "",
            "source_path": "/data",
        }

        response = client.post("/api/schedules/", json=invalid_data)

        assert response.status_code == 200
        html_content = response.text
        error_message = extract_error_message(html_content)
        assert "Cron expression is required" in error_message

    def test_create_schedule_invalid_cron_expression_too_few_parts(
        self, client: TestClient, setup_dependencies: Dict[str, Any]
    ) -> None:
        """Test creating a schedule with cron expression having too few parts."""
        invalid_data = {
            "name": "Test Schedule",
            "repository_id": 1,
            "cron_expression": "0 2 * *",  # Only 4 parts
            "source_path": "/data",
        }

        response = client.post("/api/schedules/", json=invalid_data)

        assert response.status_code == 200
        html_content = response.text
        error_message = extract_error_message(html_content)
        assert "must have 5 parts" in error_message

    def test_create_schedule_invalid_cron_expression_too_many_parts(
        self, client: TestClient, setup_dependencies: Dict[str, Any]
    ) -> None:
        """Test creating a schedule with cron expression having too many parts."""
        invalid_data = {
            "name": "Test Schedule",
            "repository_id": 1,
            "cron_expression": "0 2 * * * *",  # 6 parts
            "source_path": "/data",
        }

        response = client.post("/api/schedules/", json=invalid_data)

        assert response.status_code == 200
        html_content = response.text
        error_message = extract_error_message(html_content)
        assert "must have 5 parts" in error_message

    def test_create_schedule_complex_valid_cron_expressions(
        self, client: TestClient, setup_dependencies: Dict[str, Any]
    ) -> None:
        """Test creating schedules with various valid cron expressions."""
        test_cases = [
            ("*/5 * * * *", "Every 5 minutes"),
            ("0 9-17 * * 1-5", "Business hours"),
            ("30 14 * * 0", "Sunday afternoon"),
            ("0 0 1 * *", "Monthly"),
            ("15,45 * * * *", "Twice hourly"),
        ]

        for cron_expr, description in test_cases:
            valid_data = {
                "name": f"Test Schedule - {description}",
                "repository_id": 1,
                "cron_expression": cron_expr,
                "source_path": "/data",
            }

            response = client.post("/api/schedules/", json=valid_data)

            assert response.status_code == 200, (
                f"Failed for cron expression: {cron_expr}"
            )
            html_content = response.text
            assert (
                "Schedule created successfully" in html_content
                or description in html_content
            )

    def test_create_schedule_whitespace_handling(
        self, client: TestClient, setup_dependencies: Dict[str, Any]
    ) -> None:
        """Test creating a schedule with whitespace in inputs."""
        data_with_whitespace = {
            "name": "  Test Schedule  ",
            "repository_id": 1,
            "cron_expression": "  0 2 * * *  ",
            "source_path": "  /data  ",
        }

        response = client.post("/api/schedules/", json=data_with_whitespace)

        assert response.status_code == 200
        html_content = response.text
        assert (
            "Schedule created successfully" in html_content
            or "Test Schedule" in html_content
        )

    def test_create_schedule_optional_fields_handling(
        self, client: TestClient, setup_dependencies: Dict[str, Any]
    ) -> None:
        """Test creating a schedule with various optional field values."""
        test_cases = [
            {"cloud_sync_config_id": ""},
            {"cloud_sync_config_id": "2"},
            {"cloud_sync_config_id": "not-a-number"},  # Should be converted to None
            {"prune_config_id": "3"},
            {"notification_config_id": "4"},
        ]

        for optional_fields in test_cases:
            valid_data = {
                "name": "Test Schedule",
                "repository_id": 1,
                "cron_expression": "0 2 * * *",
                "source_path": "/data",
                **optional_fields,
            }

            response = client.post("/api/schedules/", json=valid_data)

            assert response.status_code == 200, (
                f"Failed for optional fields: {optional_fields}"
            )

    def test_create_schedule_nonexistent_repository(
        self, client: TestClient, setup_dependencies: Dict[str, Any]
    ) -> None:
        """Test creating a schedule with non-existent repository."""
        invalid_data = {
            "name": "Test Schedule",
            "repository_id": 999,  # Non-existent repository
            "cron_expression": "0 2 * * *",
            "source_path": "/data",
        }

        response = client.post("/api/schedules/", json=invalid_data)

        assert response.status_code == 200
        html_content = response.text
        assert "Repository not found" in html_content or "error" in html_content.lower()

    def test_create_schedule_scheduler_service_failure(
        self, client: TestClient, setup_dependencies: Dict[str, Any]
    ) -> None:
        """Test creating a schedule when scheduler service fails."""
        # Make the scheduler service fail
        setup_dependencies["scheduler_service"].add_schedule.side_effect = Exception(
            "Scheduler error"
        )

        valid_data = {
            "name": "Test Schedule",
            "repository_id": 1,
            "cron_expression": "0 2 * * *",
            "source_path": "/data",
        }

        response = client.post("/api/schedules/", json=valid_data)

        assert response.status_code == 200
        html_content = response.text
        assert (
            "Failed to schedule job" in html_content or "error" in html_content.lower()
        )

    def test_create_schedule_invalid_json(
        self, client: TestClient, setup_dependencies: Dict[str, Any]
    ) -> None:
        """Test creating a schedule with invalid JSON."""
        response = client.post("/api/schedules/", content="invalid json")

        assert response.status_code == 200  # FastAPI returns 422 for invalid JSON

    def test_create_schedule_empty_json(
        self, client: TestClient, setup_dependencies: Dict[str, Any]
    ) -> None:
        """Test creating a schedule with empty JSON."""
        response = client.post("/api/schedules/", json={})

        assert response.status_code == 200
        html_content = response.text
        assert "required" in html_content.lower()

    def test_create_schedule_htmx_headers(
        self, client: TestClient, setup_dependencies: Dict[str, Any]
    ) -> None:
        """Test that successful creation returns proper HTMX headers."""
        valid_data = {
            "name": "Test Schedule",
            "repository_id": 1,
            "cron_expression": "0 2 * * *",
            "source_path": "/data",
        }

        response = client.post("/api/schedules/", json=valid_data)

        assert response.status_code == 200
        # Check for HTMX trigger header
        assert "HX-Trigger" in response.headers
        assert response.headers["HX-Trigger"] == "scheduleUpdate"

    def test_create_schedule_response_format(
        self, client: TestClient, setup_dependencies: Dict[str, Any]
    ) -> None:
        """Test that responses are properly formatted HTML for HTMX."""
        valid_data = {
            "name": "Test Schedule",
            "repository_id": 1,
            "cron_expression": "0 2 * * *",
            "source_path": "/data",
        }

        response = client.post("/api/schedules/", json=valid_data)

        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/html")

        html_content = response.text
        # Should contain HTML elements
        assert "<div" in html_content
        # Should contain HTMX attributes for notifications
        assert "hx-get" in html_content
