"""
Tests for refactored jobs API endpoints
"""
import pytest
from httpx import AsyncClient
from unittest.mock import Mock, AsyncMock, patch

from app.models.database import Repository, Job
from app.models.schemas import BackupRequest, PruneRequest, CheckRequest


class TestJobsAPI:
    """Test class for jobs API endpoints after refactoring."""

    @pytest.mark.asyncio
    async def test_create_backup_success(self, async_client: AsyncClient, test_db):
        """Test successful backup job creation."""
        # Create test repository
        repository = Repository(id=1, name="test-repo", path="/tmp/test-repo")
        repository.set_passphrase("test-passphrase")
        test_db.add(repository)
        test_db.commit()
        
        backup_data = {
            "repository_id": 1,
            "source_path": "/data",
            "compression": "lz4",
            "dry_run": False
        }
        
        with patch('app.api.jobs.job_service') as mock_service:
            mock_service.create_backup_job = AsyncMock(return_value={"job_id": "job-123", "status": "started"})
            
            response = await async_client.post("/api/jobs/backup", json=backup_data)
            
            assert response.status_code == 200
            data = response.json()
            assert data["job_id"] == "job-123"
            assert data["status"] == "started"
            
            # Verify service was called
            mock_service.create_backup_job.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_backup_repository_not_found(self, async_client: AsyncClient):
        """Test backup creation with non-existent repository."""
        backup_data = {
            "repository_id": 999,
            "source_path": "/data",
            "compression": "lz4",
            "dry_run": False
        }
        
        with patch('app.api.jobs.job_service') as mock_service:
            mock_service.create_backup_job = AsyncMock(side_effect=ValueError("Repository not found"))
            
            response = await async_client.post("/api/jobs/backup", json=backup_data)
            
            assert response.status_code == 404
            assert response.json()["detail"] == "Repository not found"

    @pytest.mark.asyncio
    async def test_create_backup_service_error(self, async_client: AsyncClient):
        """Test backup creation with service error."""
        backup_data = {
            "repository_id": 1,
            "source_path": "/data",
            "compression": "lz4",
            "dry_run": False
        }
        
        with patch('app.api.jobs.job_service') as mock_service:
            mock_service.create_backup_job = AsyncMock(side_effect=Exception("Service error"))
            
            response = await async_client.post("/api/jobs/backup", json=backup_data)
            
            assert response.status_code == 500
            assert "Failed to start backup" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_create_prune_success(self, async_client: AsyncClient):
        """Test successful prune job creation."""
        prune_data = {
            "repository_id": 1,
            "strategy": "simple",
            "keep_within_days": 30,
            "dry_run": False,
            "show_list": True,
            "show_stats": True,
            "save_space": False,
            "force_prune": False
        }
        
        with patch('app.api.jobs.job_service') as mock_service:
            mock_service.create_prune_job = AsyncMock(return_value={"job_id": "prune-123", "status": "started"})
            
            response = await async_client.post("/api/jobs/prune", json=prune_data)
            
            assert response.status_code == 200
            data = response.json()
            assert data["job_id"] == "prune-123"
            assert data["status"] == "started"

    @pytest.mark.asyncio
    async def test_create_check_success(self, async_client: AsyncClient):
        """Test successful check job creation."""
        check_data = {
            "repository_id": 1,
            "check_type": "repository",
            "verify_data": True,
            "repair_mode": False,
            "save_space": True,
            "max_duration": 3600
        }
        
        with patch('app.api.jobs.job_service') as mock_service:
            mock_service.create_check_job = AsyncMock(return_value={"job_id": "check-123", "status": "started"})
            
            response = await async_client.post("/api/jobs/check", json=check_data)
            
            assert response.status_code == 200
            data = response.json()
            assert data["job_id"] == "check-123"
            assert data["status"] == "started"

    @pytest.mark.asyncio
    async def test_create_check_policy_not_found(self, async_client: AsyncClient):
        """Test check creation with non-existent policy."""
        check_data = {
            "repository_id": 1,
            "check_config_id": 999
        }
        
        with patch('app.api.jobs.job_service') as mock_service:
            mock_service.create_check_job = AsyncMock(side_effect=ValueError("Check policy not found"))
            
            response = await async_client.post("/api/jobs/check", json=check_data)
            
            assert response.status_code == 404
            assert response.json()["detail"] == "Check policy not found"

    @pytest.mark.asyncio
    async def test_create_check_policy_disabled(self, async_client: AsyncClient):
        """Test check creation with disabled policy."""
        check_data = {
            "repository_id": 1,
            "check_config_id": 1
        }
        
        with patch('app.api.jobs.job_service') as mock_service:
            mock_service.create_check_job = AsyncMock(side_effect=ValueError("Check policy is disabled"))
            
            response = await async_client.post("/api/jobs/check", json=check_data)
            
            assert response.status_code == 400
            assert response.json()["detail"] == "Check policy is disabled"

    @pytest.mark.asyncio
    async def test_stream_all_jobs(self, async_client: AsyncClient):
        """Test streaming all jobs endpoint."""
        with patch('app.api.jobs.job_stream_service') as mock_service:
            mock_response = Mock()
            mock_service.stream_all_jobs = AsyncMock(return_value=mock_response)
            
            response = await async_client.get("/api/jobs/stream")
            
            # The response should be the mock response from the service
            assert response == mock_response
            mock_service.stream_all_jobs.assert_called_once()

    def test_list_jobs(self, async_client, test_db):
        """Test listing jobs endpoint."""
        with patch('app.api.jobs.job_service') as mock_service:
            mock_jobs = [
                {
                    "id": 1,
                    "job_id": "1",
                    "type": "backup",
                    "status": "completed",
                    "source": "database"
                }
            ]
            mock_service.list_jobs.return_value = mock_jobs
            
            response = async_client.get("/api/jobs/?skip=0&limit=10")
            
            assert response.status_code == 200
            data = response.json()
            assert len(data) == 1
            assert data[0]["type"] == "backup"
            
            # Verify service was called with correct parameters
            mock_service.list_jobs.assert_called_once_with(0, 10, None, test_db)

    def test_list_jobs_with_type_filter(self, async_client, test_db):
        """Test listing jobs with type filter."""
        with patch('app.api.jobs.job_service') as mock_service:
            mock_service.list_jobs.return_value = []
            
            response = async_client.get("/api/jobs/?type=backup")
            
            assert response.status_code == 200
            
            # Verify service was called with type filter
            mock_service.list_jobs.assert_called_once_with(0, 100, "backup", test_db)

    def test_get_jobs_html(self, async_client, test_db):
        """Test getting jobs HTML endpoint."""
        with patch('app.api.jobs.job_render_service') as mock_service:
            mock_service.render_jobs_html.return_value = "<div>Jobs HTML</div>"
            
            response = async_client.get("/api/jobs/html")
            
            assert response.status_code == 200
            assert response.headers["content-type"] == "text/html; charset=utf-8"
            assert response.text == "<div>Jobs HTML</div>"
            
            # Verify service was called
            mock_service.render_jobs_html.assert_called_once_with(test_db, None)

    def test_get_jobs_html_with_expand(self, async_client, test_db):
        """Test getting jobs HTML with expand parameter."""
        with patch('app.api.jobs.job_render_service') as mock_service:
            mock_service.render_jobs_html.return_value = "<div>Expanded Jobs HTML</div>"
            
            response = async_client.get("/api/jobs/html?expand=123")
            
            assert response.status_code == 200
            assert response.text == "<div>Expanded Jobs HTML</div>"
            
            # Verify service was called with expand parameter
            mock_service.render_jobs_html.assert_called_once_with(test_db, "123")

    def test_get_current_jobs_html(self, async_client):
        """Test getting current jobs HTML endpoint."""
        with patch('app.api.jobs.job_render_service') as mock_service:
            mock_service.render_current_jobs_html.return_value = "<div>Current Jobs</div>"
            
            response = async_client.get("/api/jobs/current/html")
            
            assert response.status_code == 200
            assert response.headers["content-type"] == "text/html; charset=utf-8"
            assert response.text == "<div>Current Jobs</div>"
            
            mock_service.render_current_jobs_html.assert_called_once()

    def test_get_job_success(self, async_client, test_db):
        """Test getting job details."""
        mock_job = {
            "id": 1,
            "job_id": "1",
            "type": "backup",
            "status": "completed",
            "source": "database"
        }
        
        with patch('app.api.jobs.job_service') as mock_service:
            mock_service.get_job.return_value = mock_job
            
            response = async_client.get("/api/jobs/1")
            
            assert response.status_code == 200
            data = response.json()
            assert data["type"] == "backup"
            assert data["status"] == "completed"
            
            mock_service.get_job.assert_called_once_with("1", test_db)

    def test_get_job_not_found(self, async_client, test_db):
        """Test getting non-existent job."""
        with patch('app.api.jobs.job_service') as mock_service:
            mock_service.get_job.return_value = None
            
            response = async_client.get("/api/jobs/999")
            
            assert response.status_code == 404
            assert response.json()["detail"] == "Job not found"

    @pytest.mark.asyncio
    async def test_get_job_status_success(self, async_client):
        """Test getting job status."""
        mock_status = {"status": "running", "progress": 50}
        
        with patch('app.api.jobs.job_service') as mock_service:
            mock_service.get_job_status = AsyncMock(return_value=mock_status)
            
            response = await async_client.get("/api/jobs/job-123/status")
            
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "running"
            assert data["progress"] == 50

    @pytest.mark.asyncio
    async def test_get_job_status_with_error(self, async_client):
        """Test getting job status when output contains error."""
        mock_status = {"error": "Job not found"}
        
        with patch('app.api.jobs.job_service') as mock_service:
            mock_service.get_job_status = AsyncMock(return_value=mock_status)
            
            response = await async_client.get("/api/jobs/job-123/status")
            
            assert response.status_code == 404
            assert response.json()["detail"] == "Job not found"

    @pytest.mark.asyncio
    async def test_get_job_output_success(self, async_client, test_db):
        """Test getting job output."""
        mock_output = {
            "job_id": "job-123",
            "status": "running",
            "lines": ["Starting backup...", "Processing files..."]
        }
        
        with patch('app.api.jobs.job_service') as mock_service:
            mock_service.get_job_output = AsyncMock(return_value=mock_output)
            
            response = await async_client.get("/api/jobs/job-123/output?last_n_lines=50")
            
            assert response.status_code == 200
            data = response.json()
            assert data["job_id"] == "job-123"
            assert len(data["lines"]) == 2
            
            mock_service.get_job_output.assert_called_once_with("job-123", 50)

    @pytest.mark.asyncio
    async def test_stream_job_output(self, async_client, test_db):
        """Test streaming job output endpoint."""
        with patch('app.api.jobs.job_stream_service') as mock_service:
            mock_response = Mock()
            mock_service.stream_job_output = AsyncMock(return_value=mock_response)
            
            response = await async_client.get("/api/jobs/job-123/stream")
            
            assert response == mock_response
            mock_service.stream_job_output.assert_called_once_with("job-123")

    @pytest.mark.asyncio
    async def test_cancel_job_success(self, async_client, test_db):
        """Test cancelling a job successfully."""
        with patch('app.api.jobs.job_service') as mock_service:
            mock_service.cancel_job = AsyncMock(return_value=True)
            
            response = await async_client.delete("/api/jobs/job-123")
            
            assert response.status_code == 200
            data = response.json()
            assert data["message"] == "Job cancelled successfully"
            
            mock_service.cancel_job.assert_called_once_with("job-123", test_db)

    @pytest.mark.asyncio
    async def test_cancel_job_not_found(self, async_client, test_db):
        """Test cancelling a non-existent job."""
        with patch('app.api.jobs.job_service') as mock_service:
            mock_service.cancel_job = AsyncMock(return_value=False)
            
            response = await async_client.delete("/api/jobs/job-999")
            
            assert response.status_code == 404
            assert response.json()["detail"] == "Job not found"

    def test_get_manager_stats(self, async_client):
        """Test getting manager statistics."""
        mock_stats = {
            "total_jobs": 10,
            "running_jobs": 2,
            "completed_jobs": 7,
            "failed_jobs": 1,
            "active_processes": 2
        }
        
        with patch('app.api.jobs.job_service') as mock_service:
            mock_service.get_manager_stats.return_value = mock_stats
            
            response = async_client.get("/api/jobs/manager/stats")
            
            assert response.status_code == 200
            data = response.json()
            assert data["total_jobs"] == 10
            assert data["running_jobs"] == 2
            assert data["completed_jobs"] == 7
            assert data["failed_jobs"] == 1

    def test_cleanup_completed_jobs(self, async_client):
        """Test cleaning up completed jobs."""
        with patch('app.api.jobs.job_service') as mock_service:
            mock_service.cleanup_completed_jobs.return_value = 5
            
            response = async_client.post("/api/jobs/manager/cleanup")
            
            assert response.status_code == 200
            data = response.json()
            assert data["message"] == "Cleaned up 5 completed jobs"

    def test_get_queue_stats(self, async_client):
        """Test getting queue statistics."""
        mock_stats = {"queued": 3, "processing": 1}
        
        with patch('app.api.jobs.job_service') as mock_service:
            mock_service.get_queue_stats.return_value = mock_stats
            
            response = async_client.get("/api/jobs/queue/stats")
            
            assert response.status_code == 200
            data = response.json()
            assert data["queued"] == 3
            assert data["processing"] == 1

    def test_run_database_migration_success(self, async_client, test_db):
        """Test successful database migration."""
        with patch('app.api.jobs.migrate_job_table', create=True) as mock_migrate:
            mock_migrate.return_value = None  # Success
            
            response = client.post("/api/jobs/migrate")
            
            assert response.status_code == 200
            data = response.json()
            assert data["message"] == "Database migration completed successfully"
            
            mock_migrate.assert_called_once()

    def test_run_database_migration_failure(self, async_client, test_db):
        """Test failed database migration."""
        with patch('app.api.jobs.migrate_job_table', create=True) as mock_migrate:
            mock_migrate.side_effect = Exception("Migration error")
            
            response = client.post("/api/jobs/migrate")
            
            assert response.status_code == 500
            assert "Migration failed" in response.json()["detail"]