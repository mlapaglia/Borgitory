"""
Simplified tests for job stop API endpoints
Tests that the endpoint calls the service correctly and returns HTML
"""

import uuid
import pytest
from fastapi.testclient import TestClient
from unittest.mock import Mock, AsyncMock

from borgitory.main import app
from borgitory.models.job_results import JobStopResult, JobStopError
from borgitory.dependencies import get_job_service


class TestJobStopAPISimple:
    """Simplified test job stop API endpoints"""

    @pytest.fixture
    def client(self) -> TestClient:
        """Create FastAPI test client"""
        return TestClient(app)

    @pytest.fixture
    def mock_job_service(self) -> Mock:
        """Create mock job service for API testing"""
        mock_service = Mock()
        return mock_service

    def test_stop_job_success_calls_service(
        self, client: TestClient, mock_job_service: Mock
    ) -> None:
        """Test that successful job stop calls the service correctly"""
        # Arrange
        job_id = uuid.uuid4()
        mock_job_service.stop_job = AsyncMock(
            return_value=JobStopResult(
                job_id=job_id,
                success=True,
                message="Job stopped successfully. 2 tasks skipped.",
                tasks_skipped=2,
                current_task_killed=True,
            )
        )

        # Override dependencies
        app.dependency_overrides[get_job_service] = lambda: mock_job_service

        try:
            # Act
            response = client.post(f"/api/jobs/{job_id}/stop")

            # Assert
            assert response.status_code == 200
            assert response.headers["content-type"] == "text/html; charset=utf-8"
            mock_job_service.stop_job.assert_called_once_with(job_id)

            # Verify response contains success indicators
            response_text = response.text
            assert "Job Stopped Successfully" in response_text
            assert "Job stopped successfully. 2 tasks skipped." in response_text

        finally:
            app.dependency_overrides.clear()

    def test_stop_job_error_calls_service(
        self, client: TestClient, mock_job_service: Mock
    ) -> None:
        """Test that job stop error calls the service correctly"""
        # Arrange
        job_id = uuid.uuid4()
        mock_job_service.stop_job = AsyncMock(
            return_value=JobStopError(
                job_id=job_id, error="Job not found", error_code="JOB_NOT_FOUND"
            )
        )

        # Override dependencies
        app.dependency_overrides[get_job_service] = lambda: mock_job_service

        try:
            # Act
            response = client.post(f"/api/jobs/{job_id}/stop")

            # Assert
            assert response.status_code == 400
            assert response.headers["content-type"] == "text/html; charset=utf-8"
            mock_job_service.stop_job.assert_called_once_with(job_id)

            # Verify response contains error indicators
            response_text = response.text
            assert "Failed to Stop Job" in response_text
            assert "Job not found" in response_text

        finally:
            app.dependency_overrides.clear()

    def test_stop_job_invalid_status_error(
        self, client: TestClient, mock_job_service: Mock
    ) -> None:
        """Test stopping job in invalid status returns proper error"""
        # Arrange
        job_id = uuid.uuid4()
        mock_job_service.stop_job = AsyncMock(
            return_value=JobStopError(
                job_id=job_id,
                error="Cannot stop job in status: completed",
                error_code="INVALID_STATUS",
            )
        )

        # Override dependencies
        app.dependency_overrides[get_job_service] = lambda: mock_job_service

        try:
            # Act
            response = client.post(f"/api/jobs/{job_id}/stop")

            # Assert
            assert response.status_code == 400
            assert "Cannot stop job in status: completed" in response.text
            assert "INVALID_STATUS" in response.text

        finally:
            app.dependency_overrides.clear()

    def test_stop_job_endpoint_path_validation(
        self, client: TestClient, mock_job_service: Mock
    ) -> None:
        """Test that the stop job endpoint is correctly routed"""
        # Arrange
        job_id = uuid.uuid4()
        mock_job_service.stop_job = AsyncMock(
            return_value=JobStopResult(
                job_id=job_id,
                success=True,
                message="Job stopped successfully.",
                tasks_skipped=1,
                current_task_killed=False,
            )
        )

        # Override dependencies
        app.dependency_overrides[get_job_service] = lambda: mock_job_service

        try:
            # Act - Test the exact endpoint path
            response = client.post(f"/api/jobs/{job_id}/stop")

            # Assert
            assert response.status_code == 200
            mock_job_service.stop_job.assert_called_once_with(job_id)

        finally:
            app.dependency_overrides.clear()

    def test_stop_job_method_not_allowed(self, client: TestClient) -> None:
        """Test that only POST method is allowed for stop endpoint"""
        job_id = uuid.uuid4()
        # Act & Assert - GET should not be allowed
        response = client.get(f"/api/jobs/{job_id}/stop")
        assert response.status_code == 405  # Method Not Allowed

        # Act & Assert - PUT should not be allowed
        response = client.put(f"/api/jobs/{job_id}/stop")
        assert response.status_code == 405  # Method Not Allowed

        # Act & Assert - DELETE should not be allowed
        response = client.delete(f"/api/jobs/{job_id}/stop")
        assert response.status_code == 405  # Method Not Allowed

    def test_stop_job_success_with_task_details(
        self, client: TestClient, mock_job_service: Mock
    ) -> None:
        """Test successful job stop with task details in response"""
        # Arrange
        job_id = uuid.uuid4()
        mock_job_service.stop_job = AsyncMock(
            return_value=JobStopResult(
                job_id=job_id,
                success=True,
                message="Job stopped successfully. 3 tasks skipped.",
                tasks_skipped=3,
                current_task_killed=True,
            )
        )

        # Override dependencies
        app.dependency_overrides[get_job_service] = lambda: mock_job_service

        try:
            # Act
            response = client.post(f"/api/jobs/{job_id}/stop")

            # Assert
            assert response.status_code == 200
            response_text = response.text
            assert "3 remaining tasks were skipped" in response_text
            assert "Current running task was terminated" in response_text

        finally:
            app.dependency_overrides.clear()

    def test_stop_job_no_tasks_skipped(
        self, client: TestClient, mock_job_service: Mock
    ) -> None:
        """Test stopping job with no remaining tasks"""
        # Arrange
        job_id = uuid.uuid4()
        mock_job_service.stop_job = AsyncMock(
            return_value=JobStopResult(
                job_id=job_id,
                success=True,
                message="Job stopped successfully. 0 tasks skipped.",
                tasks_skipped=0,
                current_task_killed=True,
            )
        )

        # Override dependencies
        app.dependency_overrides[get_job_service] = lambda: mock_job_service

        try:
            # Act
            response = client.post(f"/api/jobs/{job_id}/stop")

            # Assert
            assert response.status_code == 200
            response_text = response.text
            # Should show that current task was terminated but no tasks were skipped
            assert "Current running task was terminated" in response_text
            # The template should show the message as-is, which includes "0 tasks skipped"
            assert "Job stopped successfully. 0 tasks skipped." in response_text

        finally:
            app.dependency_overrides.clear()
