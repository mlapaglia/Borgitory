"""
Tests for schedule patterns API endpoints in schedules.py

Tests all pattern-related endpoints using proper DI with mocks, no patches.
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


class TestSchedulePatternsAPI:
    """Test the Schedule Patterns API endpoints - HTMX/HTTP behavior"""

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

    # Test add-pattern-field endpoint
    def test_add_pattern_field_success(
        self, setup_test_dependencies: Dict[str, Any]
    ) -> None:
        """Test adding a new pattern field."""
        form_data = {
            "pattern_name": ["existing pattern"],
            "pattern_expression": ["*.pdf"],
            "pattern_action": ["include"],
            "pattern_style": ["sh"],
        }

        response = client.post(
            "/api/schedules/patterns/add-pattern-field",
            data=form_data,
        )

        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")

    def test_add_pattern_field_empty_form(
        self, setup_test_dependencies: Dict[str, Any]
    ) -> None:
        """Test adding pattern field with empty form data."""
        form_data: Dict[str, str] = {}

        response = client.post(
            "/api/schedules/patterns/add-pattern-field",
            data=form_data,
        )

        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")

    # Test move-pattern endpoint
    def test_move_pattern_up_success(
        self, setup_test_dependencies: Dict[str, Any]
    ) -> None:
        """Test moving a pattern up in the list."""
        form_data = {
            "index": "1",
            "direction": "up",
            "pattern_name": ["Pattern 1", "Pattern 2"],
            "pattern_expression": ["*.txt", "*.pdf"],
            "pattern_action": ["include", "exclude"],
            "pattern_style": ["sh", "fm"],
        }

        response = client.post(
            "/api/schedules/patterns/move-pattern",
            data=form_data,
        )

        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")

    def test_move_pattern_down_success(
        self, setup_test_dependencies: Dict[str, Any]
    ) -> None:
        """Test moving a pattern down in the list."""
        form_data = {
            "index": "0",
            "direction": "down",
            "pattern_name": ["Pattern A", "Pattern B"],
            "pattern_expression": ["*.log", "*.tmp"],
            "pattern_action": ["exclude", "include"],
            "pattern_style": ["re", "pp"],
        }

        response = client.post(
            "/api/schedules/patterns/move-pattern",
            data=form_data,
        )

        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")

    def test_move_pattern_invalid_direction(
        self, setup_test_dependencies: Dict[str, Any]
    ) -> None:
        """Test moving pattern with invalid direction."""
        form_data = {
            "index": "0",
            "direction": "sideways",  # Invalid direction
            "pattern_name": ["Pattern 1"],
            "pattern_expression": ["*.txt"],
            "pattern_action": ["include"],
            "pattern_style": ["sh"],
        }

        response = client.post(
            "/api/schedules/patterns/move-pattern",
            data=form_data,
        )

        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")

    def test_move_pattern_error_handling(
        self, setup_test_dependencies: Dict[str, Any]
    ) -> None:
        """Test move pattern endpoint error handling."""
        form_data = {
            "index": "invalid",  # Invalid index
            "direction": "up",
        }

        response = client.post(
            "/api/schedules/patterns/move-pattern",
            data=form_data,
        )

        assert response.status_code == 200
        # Should return empty container on error
        assert '<div class="space-y-4"></div>' in response.text

    # Test remove-pattern-field endpoint
    def test_remove_pattern_field_success(
        self, setup_test_dependencies: Dict[str, Any]
    ) -> None:
        """Test removing a pattern field successfully."""
        form_data = {
            "index": "0",
            "pattern_name": ["Pattern 1", "Pattern 2"],
            "pattern_expression": ["*.txt", "*.pdf"],
            "pattern_action": ["include", "exclude"],
            "pattern_style": ["sh", "fm"],
        }

        response = client.post(
            "/api/schedules/patterns/remove-pattern-field",
            data=form_data,
        )

        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")

    def test_remove_pattern_field_invalid_index(
        self, setup_test_dependencies: Dict[str, Any]
    ) -> None:
        """Test removing pattern field with invalid index."""
        form_data = {
            "index": "invalid",  # Invalid index
            "pattern_name": ["Pattern 1"],
            "pattern_expression": ["*.txt"],
        }

        response = client.post(
            "/api/schedules/patterns/remove-pattern-field",
            data=form_data,
        )

        assert response.status_code == 200
        # Should return empty container on error
        assert '<div class="space-y-4"></div>' in response.text

    # Test patterns-modal endpoint
    def test_get_patterns_modal_with_data(
        self, setup_test_dependencies: Dict[str, Any]
    ) -> None:
        """Test opening patterns modal with existing pattern data."""
        json_data = {
            "patterns": '[{"name": "Test Pattern", "expression": "*.pdf", "pattern_type": "include", "style": "sh"}]'
        }

        response = client.post(
            "/api/schedules/patterns/patterns-modal",
            json=json_data,
        )

        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")

    def test_get_patterns_modal_empty_data(
        self, setup_test_dependencies: Dict[str, Any]
    ) -> None:
        """Test opening patterns modal with no existing patterns."""
        json_data: Dict[str, str] = {"patterns": "[]"}

        response = client.post(
            "/api/schedules/patterns/patterns-modal",
            json=json_data,
        )

        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")

    def test_get_patterns_modal_invalid_json(
        self, setup_test_dependencies: Dict[str, Any]
    ) -> None:
        """Test patterns modal with invalid JSON data."""
        json_data = {"patterns": "invalid json"}

        response = client.post(
            "/api/schedules/patterns/patterns-modal",
            json=json_data,
        )

        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")

    def test_get_patterns_modal_no_json(
        self, setup_test_dependencies: Dict[str, Any]
    ) -> None:
        """Test patterns modal with no JSON data."""
        response = client.post("/api/schedules/patterns/patterns-modal")

        assert response.status_code == 200  # Endpoint handles missing JSON gracefully
        assert "text/html" in response.headers.get("content-type", "")

    # Test save-patterns endpoint
    def test_save_patterns_success(
        self, setup_test_dependencies: Dict[str, Any]
    ) -> None:
        """Test saving patterns successfully."""
        form_data = {
            "pattern_name": ["Valid Pattern"],
            "pattern_expression": ["*.pdf"],
            "pattern_action": ["include"],
            "pattern_style": ["sh"],
        }

        response = client.post(
            "/api/schedules/patterns/save-patterns",
            data=form_data,
        )

        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")

    def test_save_patterns_validation_error(
        self, setup_test_dependencies: Dict[str, Any]
    ) -> None:
        """Test saving patterns with validation errors."""
        form_data = {
            "pattern_name": ["Pattern with no expression"],
            "pattern_expression": [""],  # Empty expression
            "pattern_action": ["include"],
            "pattern_style": ["sh"],
        }

        response = client.post(
            "/api/schedules/patterns/save-patterns",
            data=form_data,
        )

        assert response.status_code == 400
        assert "text/html" in response.headers.get("content-type", "")

    def test_save_patterns_empty_form(
        self, setup_test_dependencies: Dict[str, Any]
    ) -> None:
        """Test saving with completely empty form."""
        form_data: Dict[str, str] = {}

        response = client.post(
            "/api/schedules/patterns/save-patterns",
            data=form_data,
        )

        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")

    def test_save_patterns_multiple_patterns(
        self, setup_test_dependencies: Dict[str, Any]
    ) -> None:
        """Test saving multiple patterns."""
        form_data = {
            "pattern_name": ["Include PDFs", "Exclude Logs"],
            "pattern_expression": ["*.pdf", "*.log"],
            "pattern_action": ["include", "exclude"],
            "pattern_style": ["sh", "fm"],
        }

        response = client.post(
            "/api/schedules/patterns/save-patterns",
            data=form_data,
        )

        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")

    # Test validate-all-patterns endpoint
    def test_validate_all_patterns_success(
        self, setup_test_dependencies: Dict[str, Any]
    ) -> None:
        """Test validating all patterns successfully."""
        form_data = {
            "pattern_name": ["Valid Pattern"],
            "pattern_expression": ["*.pdf"],
            "pattern_action": ["include"],
            "pattern_style": ["sh"],
        }

        response = client.post(
            "/api/schedules/patterns/validate-all-patterns",
            data=form_data,
        )

        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")

    def test_validate_all_patterns_empty_form(
        self, setup_test_dependencies: Dict[str, Any]
    ) -> None:
        """Test validating with empty form."""
        form_data: Dict[str, str] = {}

        response = client.post(
            "/api/schedules/patterns/validate-all-patterns",
            data=form_data,
        )

        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")

    def test_validate_all_patterns_multiple_patterns(
        self, setup_test_dependencies: Dict[str, Any]
    ) -> None:
        """Test validating multiple patterns."""
        form_data = {
            "pattern_name": ["Pattern 1", "Pattern 2", "Pattern 3"],
            "pattern_expression": ["*.pdf", "*.log", "*.tmp"],
            "pattern_action": ["include", "exclude", "exclude_norec"],
            "pattern_style": ["sh", "fm", "re"],
        }

        response = client.post(
            "/api/schedules/patterns/validate-all-patterns",
            data=form_data,
        )

        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")

    def test_validate_all_patterns_with_invalid_patterns(
        self, setup_test_dependencies: Dict[str, Any]
    ) -> None:
        """Test validating patterns with some invalid ones."""
        form_data = {
            "pattern_name": ["Valid Pattern", "Invalid Pattern"],
            "pattern_expression": ["*.pdf", ""],  # Second has empty expression
            "pattern_action": ["include", "exclude"],
            "pattern_style": ["sh", "fm"],
        }

        response = client.post(
            "/api/schedules/patterns/validate-all-patterns",
            data=form_data,
        )

        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")

    def test_validate_all_patterns_error_handling(
        self, setup_test_dependencies: Dict[str, Any]
    ) -> None:
        """Test validate patterns endpoint error handling."""
        # This test simulates an unexpected error during validation
        # The endpoint should handle it gracefully and return error template

        # We can't easily simulate an internal error without mocking,
        # but we can test that the endpoint handles malformed data
        form_data = {
            "pattern_name": ["Test"],
            # Missing other required fields to potentially cause issues
        }

        response = client.post(
            "/api/schedules/patterns/validate-all-patterns",
            data=form_data,
        )

        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")

    # Test close-modal endpoint
    def test_close_patterns_modal(
        self, setup_test_dependencies: Dict[str, Any]
    ) -> None:
        """Test closing patterns modal without saving."""
        response = client.get("/api/schedules/patterns/close-modal")

        assert response.status_code == 200
        assert '<div id="modal-container"></div>' in response.text

    # Unit tests for helper functions
    def test_pattern_service_integration_extract_patterns(self) -> None:
        """Test PatternService integration with API endpoints."""
        from borgitory.services.scheduling.pattern_service import PatternService

        class MockFormData:
            def __init__(self, data: Dict[str, List[str]]) -> None:
                self.data = data

            def getlist(self, key: str) -> List[str]:
                return self.data.get(key, [])

        form_data = MockFormData(
            {
                "pattern_name": ["Test Pattern"],
                "pattern_expression": ["*.pdf"],
                "pattern_action": ["include"],
                "pattern_style": ["sh"],
            }
        )

        patterns = PatternService.extract_patterns_from_form(form_data)
        assert len(patterns) == 1
        assert patterns[0].name == "Test Pattern"
        assert patterns[0].expression == "*.pdf"

    def test_pattern_service_integration_convert_to_json(self) -> None:
        """Test PatternService JSON conversion integration."""
        from borgitory.services.scheduling.pattern_service import PatternService

        class MockFormData:
            def __init__(self, data: Dict[str, List[str]]) -> None:
                self.data = data

            def getlist(self, key: str) -> List[str]:
                return self.data.get(key, [])

        form_data = MockFormData(
            {
                "pattern_name": ["Pattern 1", "Pattern 2"],
                "pattern_expression": ["*.pdf", "*.log"],
                "pattern_action": ["include", "exclude"],
                "pattern_style": ["sh", "fm"],
            }
        )

        result = PatternService.convert_patterns_to_json(form_data)
        assert result is not None

        parsed = json.loads(result)
        assert len(parsed) == 2
        assert parsed[0]["name"] == "Pattern 1"
        assert parsed[1]["name"] == "Pattern 2"

    def test_pattern_service_integration_validation(self) -> None:
        """Test PatternService validation integration."""
        from borgitory.services.scheduling.pattern_service import PatternService

        class MockFormData:
            def __init__(self, data: Dict[str, List[str]]) -> None:
                self.data = data

            def getlist(self, key: str) -> List[str]:
                return self.data.get(key, [])

        # Valid patterns
        form_data = MockFormData(
            {
                "pattern_name": ["Valid Pattern"],
                "pattern_expression": ["*.pdf"],
                "pattern_action": ["include"],
                "pattern_style": ["sh"],
            }
        )

        is_valid, error = PatternService.validate_patterns_for_save(form_data)
        assert is_valid is True
        assert error is None

        # Invalid patterns
        form_data = MockFormData(
            {
                "pattern_name": [""],  # Empty name
                "pattern_expression": ["*.pdf"],
                "pattern_action": ["include"],
                "pattern_style": ["sh"],
            }
        )

        is_valid, error = PatternService.validate_patterns_for_save(form_data)
        assert is_valid is False
        assert error is not None
        assert "Pattern name is required" in error
