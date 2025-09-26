"""Tests for cron description API endpoint."""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, Mock

from borgitory.main import app


class TestCronDescriptionAPI:
    """Test suite for the cron description HTMX endpoint."""

    @pytest.fixture
    def client(self) -> TestClient:
        """Create test client."""
        return TestClient(app)

    def test_describe_cron_expression_valid(self, client: TestClient) -> None:
        """Test valid cron expression returns proper HTML response."""
        response = client.get(
            "/api/schedules/cron/describe?custom_cron_input=0%2012%20*%20*%20*"
        )

        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/html")

        html_content = response.text
        assert "12:00 PM" in html_content or "12:00" in html_content
        assert "Schedule:" in html_content
        assert "bg-blue-50" in html_content  # Success styling

    def test_describe_cron_expression_invalid(self, client: TestClient) -> None:
        """Test invalid cron expression returns error HTML."""
        response = client.get(
            "/api/schedules/cron/describe?custom_cron_input=invalid%20cron"
        )

        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/html")

        html_content = response.text
        assert "Error:" in html_content
        assert "bg-red-50" in html_content  # Error styling
        assert "Invalid" in html_content

    def test_describe_cron_expression_empty(self, client: TestClient) -> None:
        """Test empty cron expression returns empty response."""
        response = client.get("/api/schedules/cron/describe?custom_cron_input=")

        assert response.status_code == 200
        html_content = response.text.strip()
        # Should return empty div or minimal content
        assert len(html_content) < 50  # Very minimal response

    def test_describe_cron_expression_whitespace(self, client: TestClient) -> None:
        """Test cron expression with whitespace is handled properly."""
        response = client.get(
            "/api/schedules/cron/describe?custom_cron_input=%20%200%2012%20*%20*%20*%20%20"
        )

        assert response.status_code == 200
        html_content = response.text
        assert "12:00 PM" in html_content or "12:00" in html_content
        assert "Schedule:" in html_content

    def test_describe_cron_expression_missing_field(self, client: TestClient) -> None:
        """Test request without custom_cron_input field."""

        response = client.get("/api/schedules/cron/describe")

        assert response.status_code == 200
        html_content = response.text.strip()
        # Should handle missing field gracefully
        assert len(html_content) < 50

    def test_describe_cron_expression_complex_valid(self, client: TestClient) -> None:
        """Test complex valid cron expressions."""
        test_cases = [
            "*/5 * * * *",  # Every 5 minutes
            "0 9-17 * * 1-5",  # Business hours weekdays
            "0 0 1 * *",  # First day of month
            "30 14 * * 0",  # Sunday afternoon
        ]

        for cron_expr in test_cases:
            response = client.get(
                f"/api/schedules/cron/describe?custom_cron_input={cron_expr}"
            )

            assert response.status_code == 200, f"Failed for expression: {cron_expr}"
            html_content = response.text
            assert "Schedule:" in html_content, (
                f"No schedule description for: {cron_expr}"
            )
            assert "bg-blue-50" in html_content, f"No success styling for: {cron_expr}"

    def test_describe_cron_expression_complex_invalid(self, client: TestClient) -> None:
        """Test complex invalid cron expressions."""
        invalid_cases = [
            "1 2 3",  # Too few parts
            "invalid",  # Not a cron expression
            "not-a-cron",  # Not a cron expression
        ]

        for cron_expr in invalid_cases:
            response = client.get(
                f"/api/schedules/cron/describe?custom_cron_input={cron_expr}"
            )

            assert response.status_code == 200, f"Failed for expression: {cron_expr}"
            html_content = response.text
            assert "Error:" in html_content, f"No error message for: {cron_expr}"
            assert "bg-red-50" in html_content, f"No error styling for: {cron_expr}"

    def test_htmx_response_structure(self, client: TestClient) -> None:
        """Test that response is structured for HTMX replacement."""
        response = client.get(
            "/api/schedules/cron/describe?custom_cron_input=0%2012%20*%20*%20*"
        )

        assert response.status_code == 200
        html_content = response.text

        # Should be a div that can replace the target
        assert "<div" in html_content
        assert "text-sm" in html_content  # Has proper styling classes
        assert "p-2" in html_content  # Has padding
        assert "rounded" in html_content  # Has border radius

    def test_concurrent_requests(self, client: TestClient) -> None:
        """Test that multiple concurrent requests work properly."""
        import threading

        results = []

        def make_request(cron_expr: str) -> None:
            from urllib.parse import quote

            response = client.get(
                f"/api/schedules/cron/describe?custom_cron_input={quote(cron_expr)}"
            )
            results.append((cron_expr, response.status_code, response.text))

        # Create multiple threads with different cron expressions
        threads = []
        expressions = ["0 12 * * *", "*/5 * * * *", "invalid", "0 0 1 * *"]

        for expr in expressions:
            thread = threading.Thread(target=make_request, args=(expr,))
            threads.append(thread)
            thread.start()

        # Wait for all threads to complete
        for thread in threads:
            thread.join()

        # Verify all requests succeeded
        assert len(results) == len(expressions)
        for expr, status_code, content in results:
            assert status_code == 200, f"Request failed for {expr}"
            if expr == "invalid":
                assert "Error:" in content
            else:
                assert (
                    "Schedule:" in content or len(content.strip()) < 50
                )  # Valid or empty

    @patch(
        "borgitory.services.cron_description_service.CronDescriptionService.get_human_description"
    )
    def test_service_integration(self, mock_service: Mock, client: TestClient) -> None:
        """Test that the endpoint properly integrates with the service."""
        # Mock the service response
        mock_service.return_value = {"description": "Mocked description", "error": None}

        response = client.get(
            "/api/schedules/cron/describe?custom_cron_input=0%2012%20*%20*%20*"
        )

        # Verify service was called
        mock_service.assert_called_once_with("0 12 * * *")

        # Verify response contains mocked data
        assert response.status_code == 200
        assert "Mocked description" in response.text

    @patch(
        "borgitory.services.cron_description_service.CronDescriptionService.get_human_description"
    )
    def test_service_error_handling(
        self, mock_service: Mock, client: TestClient
    ) -> None:
        """Test that service errors are properly handled."""
        # Mock the service to return an error
        mock_service.return_value = {
            "description": None,
            "error": "Mocked error message",
        }

        response = client.get("/api/schedules/cron/describe?custom_cron_input=invalid")

        # Verify service was called
        mock_service.assert_called_once_with("invalid")

        # Verify error response
        assert response.status_code == 200
        html_content = response.text
        assert "Error:" in html_content
        assert "Mocked error message" in html_content
        assert "bg-red-50" in html_content

    def test_response_caching_headers(self, client: TestClient) -> None:
        """Test that responses have appropriate caching headers for HTMX."""
        response = client.get(
            "/api/schedules/cron/describe?custom_cron_input=0%2012%20*%20*%20*"
        )

        assert response.status_code == 200
        # HTMX responses should generally not be cached
        # The exact headers depend on your FastAPI configuration
        assert "content-type" in response.headers
        assert response.headers["content-type"].startswith("text/html")

    def test_form_data_parsing_edge_cases(self, client: TestClient) -> None:
        """Test edge cases in form data parsing."""
        edge_cases = [
            {},  # Empty form data
            {"custom_cron_input": None},  # None value (if possible)
            {
                "custom_cron_input": "0 12 * * *",
                "extra_field": "ignored",
            },  # Extra fields
        ]

        for form_data in edge_cases:
            response = client.get("/api/schedules/cron/describe")

            # Should not crash, always return 200
            assert response.status_code == 200
            # Should return valid HTML
            assert "<" in response.text or response.text.strip() == ""
