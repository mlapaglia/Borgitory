"""
Tests for repository statistics HTML endpoint functionality
"""

import pytest
from typing import Any
from unittest.mock import Mock
from httpx import AsyncClient, ASGITransport

from borgitory.main import app
from borgitory.models.database import Repository, get_db
from borgitory.services.repositories.repository_stats_service import (
    RepositoryStatsService,
)
from borgitory.dependencies import get_repository_stats_service


class TestRepositoryStatsHTML:
    """Test suite for synchronous repository statistics HTML generation"""

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
    async def test_stats_html_basic_flow(
        self, mock_repository: Mock, mock_db: Mock
    ) -> None:
        """Test that stats HTML endpoint returns complete HTML with charts"""

        # Override database dependency
        def override_get_db() -> Mock:
            mock_db.query.return_value.filter.return_value.first.return_value = (
                mock_repository
            )
            return mock_db

        app.dependency_overrides[get_db] = override_get_db

        # Mock the stats service to return test data
        async def mock_get_stats(
            repo: Any, db: Any, progress_callback=None
        ) -> dict[str, Any]:
            return {
                "repository_path": repo.path,
                "total_archives": 3,
                "archive_stats": [],
                "size_over_time": {
                    "labels": ["2023-01-01"],
                    "datasets": [{"label": "Original Size", "data": [100]}],
                },
                "dedup_compression_stats": {
                    "labels": ["2023-01-01"],
                    "datasets": [{"label": "Compression", "data": [25]}],
                },
                "file_type_stats": {
                    "count_chart": {"labels": ["2023-01-01"], "datasets": []},
                    "size_chart": {"labels": ["2023-01-01"], "datasets": []},
                },
                "summary": {
                    "total_archives": 3,
                    "latest_archive_date": "2023-01-01",
                    "total_original_size_gb": 1.0,
                    "total_compressed_size_gb": 0.75,
                    "total_deduplicated_size_gb": 0.5,
                    "overall_compression_ratio": 25.0,
                    "overall_deduplication_ratio": 33.3,
                    "space_saved_gb": 0.5,
                    "average_archive_size_gb": 0.33,
                },
            }

        # Mock the dependency injection
        mock_stats_service = Mock(spec=RepositoryStatsService)
        mock_stats_service.get_repository_statistics.side_effect = mock_get_stats

        app.dependency_overrides[get_repository_stats_service] = (
            lambda: mock_stats_service
        )

        try:
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as ac:
                # Make request to HTML stats endpoint
                response = await ac.get(
                    f"/api/repositories/{mock_repository.id}/stats/html"
                )

                assert response.status_code == 200
                assert "text/html" in response.headers["content-type"]

                html_content = response.text

                # Verify HTML contains expected elements
                assert "Total Archives" in html_content
                assert "Space Saved" in html_content
                assert "Compression" in html_content
                assert "Deduplication" in html_content

                # Verify chart elements are present
                assert 'id="sizeChart"' in html_content
                assert 'id="ratioChart"' in html_content
                assert 'id="fileTypeCountChart"' in html_content
                assert 'id="fileTypeSizeChart"' in html_content

                # Verify chart data is embedded
                assert 'id="chart-data"' in html_content
                assert "data-size-chart=" in html_content
                assert "data-ratio-chart=" in html_content

                # Verify inline chart initialization script is present
                assert "new Chart(" in html_content
                assert "Error initializing charts" in html_content

        finally:
            # Clean up dependency override
            if get_repository_stats_service in app.dependency_overrides:
                del app.dependency_overrides[get_repository_stats_service]

    @pytest.mark.asyncio
    async def test_stats_html_error_handling(
        self, mock_repository: Mock, mock_db: Mock
    ) -> None:
        """Test that errors are properly returned as HTML"""

        # Override database dependency
        def override_get_db() -> Mock:
            mock_db.query.return_value.filter.return_value.first.return_value = (
                mock_repository
            )
            return mock_db

        app.dependency_overrides[get_db] = override_get_db

        # Mock the stats service to return an error
        async def mock_get_stats_error(
            repo: Any, db: Any, progress_callback=None
        ) -> dict[str, Any]:
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
                    f"/api/repositories/{mock_repository.id}/stats/html"
                )

                assert response.status_code == 500
                assert "text/html" in response.headers["content-type"]

                html_content = response.text

                # Verify error message format
                assert "text-red-700" in html_content, (
                    "Error should be styled with red text"
                )
                assert "No archives found" in html_content, (
                    "Error should contain expected message"
                )

        finally:
            # Clean up dependency override
            if get_repository_stats_service in app.dependency_overrides:
                del app.dependency_overrides[get_repository_stats_service]

    @pytest.mark.asyncio
    async def test_stats_html_repository_not_found(self, mock_db: Mock) -> None:
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
                # The cancel_on_disconnect decorator wraps HTTPException in an ExceptionGroup
                # In testing, this causes the client to raise the exception instead of returning a response
                try:
                    response = await ac.get("/api/repositories/999/stats/html")

                    # If we get a response, it should be 404
                    assert response.status_code == 404
                    response_data = response.json()
                    assert "Repository not found" in response_data["detail"]

                except Exception as e:
                    # The exception was wrapped - check that it contains our HTTPException
                    exception_str = str(e)
                    # Check if it's an exception group and look for the inner HTTPException
                    if hasattr(e, "exceptions"):
                        # It's an ExceptionGroup - check the inner exceptions
                        found_repo_error = False
                        for inner_exc in e.exceptions:
                            if "Repository not found" in str(inner_exc):
                                found_repo_error = True
                                break
                        assert found_repo_error, (
                            f"Expected 'Repository not found' in inner exceptions, got: {[str(exc) for exc in e.exceptions]}"
                        )
                    else:
                        # Regular exception
                        assert "Repository not found" in exception_str
        finally:
            # Clean up dependency override
            app.dependency_overrides.clear()

    def test_loading_state_html_template_elements(self) -> None:
        """Test that loading template has correct HTMX elements"""
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

        # Verify HTMX attributes are set up
        assert 'hx-get="/api/repositories/1/stats/html"' in html_content, (
            "Should have hx-get to stats HTML endpoint"
        )
        assert 'hx-target="#statistics-content"' in html_content, (
            "Should target statistics content div"
        )
        assert 'hx-swap="innerHTML"' in html_content, "Should swap innerHTML"
        assert 'hx-trigger="load"' in html_content, "Should trigger on load"

        # Verify loading spinner structure
        assert "animate-spin" in html_content, "Should have loading spinner"
        assert "Loading repository statistics" in html_content, (
            "Should have loading message"
        )

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_full_stats_html_integration(self) -> None:
        """
        Integration test that verifies the complete stats HTML generation flow
        This test requires a test repository to be available
        """
        # This would test with actual borg commands if test repo exists
        # Skip for now since it requires external dependencies
        pytest.skip("Integration test requires test borg repository")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
