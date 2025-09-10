"""
Tests for sync API endpoints
"""
import pytest
from httpx import AsyncClient
from unittest.mock import Mock

from app.main import app
from app.models.database import Repository, Job, CloudSyncConfig
from app.dependencies import get_rclone_service


class TestSyncEndpoints:
    """Test class for sync API endpoints."""
    
    @pytest.mark.asyncio
    async def test_list_remotes(self, async_client: AsyncClient, mock_rclone_service):
        """Test listing configured remotes."""
        mock_rclone_service.get_configured_remotes.return_value = ["remote1", "remote2"]
        
        # Override dependency injection
        app.dependency_overrides[get_rclone_service] = lambda: mock_rclone_service
        
        try:
            response = await async_client.get("/api/sync/remotes")
        finally:
            # Clean up
            if get_rclone_service in app.dependency_overrides:
                del app.dependency_overrides[get_rclone_service]
        
        assert response.status_code == 200
        data = response.json()
        assert "remotes" in data
        assert data["remotes"] == ["remote1", "remote2"]
    
    @pytest.mark.asyncio
    async def test_sync_repository_success(self, async_client: AsyncClient, test_db, sample_sync_request, mock_rclone_service):
        """Test successful repository sync initiation."""
        # Create test repository in database
        repository = Repository(
            id=1,
            name="test-repo",
            path="/tmp/test-repo"
        )
        repository.set_passphrase("test-passphrase")  # Set encrypted passphrase
        test_db.add(repository)
        test_db.commit()
        
        # Override dependency injection
        app.dependency_overrides[get_rclone_service] = lambda: mock_rclone_service
        
        try:
            response = await async_client.post(
                "/api/sync/sync",
                json=sample_sync_request
            )
            
            assert response.status_code == 200
            data = response.json()
            assert "job_id" in data
            assert data["status"] == "started"
            assert isinstance(data["job_id"], str)  # UUID is now a string
            
            # Verify job was created in database
            job = test_db.query(Job).filter(Job.id == data["job_id"]).first()
            assert job is not None
            assert job.repository_id == sample_sync_request["repository_id"]
            assert job.type == "sync"
            assert job.status == "pending"
        finally:
            # Clean up
            if get_rclone_service in app.dependency_overrides:
                del app.dependency_overrides[get_rclone_service]
    
    @pytest.mark.asyncio
    async def test_sync_repository_not_found(self, async_client: AsyncClient, sample_sync_request):
        """Test sync request with non-existent repository."""
        response = await async_client.post(
            "/api/sync/sync",
            json=sample_sync_request
        )
        
        assert response.status_code == 404
        data = response.json()
        assert data["detail"] == "Repository not found"
    
    @pytest.mark.asyncio
    async def test_sync_repository_invalid_data(self, async_client: AsyncClient):
        """Test sync request with invalid data."""
        invalid_request = {
            "repository_id": "not-a-number",  # Invalid type
            "remote_name": "test-config"
            # Missing required fields
        }
        
        response = await async_client.post(
            "/api/sync/sync",
            json=invalid_request
        )
        
        assert response.status_code == 422  # Validation error


class TestSyncRepositoryTask:
    """Test class for sync repository background task."""
    
    @pytest.mark.asyncio
    async def test_sync_repository_task_success(self, test_db, mock_rclone_service):
        """Test successful sync repository task execution."""
        from app.api.sync import sync_repository_task
        
        # Create test data
        repository = Repository(id=1, name="test-repo", path="/tmp/test-repo")
        repository.set_passphrase("test-passphrase")  # Set encrypted passphrase
        job = Job(id=1, repository_id=1, type="sync", status="pending")
        config = CloudSyncConfig(
            id=1,
            name="test-config", 
            provider="s3",
            bucket_name="test-bucket",
            encrypted_access_key="encrypted_key",
            encrypted_secret_key="encrypted_secret"
        )
        
        test_db.add_all([repository, job, config])
        test_db.commit()
        
        # Mock the get_credentials method
        config.get_credentials = Mock(return_value=("access_key", "secret_key"))
        
        # Execute the task
        await sync_repository_task(
            repository_id=1,
            config_name="test-config",
            bucket_name="test-bucket", 
            path_prefix="backups/",
            job_id=1,
            db_session=test_db,
            rclone=mock_rclone_service
        )
        
        # Verify job was updated
        updated_job = test_db.query(Job).filter(Job.id == 1).first()
        assert updated_job.status == "completed"
        assert updated_job.finished_at is not None
        
        # Verify rclone service was called
        mock_rclone_service.sync_repository_to_s3.assert_called_once()
    
    @pytest.mark.asyncio 
    async def test_sync_repository_task_missing_records(self, test_db, mock_rclone_service):
        """Test sync task with missing database records."""
        from app.api.sync import sync_repository_task
        
        # Execute task without creating required records
        await sync_repository_task(
            repository_id=999,  # Non-existent
            config_name="non-existent",
            bucket_name="test-bucket",
            path_prefix="backups/",
            job_id=999,  # Non-existent
            db_session=test_db,
            rclone=mock_rclone_service
        )
        
        # Verify rclone service was not called
        mock_rclone_service.sync_repository_to_s3.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_sync_repository_task_rclone_error(self, test_db, mock_rclone_service):
        """Test sync task handling rclone service errors."""
        from app.api.sync import sync_repository_task
        
        # Create test data
        repository = Repository(id=1, name="test-repo", path="/tmp/test-repo")
        repository.set_passphrase("test-passphrase")  # Set encrypted passphrase
        job = Job(id=1, repository_id=1, type="sync", status="pending")
        config = CloudSyncConfig(
            id=1,
            name="test-config",
            provider="s3", 
            bucket_name="test-bucket",
            encrypted_access_key="encrypted_key",
            encrypted_secret_key="encrypted_secret"
        )
        
        test_db.add_all([repository, job, config])
        test_db.commit()
        
        # Mock credentials and error generator
        config.get_credentials = Mock(return_value=("access_key", "secret_key"))
        
        async def error_generator():
            yield {"type": "log", "stream": "stdout", "message": "Starting sync"}
            yield {"type": "error", "message": "Sync failed"}
        
        mock_rclone_service.sync_repository_to_s3.return_value = error_generator()
        
        # Execute the task
        await sync_repository_task(
            repository_id=1,
            config_name="test-config", 
            bucket_name="test-bucket",
            path_prefix="backups/",
            job_id=1,
            db_session=test_db,
            rclone=mock_rclone_service
        )
        
        # Verify job was marked as failed
        updated_job = test_db.query(Job).filter(Job.id == 1).first()
        assert updated_job.status == "failed"
        assert updated_job.error == "Sync failed"
        assert updated_job.finished_at is not None