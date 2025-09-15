"""
Tests for jobs API endpoints
"""

import pytest
from unittest.mock import Mock, AsyncMock
from datetime import datetime, UTC
from fastapi import Request
from fastapi.responses import HTMLResponse
from httpx import AsyncClient
from sqlalchemy.orm import Session

from main import app
from models.database import Repository, Job
from dependencies import (
    get_job_service,
    get_job_stream_service,
    get_job_render_service,
    get_templates,
    get_job_manager_dependency,
)
from services.jobs.job_service import JobService
from services.jobs.job_stream_service import JobStreamService
from services.jobs.job_render_service import JobRenderService
from services.jobs.job_manager import JobManager


class TestJobsAPI:
    """Test class for jobs API endpoints."""

    @pytest.fixture
    def sample_repository(self, test_db: Session):
        """Create a sample repository for testing."""
        repo = Repository(name="test-repo", path="/tmp/test-repo")
        repo.set_passphrase("test-passphrase")
        test_db.add(repo)
        test_db.commit()
        test_db.refresh(repo)
        return repo

    @pytest.fixture
    def sample_database_job(self, test_db: Session, sample_repository):
        """Create a sample database job for testing."""
        job = Job(
            id="test-job-123",
            repository_id=sample_repository.id,
            type="backup",
            status="completed",
            started_at=datetime.now(UTC),
            finished_at=datetime.now(UTC),
            log_output="Test job output",
            job_type="composite",
            total_tasks=1,
            completed_tasks=1,
        )
        test_db.add(job)
        test_db.commit()
        test_db.refresh(job)
        return job

    @pytest.fixture
    def mock_job_service(self):
        """Mock JobService for testing."""
        mock = Mock(spec=JobService)
        mock.db = Mock()
        mock.create_backup_job = AsyncMock()
        mock.create_prune_job = AsyncMock()
        mock.create_check_job = AsyncMock()
        mock.list_jobs = Mock()
        mock.get_job = Mock()
        mock.get_job_status = AsyncMock()
        mock.get_job_output = AsyncMock()
        mock.cancel_job = AsyncMock()
        mock.run_database_migration = Mock()
        return mock

    @pytest.fixture
    def mock_job_stream_service(self):
        """Mock JobStreamService for testing."""
        mock = Mock(spec=JobStreamService)
        mock.stream_all_jobs = AsyncMock()
        mock.stream_job_output = AsyncMock()
        mock.stream_task_output = AsyncMock()
        return mock

    @pytest.fixture
    def mock_job_render_service(self):
        """Mock JobRenderService for testing."""
        mock = Mock(spec=JobRenderService)
        mock.render_jobs_html = Mock()
        mock.render_current_jobs_html = Mock()
        mock.stream_current_jobs_html = Mock()
        mock.get_job_for_render = Mock()
        return mock

    @pytest.fixture
    def mock_job_manager(self):
        """Mock JobManager for testing."""
        mock = Mock(spec=JobManager)
        mock.jobs = {}
        mock._processes = {}
        mock.cleanup_job = Mock()
        mock.get_queue_stats = Mock()
        return mock

    @pytest.fixture
    def mock_templates(self):
        """Mock templates dependency."""
        mock = Mock()
        mock.TemplateResponse = Mock()
        mock.TemplateResponse.return_value = HTMLResponse(content="<div>Test</div>")
        return mock

    @pytest.fixture
    def mock_request(self):
        """Mock FastAPI request."""
        request = Mock(spec=Request)
        request.headers = {}
        return request

    @pytest.fixture
    def setup_dependencies(
        self,
        mock_job_service,
        mock_job_stream_service,
        mock_job_render_service,
        mock_job_manager,
        mock_templates,
    ):
        """Setup dependency overrides for testing."""
        from api.jobs import get_job_manager_dependency as local_get_jm_dep

        app.dependency_overrides[get_job_service] = lambda: mock_job_service
        app.dependency_overrides[get_job_stream_service] = (
            lambda: mock_job_stream_service
        )
        app.dependency_overrides[get_job_render_service] = (
            lambda: mock_job_render_service
        )
        app.dependency_overrides[get_job_manager_dependency] = lambda: mock_job_manager
        app.dependency_overrides[local_get_jm_dep] = lambda: mock_job_manager
        app.dependency_overrides[get_templates] = lambda: mock_templates

        yield {
            "job_service": mock_job_service,
            "job_stream_service": mock_job_stream_service,
            "job_render_service": mock_job_render_service,
            "job_manager": mock_job_manager,
            "templates": mock_templates,
        }

        app.dependency_overrides.clear()

    # Test job creation endpoints

    @pytest.mark.asyncio
    async def test_create_backup_success(
        self, async_client: AsyncClient, setup_dependencies, sample_repository
    ):
        """Test successful backup job creation."""
        setup_dependencies["job_service"].create_backup_job.return_value = {
            "job_id": "test-job-123",
            "status": "started",
        }

        backup_request = {
            "repository_id": sample_repository.id,
            "source_path": "/test/path",
            "compression": "zstd",
            "dry_run": False,
        }

        response = await async_client.post("/api/jobs/backup", json=backup_request)

        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        setup_dependencies["job_service"].create_backup_job.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_backup_repository_not_found(
        self, async_client: AsyncClient, setup_dependencies
    ):
        """Test backup job creation with non-existent repository."""
        setup_dependencies["job_service"].create_backup_job.side_effect = ValueError(
            "Repository not found"
        )

        backup_request = {
            "repository_id": 999,
            "source_path": "/test/path",
            "compression": "zstd",
            "dry_run": False,
        }

        response = await async_client.post("/api/jobs/backup", json=backup_request)

        # The API returns 200 with HTML error content, not 400
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

    @pytest.mark.asyncio
    async def test_create_backup_general_error(
        self, async_client: AsyncClient, setup_dependencies, sample_repository
    ):
        """Test backup job creation with general error."""
        setup_dependencies["job_service"].create_backup_job.side_effect = Exception(
            "General error"
        )

        backup_request = {
            "repository_id": sample_repository.id,
            "source_path": "/test/path",
            "compression": "zstd",
            "dry_run": False,
        }

        response = await async_client.post("/api/jobs/backup", json=backup_request)

        # The API returns 200 with HTML error content, not 500
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

    @pytest.mark.asyncio
    async def test_create_prune_success(
        self, async_client: AsyncClient, setup_dependencies, sample_repository
    ):
        """Test successful prune job creation."""
        setup_dependencies["job_service"].create_prune_job.return_value = {
            "job_id": "prune-job-123"
        }

        prune_request = {
            "repository_id": sample_repository.id,
            "strategy": "simple",
            "keep_within_days": 30,
            "dry_run": True,
        }

        response = await async_client.post("/api/jobs/prune", json=prune_request)

        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        setup_dependencies["job_service"].create_prune_job.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_prune_error(
        self, async_client: AsyncClient, setup_dependencies
    ):
        """Test prune job creation with error."""
        setup_dependencies["job_service"].create_prune_job.side_effect = ValueError(
            "Invalid prune configuration"
        )

        prune_request = {
            "repository_id": 999,
            "strategy": "simple",
            "keep_within_days": 30,
            "dry_run": True,
        }

        response = await async_client.post("/api/jobs/prune", json=prune_request)

        # The API returns 200 with HTML error content, not 400
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

    @pytest.mark.asyncio
    async def test_create_check_success(
        self, async_client: AsyncClient, setup_dependencies, sample_repository
    ):
        """Test successful check job creation."""
        setup_dependencies["job_service"].create_check_job.return_value = {
            "job_id": "check-job-123"
        }

        check_request = {
            "repository_id": sample_repository.id,
            "check_type": "full",
            "verify_data": False,
        }

        response = await async_client.post("/api/jobs/check", json=check_request)

        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        setup_dependencies["job_service"].create_check_job.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_check_error(
        self, async_client: AsyncClient, setup_dependencies
    ):
        """Test check job creation with error."""
        setup_dependencies["job_service"].create_check_job.side_effect = Exception(
            "Check job failed"
        )

        check_request = {
            "repository_id": 999,
            "check_type": "full",
            "verify_data": False,
        }

        response = await async_client.post("/api/jobs/check", json=check_request)

        # The API returns 200 with HTML error content, not 500
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

    # Test job retrieval endpoints

    @pytest.mark.asyncio
    async def test_list_jobs(self, async_client: AsyncClient, setup_dependencies):
        """Test listing jobs."""
        setup_dependencies["job_service"].list_jobs.return_value = [
            {"id": "job-1", "type": "backup", "status": "completed"},
            {"id": "job-2", "type": "prune", "status": "running"},
        ]

        response = await async_client.get("/api/jobs/")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        assert data[0]["id"] == "job-1"
        setup_dependencies["job_service"].list_jobs.assert_called_once_with(
            0, 100, None
        )

    @pytest.mark.asyncio
    async def test_list_jobs_with_params(
        self, async_client: AsyncClient, setup_dependencies
    ):
        """Test listing jobs with query parameters."""
        setup_dependencies["job_service"].list_jobs.return_value = []

        response = await async_client.get("/api/jobs/?skip=10&limit=50&type=backup")

        assert response.status_code == 200
        setup_dependencies["job_service"].list_jobs.assert_called_once_with(
            10, 50, "backup"
        )

    @pytest.mark.asyncio
    async def test_get_jobs_html(self, async_client: AsyncClient, setup_dependencies):
        """Test getting jobs as HTML."""
        setup_dependencies[
            "job_render_service"
        ].render_jobs_html.return_value = HTMLResponse(content="<div>Jobs HTML</div>")

        response = await async_client.get("/api/jobs/html")

        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        setup_dependencies["job_render_service"].render_jobs_html.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_current_jobs_html(
        self, async_client: AsyncClient, setup_dependencies
    ):
        """Test getting current jobs as HTML."""
        setup_dependencies[
            "job_render_service"
        ].render_current_jobs_html.return_value = "<div>Current Jobs</div>"

        response = await async_client.get("/api/jobs/current/html")

        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        setup_dependencies[
            "job_render_service"
        ].render_current_jobs_html.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_job_success(self, async_client: AsyncClient, setup_dependencies):
        """Test getting specific job details."""
        job_data = {"id": "test-job-123", "type": "backup", "status": "completed"}
        setup_dependencies["job_service"].get_job.return_value = job_data

        response = await async_client.get("/api/jobs/test-job-123")

        assert response.status_code == 200
        assert response.json() == job_data
        setup_dependencies["job_service"].get_job.assert_called_once_with(
            "test-job-123"
        )

    @pytest.mark.asyncio
    async def test_get_job_not_found(
        self, async_client: AsyncClient, setup_dependencies
    ):
        """Test getting non-existent job."""
        setup_dependencies["job_service"].get_job.return_value = None

        response = await async_client.get("/api/jobs/non-existent-job")

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_get_job_status_success(
        self, async_client: AsyncClient, setup_dependencies
    ):
        """Test getting job status."""
        status_data = {"status": "running", "progress": 50}
        setup_dependencies["job_service"].get_job_status.return_value = status_data

        response = await async_client.get("/api/jobs/test-job-123/status")

        assert response.status_code == 200
        assert response.json() == status_data
        setup_dependencies["job_service"].get_job_status.assert_called_once_with(
            "test-job-123"
        )

    @pytest.mark.asyncio
    async def test_get_job_status_error(
        self, async_client: AsyncClient, setup_dependencies
    ):
        """Test getting job status with error."""
        setup_dependencies["job_service"].get_job_status.return_value = {
            "error": "Job not found"
        }

        response = await async_client.get("/api/jobs/non-existent-job/status")

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_get_job_output_success(
        self, async_client: AsyncClient, setup_dependencies
    ):
        """Test getting job output."""
        output_data = {"output": ["line 1", "line 2"], "total_lines": 2}
        setup_dependencies["job_service"].get_job_output.return_value = output_data

        response = await async_client.get("/api/jobs/test-job-123/output")

        assert response.status_code == 200
        assert response.json() == output_data
        setup_dependencies["job_service"].get_job_output.assert_called_once_with(
            "test-job-123", 100
        )

    @pytest.mark.asyncio
    async def test_get_job_output_with_limit(
        self, async_client: AsyncClient, setup_dependencies
    ):
        """Test getting job output with custom limit."""
        output_data = {"output": ["line 1"], "total_lines": 1}
        setup_dependencies["job_service"].get_job_output.return_value = output_data

        response = await async_client.get(
            "/api/jobs/test-job-123/output?last_n_lines=50"
        )

        assert response.status_code == 200
        setup_dependencies["job_service"].get_job_output.assert_called_once_with(
            "test-job-123", 50
        )

    # Test streaming endpoints

    @pytest.mark.asyncio
    async def test_stream_all_jobs(self, async_client: AsyncClient, setup_dependencies):
        """Test streaming all jobs endpoint."""
        from fastapi.responses import StreamingResponse

        mock_response = StreamingResponse(
            iter([b"data: test\n\n"]), media_type="text/event-stream"
        )
        setup_dependencies[
            "job_stream_service"
        ].stream_all_jobs.return_value = mock_response

        response = await async_client.get("/api/jobs/stream")

        assert response.status_code == 200
        setup_dependencies["job_stream_service"].stream_all_jobs.assert_called_once()

    @pytest.mark.asyncio
    async def test_stream_job_output(
        self, async_client: AsyncClient, setup_dependencies
    ):
        """Test streaming specific job output."""
        from fastapi.responses import StreamingResponse

        mock_response = StreamingResponse(
            iter([b"data: job output\n\n"]), media_type="text/event-stream"
        )
        setup_dependencies[
            "job_stream_service"
        ].stream_job_output.return_value = mock_response

        response = await async_client.get("/api/jobs/test-job-123/stream")

        assert response.status_code == 200
        setup_dependencies[
            "job_stream_service"
        ].stream_job_output.assert_called_once_with("test-job-123")

    @pytest.mark.asyncio
    async def test_stream_task_output(
        self, async_client: AsyncClient, setup_dependencies
    ):
        """Test streaming specific task output."""
        from fastapi.responses import StreamingResponse

        mock_response = StreamingResponse(
            iter([b"data: task output\n\n"]), media_type="text/event-stream"
        )
        setup_dependencies[
            "job_stream_service"
        ].stream_task_output.return_value = mock_response

        response = await async_client.get("/api/jobs/test-job-123/tasks/1/stream")

        assert response.status_code == 200
        setup_dependencies[
            "job_stream_service"
        ].stream_task_output.assert_called_once_with("test-job-123", 1)

    # Test job management endpoints

    @pytest.mark.asyncio
    async def test_cancel_job_success(
        self, async_client: AsyncClient, setup_dependencies
    ):
        """Test successful job cancellation."""
        setup_dependencies["job_service"].cancel_job.return_value = True

        response = await async_client.delete("/api/jobs/test-job-123")

        assert response.status_code == 200
        assert response.json() == {"message": "Job cancelled successfully"}
        setup_dependencies["job_service"].cancel_job.assert_called_once_with(
            "test-job-123"
        )

    @pytest.mark.asyncio
    async def test_cancel_job_not_found(
        self, async_client: AsyncClient, setup_dependencies
    ):
        """Test cancelling non-existent job."""
        setup_dependencies["job_service"].cancel_job.return_value = False

        response = await async_client.delete("/api/jobs/non-existent-job")

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_get_job_manager_stats(
        self, async_client: AsyncClient, setup_dependencies
    ):
        """Test getting job manager statistics."""
        # Setup mock job manager with some test data
        from services.jobs.job_manager import BorgJob
        from datetime import datetime, UTC

        mock_jobs = {
            "job-1": BorgJob(
                id="job-1",
                command=["test"],
                job_type="backup",
                status="running",
                started_at=datetime.now(UTC),
            ),
            "job-2": BorgJob(
                id="job-2",
                command=["test"],
                job_type="backup",
                status="completed",
                started_at=datetime.now(UTC),
            ),
            "job-3": BorgJob(
                id="job-3",
                command=["test"],
                job_type="backup",
                status="failed",
                started_at=datetime.now(UTC),
            ),
        }
        setup_dependencies["job_manager"].jobs = mock_jobs

        response = await async_client.get("/api/jobs/manager/stats")

        assert response.status_code == 200
        data = response.json()
        assert data["total_jobs"] == 3
        assert data["running_jobs"] == 1
        assert data["completed_jobs"] == 1
        assert data["failed_jobs"] == 1

    @pytest.mark.asyncio
    async def test_cleanup_completed_jobs(
        self, async_client: AsyncClient, setup_dependencies
    ):
        """Test cleaning up completed jobs."""
        # Setup mock job manager with completed jobs
        from services.jobs.job_manager import BorgJob
        from datetime import datetime, UTC

        mock_jobs = {
            "job-1": BorgJob(
                id="job-1",
                command=["test"],
                job_type="backup",
                status="completed",
                started_at=datetime.now(UTC),
            ),
            "job-2": BorgJob(
                id="job-2",
                command=["test"],
                job_type="backup",
                status="failed",
                started_at=datetime.now(UTC),
            ),
            "job-3": BorgJob(
                id="job-3",
                command=["test"],
                job_type="backup",
                status="running",
                started_at=datetime.now(UTC),
            ),
        }
        setup_dependencies["job_manager"].jobs = mock_jobs

        response = await async_client.post("/api/jobs/manager/prune")

        assert response.status_code == 200
        data = response.json()
        assert "Cleaned up" in data["message"]
        assert setup_dependencies["job_manager"].cleanup_job.call_count == 2

    @pytest.mark.asyncio
    async def test_get_queue_stats(self, async_client: AsyncClient, setup_dependencies):
        """Test getting queue statistics."""
        # The actual queue stats structure from the real implementation
        queue_stats = {
            "available_slots": 5,
            "max_concurrent_backups": 5,
            "queue_size": 0,
            "queued_backups": 0,
            "running_backups": 0,
        }
        setup_dependencies["job_manager"].get_queue_stats.return_value = queue_stats

        response = await async_client.get("/api/jobs/queue/stats")

        assert response.status_code == 200
        data = response.json()
        # Check that we get the expected structure
        assert "available_slots" in data
        assert "max_concurrent_backups" in data
        setup_dependencies["job_manager"].get_queue_stats.assert_called_once()

    @pytest.mark.asyncio
    async def test_run_database_migration_success(
        self, async_client: AsyncClient, setup_dependencies
    ):
        """Test successful database migration."""
        migration_result = {"status": "success", "message": "Migration completed"}
        setup_dependencies[
            "job_service"
        ].run_database_migration.return_value = migration_result

        response = await async_client.post("/api/jobs/migrate")

        assert response.status_code == 200
        assert response.json() == migration_result
        setup_dependencies["job_service"].run_database_migration.assert_called_once()

    @pytest.mark.asyncio
    async def test_run_database_migration_error(
        self, async_client: AsyncClient, setup_dependencies
    ):
        """Test database migration with error."""
        setup_dependencies[
            "job_service"
        ].run_database_migration.side_effect = Exception("Migration failed")

        response = await async_client.post("/api/jobs/migrate")

        assert response.status_code == 500

    # Test HTMX-specific endpoints

    @pytest.mark.asyncio
    async def test_toggle_job_details(
        self, async_client: AsyncClient, setup_dependencies
    ):
        """Test toggling job details visibility."""
        job_data = {
            "job": {"id": "test-job-123", "status": "completed"},
            "expand_details": False,
        }
        setup_dependencies[
            "job_render_service"
        ].get_job_for_render.return_value = job_data

        response = await async_client.get(
            "/api/jobs/test-job-123/toggle-details?expanded=false"
        )

        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        setup_dependencies["job_render_service"].get_job_for_render.assert_called_once()

    @pytest.mark.asyncio
    async def test_toggle_job_details_not_found(
        self, async_client: AsyncClient, setup_dependencies
    ):
        """Test toggling details for non-existent job."""
        setup_dependencies["job_render_service"].get_job_for_render.return_value = None

        response = await async_client.get("/api/jobs/non-existent-job/toggle-details")

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_get_job_details_static(
        self, async_client: AsyncClient, setup_dependencies
    ):
        """Test getting static job details."""
        job_data = {"job": {"id": "test-job-123", "status": "completed"}}
        setup_dependencies[
            "job_render_service"
        ].get_job_for_render.return_value = job_data

        response = await async_client.get("/api/jobs/test-job-123/details-static")

        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

    @pytest.mark.asyncio
    async def test_toggle_task_details(
        self, async_client: AsyncClient, setup_dependencies
    ):
        """Test toggling task details visibility."""
        from types import SimpleNamespace

        task = SimpleNamespace()
        task.task_order = 1

        # Create a proper job object with status attribute
        job_obj = SimpleNamespace()
        job_obj.id = "test-job-123"
        job_obj.status = "completed"

        job_data = {"job": job_obj, "sorted_tasks": [task]}
        setup_dependencies[
            "job_render_service"
        ].get_job_for_render.return_value = job_data

        response = await async_client.get(
            "/api/jobs/test-job-123/tasks/1/toggle-details"
        )

        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

    @pytest.mark.asyncio
    async def test_toggle_task_details_task_not_found(
        self, async_client: AsyncClient, setup_dependencies
    ):
        """Test toggling details for non-existent task."""
        job_data = {
            "job": {"id": "test-job-123", "status": "completed"},
            "sorted_tasks": [],
        }
        setup_dependencies[
            "job_render_service"
        ].get_job_for_render.return_value = job_data

        response = await async_client.get(
            "/api/jobs/test-job-123/tasks/999/toggle-details"
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_copy_job_output(self, async_client: AsyncClient, setup_dependencies):
        """Test copying job output to clipboard."""
        response = await async_client.post("/api/jobs/test-job-123/copy-output")

        assert response.status_code == 200
        assert response.json() == {"message": "Output copied to clipboard"}

    @pytest.mark.asyncio
    async def test_copy_task_output(
        self, async_client: AsyncClient, setup_dependencies
    ):
        """Test copying task output to clipboard."""
        response = await async_client.post("/api/jobs/test-job-123/tasks/1/copy-output")

        assert response.status_code == 200
        assert response.json() == {"message": "Task output copied to clipboard"}

    # Test request validation

    @pytest.mark.asyncio
    async def test_backup_request_validation(
        self, async_client: AsyncClient, setup_dependencies
    ):
        """Test backup request validation."""
        # Test missing repository_id
        invalid_request = {
            "source_path": "/test/path",
            "compression": "zstd",
        }

        response = await async_client.post("/api/jobs/backup", json=invalid_request)
        assert response.status_code == 422

        # Test invalid repository_id (must be > 0)
        invalid_request = {
            "repository_id": 0,
            "source_path": "/test/path",
            "compression": "zstd",
        }

        response = await async_client.post("/api/jobs/backup", json=invalid_request)
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_prune_request_validation(
        self, async_client: AsyncClient, setup_dependencies
    ):
        """Test prune request validation."""
        # Test missing repository_id
        invalid_request = {
            "strategy": "simple",
            "keep_within_days": 30,
        }

        response = await async_client.post("/api/jobs/prune", json=invalid_request)
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_check_request_validation(
        self, async_client: AsyncClient, setup_dependencies
    ):
        """Test check request validation."""
        # Test missing repository_id
        invalid_request = {
            "check_type": "full",
            "verify_data": False,
        }

        response = await async_client.post("/api/jobs/check", json=invalid_request)
        assert response.status_code == 422


class TestJobsAPIIntegration:
    """Integration tests for jobs API with real database."""

    @pytest.mark.asyncio
    async def test_job_endpoint_registration(self, async_client: AsyncClient):
        """Test that job endpoints are properly registered."""
        # Test that endpoints exist by checking for proper error responses
        # rather than trying to execute the full job creation flow

        # Test backup endpoint with invalid data
        response = await async_client.post("/api/jobs/backup", json={})
        assert response.status_code == 422  # Validation error

        # Test job listing endpoint
        response = await async_client.get("/api/jobs/")
        assert response.status_code == 200
