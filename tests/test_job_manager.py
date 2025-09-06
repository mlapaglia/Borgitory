import asyncio
import pytest
import uuid
from datetime import datetime
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from collections import deque

from app.services.job_manager import (
    BorgJobManager,
    BorgJobManagerConfig,
    BorgJob,
    BorgJobTask,
    get_job_manager,
    reset_job_manager,
)


class TestBorgJobManagerConfig:
    """Test BorgJobManagerConfig dataclass"""

    def test_default_config(self):
        """Test default configuration values"""
        config = BorgJobManagerConfig()
        
        assert config.max_concurrent_backups == 5
        assert config.auto_cleanup_delay == 30
        assert config.max_output_lines == 1000
        assert config.queue_poll_interval == 0.1
        assert config.sse_keepalive_timeout == 30.0

    def test_custom_config(self):
        """Test custom configuration values"""
        config = BorgJobManagerConfig(
            max_concurrent_backups=10,
            auto_cleanup_delay=60,
            max_output_lines=2000,
            queue_poll_interval=0.5,
            sse_keepalive_timeout=45.0,
        )
        
        assert config.max_concurrent_backups == 10
        assert config.auto_cleanup_delay == 60
        assert config.max_output_lines == 2000
        assert config.queue_poll_interval == 0.5
        assert config.sse_keepalive_timeout == 45.0


class TestBorgJobTask:
    """Test BorgJobTask dataclass"""

    def test_default_task(self):
        """Test default task creation"""
        task = BorgJobTask(task_type="backup", task_name="Test Backup")
        
        assert task.task_type == "backup"
        assert task.task_name == "Test Backup"
        assert task.status == "pending"
        assert task.started_at is None
        assert task.completed_at is None
        assert task.return_code is None
        assert task.error is None
        assert isinstance(task.output_lines, deque)
        assert isinstance(task.parameters, dict)

    def test_custom_task(self):
        """Test custom task creation with parameters"""
        task = BorgJobTask(
            task_type="prune",
            task_name="Test Prune",
            status="running",
            parameters={"keep_daily": 7, "keep_weekly": 4},
        )
        
        assert task.task_type == "prune"
        assert task.task_name == "Test Prune"
        assert task.status == "running"
        assert task.parameters["keep_daily"] == 7
        assert task.parameters["keep_weekly"] == 4


class TestBorgJob:
    """Test BorgJob dataclass"""

    def test_simple_job(self):
        """Test simple job creation"""
        job_id = str(uuid.uuid4())
        started_at = datetime.now()
        
        job = BorgJob(
            id=job_id,
            status="running",
            started_at=started_at,
            command=["borg", "create", "repo::archive", "/data"],
        )
        
        assert job.id == job_id
        assert job.status == "running"
        assert job.started_at == started_at
        assert job.command == ["borg", "create", "repo::archive", "/data"]
        assert job.job_type == "simple"
        assert job.current_task_index == 0
        assert len(job.tasks) == 0
        assert isinstance(job.output_lines, deque)

    def test_composite_job(self):
        """Test composite job creation"""
        job_id = str(uuid.uuid4())
        started_at = datetime.now()
        task1 = BorgJobTask(task_type="backup", task_name="Backup")
        task2 = BorgJobTask(task_type="prune", task_name="Prune")
        
        job = BorgJob(
            id=job_id,
            status="pending",
            started_at=started_at,
            job_type="composite",
            tasks=[task1, task2],
            repository_id=1,
        )
        
        assert job.id == job_id
        assert job.status == "pending"
        assert job.job_type == "composite"
        assert len(job.tasks) == 2
        assert job.repository_id == 1

    def test_get_current_task(self):
        """Test getting current task from composite job"""
        task1 = BorgJobTask(task_type="backup", task_name="Backup")
        task2 = BorgJobTask(task_type="prune", task_name="Prune")
        
        job = BorgJob(
            id="test",
            status="running",
            started_at=datetime.now(),
            job_type="composite",
            tasks=[task1, task2],
            current_task_index=0,
        )
        
        # Test first task
        current_task = job.get_current_task()
        assert current_task == task1
        
        # Test second task
        job.current_task_index = 1
        current_task = job.get_current_task()
        assert current_task == task2
        
        # Test out of bounds
        job.current_task_index = 2
        current_task = job.get_current_task()
        assert current_task is None
        
        # Test simple job
        simple_job = BorgJob(id="simple", status="running", started_at=datetime.now())
        assert simple_job.get_current_task() is None

    def test_is_composite(self):
        """Test is_composite method"""
        # Simple job
        simple_job = BorgJob(id="simple", status="running", started_at=datetime.now())
        assert not simple_job.is_composite()
        
        # Composite job with tasks
        task = BorgJobTask(task_type="backup", task_name="Backup")
        composite_job = BorgJob(
            id="composite",
            status="running",
            started_at=datetime.now(),
            job_type="composite",
            tasks=[task],
        )
        assert composite_job.is_composite()
        
        # Composite job type but no tasks
        empty_composite = BorgJob(
            id="empty",
            status="running",
            started_at=datetime.now(),
            job_type="composite",
        )
        assert not empty_composite.is_composite()


class TestBorgJobManager:
    """Test BorgJobManager class"""

    @pytest.fixture
    def config(self):
        """Test configuration"""
        return BorgJobManagerConfig(max_concurrent_backups=2, max_output_lines=100)

    @pytest.fixture
    def job_manager(self, config):
        """Create job manager for testing"""
        return BorgJobManager(config)

    def test_initialization(self, job_manager):
        """Test job manager initialization"""
        assert isinstance(job_manager.config, BorgJobManagerConfig)
        assert job_manager.config.max_concurrent_backups == 2
        assert job_manager.jobs == {}
        assert job_manager._processes == {}
        assert job_manager._event_queues == []
        assert job_manager.MAX_CONCURRENT_BACKUPS == 2
        assert job_manager._backup_queue is None
        assert job_manager._backup_semaphore is None
        assert not job_manager._queue_processor_started
        assert not job_manager._shutdown_requested

    def test_initialization_with_default_config(self):
        """Test job manager with default config"""
        manager = BorgJobManager()
        assert isinstance(manager.config, BorgJobManagerConfig)
        assert manager.config.max_concurrent_backups == 5

    @pytest.mark.asyncio
    async def test_initialize(self, job_manager):
        """Test async initialization"""
        await job_manager.initialize()
        
        assert job_manager._backup_queue is not None
        assert job_manager._backup_semaphore is not None
        assert job_manager._backup_semaphore._value == 2  # max_concurrent_backups

    @pytest.mark.asyncio
    async def test_shutdown(self, job_manager):
        """Test graceful shutdown"""
        # Initialize first
        await job_manager.initialize()
        
        # Add some mock data
        job_manager.jobs["test"] = Mock()
        process_mock = Mock()
        process_mock.returncode = None
        process_mock.terminate = Mock()
        process_mock.kill = Mock()
        job_manager._processes["test"] = process_mock
        job_manager._event_queues.append(asyncio.Queue())
        
        await job_manager.shutdown()
        
        assert job_manager._shutdown_requested
        assert job_manager.jobs == {}
        assert job_manager._processes == {}
        assert job_manager._event_queues == []
        assert not job_manager._queue_processor_started

    def test_create_job_task(self, job_manager):
        """Test task creation"""
        task = job_manager._create_job_task(
            task_type="backup",
            task_name="Test Backup",
            parameters={"source_path": "/data"},
        )
        
        assert task.task_type == "backup"
        assert task.task_name == "Test Backup"
        assert task.parameters["source_path"] == "/data"
        assert task.output_lines.maxlen == 100  # config.max_output_lines

    def test_create_job(self, job_manager):
        """Test job creation"""
        job_id = str(uuid.uuid4())
        job = job_manager._create_job(
            job_id=job_id,
            status="running",
            started_at=datetime.now(),
        )
        
        assert job.id == job_id
        assert job.status == "running"
        assert job.output_lines.maxlen == 100  # config.max_output_lines

    @patch("app.utils.db_session.get_db_session")
    def test_get_repository_data(self, mock_get_db_session, job_manager):
        """Test getting repository data"""
        # Mock the context manager properly using MagicMock
        mock_session = Mock()
        mock_context = MagicMock()
        mock_context.__enter__.return_value = mock_session
        mock_context.__exit__.return_value = None
        mock_get_db_session.return_value = mock_context
        
        mock_repo = Mock()
        mock_repo.id = 1
        mock_repo.name = "Test Repo"
        mock_repo.path = "/tmp/repo"
        mock_repo.get_passphrase.return_value = "test_passphrase"
        
        mock_session.query.return_value.filter.return_value.first.return_value = mock_repo
        
        result = job_manager._get_repository_data(1)
        
        assert result["id"] == 1
        assert result["name"] == "Test Repo"
        assert result["path"] == "/tmp/repo"
        assert result["passphrase"] == "test_passphrase"

    @patch("app.utils.db_session.get_db_session")
    def test_get_repository_data_not_found(self, mock_get_db_session, job_manager):
        """Test getting repository data when not found"""
        mock_session = Mock()
        mock_context = MagicMock()
        mock_context.__enter__.return_value = mock_session
        mock_context.__exit__.return_value = None
        mock_get_db_session.return_value = mock_context
        mock_session.query.return_value.filter.return_value.first.return_value = None
        
        result = job_manager._get_repository_data(999)
        assert result is None

    @pytest.mark.asyncio
    @patch("uuid.uuid4")
    async def test_start_borg_command_non_backup(self, mock_uuid, job_manager):
        """Test starting non-backup borg command"""
        mock_uuid.return_value = "test-job-id"
        
        with patch.object(job_manager, "_run_borg_job", new=AsyncMock()) as mock_run:
            job_id = await job_manager.start_borg_command(
                command=["borg", "list", "repo"],
                env={"TEST": "value"},
                is_backup=False,
            )
        
        assert job_id == "test-job-id"
        assert "test-job-id" in job_manager.jobs
        job = job_manager.jobs["test-job-id"]
        assert job.status == "running"
        assert job.command == ["borg", "list", "repo"]
        mock_run.assert_called_once()

    @pytest.mark.asyncio
    @patch("uuid.uuid4")
    async def test_start_borg_command_backup(self, mock_uuid, job_manager):
        """Test starting backup borg command"""
        mock_uuid.return_value = "backup-job-id"
        await job_manager.initialize()
        
        job_id = await job_manager.start_borg_command(
            command=["borg", "create", "repo::archive", "/data"],
            env={"TEST": "value"},
            is_backup=True,
        )
        
        assert job_id == "backup-job-id"
        assert "backup-job-id" in job_manager.jobs
        job = job_manager.jobs["backup-job-id"]
        assert job.status == "queued"
        assert job_manager._queue_processor_started

    def test_broadcast_job_event(self, job_manager):
        """Test broadcasting job events"""
        # Add some queues
        queue1 = Mock()
        queue1.full.return_value = False
        queue2 = Mock()
        queue2.full.return_value = True  # Full queue
        queue3 = Mock()
        queue3.full.return_value = False
        queue3.put_nowait.side_effect = Exception("Queue error")  # Failed queue
        
        job_manager._event_queues = [queue1, queue2, queue3]
        
        event = {"type": "test", "data": "value"}
        job_manager._broadcast_job_event(event)
        
        # Only queue1 should receive the event
        queue1.put_nowait.assert_called_once_with(event)
        queue2.put_nowait.assert_not_called()  # Was full
        
        # queue3 should be removed due to error
        assert queue3 not in job_manager._event_queues
        assert len(job_manager._event_queues) == 2  # queue1 and queue2 remain

    @pytest.mark.asyncio
    async def test_get_queue_stats(self, job_manager):
        """Test getting queue statistics"""
        # Initialize the job manager to create the queue
        await job_manager.initialize()
        
        # Add some mock jobs
        running_backup = Mock()
        running_backup.status = "running"
        running_backup.command = ["borg", "create", "repo::archive", "/data"]
        
        running_other = Mock()
        running_other.status = "running"
        running_other.command = ["borg", "list", "repo"]
        
        queued_backup = Mock()
        queued_backup.status = "queued"
        
        job_manager.jobs = {
            "running_backup": running_backup,
            "running_other": running_other,
            "queued_backup": queued_backup,
        }
        
        stats = job_manager.get_queue_stats()
        
        assert stats["max_concurrent_backups"] == 2
        assert stats["running_backups"] == 1  # Only running_backup has "create" in command
        assert stats["queued_backups"] == 1
        assert stats["available_slots"] == 1
        assert stats["queue_size"] == 0  # Queue is empty

    def test_get_job_status(self, job_manager):
        """Test getting job status"""
        job = Mock()
        job.status = "completed"
        job.started_at = datetime(2023, 1, 1, 12, 0, 0)
        job.completed_at = datetime(2023, 1, 1, 12, 5, 0)
        job.return_code = 0
        job.error = None
        
        job_manager.jobs["test"] = job
        
        status = job_manager.get_job_status("test")
        
        assert status["running"] is False
        assert status["completed"] is True
        assert status["status"] == "completed"
        assert status["return_code"] == 0
        assert status["error"] is None

    def test_get_job_status_not_found(self, job_manager):
        """Test getting status for non-existent job"""
        status = job_manager.get_job_status("nonexistent")
        assert status is None

    def test_cleanup_job(self, job_manager):
        """Test cleaning up job"""
        job_manager.jobs["test"] = Mock()
        
        result = job_manager.cleanup_job("test")
        assert result is True
        assert "test" not in job_manager.jobs
        
        # Test cleanup of non-existent job
        result = job_manager.cleanup_job("nonexistent")
        assert result is False

    def test_subscribe_unsubscribe_events(self, job_manager):
        """Test event subscription/unsubscription"""
        queue = job_manager.subscribe_to_events()
        
        assert isinstance(queue, asyncio.Queue)
        assert queue in job_manager._event_queues
        
        job_manager.unsubscribe_from_events(queue)
        assert queue not in job_manager._event_queues

    @pytest.mark.asyncio
    async def test_stream_all_job_updates(self, job_manager):
        """Test streaming all job updates"""
        # This is a complex generator test
        async def test_stream():
            stream_gen = job_manager.stream_all_job_updates()
            
            # Start the generator
            stream_task = asyncio.create_task(stream_gen.__anext__())
            
            # Give it a moment to set up
            await asyncio.sleep(0.01)
            
            # Send an event
            job_manager._broadcast_job_event({"type": "test", "data": "value"})
            
            # Get the event
            try:
                event = await asyncio.wait_for(stream_task, timeout=0.1)
                assert event["type"] == "test"
                assert event["data"] == "value"
            except asyncio.TimeoutError:
                # Event should arrive quickly
                assert False, "Event not received in time"
            
            # Clean up
            await stream_gen.aclose()
        
        await test_stream()

    @pytest.mark.asyncio
    async def test_cancel_job(self, job_manager):
        """Test cancelling a running job"""
        # Test successful cancellation
        process_mock = Mock()
        process_mock.returncode = None
        process_mock.terminate = Mock()
        job_manager._processes["test"] = process_mock
        
        result = await job_manager.cancel_job("test")
        assert result is True
        process_mock.terminate.assert_called_once()

    @pytest.mark.asyncio
    async def test_cancel_job_not_found(self, job_manager):
        """Test cancelling non-existent job"""
        result = await job_manager.cancel_job("nonexistent")
        assert result is False


class TestJobManagerFactory:
    """Test job manager factory functions"""

    def teardown_method(self):
        """Reset job manager after each test"""
        reset_job_manager()

    def test_get_job_manager_singleton(self):
        """Test that get_job_manager returns same instance"""
        manager1 = get_job_manager()
        manager2 = get_job_manager()
        
        assert manager1 is manager2

    def test_get_job_manager_with_config(self):
        """Test get_job_manager with custom config"""
        config = BorgJobManagerConfig(max_concurrent_backups=10)
        manager = get_job_manager(config)
        
        assert manager.config.max_concurrent_backups == 10

    @patch.dict("os.environ", {"BORG_MAX_CONCURRENT_BACKUPS": "8", "BORG_AUTO_CLEANUP_DELAY": "45"})
    def test_get_job_manager_with_env_vars(self):
        """Test get_job_manager with environment variables"""
        manager = get_job_manager()
        
        assert manager.config.max_concurrent_backups == 8
        assert manager.config.auto_cleanup_delay == 45

    def test_reset_job_manager(self):
        """Test resetting job manager"""
        manager1 = get_job_manager()
        reset_job_manager()
        manager2 = get_job_manager()
        
        assert manager1 is not manager2