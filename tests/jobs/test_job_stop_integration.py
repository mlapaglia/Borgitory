"""
Integration tests for job stop functionality
Tests full flow with real database and services
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from unittest.mock import Mock, AsyncMock

from borgitory.main import app
from borgitory.models.database import Repository, Job
from borgitory.utils.datetime_utils import now_utc
from borgitory.models.database import get_db
from borgitory.dependencies import get_job_manager_dependency


class TestJobStopIntegration:
    """Integration tests for job stop functionality"""

    @pytest.fixture
    def client(self) -> TestClient:
        """Create FastAPI test client"""
        return TestClient(app)

    @pytest.fixture
    def mock_job_manager(self) -> Mock:
        """Create mock job manager for integration testing"""
        mock_manager = Mock()
        return mock_manager

    def test_stop_database_job_full_integration(
        self, client: TestClient, test_db: Session, mock_job_manager: Mock
    ) -> None:
        """Test stopping a database job through full API integration"""
        # Arrange - Create real database entities
        repository = Repository()
        repository.name = "integration-test-repo"
        repository.path = "/tmp/integration-test"
        repository.set_passphrase("test-passphrase")
        test_db.add(repository)
        test_db.flush()

        job = Job()
        job.id = "db-job"  # Short ID to trigger database path
        job.repository_id = repository.id
        job.type = "backup"  # Required field
        job.status = "running"
        job.started_at = now_utc()
        job.job_type = "simple"  # This is the correct field name
        test_db.add(job)
        test_db.commit()

        # Override dependencies with real database and mock job manager
        app.dependency_overrides[get_db] = lambda: test_db
        app.dependency_overrides[get_job_manager_dependency] = lambda: mock_job_manager

        try:
            # Act
            response = client.post("/api/jobs/db-job/stop")

            # Assert
            assert response.status_code == 200

            # Verify database was updated
            updated_job = test_db.query(Job).filter(Job.id == "db-job").first()
            assert updated_job is not None
            assert updated_job.status == "stopped"
            assert updated_job.error == "Manually stopped by user"
            assert updated_job.finished_at is not None

            # Verify response contains success message
            response_text = response.text
            assert "Job Stopped Successfully" in response_text
            assert "Database job stopped successfully" in response_text

        finally:
            app.dependency_overrides.clear()

    def test_stop_composite_job_full_integration(
        self, client: TestClient, test_db: Session, mock_job_manager: Mock
    ) -> None:
        """Test stopping a composite job through full API integration"""
        # Arrange - Mock job manager for composite job
        job_id = "composite-integration-job-123456789012"
        mock_job_manager.stop_job = AsyncMock(
            return_value={
                "success": True,
                "message": "Job stopped successfully. 3 tasks skipped.",
                "tasks_skipped": 3,
                "current_task_killed": True,
            }
        )

        # Override dependencies
        app.dependency_overrides[get_db] = lambda: test_db
        app.dependency_overrides[get_job_manager_dependency] = lambda: mock_job_manager

        try:
            # Act
            response = client.post(f"/api/jobs/{job_id}/stop")

            # Assert
            assert response.status_code == 200
            mock_job_manager.stop_job.assert_called_once_with(job_id)

            # Verify response contains success message
            response_text = response.text
            assert "Job Stopped Successfully" in response_text
            assert "Job stopped successfully. 3 tasks skipped." in response_text
            assert "3 remaining tasks were skipped" in response_text
            assert "Current running task was terminated" in response_text

        finally:
            app.dependency_overrides.clear()

    def test_stop_job_not_found_integration(
        self, client: TestClient, test_db: Session, mock_job_manager: Mock
    ) -> None:
        """Test stopping non-existent job through full API integration"""
        # Arrange - Mock job manager to return not found
        job_id = "non-existent-integration-job-123456789012"
        mock_job_manager.stop_job = AsyncMock(
            return_value={
                "success": False,
                "error": "Job not found",
                "error_code": "JOB_NOT_FOUND",
            }
        )

        # Override dependencies
        app.dependency_overrides[get_db] = lambda: test_db
        app.dependency_overrides[get_job_manager_dependency] = lambda: mock_job_manager

        try:
            # Act
            response = client.post(f"/api/jobs/{job_id}/stop")

            # Assert
            assert response.status_code == 400

            # Verify response contains error message
            response_text = response.text
            assert "Failed to Stop Job" in response_text
            assert "Job not found" in response_text
            assert "Error Code: JOB_NOT_FOUND" in response_text

        finally:
            app.dependency_overrides.clear()

    def test_stop_job_invalid_status_integration(
        self, client: TestClient, test_db: Session, mock_job_manager: Mock
    ) -> None:
        """Test stopping job in invalid status through full API integration"""
        # Arrange - Create completed database job
        repository = Repository()
        repository.name = "completed-job-repo"
        repository.path = "/tmp/completed-job"
        repository.set_passphrase("test-passphrase")
        test_db.add(repository)
        test_db.flush()

        job = Job()
        job.id = "comp-job"  # Short ID to trigger database path
        job.repository_id = repository.id
        job.type = "backup"  # Required field
        job.status = "completed"
        job.started_at = now_utc()
        job.finished_at = now_utc()
        job.job_type = "simple"  # This is the correct field name
        test_db.add(job)
        test_db.commit()

        # Override dependencies
        app.dependency_overrides[get_db] = lambda: test_db
        app.dependency_overrides[get_job_manager_dependency] = lambda: mock_job_manager

        try:
            # Act
            response = client.post("/api/jobs/comp-job/stop")

            # Assert
            assert response.status_code == 400

            # Verify response contains error message
            response_text = response.text
            assert "Failed to Stop Job" in response_text
            assert "Cannot stop job in status: completed" in response_text
            assert "Error Code: INVALID_STATUS" in response_text

        finally:
            app.dependency_overrides.clear()

    def test_stop_job_with_real_templates(
        self, client: TestClient, test_db: Session, mock_job_manager: Mock
    ) -> None:
        """Test stop job with real template rendering (no template mocking)"""
        # Arrange - Create running database job
        repository = Repository()
        repository.name = "template-test-repo"
        repository.path = "/tmp/template-test"
        repository.set_passphrase("test-passphrase")
        test_db.add(repository)
        test_db.flush()

        job = Job()
        job.id = "tmpl-job"  # Short ID to trigger database path
        job.repository_id = repository.id
        job.type = "backup"  # Required field
        job.status = "running"
        job.started_at = now_utc()
        job.job_type = "simple"  # This is the correct field name
        test_db.add(job)
        test_db.commit()

        # Override only database dependency (use real templates)
        app.dependency_overrides[get_db] = lambda: test_db
        app.dependency_overrides[get_job_manager_dependency] = lambda: mock_job_manager

        try:
            # Act
            response = client.post("/api/jobs/tmpl-job/stop")

            # Assert
            assert response.status_code == 200
            assert response.headers["content-type"] == "text/html; charset=utf-8"

            # Verify actual HTML structure
            html_content = response.text
            assert '<div class="bg-green-50' in html_content  # Success styling
            assert "Job Stopped Successfully" in html_content
            assert "Database job stopped successfully" in html_content

            # Verify database was actually updated
            updated_job = test_db.query(Job).filter(Job.id == "tmpl-job").first()
            assert updated_job is not None
            assert updated_job.status == "stopped"

        finally:
            app.dependency_overrides.clear()

    def test_stop_job_htmx_headers(
        self, client: TestClient, test_db: Session, mock_job_manager: Mock
    ) -> None:
        """Test that stop job endpoint works with HTMX headers"""
        # Arrange
        repository = Repository()
        repository.name = "htmx-test-repo"
        repository.path = "/tmp/htmx-test"
        repository.set_passphrase("test-passphrase")
        test_db.add(repository)
        test_db.flush()

        job = Job()
        job.id = "htmx-job"  # Short ID to trigger database path
        job.repository_id = repository.id
        job.type = "backup"  # Required field
        job.status = "running"
        job.started_at = now_utc()
        job.job_type = "simple"  # This is the correct field name
        test_db.add(job)
        test_db.commit()

        # Override dependencies
        app.dependency_overrides[get_db] = lambda: test_db
        app.dependency_overrides[get_job_manager_dependency] = lambda: mock_job_manager

        try:
            # Act - Send request with HTMX headers
            response = client.post(
                "/api/jobs/htmx-job/stop",
                headers={
                    "HX-Request": "true",
                    "HX-Target": "job-stop-result-htmx-test-job",
                },
            )

            # Assert
            assert response.status_code == 200
            assert "Job Stopped Successfully" in response.text

        finally:
            app.dependency_overrides.clear()
