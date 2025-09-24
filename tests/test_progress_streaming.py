"""
Tests for repository statistics HTML endpoint functionality
"""

import pytest
from unittest.mock import Mock

from borgitory.models.database import Repository


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
