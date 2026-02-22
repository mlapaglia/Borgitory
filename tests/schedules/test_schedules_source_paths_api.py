"""
Tests for schedule source paths API endpoints in schedules.py

Tests all source-path-related endpoints using proper DI with mocks, no patches.
"""

import pytest
from typing import Any, Dict
from unittest.mock import AsyncMock, Mock
from httpx import AsyncClient
from fastapi.responses import HTMLResponse

from borgitory.main import app
from borgitory.dependencies import (
    get_schedule_service,
    get_templates,
    get_configuration_service,
)
from borgitory.services.scheduling.schedule_service import ScheduleService
from borgitory.services.configuration_service import ConfigurationService


class TestScheduleSourcePathsAPI:
    """Test the Schedule Source Paths API endpoints - HTMX/HTTP behavior"""

    @pytest.fixture(scope="function")
    def setup_test_dependencies(self) -> Dict[str, Any]:
        """Setup dependency overrides for each test."""
        mock_scheduler_service = AsyncMock()
        mock_scheduler_service.add_schedule.return_value = None
        mock_scheduler_service.update_schedule.return_value = None
        mock_scheduler_service.remove_schedule.return_value = None

        schedule_service = ScheduleService(mock_scheduler_service)
        configuration_service = ConfigurationService()

        mock_templates = Mock()
        captured_contexts: list[Dict[str, Any]] = []

        def mock_template_response(
            request: Any,
            template_name: str,
            context: Any = None,
            status_code: int = 200,
        ) -> HTMLResponse:
            captured_contexts.append(
                {"template": template_name, "context": context or {}}
            )
            return HTMLResponse(
                content=f"<div>Mock response for {template_name}</div>",
                status_code=status_code,
            )

        mock_templates.TemplateResponse = mock_template_response

        app.dependency_overrides[get_schedule_service] = lambda: schedule_service
        app.dependency_overrides[get_configuration_service] = (
            lambda: configuration_service
        )
        app.dependency_overrides[get_templates] = lambda: mock_templates

        return {
            "schedule_service": schedule_service,
            "configuration_service": configuration_service,
            "templates": mock_templates,
            "captured_contexts": captured_contexts,
        }

    def teardown_method(self) -> None:
        app.dependency_overrides.clear()

    # ── add-field endpoint ──────────────────────────────────────────────

    async def test_add_field_appends_empty_path(
        self, setup_test_dependencies: Dict[str, Any], async_client: AsyncClient
    ) -> None:
        """Adding a field should append one empty string to the paths list."""
        captured = setup_test_dependencies["captured_contexts"]
        json_data = {"source_paths": ["/data"]}

        response = await async_client.post(
            "/api/schedules/source-paths/add-field",
            json=json_data,
        )

        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")
        ctx = captured[-1]["context"]
        assert ctx["source_paths"] == ["/data", ""]

    async def test_add_field_with_multiple_existing_paths(
        self, setup_test_dependencies: Dict[str, Any], async_client: AsyncClient
    ) -> None:
        captured = setup_test_dependencies["captured_contexts"]
        json_data = {"source_paths": ["/src", "/Documents", "/Pictures"]}

        response = await async_client.post(
            "/api/schedules/source-paths/add-field",
            json=json_data,
        )

        assert response.status_code == 200
        ctx = captured[-1]["context"]
        assert ctx["source_paths"] == ["/src", "/Documents", "/Pictures", ""]

    async def test_add_field_empty_form(
        self, setup_test_dependencies: Dict[str, Any], async_client: AsyncClient
    ) -> None:
        """Adding a field with no existing paths should result in one empty path."""
        captured = setup_test_dependencies["captured_contexts"]
        json_data: Dict[str, Any] = {}

        response = await async_client.post(
            "/api/schedules/source-paths/add-field",
            json=json_data,
        )

        assert response.status_code == 200
        ctx = captured[-1]["context"]
        assert ctx["source_paths"] == [""]

    async def test_add_field_single_string_source_paths(
        self, setup_test_dependencies: Dict[str, Any], async_client: AsyncClient
    ) -> None:
        """json-enc sends a bare string when there's only one input with that name."""
        captured = setup_test_dependencies["captured_contexts"]
        json_data = {"source_paths": "/only-one"}

        response = await async_client.post(
            "/api/schedules/source-paths/add-field",
            json=json_data,
        )

        assert response.status_code == 200
        ctx = captured[-1]["context"]
        assert ctx["source_paths"] == ["/only-one", ""]

    async def test_add_field_preserves_entered_text(
        self, setup_test_dependencies: Dict[str, Any], async_client: AsyncClient
    ) -> None:
        captured = setup_test_dependencies["captured_contexts"]
        json_data = {"source_paths": ["/my/typed/path"]}

        response = await async_client.post(
            "/api/schedules/source-paths/add-field",
            json=json_data,
        )

        assert response.status_code == 200
        ctx = captured[-1]["context"]
        assert "/my/typed/path" in ctx["source_paths"]

    async def test_add_field_renders_correct_template(
        self, setup_test_dependencies: Dict[str, Any], async_client: AsyncClient
    ) -> None:
        captured = setup_test_dependencies["captured_contexts"]

        await async_client.post(
            "/api/schedules/source-paths/add-field",
            json={"source_paths": ["/data"]},
        )

        assert (
            captured[-1]["template"]
            == "partials/schedules/source_paths_container.html"
        )

    # ── remove-field endpoint ───────────────────────────────────────────

    async def test_remove_field_removes_by_index(
        self, setup_test_dependencies: Dict[str, Any], async_client: AsyncClient
    ) -> None:
        captured = setup_test_dependencies["captured_contexts"]
        json_data = {
            "source_paths": ["/keep", "/remove", "/also-keep"],
            "remove_index": 1,
        }

        response = await async_client.post(
            "/api/schedules/source-paths/remove-field",
            json=json_data,
        )

        assert response.status_code == 200
        ctx = captured[-1]["context"]
        assert ctx["source_paths"] == ["/keep", "/also-keep"]

    async def test_remove_field_first_index(
        self, setup_test_dependencies: Dict[str, Any], async_client: AsyncClient
    ) -> None:
        captured = setup_test_dependencies["captured_contexts"]
        json_data = {
            "source_paths": ["/first", "/second"],
            "remove_index": 0,
        }

        response = await async_client.post(
            "/api/schedules/source-paths/remove-field",
            json=json_data,
        )

        assert response.status_code == 200
        ctx = captured[-1]["context"]
        assert ctx["source_paths"] == ["/second"]

    async def test_remove_field_last_index(
        self, setup_test_dependencies: Dict[str, Any], async_client: AsyncClient
    ) -> None:
        captured = setup_test_dependencies["captured_contexts"]
        json_data = {
            "source_paths": ["/first", "/second", "/third"],
            "remove_index": 2,
        }

        response = await async_client.post(
            "/api/schedules/source-paths/remove-field",
            json=json_data,
        )

        assert response.status_code == 200
        ctx = captured[-1]["context"]
        assert ctx["source_paths"] == ["/first", "/second"]

    async def test_remove_last_remaining_path_leaves_empty(
        self, setup_test_dependencies: Dict[str, Any], async_client: AsyncClient
    ) -> None:
        """Removing the only path should leave one empty path so the UI isn't blank."""
        captured = setup_test_dependencies["captured_contexts"]
        json_data = {
            "source_paths": ["/only-path"],
            "remove_index": 0,
        }

        response = await async_client.post(
            "/api/schedules/source-paths/remove-field",
            json=json_data,
        )

        assert response.status_code == 200
        ctx = captured[-1]["context"]
        assert ctx["source_paths"] == [""]

    async def test_remove_field_out_of_range_index(
        self, setup_test_dependencies: Dict[str, Any], async_client: AsyncClient
    ) -> None:
        """Out-of-range index should leave the list unchanged."""
        captured = setup_test_dependencies["captured_contexts"]
        json_data = {
            "source_paths": ["/data"],
            "remove_index": 99,
        }

        response = await async_client.post(
            "/api/schedules/source-paths/remove-field",
            json=json_data,
        )

        assert response.status_code == 200
        ctx = captured[-1]["context"]
        assert ctx["source_paths"] == ["/data"]

    async def test_remove_field_negative_index(
        self, setup_test_dependencies: Dict[str, Any], async_client: AsyncClient
    ) -> None:
        """Negative index should leave the list unchanged."""
        captured = setup_test_dependencies["captured_contexts"]
        json_data = {
            "source_paths": ["/data"],
            "remove_index": -1,
        }

        response = await async_client.post(
            "/api/schedules/source-paths/remove-field",
            json=json_data,
        )

        assert response.status_code == 200
        ctx = captured[-1]["context"]
        assert ctx["source_paths"] == ["/data"]

    async def test_remove_field_invalid_index_string(
        self, setup_test_dependencies: Dict[str, Any], async_client: AsyncClient
    ) -> None:
        """Non-integer index should be handled gracefully."""
        captured = setup_test_dependencies["captured_contexts"]
        json_data = {
            "source_paths": ["/data", "/backup"],
            "remove_index": "abc",
        }

        response = await async_client.post(
            "/api/schedules/source-paths/remove-field",
            json=json_data,
        )

        assert response.status_code == 200
        ctx = captured[-1]["context"]
        assert ctx["source_paths"] == ["/data", "/backup"]

    async def test_remove_field_missing_index_defaults_to_zero(
        self, setup_test_dependencies: Dict[str, Any], async_client: AsyncClient
    ) -> None:
        """Missing remove_index should default to 0."""
        captured = setup_test_dependencies["captured_contexts"]
        json_data = {
            "source_paths": ["/first", "/second"],
        }

        response = await async_client.post(
            "/api/schedules/source-paths/remove-field",
            json=json_data,
        )

        assert response.status_code == 200
        ctx = captured[-1]["context"]
        assert ctx["source_paths"] == ["/second"]

    async def test_remove_field_empty_form(
        self, setup_test_dependencies: Dict[str, Any], async_client: AsyncClient
    ) -> None:
        """Empty JSON body should result in one empty path."""
        captured = setup_test_dependencies["captured_contexts"]
        json_data: Dict[str, Any] = {}

        response = await async_client.post(
            "/api/schedules/source-paths/remove-field",
            json=json_data,
        )

        assert response.status_code == 200
        ctx = captured[-1]["context"]
        assert ctx["source_paths"] == [""]

    async def test_remove_field_renders_correct_template(
        self, setup_test_dependencies: Dict[str, Any], async_client: AsyncClient
    ) -> None:
        captured = setup_test_dependencies["captured_contexts"]

        await async_client.post(
            "/api/schedules/source-paths/remove-field",
            json={"source_paths": ["/a", "/b"], "remove_index": 0},
        )

        assert (
            captured[-1]["template"]
            == "partials/schedules/source_paths_container.html"
        )
