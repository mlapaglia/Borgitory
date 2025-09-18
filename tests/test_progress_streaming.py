"""
Tests for repository statistics progress streaming functionality
"""

import pytest
import asyncio
from typing import Any, Callable, Optional, List
from unittest.mock import Mock
from httpx import AsyncClient, ASGITransport

from borgitory.main import app
from borgitory.models.database import Repository, get_db
from borgitory.services.repositories.repository_stats_service import (
    RepositoryStatsService,
)
from borgitory.dependencies import get_repository_stats_service


class TestProgressStreaming:
    """Test suite for SSE progress streaming during repository statistics generation"""

    @pytest.fixture
    def mock_repository(self) -> Mock:
        """Create a mock repository for testing"""
        repo = Mock(spec=Repository)
        repo.id = 1
        repo.name = "test-repo"
        repo.path = "/test/repo"
        repo.get_passphrase.return_value = "test-passphrase"
        return repo

    @pytest.fixture
    def mock_db(self) -> Mock:
        """Create a mock database session"""
        db = Mock()
        return db

    @pytest.mark.asyncio
    async def test_progress_streaming_basic_flow(
        self, mock_repository: Mock, mock_db: Mock
    ) -> None:
        """Test that progress streaming sends expected SSE events"""

        # Override database dependency
        def override_get_db() -> Mock:
            mock_db.query.return_value.filter.return_value.first.return_value = (
                mock_repository
            )
            return mock_db

        app.dependency_overrides[get_db] = override_get_db

        # Mock the stats service to call progress callback with test data
        async def mock_get_stats(
            repo: Any, db: Any, progress_callback: Optional[Callable[..., None]] = None
        ) -> dict[str, Any]:
            if progress_callback:
                # Simulate the progress flow with small delays to allow queue processing
                progress_callback("Initializing repository analysis...", 5)
                await asyncio.sleep(0.01)
                progress_callback("Scanning repository for archives...", 10)
                await asyncio.sleep(0.01)
                progress_callback("Found 3 archives. Analyzing archive details...", 15)
                await asyncio.sleep(0.01)
                progress_callback("Analyzing archive 1/3: test-archive-1", 25)
                await asyncio.sleep(0.01)
                progress_callback("Analyzing archive 2/3: test-archive-2", 35)
                await asyncio.sleep(0.01)
                progress_callback("Building size and compression statistics...", 65)
                await asyncio.sleep(0.01)
                progress_callback("Finalizing statistics and building charts...", 90)
                await asyncio.sleep(0.01)
                progress_callback("Statistics analysis complete!", 100)

            return {
                "repository_path": repo.path,
                "total_archives": 3,
                "summary": {"total_archives": 3},
            }

        # Mock the dependency injection
        mock_stats_service = Mock(spec=RepositoryStatsService)
        mock_stats_service.get_repository_statistics.side_effect = mock_get_stats

        app.dependency_overrides[get_repository_stats_service] = (
            lambda: mock_stats_service
        )

        try:
            # Use AsyncClient for SSE endpoint testing
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as ac:
                # Make request to progress streaming endpoint
                response = await ac.get(
                    f"/api/repositories/{mock_repository.id}/stats/progress"
                )

                assert response.status_code == 200
                assert (
                    response.headers["content-type"]
                    == "text/event-stream; charset=utf-8"
                )

                # Parse SSE events from response
                events = self._parse_sse_events(response.text)

                # Verify we received expected events
                progress_events = [e for e in events if e["event"] == "progress"]
                progress_bar_events = [
                    e for e in events if e["event"] == "progress-bar"
                ]
                complete_events = [e for e in events if e["event"] == "complete"]

                # Should have multiple progress messages (at least a few)
                assert len(progress_events) >= 3, (
                    f"Should have at least 3 progress messages, got {len(progress_events)}"
                )

                # Should have corresponding progress bar updates
                assert len(progress_bar_events) >= 3, (
                    f"Should have at least 3 progress bar updates, got {len(progress_bar_events)}"
                )

                # Should have completion event
                assert len(complete_events) == 1, (
                    "Should have exactly 1 completion event"
                )

                # Verify progress percentages are increasing
                percentages = []
                for event in progress_bar_events:
                    # Extract percentage from HTML
                    html = event["data"]
                    if "width:" in html and "%" in html:
                        percent_str = html.split("width: ")[1].split("%")[0]
                        percentages.append(int(percent_str))

                # Only validate if we got percentages
                if percentages:
                    assert percentages == sorted(percentages), (
                        "Progress percentages should be increasing"
                    )
                    assert percentages[0] >= 5, "Should start at least at 5%"
                    if len(percentages) > 1:
                        assert percentages[-1] >= percentages[0], (
                            "Should progress forward"
                        )
        finally:
            # Clean up dependency override
            if get_repository_stats_service in app.dependency_overrides:
                del app.dependency_overrides[get_repository_stats_service]

    @pytest.mark.asyncio
    async def test_progress_streaming_error_handling(
        self, mock_repository: Mock, mock_db: Mock
    ) -> None:
        """Test that errors are properly streamed via SSE"""

        # Override database dependency
        def override_get_db() -> Mock:
            mock_db.query.return_value.filter.return_value.first.return_value = (
                mock_repository
            )
            return mock_db

        app.dependency_overrides[get_db] = override_get_db

        # Mock the stats service to return an error
        async def mock_get_stats_error(
            repo: Any, db: Any, progress_callback: Optional[Callable[..., None]] = None
        ) -> dict[str, Any]:
            if progress_callback:
                progress_callback("Initializing repository analysis...", 5)
                await asyncio.sleep(0.01)
                progress_callback("Scanning repository for archives...", 10)
                await asyncio.sleep(0.01)

            return {"error": "No archives found in repository"}

        # Mock the dependency injection for error case
        mock_stats_service = Mock(spec=RepositoryStatsService)
        mock_stats_service.get_repository_statistics.side_effect = mock_get_stats_error

        app.dependency_overrides[get_repository_stats_service] = (
            lambda: mock_stats_service
        )

        try:
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as ac:
                response = await ac.get(
                    f"/api/repositories/{mock_repository.id}/stats/progress"
                )

                assert response.status_code == 200

                events = self._parse_sse_events(response.text)

                # Should have progress events before error
                progress_events = [e for e in events if e["event"] == "progress"]
                error_events = [e for e in events if e["event"] == "error"]

                assert len(progress_events) >= 1, (
                    f"Should have initial progress messages, got {len(progress_events)}"
                )
                assert len(error_events) == 1, "Should have exactly 1 error event"

                # Verify error message format
                error_html = error_events[0]["data"]
                assert "text-red-700" in error_html, (
                    "Error should be styled with red text"
                )
                assert "No archives found" in error_html, (
                    "Error should contain expected message"
                )

        finally:
            # Clean up dependency override
            if get_repository_stats_service in app.dependency_overrides:
                del app.dependency_overrides[get_repository_stats_service]

    @pytest.mark.asyncio
    async def test_progress_streaming_repository_not_found(self, mock_db: Mock) -> None:
        """Test handling of non-existent repository"""

        # Override database dependency
        def override_get_db() -> Mock:
            mock_db.query.return_value.filter.return_value.first.return_value = None
            return mock_db

        app.dependency_overrides[get_db] = override_get_db

        try:
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as ac:
                response = await ac.get("/api/repositories/999/stats/progress")

                assert response.status_code == 404
                assert "Repository not found" in response.text
        finally:
            # Clean up dependency override
            app.dependency_overrides.clear()

    def test_progress_streaming_html_template_elements(self) -> None:
        """Test that loading template has correct SSE swap elements"""
        from fastapi.templating import Jinja2Templates
        from fastapi import Request
        from unittest.mock import MagicMock

        templates = Jinja2Templates(directory="src/borgitory/templates")

        # Mock request object
        mock_request = MagicMock(spec=Request)

        # Render template
        response = templates.TemplateResponse(
            mock_request, "partials/statistics/loading_state.html", {"repository_id": 1}
        )

        html_content = bytes(response.body).decode()

        # Verify SSE connection is set up
        assert 'hx-ext="sse"' in html_content, "Should have SSE extension"
        assert 'sse-connect="/api/repositories/1/stats/progress"' in html_content, (
            "Should connect to progress endpoint"
        )

        # Verify SSE swap elements
        assert 'sse-swap="progress"' in html_content, (
            "Should have progress message swap"
        )
        assert 'sse-swap="progress-bar"' in html_content, (
            "Should have progress bar swap"
        )
        assert 'sse-swap="error"' in html_content, "Should have error message swap"
        assert 'sse-swap="complete"' in html_content, "Should have completion handler"

        # Verify progress bar structure
        assert 'id="progress-bar-inner"' in html_content, (
            "Should have progress bar inner element"
        )
        assert "bg-gray-200 dark:bg-gray-700 rounded-full h-2" in html_content, (
            "Should have progress track"
        )

    def _parse_sse_events(self, sse_text: str) -> List[dict[str, str]]:
        """Parse SSE response text into event objects"""
        events = []
        current_event = {}

        for line in sse_text.split("\n"):
            line = line.strip()

            if line.startswith("event:"):
                current_event["event"] = line.split("event:", 1)[1].strip()
            elif line.startswith("data:"):
                current_event["data"] = line.split("data:", 1)[1].strip()
            elif line == "" and current_event:
                # End of event
                events.append(current_event)
                current_event = {}

        return events

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_full_progress_streaming_integration(self) -> None:
        """
        Integration test that verifies the complete progress streaming flow
        This test requires a test repository to be available
        """
        # This would test with actual borg commands if test repo exists
        # Skip for now since it requires external dependencies
        pytest.skip("Integration test requires test borg repository")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
