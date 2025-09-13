"""
Tests for jobs API endpoints - HTMX and response validation focused
"""

import pytest
from unittest.mock import MagicMock, AsyncMock
from fastapi import Request
from fastapi.responses import HTMLResponse

from app.models.schemas import BackupRequest, PruneRequest, CheckRequest
from app.models.enums import JobType


@pytest.fixture
def mock_request():
    """Mock FastAPI request"""
    request = MagicMock(spec=Request)
    request.headers = {}
    return request


@pytest.fixture
def mock_templates():
    """Mock templates dependency"""
    templates = MagicMock()
    mock_response = MagicMock(spec=HTMLResponse)
    mock_response.headers = {}
    templates.TemplateResponse.return_value = mock_response
    templates.get_template.return_value.render.return_value = "mocked html content"
    return templates


@pytest.fixture
def mock_job_service():
    """Mock JobService"""
    service = MagicMock()
    service.create_backup_job = AsyncMock()
    service.create_prune_job = AsyncMock()
    service.create_check_job = AsyncMock()
    service.get_job_status = AsyncMock()
    service.get_job_output = AsyncMock()
    service.cancel_job = AsyncMock()
    return service


@pytest.fixture
def mock_render_service():
    """Mock JobRenderService"""
    service = MagicMock()
    return service


@pytest.fixture
def mock_stream_service():
    """Mock JobStreamService"""
    service = MagicMock()
    service.stream_all_jobs = AsyncMock()
    service.stream_job_output = AsyncMock()
    return service


@pytest.fixture
def sample_backup_request():
    """Sample backup request data"""
    return BackupRequest(
        repository_id=1,
        source_path="/test/path",
        compression="lz4",
        dry_run=False,
        cleanup_config_id=None,
        check_config_id=None,
        cloud_sync_config_id=None,
        notification_config_id=None
    )


@pytest.fixture
def sample_prune_request():
    """Sample prune request data"""
    return PruneRequest(
        repository_id=1,
        strategy="simple",
        keep_within_days=30
    )


@pytest.fixture
def sample_check_request():
    """Sample check request data"""
    return CheckRequest(
        repository_id=1,
        repository_only=False,
        archives_only=False,
        verify_data=False,
        repair=False,
        check_config_id=None
    )


class TestJobsAPI:
    """Test class for API endpoints focusing on HTMX responses."""

    @pytest.mark.asyncio
    async def test_create_backup_success_htmx_response(self, mock_request, mock_templates, mock_job_service, sample_backup_request):
        """Test successful backup creation returns correct HTMX response."""
        from app.api.jobs import create_backup

        # Mock successful service response
        mock_job_service.create_backup_job.return_value = {"job_id": "test-job-123", "status": "started"}

        await create_backup(
            sample_backup_request, mock_request, mock_job_service, mock_templates
        )

        # Verify service was called with correct parameters
        mock_job_service.create_backup_job.assert_called_once_with(sample_backup_request, JobType.MANUAL_BACKUP)

        # Verify HTMX success template response
        mock_templates.TemplateResponse.assert_called_once_with(
            mock_request,
            "partials/jobs/backup_success.html",
            {"job_id": "test-job-123"},
        )

    @pytest.mark.asyncio
    async def test_create_backup_repository_not_found_htmx_response(self, mock_request, mock_templates, mock_job_service, sample_backup_request):
        """Test backup creation with repository not found returns correct HTMX error response."""
        from app.api.jobs import create_backup

        # Mock service failure
        mock_job_service.create_backup_job.side_effect = ValueError("Repository not found")

        await create_backup(
            sample_backup_request, mock_request, mock_job_service, mock_templates
        )

        # Verify error template response
        mock_templates.TemplateResponse.assert_called_once_with(
            mock_request,
            "partials/jobs/backup_error.html",
            {"error_message": "Repository not found: Repository not found"},
            status_code=400,
        )

    @pytest.mark.asyncio
    async def test_create_backup_general_error_htmx_response(self, mock_request, mock_templates, mock_job_service, sample_backup_request):
        """Test backup creation with general error returns correct HTMX error response."""
        from app.api.jobs import create_backup

        # Mock service failure
        mock_job_service.create_backup_job.side_effect = Exception("Database connection failed")

        await create_backup(
            sample_backup_request, mock_request, mock_job_service, mock_templates
        )

        # Verify error template response
        mock_templates.TemplateResponse.assert_called_once_with(
            mock_request,
            "partials/jobs/backup_error.html",
            {"error_message": "Failed to start backup: Database connection failed"},
            status_code=500,
        )

    @pytest.mark.asyncio
    async def test_create_prune_job_success_htmx_response(self, mock_request, mock_templates, mock_job_service, sample_prune_request):
        """Test successful prune job creation returns correct HTMX response."""
        from app.api.jobs import create_prune_job

        # Mock successful service response
        mock_job_service.create_prune_job.return_value = {"job_id": "prune-job-456", "status": "started"}

        await create_prune_job(
            mock_request, sample_prune_request, mock_job_service, mock_templates
        )

        # Verify service was called with correct parameters
        mock_job_service.create_prune_job.assert_called_once_with(sample_prune_request)

        # Verify HTMX success template response
        mock_templates.TemplateResponse.assert_called_once_with(
            mock_request,
            "partials/cleanup/prune_success.html",
            {"job_id": "prune-job-456"},
        )

    @pytest.mark.asyncio
    async def test_create_prune_job_value_error_htmx_response(self, mock_request, mock_templates, mock_job_service, sample_prune_request):
        """Test prune job creation with value error returns correct HTMX error response."""
        from app.api.jobs import create_prune_job

        # Mock service failure
        mock_job_service.create_prune_job.side_effect = ValueError("Repository not found")

        await create_prune_job(
            mock_request, sample_prune_request, mock_job_service, mock_templates
        )

        # Verify error template response
        mock_templates.TemplateResponse.assert_called_once_with(
            mock_request,
            "partials/cleanup/prune_error.html",
            {"error_message": "Repository not found"},
            status_code=400,
        )

    @pytest.mark.asyncio
    async def test_create_prune_job_general_error_htmx_response(self, mock_request, mock_templates, mock_job_service, sample_prune_request):
        """Test prune job creation with general error returns correct HTMX error response."""
        from app.api.jobs import create_prune_job

        # Mock service failure
        mock_job_service.create_prune_job.side_effect = Exception("Prune execution failed")

        await create_prune_job(
            mock_request, sample_prune_request, mock_job_service, mock_templates
        )

        # Verify error template response
        mock_templates.TemplateResponse.assert_called_once_with(
            mock_request,
            "partials/cleanup/prune_error.html",
            {"error_message": "Failed to start prune job: Prune execution failed"},
            status_code=500,
        )

    @pytest.mark.asyncio
    async def test_create_check_job_success_htmx_response(self, mock_request, mock_templates, mock_job_service, sample_check_request):
        """Test successful check job creation returns correct HTMX response."""
        from app.api.jobs import create_check_job

        # Mock successful service response
        mock_job_service.create_check_job.return_value = {"job_id": "check-job-789", "status": "started"}

        await create_check_job(
            mock_request, sample_check_request, mock_job_service, mock_templates
        )

        # Verify service was called with correct parameters
        mock_job_service.create_check_job.assert_called_once_with(sample_check_request)

        # Verify HTMX success template response
        mock_templates.TemplateResponse.assert_called_once_with(
            mock_request,
            "partials/repository_check/check_success.html",
            {"job_id": "check-job-789"},
        )

    @pytest.mark.asyncio
    async def test_create_check_job_value_error_htmx_response(self, mock_request, mock_templates, mock_job_service, sample_check_request):
        """Test check job creation with value error returns correct HTMX error response."""
        from app.api.jobs import create_check_job

        # Mock service failure
        mock_job_service.create_check_job.side_effect = ValueError("Check configuration not found")

        await create_check_job(
            mock_request, sample_check_request, mock_job_service, mock_templates
        )

        # Verify error template response
        mock_templates.TemplateResponse.assert_called_once_with(
            mock_request,
            "partials/repository_check/check_error.html",
            {"error_message": "Check configuration not found"},
            status_code=400,
        )

    @pytest.mark.asyncio
    async def test_create_check_job_general_error_htmx_response(self, mock_request, mock_templates, mock_job_service, sample_check_request):
        """Test check job creation with general error returns correct HTMX error response."""
        from app.api.jobs import create_check_job

        # Mock service failure
        mock_job_service.create_check_job.side_effect = Exception("Check execution failed")

        await create_check_job(
            mock_request, sample_check_request, mock_job_service, mock_templates
        )

        # Verify error template response
        mock_templates.TemplateResponse.assert_called_once_with(
            mock_request,
            "partials/repository_check/check_error.html",
            {"error_message": "Failed to start check job: Check execution failed"},
            status_code=500,
        )

    def test_list_jobs_success(self, mock_job_service):
        """Test listing jobs returns service result."""
        from app.api.jobs import list_jobs

        mock_jobs = [{"id": "1", "type": "backup"}, {"id": "2", "type": "prune"}]
        mock_job_service.list_jobs.return_value = mock_jobs

        result = list_jobs(mock_job_service, skip=0, limit=100, type="backup")

        # Verify service was called with correct parameters
        mock_job_service.list_jobs.assert_called_once_with(0, 100, "backup")

        # Verify result is returned
        assert result == mock_jobs

    def test_get_jobs_html_success(self, mock_render_service, mock_job_service):
        """Test getting jobs HTML returns correct template response."""
        from app.api.jobs import get_jobs_html

        mock_render_service.render_jobs_html.return_value = "<div>Job History</div>"

        result = get_jobs_html(mock_render_service, mock_job_service, expand="job-123")

        # Verify render service was called
        mock_render_service.render_jobs_html.assert_called_once_with(mock_job_service.db, "job-123")

        # Verify result is returned
        assert result == "<div>Job History</div>"

    def test_get_current_jobs_html_success(self, mock_render_service):
        """Test getting current jobs HTML returns correct response."""
        from app.api.jobs import get_current_jobs_html

        mock_render_service.render_current_jobs_html.return_value = "<div>Current Jobs</div>"

        result = get_current_jobs_html(mock_render_service)

        # Verify render service was called
        mock_render_service.render_current_jobs_html.assert_called_once()

        # Verify HTMLResponse is returned
        assert hasattr(result, 'body')

    def test_get_job_success(self, mock_job_service):
        """Test getting job details returns service result."""
        from app.api.jobs import get_job

        mock_job = {"id": "test-job", "status": "completed"}
        mock_job_service.get_job.return_value = mock_job

        result = get_job("test-job", mock_job_service)

        # Verify service was called
        mock_job_service.get_job.assert_called_once_with("test-job")

        # Verify result is returned
        assert result == mock_job

    def test_get_job_not_found_raises_exception(self, mock_job_service):
        """Test getting non-existent job raises HTTPException."""
        from app.api.jobs import get_job
        from fastapi import HTTPException

        mock_job_service.get_job.return_value = None

        with pytest.raises(HTTPException) as exc_info:
            get_job("nonexistent-job", mock_job_service)

        assert exc_info.value.status_code == 404
        assert "Job not found" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    async def test_get_job_status_success(self, mock_job_service):
        """Test getting job status returns service result."""
        from app.api.jobs import get_job_status

        mock_status = {"status": "running", "progress": 50}
        mock_job_service.get_job_status.return_value = mock_status

        result = await get_job_status("test-job", mock_job_service)

        # Verify service was called
        mock_job_service.get_job_status.assert_called_once_with("test-job")

        # Verify result is returned
        assert result == mock_status

    @pytest.mark.asyncio
    async def test_get_job_status_with_error_raises_exception(self, mock_job_service):
        """Test getting job status with error raises HTTPException."""
        from app.api.jobs import get_job_status
        from fastapi import HTTPException

        mock_job_service.get_job_status.return_value = {"error": "Job not found"}

        with pytest.raises(HTTPException) as exc_info:
            await get_job_status("test-job", mock_job_service)

        assert exc_info.value.status_code == 404
        assert "Job not found" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    async def test_get_job_status_exception_raises_http_exception(self, mock_job_service):
        """Test getting job status with service exception raises HTTPException."""
        from app.api.jobs import get_job_status
        from fastapi import HTTPException

        mock_job_service.get_job_status.side_effect = Exception("Service error")

        with pytest.raises(HTTPException) as exc_info:
            await get_job_status("test-job", mock_job_service)

        assert exc_info.value.status_code == 500
        assert "Service error" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    async def test_get_job_output_success(self, mock_job_service):
        """Test getting job output returns service result."""
        from app.api.jobs import get_job_output

        mock_output = {"lines": ["line1", "line2"], "status": "running"}
        mock_job_service.get_job_output.return_value = mock_output

        result = await get_job_output("test-job", mock_job_service, last_n_lines=50)

        # Verify service was called
        mock_job_service.get_job_output.assert_called_once_with("test-job", 50)

        # Verify result is returned
        assert result == mock_output

    @pytest.mark.asyncio
    async def test_get_job_output_with_error_raises_exception(self, mock_job_service):
        """Test getting job output with error raises HTTPException."""
        from app.api.jobs import get_job_output
        from fastapi import HTTPException

        mock_job_service.get_job_output.return_value = {"error": "Job not found"}

        with pytest.raises(HTTPException) as exc_info:
            await get_job_output("test-job", mock_job_service)

        assert exc_info.value.status_code == 404
        assert "Job not found" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    async def test_get_job_output_exception_raises_http_exception(self, mock_job_service):
        """Test getting job output with service exception raises HTTPException."""
        from app.api.jobs import get_job_output
        from fastapi import HTTPException

        mock_job_service.get_job_output.side_effect = Exception("Service error")

        with pytest.raises(HTTPException) as exc_info:
            await get_job_output("test-job", mock_job_service)

        assert exc_info.value.status_code == 500
        assert "Service error" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    async def test_stream_all_jobs_success(self, mock_stream_service):
        """Test streaming all jobs returns service result."""
        from app.api.jobs import stream_all_jobs

        mock_stream = "mock-stream-response"
        mock_stream_service.stream_all_jobs.return_value = mock_stream

        result = await stream_all_jobs(mock_stream_service)

        # Verify service was called
        mock_stream_service.stream_all_jobs.assert_called_once()

        # Verify result is returned
        assert result == mock_stream

    @pytest.mark.asyncio
    async def test_stream_job_output_success(self, mock_stream_service):
        """Test streaming job output returns service result."""
        from app.api.jobs import stream_job_output

        mock_stream = "mock-job-stream-response"
        mock_stream_service.stream_job_output.return_value = mock_stream

        result = await stream_job_output("test-job", mock_stream_service)

        # Verify service was called
        mock_stream_service.stream_job_output.assert_called_once_with("test-job")

        # Verify result is returned
        assert result == mock_stream

    @pytest.mark.asyncio
    async def test_cancel_job_success(self, mock_job_service):
        """Test successfully cancelling a job."""
        from app.api.jobs import cancel_job

        mock_job_service.cancel_job.return_value = True

        result = await cancel_job("test-job", mock_job_service)

        # Verify service was called
        mock_job_service.cancel_job.assert_called_once_with("test-job")

        # Verify success response
        assert result == {"message": "Job cancelled successfully"}

    @pytest.mark.asyncio
    async def test_cancel_job_not_found_raises_exception(self, mock_job_service):
        """Test cancelling non-existent job raises HTTPException."""
        from app.api.jobs import cancel_job
        from fastapi import HTTPException

        mock_job_service.cancel_job.return_value = False

        with pytest.raises(HTTPException) as exc_info:
            await cancel_job("nonexistent-job", mock_job_service)

        assert exc_info.value.status_code == 404
        assert "Job not found" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    async def test_toggle_job_details_success_htmx_response(self, mock_request, mock_templates, mock_render_service, mock_job_service):
        """Test toggling job details returns correct HTMX response."""
        from app.api.jobs import toggle_job_details

        mock_job = {"id": "test-job", "expand_details": True}
        mock_render_service.get_job_for_render.return_value = mock_job

        await toggle_job_details(
            "test-job", mock_request, mock_render_service, mock_templates, mock_job_service, expanded="false"
        )

        # Verify render service was called
        mock_render_service.get_job_for_render.assert_called_once_with("test-job", mock_job_service.db)

        # Verify template response
        mock_templates.TemplateResponse.assert_called_once_with(mock_request, "partials/jobs/job_item.html", mock_job)

    @pytest.mark.asyncio
    async def test_toggle_job_details_not_found_raises_exception(self, mock_request, mock_templates, mock_render_service, mock_job_service):
        """Test toggling details for non-existent job raises HTTPException."""
        from app.api.jobs import toggle_job_details
        from fastapi import HTTPException

        mock_render_service.get_job_for_render.return_value = None

        with pytest.raises(HTTPException) as exc_info:
            await toggle_job_details(
                "nonexistent-job", mock_request, mock_render_service, mock_templates, mock_job_service
            )

        assert exc_info.value.status_code == 404
        assert "Job not found" in str(exc_info.value.detail)

    def test_run_database_migration_success(self, mock_job_service):
        """Test successful database migration."""
        from app.api.jobs import run_database_migration

        mock_job_service.run_database_migration.return_value = {"message": "Database migration completed successfully"}

        result = run_database_migration(mock_job_service)

        # Verify service was called
        mock_job_service.run_database_migration.assert_called_once()

        # Verify success response
        assert result == {"message": "Database migration completed successfully"}

    def test_run_database_migration_failure_raises_exception(self, mock_job_service):
        """Test database migration failure raises HTTPException."""
        from app.api.jobs import run_database_migration
        from fastapi import HTTPException

        mock_job_service.run_database_migration.side_effect = Exception("Migration error")

        with pytest.raises(HTTPException) as exc_info:
            run_database_migration(mock_job_service)

        assert exc_info.value.status_code == 500
        assert "Migration failed: Migration error" in str(exc_info.value.detail)