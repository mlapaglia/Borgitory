"""
Tests for schedule hooks API endpoints in schedules.py

Tests all hook-related endpoints using proper DI with mocks, no patches.
"""

import pytest
import json
from typing import Any, Dict, List
from unittest.mock import AsyncMock, Mock
from fastapi.testclient import TestClient
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from borgitory.main import app
from borgitory.dependencies import (
    get_schedule_service,
    get_templates,
    get_configuration_service,
)
from borgitory.services.scheduling.schedule_service import ScheduleService
from borgitory.services.configuration_service import ConfigurationService

client = TestClient(app)


class TestScheduleHooksAPI:
    """Test the Schedule Hooks API endpoints - HTMX/HTTP behavior"""

    @pytest.fixture(scope="function")
    def setup_test_dependencies(self, test_db: Session) -> Dict[str, Any]:
        """Setup dependency overrides for each test."""
        # Create mock scheduler service
        mock_scheduler_service = AsyncMock()
        mock_scheduler_service.add_schedule.return_value = None
        mock_scheduler_service.update_schedule.return_value = None
        mock_scheduler_service.remove_schedule.return_value = None

        # Create real services with test database
        schedule_service = ScheduleService(test_db, mock_scheduler_service)
        configuration_service = ConfigurationService(test_db)

        # Create mock templates service that returns proper HTMLResponse
        mock_templates = Mock()

        def mock_template_response(
            request: Any,
            template_name: str,
            context: Any = None,
            status_code: int = 200,
        ) -> HTMLResponse:
            """Mock template response that returns HTMLResponse"""
            return HTMLResponse(
                content=f"<div>Mock response for {template_name}</div>",
                status_code=status_code,
            )

        mock_templates.TemplateResponse = mock_template_response

        # Override dependencies
        app.dependency_overrides[get_schedule_service] = lambda: schedule_service
        app.dependency_overrides[get_configuration_service] = (
            lambda: configuration_service
        )
        app.dependency_overrides[get_templates] = lambda: mock_templates

        return {
            "schedule_service": schedule_service,
            "configuration_service": configuration_service,
            "templates": mock_templates,
            "scheduler_service": mock_scheduler_service,
        }

    def teardown_method(self) -> None:
        """Clean up dependency overrides after each test."""
        app.dependency_overrides.clear()

    # Test add-hook-field endpoint
    def test_add_hook_field_pre_hook(
        self, setup_test_dependencies: Dict[str, Any]
    ) -> None:
        """Test adding a new pre-hook field."""
        form_data = {
            "hook_type": "pre",
            "pre_hook_name": ["existing hook"],
            "pre_hook_command": ["echo existing"],
        }

        response = client.post(
            "/api/schedules/hooks/add-hook-field",
            data=form_data,
        )

        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")

    def test_add_hook_field_post_hook(
        self, setup_test_dependencies: Dict[str, Any]
    ) -> None:
        """Test adding a new post-hook field."""
        form_data = {
            "hook_type": "post",
            "post_hook_name": ["existing post hook"],
            "post_hook_command": ["echo post existing"],
        }

        response = client.post(
            "/api/schedules/hooks/add-hook-field",
            data=form_data,
        )

        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")

    def test_add_hook_field_empty_form(
        self, setup_test_dependencies: Dict[str, Any]
    ) -> None:
        """Test adding hook field with empty form data."""
        form_data = {"hook_type": "pre"}

        response = client.post(
            "/api/schedules/hooks/add-hook-field",
            data=form_data,
        )

        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")

    # Test move-hook endpoint
    def test_move_hook_up_success(
        self, setup_test_dependencies: Dict[str, Any]
    ) -> None:
        """Test moving a hook up in the list."""
        form_data = {
            "hook_type": "pre",
            "index": "1",
            "direction": "up",
            "pre_hook_name": ["Hook 1", "Hook 2"],
            "pre_hook_command": ["command1", "command2"],
        }

        response = client.post(
            "/api/schedules/hooks/move-hook",
            data=form_data,
        )

        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")

    def test_move_hook_down_success(
        self, setup_test_dependencies: Dict[str, Any]
    ) -> None:
        """Test moving a hook down in the list."""
        form_data = {
            "hook_type": "post",
            "index": "0",
            "direction": "down",
            "post_hook_name": ["Hook A", "Hook B"],
            "post_hook_command": ["commandA", "commandB"],
        }

        response = client.post(
            "/api/schedules/hooks/move-hook",
            data=form_data,
        )

        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")

    def test_move_hook_invalid_direction(
        self, setup_test_dependencies: Dict[str, Any]
    ) -> None:
        """Test moving hook with invalid direction."""
        form_data = {
            "hook_type": "pre",
            "index": "0",
            "direction": "sideways",  # Invalid direction
            "pre_hook_name": ["Hook 1"],
            "pre_hook_command": ["command1"],
        }

        response = client.post(
            "/api/schedules/hooks/move-hook",
            data=form_data,
        )

        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")

    def test_move_hook_error_handling(
        self, setup_test_dependencies: Dict[str, Any]
    ) -> None:
        """Test move hook endpoint error handling."""
        form_data = {
            "hook_type": "pre",
            "index": "invalid",  # Invalid index
            "direction": "up",
        }

        response = client.post(
            "/api/schedules/hooks/move-hook",
            data=form_data,
        )

        assert response.status_code == 200
        # Should return empty container on error
        assert '<div class="space-y-4"></div>' in response.text

    # Test remove-hook-field endpoint
    def test_remove_hook_field_success(
        self, setup_test_dependencies: Dict[str, Any]
    ) -> None:
        """Test removing a hook field successfully."""
        form_data = {
            "hook_type": "pre",
            "index": "0",
            "pre_hook_name": ["Hook 1", "Hook 2"],
            "pre_hook_command": ["command1", "command2"],
        }

        response = client.post(
            "/api/schedules/hooks/remove-hook-field",
            data=form_data,
        )

        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")

    # Test hooks-modal endpoint
    def test_get_hooks_modal_with_data(
        self, setup_test_dependencies: Dict[str, Any]
    ) -> None:
        """Test opening hooks modal with existing hook data."""
        json_data = {
            "pre_hooks": '[{"name": "Pre Hook", "command": "echo pre"}]',
            "post_hooks": '[{"name": "Post Hook", "command": "echo post"}]',
        }

        response = client.post(
            "/api/schedules/hooks/hooks-modal",
            json=json_data,
        )

        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")

    def test_get_hooks_modal_empty_data(
        self, setup_test_dependencies: Dict[str, Any]
    ) -> None:
        """Test opening hooks modal with no existing hooks."""
        json_data: Dict[str, str] = {"pre_hooks": "[]", "post_hooks": "[]"}

        response = client.post(
            "/api/schedules/hooks/hooks-modal",
            json=json_data,
        )

        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")

    def test_get_hooks_modal_invalid_json(
        self, setup_test_dependencies: Dict[str, Any]
    ) -> None:
        """Test hooks modal with invalid JSON data."""
        json_data = {
            "pre_hooks": "invalid json",
            "post_hooks": "also invalid",
        }

        response = client.post(
            "/api/schedules/hooks/hooks-modal",
            json=json_data,
        )

        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")

    # Test save-hooks endpoint
    def test_save_hooks_success(self, setup_test_dependencies: Dict[str, Any]) -> None:
        """Test saving hooks successfully."""
        form_data = {
            "pre_hook_name": ["Valid Pre Hook"],
            "pre_hook_command": ["echo pre"],
            "post_hook_name": ["Valid Post Hook"],
            "post_hook_command": ["echo post"],
        }

        response = client.post(
            "/api/schedules/hooks/save-hooks",
            data=form_data,
        )

        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")

    def test_save_hooks_validation_error(
        self, setup_test_dependencies: Dict[str, Any]
    ) -> None:
        """Test saving hooks with validation errors."""
        form_data = {
            "pre_hook_name": ["Hook with no command"],
            "pre_hook_command": [""],  # Empty command
        }

        response = client.post(
            "/api/schedules/hooks/save-hooks",
            data=form_data,
        )

        assert response.status_code == 400
        assert "text/html" in response.headers.get("content-type", "")

    def test_save_hooks_empty_form(
        self, setup_test_dependencies: Dict[str, Any]
    ) -> None:
        """Test saving with completely empty form."""
        form_data: Dict[str, str] = {}

        response = client.post(
            "/api/schedules/hooks/save-hooks",
            data=form_data,
        )

        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")

    # Test close-modal endpoint
    def test_close_modal(self, setup_test_dependencies: Dict[str, Any]) -> None:
        """Test closing modal without saving."""
        response = client.get("/api/schedules/hooks/close-modal")

        assert response.status_code == 200
        assert '<div id="modal-container"></div>' in response.text

    # Unit tests for helper functions
    def test_convert_hook_fields_to_json_dict_input(self) -> None:
        """Test convert_hook_fields_to_json with dict input."""
        from borgitory.api.schedules import convert_hook_fields_to_json

        form_data = {
            "pre_hook_name": ["Hook 1", "Hook 2"],
            "pre_hook_command": ["command1", "command2"],
        }

        result = convert_hook_fields_to_json(form_data, "pre")
        assert result is not None
        parsed = json.loads(result)

        assert len(parsed) == 2
        assert parsed[0]["name"] == "Hook 1"
        assert parsed[0]["command"] == "command1"

    def test_convert_hook_fields_to_json_single_values(self) -> None:
        """Test convert_hook_fields_to_json with single values."""
        from borgitory.api.schedules import convert_hook_fields_to_json

        form_data = {
            "post_hook_name": "Single Hook",
            "post_hook_command": "single command",
        }

        result = convert_hook_fields_to_json(form_data, "post")
        assert result is not None
        parsed = json.loads(result)

        assert len(parsed) == 1
        assert parsed[0]["name"] == "Single Hook"

    def test_validate_hooks_for_save_success(self) -> None:
        """Test _validate_hooks_for_save with valid data."""
        from borgitory.api.schedules import _validate_hooks_for_save

        class MockFormData:
            def __init__(self, data: Dict[str, List[str]]) -> None:
                self.data = data

            def getlist(self, key: str) -> List[str]:
                return self.data.get(key, [])

        form_data = MockFormData(
            {
                "pre_hook_name": ["Valid Hook"],
                "pre_hook_command": ["valid command"],
            }
        )

        is_valid, error = _validate_hooks_for_save(form_data)
        assert is_valid is True
        assert error is None

    def test_validate_hooks_for_save_error(self) -> None:
        """Test _validate_hooks_for_save with invalid data."""
        from borgitory.api.schedules import _validate_hooks_for_save

        class MockFormData:
            def __init__(self, data: Dict[str, List[str]]) -> None:
                self.data = data

            def getlist(self, key: str) -> List[str]:
                return self.data.get(key, [])

        form_data = MockFormData(
            {
                "pre_hook_name": ["Hook with missing command"],
                "pre_hook_command": [""],  # Empty command
            }
        )

        is_valid, error = _validate_hooks_for_save(form_data)
        assert is_valid is False
        assert error is not None
        assert "Hook command is required" in error

    def test_extract_hooks_from_form(self) -> None:
        """Test _extract_hooks_from_form helper function."""
        from borgitory.api.schedules import _extract_hooks_from_form

        class MockFormData:
            def __init__(self, data: Dict[str, List[str]]) -> None:
                self.data = data

            def getlist(self, key: str) -> List[str]:
                return self.data.get(key, [])

        form_data = MockFormData(
            {
                "pre_hook_name": ["Hook 1", "Hook 2"],
                "pre_hook_command": ["cmd1", "cmd2"],
            }
        )

        hooks = _extract_hooks_from_form(form_data, "pre")

        assert len(hooks) == 2
        assert hooks[0]["name"] == "Hook 1"
        assert hooks[0]["command"] == "cmd1"
        assert hooks[1]["name"] == "Hook 2"
        assert hooks[1]["command"] == "cmd2"
