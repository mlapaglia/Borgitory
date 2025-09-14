"""
Comprehensive tests for JobManager covering missing test coverage areas.
Focuses on task execution, error handling, notifications, and edge cases.
"""
import pytest
import asyncio
from unittest.mock import AsyncMock, Mock, patch
from datetime import datetime, UTC

from app.services.job_manager import (
    JobManager,
    BorgJob,
    BorgJobTask,
    get_job_manager,
    reset_job_manager
)
from app.services.job_manager import (
    JobManagerConfig,
    JobManagerFactory
)
from app.services.job_executor import ProcessResult
from app.models.database import Repository, NotificationConfig, CloudSyncConfig


# Database fixtures for comprehensive tests
@pytest.fixture
def sample_repository(test_db):
    """Create a sample repository for testing."""
    repository = Repository(
        name="test-repo",
        path="/tmp/test-repo",
        encrypted_passphrase="test-encrypted-passphrase"
    )
    test_db.add(repository)
    test_db.commit()
    test_db.refresh(repository)
    return repository


@pytest.fixture
def sample_notification_config(test_db):
    """Create a sample notification config for testing."""
    config = NotificationConfig(
        name="test-pushover",
        provider="pushover",
        enabled=True,
        notify_on_success=True,
        notify_on_failure=True
    )
    # Set encrypted credentials using the model method
    config.set_pushover_credentials("test_user_key", "test_app_token")
    test_db.add(config)
    test_db.commit()
    test_db.refresh(config)
    return config


@pytest.fixture
def sample_cloud_sync_config(test_db):
    """Create a sample cloud sync config for testing."""
    config = CloudSyncConfig(
        name="test-s3-sync",
        provider="s3",
        remote_name="test-remote",
        bucket_name="test-bucket",
        enabled=True
    )
    test_db.add(config)
    test_db.commit()
    test_db.refresh(config)
    return config


class TestBorgJobTask:
    """Test BorgJobTask data class functionality"""
    
    def test_task_creation(self):
        """Test BorgJobTask creation with defaults"""
        task = BorgJobTask(
            task_type="backup",
            task_name="Test backup"
        )
        
        assert task.task_type == "backup"
        assert task.task_name == "Test backup"
        assert task.status == "pending"
        assert task.started_at is None
        assert task.completed_at is None
        assert task.return_code is None
        assert task.error is None
        assert task.parameters == {}
        assert task.output_lines == []


class TestBorgJob:
    """Test BorgJob data class functionality"""
    
    def test_job_creation(self):
        """Test BorgJob creation with defaults"""
        job = BorgJob(
            id="test-123",
            status="pending",
            started_at=datetime.now(UTC)
        )
        
        assert job.id == "test-123"
        assert job.status == "pending"
        assert job.completed_at is None
        assert job.return_code is None
        assert job.error is None
        assert job.command is None
        assert job.job_type == "simple"
        assert job.tasks == []
        assert job.current_task_index == 0
        assert job.repository_id is None
        assert job.schedule is None
        assert job.cloud_sync_config_id is None
    
    def test_get_current_task_simple_job(self):
        """Test get_current_task for simple job returns None"""
        job = BorgJob(
            id="test-123",
            status="pending",
            started_at=datetime.now(UTC),
            job_type="simple"
        )
        
        assert job.get_current_task() is None
    
    def test_get_current_task_composite_job(self):
        """Test get_current_task for composite job with tasks"""
        task1 = BorgJobTask(task_type="backup", task_name="Backup")
        task2 = BorgJobTask(task_type="prune", task_name="Prune")
        
        job = BorgJob(
            id="test-123",
            status="running",
            started_at=datetime.now(UTC),
            job_type="composite",
            tasks=[task1, task2],
            current_task_index=1
        )
        
        current = job.get_current_task()
        assert current is not None
        assert current.task_type == "prune"
        assert current.task_name == "Prune"
    
    def test_get_current_task_invalid_index(self):
        """Test get_current_task with invalid index returns None"""
        task = BorgJobTask(task_type="backup", task_name="Backup")
        
        job = BorgJob(
            id="test-123",
            status="running",
            started_at=datetime.now(UTC),
            job_type="composite",
            tasks=[task],
            current_task_index=5  # Out of range
        )
        
        assert job.get_current_task() is None
    
    def test_is_composite_simple_job(self):
        """Test is_composite returns False for simple job"""
        job = BorgJob(
            id="test-123",
            status="pending",
            started_at=datetime.now(UTC),
            job_type="simple"
        )
        
        assert job.is_composite() is False
    
    def test_is_composite_composite_job_no_tasks(self):
        """Test is_composite returns False for composite job with no tasks"""
        job = BorgJob(
            id="test-123",
            status="pending",
            started_at=datetime.now(UTC),
            job_type="composite",
            tasks=[]
        )
        
        assert job.is_composite() is False
    
    def test_is_composite_composite_job_with_tasks(self):
        """Test is_composite returns True for composite job with tasks"""
        task = BorgJobTask(task_type="backup", task_name="Backup")
        
        job = BorgJob(
            id="test-123",
            status="pending",
            started_at=datetime.now(UTC),
            job_type="composite",
            tasks=[task]
        )
        
        assert job.is_composite() is True


class TestJobManagerErrorHandling:
    """Test error handling and edge cases in job execution"""
    
    def setup_method(self):
        """Set up test fixtures"""
        self.config = JobManagerConfig(
            max_concurrent_backups=1,
            auto_cleanup_delay_seconds=1
        )
        self.mock_dependencies = JobManagerFactory.create_for_testing()
        self.job_manager = JobManager(
            config=self.config,
            dependencies=self.mock_dependencies
        )
    
    @pytest.mark.asyncio
    async def test_execute_simple_job_process_start_failure(self):
        """Test _execute_simple_job when process start fails"""
        job = BorgJob(
            id="test-job",
            status="pending",
            started_at=datetime.now(UTC),
            job_type="simple"
        )
        
        # Mock executor to raise exception on start_process
        with patch.object(self.job_manager.executor, 'start_process', side_effect=Exception("Process start failed")):
            await self.job_manager._execute_simple_job(job, ["borg", "info", "repo"])
            
            assert job.status == "failed"
            assert job.error == "Process start failed"
            assert job.completed_at is not None
    
    @pytest.mark.asyncio
    async def test_execute_simple_job_process_execution_failure(self):
        """Test _execute_simple_job when process execution fails"""
        job = BorgJob(
            id="test-job",
            status="pending",
            started_at=datetime.now(UTC),
            job_type="simple"
        )
        
        mock_process = AsyncMock()
        mock_result = ProcessResult(
            return_code=1,
            stdout=b"",
            stderr=b"Error output",
            error="Execution failed"
        )
        
        with patch.object(self.job_manager.executor, 'start_process', return_value=mock_process), \
             patch.object(self.job_manager.executor, 'monitor_process_output', return_value=mock_result):
            
            await self.job_manager._execute_simple_job(job, ["borg", "info", "repo"])
            
            assert job.status == "failed"
            assert job.return_code == 1
            assert job.error == "Execution failed"
            assert job.completed_at is not None


class TestJobManagerTaskExecution:
    """Test individual task execution methods"""

    @pytest.fixture
    def job_manager(self):
        """Create job manager for testing"""
        config = JobManagerConfig()
        mock_dependencies = JobManagerFactory.create_for_testing()
        return JobManager(
            config=config,
            dependencies=mock_dependencies
        )
    
    @pytest.mark.asyncio
    async def test_execute_backup_task_success(self, job_manager, sample_repository):
        """Test successful backup task execution"""
        job = BorgJob(
            id="test-job",
            status="running",
            started_at=datetime.now(UTC),
            job_type="composite",
            repository_id=sample_repository.id
        )

        task = BorgJobTask(
            task_type="backup",
            task_name="Test backup",
            parameters={
                "source_path": "/data",
                "compression": "zstd",
                "dry_run": False
            }
        )

        mock_result = ProcessResult(return_code=0, stdout=b"", stderr=b"")

        with patch.object(job_manager.executor, 'start_process', return_value=AsyncMock()), \
             patch.object(job_manager.executor, 'monitor_process_output', return_value=mock_result):

            success = await job_manager._execute_backup_task(job, task, 0)

            assert success is True
            assert task.return_code == 0
            assert task.error is None
    
    @pytest.mark.asyncio
    async def test_execute_backup_task_repo_not_found(self):
        """Test backup task when repository not found"""
        job = BorgJob(
            id="test-job",
            status="running",
            started_at=datetime.now(UTC),
            job_type="composite",
            repository_id=999  # Non-existent
        )
        
        task = BorgJobTask(
            task_type="backup",
            task_name="Test backup"
        )
        
        with patch.object(self.job_manager, '_get_repository_data', return_value=None):
            success = await self.job_manager._execute_backup_task(job, task, 0)
            
            assert success is False
            assert task.return_code == 1
            assert task.error == "Repository not found"
    
    @pytest.mark.asyncio
    async def test_execute_backup_task_process_failure(self):
        """Test backup task when Borg process fails"""
        job = BorgJob(
            id="test-job",
            status="running",
            started_at=datetime.now(UTC),
            job_type="composite",
            repository_id=1
        )
        
        task = BorgJobTask(
            task_type="backup",
            task_name="Test backup",
            parameters={"source_path": "/data"}
        )
        
        mock_result = ProcessResult(return_code=2, stdout=b"", stderr=b"Backup failed")
        
        with patch.object(self.job_manager, '_get_repository_data', return_value=self.repo_data), \
             patch.object(self.job_manager.executor, 'start_process', return_value=AsyncMock()), \
             patch.object(self.job_manager.executor, 'monitor_process_output', return_value=mock_result):
            
            success = await self.job_manager._execute_backup_task(job, task, 0)
            
            assert success is False
            assert task.return_code == 2
            assert "Backup failed with return code 2" in task.error
    
    @pytest.mark.asyncio
    async def test_execute_backup_task_exception(self):
        """Test backup task when exception occurs"""
        job = BorgJob(
            id="test-job",
            status="running",
            started_at=datetime.now(UTC),
            job_type="composite",
            repository_id=1
        )
        
        task = BorgJobTask(
            task_type="backup",
            task_name="Test backup"
        )
        
        with patch.object(self.job_manager, '_get_repository_data', return_value=self.repo_data), \
             patch.object(self.job_manager.executor, 'start_process', side_effect=Exception("Unexpected error")):
            
            success = await self.job_manager._execute_backup_task(job, task, 0)
            
            assert success is False
            assert task.return_code == 1
            assert "Backup task failed: Unexpected error" in task.error
    
    @pytest.mark.asyncio
    async def test_execute_prune_task_success(self):
        """Test successful prune task execution"""
        job = BorgJob(
            id="test-job",
            status="running",
            started_at=datetime.now(UTC),
            job_type="composite",
            repository_id=1
        )
        
        task = BorgJobTask(
            task_type="prune",
            task_name="Test prune",
            parameters={
                "keep_daily": 7,
                "keep_weekly": 4,
                "dry_run": False
            }
        )
        
        mock_result = ProcessResult(return_code=0, stdout=b"", stderr=b"")
        
        with patch.object(self.job_manager, '_get_repository_data', return_value=self.repo_data), \
             patch.object(self.job_manager.executor, 'execute_prune_task', return_value=mock_result):
            
            success = await self.job_manager._execute_prune_task(job, task, 0)
            
            assert success is True
            assert task.return_code == 0
    
    @pytest.mark.asyncio
    async def test_execute_prune_task_failure(self):
        """Test prune task execution failure"""
        job = BorgJob(
            id="test-job",
            status="running",
            started_at=datetime.now(UTC),
            job_type="composite",
            repository_id=1
        )
        
        task = BorgJobTask(
            task_type="prune",
            task_name="Test prune"
        )
        
        mock_result = ProcessResult(
            return_code=1,
            stdout=b"",
            stderr=b"",
            error="Prune failed"
        )
        
        with patch.object(self.job_manager, '_get_repository_data', return_value=self.repo_data), \
             patch.object(self.job_manager.executor, 'execute_prune_task', return_value=mock_result):
            
            success = await self.job_manager._execute_prune_task(job, task, 0)
            
            assert success is False
            assert task.return_code == 1
            assert task.error == "Prune failed"
    
    @pytest.mark.asyncio
    async def test_execute_check_task_success(self):
        """Test successful check task execution"""
        job = BorgJob(
            id="test-job",
            status="running",
            started_at=datetime.now(UTC),
            job_type="composite",
            repository_id=1
        )
        
        task = BorgJobTask(
            task_type="check",
            task_name="Test check",
            parameters={
                "check_type": "full",
                "verify_data": True
            }
        )
        
        mock_result = ProcessResult(return_code=0, stdout=b"", stderr=b"")
        
        with patch.object(self.job_manager, '_get_repository_data', return_value=self.repo_data), \
             patch.object(self.job_manager.executor, 'start_process', return_value=AsyncMock()), \
             patch.object(self.job_manager.executor, 'monitor_process_output', return_value=mock_result):
            
            success = await self.job_manager._execute_check_task(job, task, 0)
            
            assert success is True
            assert task.return_code == 0
    
    @pytest.mark.asyncio
    async def test_execute_cloud_sync_task_success(self):
        """Test successful cloud sync task execution"""
        job = BorgJob(
            id="test-job",
            status="running",
            started_at=datetime.now(UTC),
            job_type="composite",
            repository_id=1,
            cloud_sync_config_id=1
        )
        
        task = BorgJobTask(
            task_type="cloud_sync",
            task_name="Test cloud sync"
        )
        
        mock_result = ProcessResult(return_code=0, stdout=b"", stderr=b"")
        
        with patch.object(self.job_manager, '_get_repository_data', return_value=self.repo_data), \
             patch.object(self.job_manager.executor, 'execute_cloud_sync_task', return_value=mock_result):
            
            success = await self.job_manager._execute_cloud_sync_task(job, task, 0)
            
            assert success is True
            assert task.return_code == 0


class TestJobManagerNotifications:
    """Test notification task execution"""

    @pytest.fixture
    def job_manager(self):
        """Create job manager for testing"""
        config = JobManagerConfig()
        mock_dependencies = JobManagerFactory.create_for_testing()
        return JobManager(
            config=config,
            dependencies=mock_dependencies
        )
    
    @pytest.mark.asyncio
    async def test_execute_notification_task_no_config_id(self, job_manager, sample_repository):
        """Test notification task when no config ID provided"""
        job = BorgJob(
            id="test-job",
            status="running",
            started_at=datetime.now(UTC),
            job_type="composite",
            repository_id=sample_repository.id
        )

        task = BorgJobTask(
            task_type="notification",
            task_name="Test notification",
            parameters={}  # No config_id
        )

        success = await job_manager._execute_notification_task(job, task, 0)

        assert success is False
        assert task.return_code == 1
        assert task.error == "No notification configuration"
    
    @pytest.mark.asyncio
    async def test_execute_notification_task_config_not_found(self, job_manager, sample_repository):
        """Test notification task when config not found"""
        job = BorgJob(
            id="test-job",
            status="running",
            started_at=datetime.now(UTC),
            job_type="composite",
            repository_id=sample_repository.id
        )

        task = BorgJobTask(
            task_type="notification",
            task_name="Test notification",
            parameters={"config_id": 999}  # Non-existent config ID
        )

        success = await job_manager._execute_notification_task(job, task, 0)

        assert success is True  # Skipped notifications return True
        assert task.status == "skipped"
        assert task.return_code == 0
    
    @pytest.mark.asyncio
    async def test_execute_notification_task_disabled(self, job_manager, sample_repository, test_db):
        """Test notification task when config is disabled"""
        # Create a disabled notification config
        disabled_config = NotificationConfig(
            name="disabled-pushover",
            provider="pushover",
            enabled=False,  # Disabled
            notify_on_success=True,
            notify_on_failure=True
        )
        disabled_config.set_pushover_credentials("test_user", "test_token")
        test_db.add(disabled_config)
        test_db.commit()
        test_db.refresh(disabled_config)

        job = BorgJob(
            id="test-job",
            status="running",
            started_at=datetime.now(UTC),
            job_type="composite",
            repository_id=sample_repository.id
        )

        task = BorgJobTask(
            task_type="notification",
            task_name="Test notification",
            parameters={"config_id": disabled_config.id}
        )

        success = await job_manager._execute_notification_task(job, task, 0)

        assert success is True  # Skipped notifications return True
        assert task.status == "skipped"
        assert task.return_code == 0
    
    @pytest.mark.asyncio
    async def test_execute_notification_task_pushover_success(self, job_manager, sample_repository, sample_notification_config):
        """Test successful Pushover notification"""
        job = BorgJob(
            id="test-job",
            status="running",
            started_at=datetime.now(UTC),
            job_type="composite",
            repository_id=sample_repository.id,
            tasks=[
                BorgJobTask(task_type="backup", task_name="Backup", status="completed")
            ]
        )

        task = BorgJobTask(
            task_type="notification",
            task_name="Test notification",
            parameters={
                "config_id": sample_notification_config.id,
                "notify_on_success": True,
                "notify_on_failure": True
            }
        )

        with patch.object(job_manager, '_send_pushover_notification', return_value=True) as mock_pushover:
            success = await job_manager._execute_notification_task(job, task, 1)

            assert success is True
            assert task.return_code == 0
            mock_pushover.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_send_pushover_notification_success(self, job_manager, sample_repository, sample_notification_config):
        """Test successful Pushover API call"""
        job = BorgJob(id="test", status="running", started_at=datetime.now(UTC))
        task = BorgJobTask(task_type="notification", task_name="Test")

        repo_data = {
            "id": sample_repository.id,
            "name": sample_repository.name,
            "path": sample_repository.path,
            "passphrase": sample_repository.get_passphrase()
        }

        mock_response = Mock()
        mock_response.status_code = 200

        mock_client = Mock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_async_client = Mock()
        mock_async_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_async_client.__aexit__ = AsyncMock(return_value=None)

        with patch('httpx.AsyncClient', return_value=mock_async_client):
            success = await job_manager._send_pushover_notification(
                sample_notification_config, job, repo_data, task, True
            )

            assert success is True
    
    @pytest.mark.asyncio
    async def test_send_pushover_notification_api_error(self, job_manager, sample_repository, sample_notification_config):
        """Test Pushover API error handling"""
        job = BorgJob(id="test", status="running", started_at=datetime.now(UTC))
        task = BorgJobTask(task_type="notification", task_name="Test")

        repo_data = {
            "id": sample_repository.id,
            "name": sample_repository.name,
            "path": sample_repository.path,
            "passphrase": sample_repository.get_passphrase()
        }

        mock_response = Mock()
        mock_response.status_code = 400
        mock_response.text = "Invalid token"

        mock_client = Mock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_async_client = Mock()
        mock_async_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_async_client.__aexit__ = AsyncMock(return_value=None)

        with patch('httpx.AsyncClient', return_value=mock_async_client):
            success = await job_manager._send_pushover_notification(
                sample_notification_config, job, repo_data, task, True
            )

            assert success is False
            assert "Pushover API error: 400" in task.error
            assert len(task.output_lines) > 0


class TestJobManagerRepositoryData:
    """Test repository data access methods"""

    @pytest.fixture
    def job_manager(self):
        """Create job manager for testing"""
        config = JobManagerConfig()
        mock_dependencies = JobManagerFactory.create_for_testing()
        return JobManager(
            config=config,
            dependencies=mock_dependencies
        )
    
    @pytest.mark.asyncio
    async def test_get_repository_data_with_database_manager(self, job_manager, sample_repository):
        """Test _get_repository_data using database manager"""
        expected_data = {
            "id": sample_repository.id,
            "name": sample_repository.name,
            "path": sample_repository.path,
            "passphrase": sample_repository.get_passphrase()
        }

        # Mock database manager
        job_manager.database_manager = Mock()
        job_manager.database_manager.get_repository_data = AsyncMock(return_value=expected_data)

        result = await job_manager._get_repository_data(sample_repository.id)

        assert result == expected_data
        job_manager.database_manager.get_repository_data.assert_called_once_with(sample_repository.id)
    
    @pytest.mark.asyncio
    async def test_get_repository_data_fallback_success(self, job_manager, sample_repository):
        """Test _get_repository_data fallback to direct DB access"""
        # Disable database manager to force fallback
        job_manager.database_manager = None

        result = await job_manager._get_repository_data(sample_repository.id)

        assert result is not None
        assert result["id"] == sample_repository.id
        assert result["name"] == "test-repo"
        assert result["path"] == "/tmp/test-repo"
        assert result["passphrase"] == sample_repository.get_passphrase()
    
    @pytest.mark.asyncio
    async def test_get_repository_data_fallback_not_found(self, job_manager):
        """Test _get_repository_data fallback when repository not found"""
        # Disable database manager
        job_manager.database_manager = None

        result = await job_manager._get_repository_data(999)  # Non-existent ID

        assert result is None


class TestJobManagerEventStreaming:
    """Test event streaming and SSE functionality"""
    
    def setup_method(self):
        """Set up test fixtures"""
        self.config = JobManagerConfig()
        self.mock_dependencies = JobManagerFactory.create_for_testing()
        self.job_manager = JobManager(
            config=self.config,
            dependencies=self.mock_dependencies
        )
    
    @pytest.mark.asyncio
    async def test_stream_job_output(self):
        """Test stream_job_output delegates to output manager"""
        job_id = "test-job"
        expected_output = [
            {"type": "output", "data": {"text": "line 1"}, "progress": {}},
            {"type": "output", "data": {"text": "line 2"}, "progress": {}}
        ]
        
        async def mock_stream():
            for output in expected_output:
                yield output
        
        self.job_manager.output_manager.stream_job_output = Mock(return_value=mock_stream())
        
        result = []
        async for output in self.job_manager.stream_job_output(job_id):
            result.append(output)
        
        assert len(result) == 2
        self.job_manager.output_manager.stream_job_output.assert_called_once_with(job_id, follow=True)
    
    @pytest.mark.asyncio
    async def test_stream_all_job_updates(self):
        """Test stream_all_job_updates delegates to event broadcaster"""
        expected_events = [
            {"type": "job_started", "job_id": "job1"},
            {"type": "job_completed", "job_id": "job1"}
        ]
        
        async def mock_stream():
            for event in expected_events:
                yield event
        
        self.job_manager.event_broadcaster.stream_all_events = Mock(return_value=mock_stream())
        
        result = []
        async for event in self.job_manager.stream_all_job_updates():
            result.append(event)
        
        assert len(result) == 2
        assert result[0]["job_id"] == "job1"
    
    def test_subscribe_to_events_with_broadcaster(self):
        """Test subscribe_to_events when broadcaster supports it"""
        mock_queue = asyncio.Queue()
        self.job_manager.event_broadcaster.subscribe_to_events = Mock(return_value=mock_queue)
        
        result = self.job_manager.subscribe_to_events()
        
        assert result == mock_queue
        self.job_manager.event_broadcaster.subscribe_to_events.assert_called_once()
    
    def test_subscribe_to_events_fallback(self):
        """Test subscribe_to_events fallback when broadcaster doesn't support it"""
        # Create a mock broadcaster without subscribe_to_events method
        mock_broadcaster = Mock(spec=[])
        self.job_manager.event_broadcaster = mock_broadcaster
        
        result = self.job_manager.subscribe_to_events()
        
        assert isinstance(result, asyncio.Queue)
        assert result.maxsize == 100
    
    def test_unsubscribe_from_events_with_broadcaster(self):
        """Test unsubscribe_from_events when broadcaster supports it"""
        mock_queue = asyncio.Queue()
        self.job_manager.event_broadcaster.unsubscribe_from_events = Mock()
        
        self.job_manager.unsubscribe_from_events(mock_queue)
        
        self.job_manager.event_broadcaster.unsubscribe_from_events.assert_called_once_with(mock_queue)
    
    def test_unsubscribe_from_events_fallback(self):
        """Test unsubscribe_from_events fallback when broadcaster doesn't support it"""
        # Create a mock broadcaster without unsubscribe_from_events method
        mock_broadcaster = Mock(spec=[])
        self.job_manager.event_broadcaster = mock_broadcaster
        
        mock_queue = asyncio.Queue()
        
        # Should not raise exception
        self.job_manager.unsubscribe_from_events(mock_queue)


class TestJobManagerFactoryAndSingleton:
    """Test factory pattern and singleton behavior"""
    
    def setup_method(self):
        """Reset singleton for each test"""
        reset_job_manager()
    
    def teardown_method(self):
        """Reset singleton after each test"""
        reset_job_manager()
    
    def test_get_job_manager_default(self):
        """Test get_job_manager with default configuration"""
        manager = get_job_manager()
        
        assert isinstance(manager, JobManager)
        assert manager.config.max_concurrent_backups == 5  # Default from env var or fallback
    
    def test_get_job_manager_singleton_behavior(self):
        """Test that get_job_manager returns same instance"""
        manager1 = get_job_manager()
        manager2 = get_job_manager()
        
        assert manager1 is manager2
    
    def test_get_job_manager_with_config(self):
        """Test get_job_manager with custom config"""
        config = JobManagerConfig(max_concurrent_backups=3)
        
        manager = get_job_manager(config)
        
        assert manager.config.max_concurrent_backups == 3
    
    def test_get_job_manager_with_backward_compatible_config(self):
        """Test get_job_manager with backward compatible config wrapper"""
        # Mock a config with to_internal_config method
        mock_config = Mock()
        internal_config = JobManagerConfig(max_concurrent_backups=2)
        mock_config.to_internal_config.return_value = internal_config
        
        manager = get_job_manager(mock_config)
        
        assert manager.config.max_concurrent_backups == 2
        mock_config.to_internal_config.assert_called_once()
    
    def test_reset_job_manager(self):
        """Test reset_job_manager functionality"""
        # Create manager
        manager1 = get_job_manager()
        
        # Reset
        reset_job_manager()
        
        # Get new manager
        manager2 = get_job_manager()
        
        assert manager1 is not manager2
    
    def test_get_job_manager_with_environment_variables(self):
        """Test get_job_manager reads environment variables"""
        with patch.dict('os.environ', {
            'BORG_MAX_CONCURRENT_BACKUPS': '4',
            'BORG_AUTO_CLEANUP_DELAY': '60',
            'BORG_MAX_OUTPUT_LINES': '2000'
        }):
            manager = get_job_manager()
            
            assert manager.config.max_concurrent_backups == 4
            assert manager.config.auto_cleanup_delay_seconds == 60
            assert manager.config.max_output_lines_per_job == 2000


class TestJobManagerCompositeJobExecution:
    """Test composite job execution with complex scenarios"""
    
    def setup_method(self):
        """Set up test fixtures"""
        self.config = JobManagerConfig()
        self.mock_dependencies = JobManagerFactory.create_for_testing()
        self.job_manager = JobManager(
            config=self.config,
            dependencies=self.mock_dependencies
        )
    
    @pytest.mark.asyncio
    async def test_execute_composite_job_critical_task_failure_skips_remaining(self):
        """Test that critical task failure skips remaining non-notification tasks"""
        # Create job with backup (fails), prune (should be skipped), notification (should run)
        backup_task = BorgJobTask(task_type="backup", task_name="Backup")
        prune_task = BorgJobTask(task_type="prune", task_name="Prune")
        notification_task = BorgJobTask(task_type="notification", task_name="Notification")
        
        job = BorgJob(
            id="test-job",
            status="pending",
            started_at=datetime.now(UTC),
            job_type="composite",
            tasks=[backup_task, prune_task, notification_task],
            repository_id=1
        )
        
        with patch.object(self.job_manager, '_execute_task', side_effect=[False, True, True]) as mock_execute:
            await self.job_manager._execute_composite_job(job)
            
            # Backup should be executed and fail
            assert backup_task.status == "failed"
            # Prune should be skipped
            assert prune_task.status == "skipped"
            # Notification should still be executed
            assert notification_task.status == "completed"
            
            # Job should be marked as failed overall
            assert job.status == "failed"
            
            # Execute should be called for backup and notification, but not prune
            assert mock_execute.call_count == 2
    
    @pytest.mark.asyncio
    async def test_execute_composite_job_exception_handling(self):
        """Test composite job handles exceptions in task execution"""
        task = BorgJobTask(task_type="backup", task_name="Backup")
        
        job = BorgJob(
            id="test-job",
            status="pending",
            started_at=datetime.now(UTC),
            job_type="composite",
            tasks=[task],
            repository_id=1
        )
        
        with patch.object(self.job_manager, '_execute_task', side_effect=Exception("Task execution failed")):
            await self.job_manager._execute_composite_job(job)
            
            assert job.status == "failed"
            assert task.status == "failed"
            assert task.error == "Task execution failed"
    
    @pytest.mark.asyncio
    async def test_execute_task_unknown_type(self):
        """Test _execute_task with unknown task type"""
        job = BorgJob(id="test", status="running", started_at=datetime.now(UTC))
        task = BorgJobTask(task_type="unknown", task_name="Unknown task")
        
        success = await self.job_manager._execute_task(job, task, 0)
        
        assert success is False
    
    @pytest.mark.asyncio
    async def test_execute_task_exception_handling(self):
        """Test _execute_task handles exceptions"""
        job = BorgJob(id="test", status="running", started_at=datetime.now(UTC))
        task = BorgJobTask(task_type="backup", task_name="Backup")
        
        with patch.object(self.job_manager, '_execute_backup_task', side_effect=Exception("Backup failed")):
            success = await self.job_manager._execute_task(job, task, 0)
            
            assert success is False
            assert task.error == "Backup failed"