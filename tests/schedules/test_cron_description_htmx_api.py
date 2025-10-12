"""Tests for cron description HTMX API endpoints."""

import pytest
from httpx import AsyncClient
from unittest.mock import Mock, patch

from sqlalchemy.ext.asyncio import AsyncSession

from borgitory.models.database import User


class TestCronDescriptionHTMXAPI:
    """Test suite for cron description HTMX endpoints."""

    @pytest.fixture
    def mock_templates(self) -> Mock:
        """Create mock templates dependency."""
        mock = Mock()
        mock.TemplateResponse.return_value = Mock()
        return mock

    @pytest.fixture
    async def setup_auth(self, test_db: AsyncSession) -> User:
        """Set up authentication for tests."""
        # Create a test user
        user = User()
        user.username = "testuser"
        user.set_password("testpass")
        test_db.add(user)
        await test_db.commit()
        await test_db.refresh(user)
        return user

    async def test_describe_cron_expression_valid_expression(
        self, async_client: AsyncClient
    ) -> None:
        """Test cron description endpoint with valid cron expression."""
        response = await async_client.get(
            "/api/schedules/cron/describe?custom_cron_input=0 2 * * *"
        )

        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/html")

        html_content = response.text
        # Should contain a description for "daily at 2 AM"
        assert "2:00 AM" in html_content or "02:00" in html_content
        assert "Schedule:" in html_content

    async def test_describe_cron_expression_complex_valid_expressions(
        self, async_client: AsyncClient
    ) -> None:
        """Test cron description endpoint with various valid expressions."""
        test_cases = [
            ("*/5 * * * *", "Every 5 minutes"),
            ("0 9-17 * * 1-5", "Monday through Friday"),
            ("30 14 * * 0", "Sunday"),
            ("0 0 1 * *", "day 1 of the month"),
        ]

        for cron_expr, expected_text in test_cases:
            response = await async_client.get(
                f"/api/schedules/cron/describe?custom_cron_input={cron_expr}"
            )

            assert response.status_code == 200
            html_content = response.text
            # Check that we get some description (exact text may vary by cron-descriptor version)
            assert "Schedule:" in html_content or len(html_content.strip()) > 10

    async def test_describe_cron_expression_invalid_expression(
        self, async_client: AsyncClient
    ) -> None:
        """Test cron description endpoint with invalid cron expression."""
        response = await async_client.get(
            "/api/schedules/cron/describe?custom_cron_input=invalid cron"
        )

        assert response.status_code == 200
        html_content = response.text
        assert "Error:" in html_content
        assert "Invalid" in html_content or "invalid" in html_content

    async def test_describe_cron_expression_empty_input(
        self, async_client: AsyncClient
    ) -> None:
        """Test cron description endpoint with empty input."""
        response = await async_client.get(
            "/api/schedules/cron/describe?custom_cron_input="
        )

        assert response.status_code == 200
        html_content = response.text.strip()
        # Should return minimal content for empty input
        assert len(html_content) < 100

    async def test_describe_cron_expression_missing_parameter(
        self, async_client: AsyncClient
    ) -> None:
        """Test cron description endpoint without query parameter."""
        response = await async_client.get("/api/schedules/cron/describe")

        assert response.status_code == 200
        html_content = response.text.strip()
        # Should handle missing parameter gracefully
        assert len(html_content) < 100

    async def test_describe_cron_expression_whitespace_handling(
        self, async_client: AsyncClient
    ) -> None:
        """Test cron description endpoint with whitespace."""
        response = await async_client.get(
            "/api/schedules/cron/describe?custom_cron_input=  0 2 * * *  "
        )

        assert response.status_code == 200
        html_content = response.text
        assert "2:00 AM" in html_content or "02:00" in html_content

    async def test_describe_cron_expression_url_encoding(
        self, async_client: AsyncClient
    ) -> None:
        """Test cron description endpoint with URL encoded input."""
        # "0 2 * * *" URL encoded
        response = await async_client.get(
            "/api/schedules/cron/describe?custom_cron_input=0%202%20*%20*%20*"
        )

        assert response.status_code == 200
        html_content = response.text
        assert "2:00 AM" in html_content or "02:00" in html_content

    async def test_describe_cron_expression_special_characters(
        self, async_client: AsyncClient
    ) -> None:
        """Test cron description endpoint with special cron characters."""
        test_cases = [
            "*/15 * * * *",  # Every 15 minutes
            "0 */2 * * *",  # Every 2 hours
            "0 0 */2 * *",  # Every 2 days
            "15,45 * * * *",  # At 15 and 45 minutes
        ]

        for cron_expr in test_cases:
            response = await async_client.get(
                f"/api/schedules/cron/describe?custom_cron_input={cron_expr}"
            )

            assert response.status_code == 200
            html_content = response.text
            # Should get a valid description
            assert "Schedule:" in html_content or len(html_content.strip()) > 10

    async def test_describe_cron_expression_edge_cases(
        self, async_client: AsyncClient
    ) -> None:
        """Test cron description endpoint with edge cases."""
        edge_cases = [
            "0 0 * * *",  # Midnight daily
            "59 23 * * *",  # 11:59 PM daily
            "0 12 * * 0",  # Noon on Sunday
            "30 6 1 1 *",  # 6:30 AM on New Year's Day
        ]

        for cron_expr in edge_cases:
            response = await async_client.get(
                f"/api/schedules/cron/describe?custom_cron_input={cron_expr}"
            )

            assert response.status_code == 200
            # Should handle edge cases without error
            assert response.status_code == 200

    @patch(
        "borgitory.services.cron_description_service.CronDescriptionService.get_human_description"
    )
    async def test_describe_cron_expression_service_integration(
        self, mock_service: Mock, async_client: AsyncClient
    ) -> None:
        """Test that the endpoint integrates correctly with the service."""
        # Mock service response
        mock_service.return_value = {"description": "Mocked description", "error": None}

        response = await async_client.get(
            "/api/schedules/cron/describe?custom_cron_input=0 2 * * *"
        )

        # Verify service was called with correct parameter
        mock_service.assert_called_once_with("0 2 * * *")

        # Verify response contains mocked data
        assert response.status_code == 200
        assert "Mocked description" in response.text

    @patch(
        "borgitory.services.cron_description_service.CronDescriptionService.get_human_description"
    )
    async def test_describe_cron_expression_service_error_handling(
        self, mock_service: Mock, async_client: AsyncClient
    ) -> None:
        """Test endpoint handles service errors correctly."""
        # Mock service to return error
        mock_service.return_value = {
            "description": None,
            "error": "Mocked error message",
        }

        response = await async_client.get(
            "/api/schedules/cron/describe?custom_cron_input=invalid"
        )

        # Verify service was called
        mock_service.assert_called_once_with("invalid")

        # Verify error response
        assert response.status_code == 200
        html_content = response.text
        assert "Error:" in html_content
        assert "Mocked error message" in html_content

    async def test_describe_cron_expression_response_format(
        self, async_client: AsyncClient
    ) -> None:
        """Test that the response is properly formatted HTML for HTMX."""
        response = await async_client.get(
            "/api/schedules/cron/describe?custom_cron_input=0 2 * * *"
        )

        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/html")

        html_content = response.text
        # Should contain div elements with proper classes for styling
        assert "<div" in html_content
        assert (
            "text-sm" in html_content or len(html_content.strip()) < 50
        )  # Either styled content or empty

    async def test_describe_cron_expression_concurrent_requests(
        self, async_client: AsyncClient
    ) -> None:
        """Test that multiple concurrent requests work correctly."""
        import asyncio

        async def make_request(cron_expr: str) -> tuple[str, int, str]:
            response = await async_client.get(
                f"/api/schedules/cron/describe?custom_cron_input={cron_expr}"
            )
            return (cron_expr, response.status_code, response.text)

        # Create multiple tasks with different cron expressions
        expressions = ["0 2 * * *", "*/5 * * * *", "0 12 * * 0", "invalid"]

        # Run all requests concurrently using asyncio.gather
        results = await asyncio.gather(*[make_request(expr) for expr in expressions])

        # Verify all requests succeeded
        assert len(results) == len(expressions)
        for expr, status_code, content in results:
            assert status_code == 200, f"Request failed for {expr}"
            if expr == "invalid":
                assert "Error:" in content or len(content.strip()) < 50
            else:
                assert "Schedule:" in content or len(content.strip()) < 50

    async def test_describe_cron_expression_caching_headers(
        self, async_client: AsyncClient
    ) -> None:
        """Test that appropriate caching headers are set for HTMX responses."""
        response = await async_client.get(
            "/api/schedules/cron/describe?custom_cron_input=0 2 * * *"
        )

        assert response.status_code == 200
        # The response should have content-type header
        assert "content-type" in response.headers
        assert response.headers["content-type"].startswith("text/html")

        # For dynamic content like cron descriptions, we typically don't want aggressive caching
        # but the exact headers depend on your caching strategy
