"""
Tests for jobs API endpoints
"""

import pytest
from typing import Generator
from unittest.mock import Mock, AsyncMock
from borgitory.utils.datetime_utils import now_utc
from fastapi import Request
from fastapi.responses import HTMLResponse
from httpx import AsyncClient
from sqlalchemy.orm import Session

from borgitory.main import app
from borgitory.models.database import Repository, Job
from borgitory.dependencies import (
    get_job_service,
    get_job_stream_service,
    get_job_render_service,
    get_templates,
    get_job_manager_dependency,
)
from borgitory.services.jobs.job_service import JobService
from borgitory.services.jobs.job_stream_service import JobStreamService
from borgitory.services.jobs.job_manager import JobManager


class TestJobsAPI:
    """Test class for jobs API endpoints."""

    @pytest.fixture
    def sample_repository(self, test_db: Session) -> Repository:
        """Create a sample repository for testing."""
        repo = Repository()
        repo.name = "test-repo"
        repo.path = "/tmp/test-repo"
        repo.set_passphrase("test-passphrase")
        test_db.add(repo)
        test_db.commit()
        test_db.refresh(repo)
        return repo

    @pytest.fixture
    def sample_database_job(
        self, test_db: Session, sample_repository: Repository
    ) -> Job:
        """Create a sample database job for testing."""
        job = Job()
        job.id = "test-job-123"
        job.repository_id = sample_repository.id
        job.type = "backup"
        job.status = "completed"
        job.started_at = now_utc()
        job.finished_at = now_utc()
        job.log_output = "Test job output"
        job.job_type = "composite"
        job.total_tasks = 1
        job.completed_tasks = 1
        test_db.add(job)
        test_db.commit()
        test_db.refresh(job)
        return job

    @pytest.fixture
    def mock_job_service(self) -> Mock:
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
        return mock

    @pytest.fixture
    def mock_job_stream_service(self) -> Mock:
        """Mock JobStreamService for testing."""
        mock = Mock(spec=JobStreamService)
        mock.stream_all_jobs = AsyncMock()
        mock.stream_job_output = AsyncMock()
        mock.stream_task_output = AsyncMock()
        return mock

    @pytest.fixture
    def mock_job_render_service(self) -> Mock:
        """Mock JobRenderService for testing."""
        from tests.utils.di_testing import MockServiceFactory

        return MockServiceFactory.create_mock_job_render_service()

    @pytest.fixture
    def mock_job_manager(self) -> Mock:
        """Mock JobManager for testing."""
        mock = Mock(spec=JobManager)
        mock.jobs = {}
        mock._processes = {}
        mock.cleanup_job = Mock()
        mock.get_queue_stats = Mock()
        return mock

    @pytest.fixture
    def mock_templates(self) -> Mock:
        """Mock templates dependency."""
        mock = Mock()
        mock.TemplateResponse = Mock()
        mock.TemplateResponse.return_value = HTMLResponse(content="<div>Test</div>")
        return mock

    @pytest.fixture
    def mock_request(self) -> Mock:
        """Mock FastAPI request."""
        request = Mock(spec=Request)
        request.headers = {}
        return request

    @pytest.fixture
    def setup_dependencies(
        self,
        mock_job_service: Mock,
        mock_job_stream_service: Mock,
        mock_job_render_service: Mock,
        mock_job_manager: Mock,
        mock_templates: Mock,
    ) -> Generator[dict[str, Mock], None, None]:
        """Setup dependency overrides for testing."""
        app.dependency_overrides[get_job_service] = lambda: mock_job_service
        app.dependency_overrides[get_job_stream_service] = (
            lambda: mock_job_stream_service
        )
        app.dependency_overrides[get_job_render_service] = (
            lambda: mock_job_render_service
        )
        app.dependency_overrides[get_job_manager_dependency] = lambda: mock_job_manager
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
        self,
        async_client: AsyncClient,
        setup_dependencies: dict[str, Mock],
        sample_repository: Repository,
    ) -> None:
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
        self, async_client: AsyncClient, setup_dependencies: dict[str, Mock]
    ) -> None:
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
        self,
        async_client: AsyncClient,
        setup_dependencies: dict[str, Mock],
        sample_repository: Repository,
    ) -> None:
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
        self,
        async_client: AsyncClient,
        setup_dependencies: dict[str, Mock],
        sample_repository: Repository,
    ) -> None:
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
        self, async_client: AsyncClient, setup_dependencies: dict[str, Mock]
    ) -> None:
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
        self,
        async_client: AsyncClient,
        setup_dependencies: dict[str, Mock],
        sample_repository: Repository,
    ) -> None:
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
        self, async_client: AsyncClient, setup_dependencies: dict[str, Mock]
    ) -> None:
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

    @pytest.mark.asyncio
    async def test_get_jobs_html(
        self, async_client: AsyncClient, setup_dependencies: dict[str, Mock]
    ) -> None:
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
        self, async_client: AsyncClient, setup_dependencies: dict[str, Mock]
    ) -> None:
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
    async def test_get_job_not_found(
        self, async_client: AsyncClient, setup_dependencies: dict[str, Mock]
    ) -> None:
        """Test getting non-existent job."""
        setup_dependencies["job_service"].get_job.return_value = None

        response = await async_client.get("/api/jobs/non-existent-job")

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_get_job_status_success(
        self, async_client: AsyncClient, setup_dependencies: dict[str, Mock]
    ) -> None:
        """Test getting job status."""
        status_data = {
            "id": "test-job-123",
            "status": "running",
            "running": True,
            "completed": False,
            "failed": False,
            "job_type": "backup",
        }
        setup_dependencies["job_service"].get_job_status.return_value = status_data

        response = await async_client.get("/api/jobs/test-job-123/status")

        assert response.status_code == 200
        response_data = response.json()

        # Verify the core fields are correct
        assert response_data["id"] == "test-job-123"
        assert response_data["status"] == "running"
        assert response_data["running"] is True
        assert response_data["completed"] is False
        assert response_data["failed"] is False
        assert response_data["job_type"] == "backup"

        setup_dependencies["job_service"].get_job_status.assert_called_once_with(
            "test-job-123"
        )

    @pytest.mark.asyncio
    async def test_get_job_status_error(
        self, async_client: AsyncClient, setup_dependencies: dict[str, Mock]
    ) -> None:
        """Test getting job status with error."""
        setup_dependencies["job_service"].get_job_status.return_value = {
            "error": "Job not found"
        }

        response = await async_client.get("/api/jobs/non-existent-job/status")

        assert response.status_code == 404

    # Test streaming endpoints

    @pytest.mark.asyncio
    async def test_stream_all_jobs(
        self, async_client: AsyncClient, setup_dependencies: dict[str, Mock]
    ) -> None:
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
        self, async_client: AsyncClient, setup_dependencies: dict[str, Mock]
    ) -> None:
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
        self, async_client: AsyncClient, setup_dependencies: dict[str, Mock]
    ) -> None:
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

    @pytest.mark.asyncio
    async def test_toggle_job_details(
        self, async_client: AsyncClient, setup_dependencies: dict[str, Mock]
    ) -> None:
        """Test toggling job details visibility."""
        # The mock already handles this case properly

        response = await async_client.get(
            "/api/jobs/test-job-123/toggle-details?expanded=false"
        )

        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        setup_dependencies[
            "job_render_service"
        ].get_job_for_template.assert_called_once()

    @pytest.mark.asyncio
    async def test_toggle_job_details_not_found(
        self, async_client: AsyncClient, setup_dependencies: dict[str, Mock]
    ) -> None:
        """Test toggling details for non-existent job."""
        # The mock already handles non-existent jobs by returning None

        response = await async_client.get("/api/jobs/non-existent-job/toggle-details")

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_get_job_details_static(
        self, async_client: AsyncClient, setup_dependencies: dict[str, Mock]
    ) -> None:
        """Test getting static job details."""
        # The mock already handles this case properly

        response = await async_client.get("/api/jobs/test-job-123/details-static")

        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

    @pytest.mark.asyncio
    async def test_toggle_task_details(
        self, async_client: AsyncClient, setup_dependencies: dict[str, Mock]
    ) -> None:
        """Test toggling task details visibility."""
        from types import SimpleNamespace

        task = SimpleNamespace()
        task.task_order = 1

        # Create a proper job object with status attribute
        job_obj = SimpleNamespace()
        job_obj.id = "test-job-123"
        job_obj.status = "completed"

        # The mock already handles this case with proper task structure
        # Task order 1 should find the task we created in the mock

        response = await async_client.get(
            "/api/jobs/test-job-123/tasks/1/toggle-details"
        )

        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

    @pytest.mark.asyncio
    async def test_toggle_task_details_task_not_found(
        self, async_client: AsyncClient, setup_dependencies: dict[str, Mock]
    ) -> None:
        """Test toggling details for non-existent task."""
        # The mock will return a job with tasks 0 and 1, but task 999 doesn't exist
        # This should result in a 404

        response = await async_client.get(
            "/api/jobs/test-job-123/tasks/999/toggle-details"
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_copy_job_output(
        self, async_client: AsyncClient, setup_dependencies: dict[str, Mock]
    ) -> None:
        """Test copying job output to clipboard."""
        response = await async_client.post("/api/jobs/test-job-123/copy-output")

        assert response.status_code == 200
        assert response.json() == {"message": "Output copied to clipboard"}

    @pytest.mark.asyncio
    async def test_copy_task_output(
        self, async_client: AsyncClient, setup_dependencies: dict[str, Mock]
    ) -> None:
        """Test copying task output to clipboard."""
        response = await async_client.post("/api/jobs/test-job-123/tasks/1/copy-output")

        assert response.status_code == 200
        assert response.json() == {"message": "Task output copied to clipboard"}

    # Test request validation

    @pytest.mark.asyncio
    async def test_backup_request_validation(
        self, async_client: AsyncClient, setup_dependencies: dict[str, Mock]
    ) -> None:
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
            "repository_id": "0",
            "source_path": "/test/path",
            "compression": "zstd",
        }

        response = await async_client.post("/api/jobs/backup", json=invalid_request)
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_prune_request_validation(
        self, async_client: AsyncClient, setup_dependencies: dict[str, Mock]
    ) -> None:
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
        self, async_client: AsyncClient, setup_dependencies: dict[str, Mock]
    ) -> None:
        """Test check request validation."""
        # Test missing repository_id
        invalid_request = {
            "check_type": "full",
            "verify_data": False,
        }

        response = await async_client.post("/api/jobs/check", json=invalid_request)
        assert response.status_code == 422
