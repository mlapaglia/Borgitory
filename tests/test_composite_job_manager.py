"""
Tests for CompositeJobManager class - multi-task job orchestration and execution
"""
import pytest
import asyncio
import uuid
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from datetime import datetime
from typing import Dict, Any, List
from contextlib import asynccontextmanager

from app.services.composite_job_manager import (
    CompositeJobManager, 
    CompositeJobInfo, 
    CompositeJobTaskInfo
)
from app.models.database import Repository, Job, JobTask, Schedule, NotificationConfig
from app.models.enums import JobType


class TestCompositeJobManager:
    """Test CompositeJobManager functionality."""
    
    def setup_method(self):
        """Set up test fixtures."""
        # Mock dependencies
        self.mock_db_session_factory = Mock()
        self.mock_db_session = Mock()
        self.mock_db_session_factory.return_value.__enter__ = Mock(return_value=self.mock_db_session)
        self.mock_db_session_factory.return_value.__exit__ = Mock(return_value=None)
        
        self.mock_rclone_service = Mock()
        self.mock_subprocess_executor = AsyncMock()
        self.mock_http_client_factory = Mock()
        
        # Create manager with mocked dependencies
        self.manager = CompositeJobManager(
            db_session_factory=self.mock_db_session_factory,
            rclone_service=self.mock_rclone_service,
            subprocess_executor=self.mock_subprocess_executor,
            http_client_factory=self.mock_http_client_factory
        )
        
        # Create mock repository
        self.mock_repository = Mock(spec=Repository)
        self.mock_repository.id = 1
        self.mock_repository.name = "test-repo"
        self.mock_repository.path = "/path/to/repo"
        self.mock_repository.get_passphrase.return_value = "test_passphrase"
        
        # Mock schedule
        self.mock_schedule = Mock(spec=Schedule)
        self.mock_schedule.cloud_sync_config_id = None

    def test_init(self):
        """Test CompositeJobManager initialization."""
        manager = CompositeJobManager()
        assert manager.jobs == {}
        assert manager._event_queues == []
        assert hasattr(manager, '_db_session_factory')
        assert hasattr(manager, '_rclone_service')
        assert hasattr(manager, '_subprocess_executor')
        assert hasattr(manager, '_http_client_factory')

    def test_get_repository_data_success(self):
        """Test successful repository data retrieval."""
        # Setup mock repository query
        mock_repo = Mock()
        mock_repo.id = 1
        mock_repo.name = "test-repo"
        mock_repo.path = "/test/path"
        mock_repo.get_passphrase.return_value = "test_pass"
        
        self.mock_db_session.query.return_value.filter.return_value.first.return_value = mock_repo
        
        result = self.manager._get_repository_data(1)
        
        assert result is not None
        assert result["id"] == 1
        assert result["name"] == "test-repo"
        assert result["path"] == "/test/path"
        assert result["passphrase"] == "test_pass"

    def test_get_repository_data_not_found(self):
        """Test repository data retrieval when repository not found."""
        self.mock_db_session.query.return_value.filter.return_value.first.return_value = None
        
        result = self.manager._get_repository_data(999)
        
        assert result is None

    @pytest.mark.asyncio
    async def test_create_composite_job_success(self):
        """Test successful composite job creation."""
        # Setup database mocks
        mock_db_job = Mock()
        mock_db_job.id = 123
        self.mock_db_session.add = Mock()
        self.mock_db_session.commit = Mock()
        self.mock_db_session.refresh = Mock()
        
        # Mock the Job constructor to return our mock
        with patch('app.services.composite_job_manager.Job', return_value=mock_db_job):
            task_definitions = [
                {"type": "backup", "name": "Backup Task", "source_path": "/data"},
                {"type": "cloud_sync", "name": "Cloud Sync Task"}
            ]
            
            job_id = await self.manager.create_composite_job(
                JobType.SCHEDULED_BACKUP,
                task_definitions,
                self.mock_repository,
                self.mock_schedule
            )
            
            # Verify job was created
            assert job_id in self.manager.jobs
            job = self.manager.jobs[job_id]
            assert job.job_type == str(JobType.SCHEDULED_BACKUP)
            assert job.repository_id == 1
            assert len(job.tasks) == 2
            assert job.tasks[0].task_type == "backup"
            assert job.tasks[1].task_type == "cloud_sync"

    @pytest.mark.asyncio
    async def test_execute_backup_task_success(self):
        """Test successful backup task execution."""
        # Create job and task
        job = CompositeJobInfo(
            id="test-job",
            db_job_id=123,
            job_type="scheduled_backup",
            repository_id=1
        )
        
        task = CompositeJobTaskInfo(
            task_type="backup",
            task_name="Test Backup",
            source_path="/data",
            compression="zstd"
        )
        
        # Setup repository data mock
        repo_data = {
            "id": 1,
            "name": "test-repo", 
            "path": "/repo/path",
            "passphrase": "test_pass"
        }
        
        with patch.object(self.manager, '_get_repository_data', return_value=repo_data), \
             patch('app.utils.security.build_secure_borg_command') as mock_build_cmd, \
             patch('app.utils.security.validate_compression') as mock_validate_comp, \
             patch('app.utils.security.validate_archive_name') as mock_validate_arch:
            
            # Setup command building
            mock_build_cmd.return_value = (["borg", "create"], {"BORG_PASSPHRASE": "test"})
            
            # Setup subprocess mock
            mock_process = AsyncMock()
            mock_process.returncode = 0
            mock_process.wait = AsyncMock(return_value=None)
            
            # Mock async iterator for stdout
            async def mock_stdout_lines():
                yield b"backup output line\n"
                yield b"backup completed\n"
            
            mock_process.stdout = mock_stdout_lines()
            self.mock_subprocess_executor.return_value = mock_process
            
            result = await self.manager._execute_backup_task(job, task, 0)
            
            assert result is True
            mock_validate_comp.assert_called_once()
            mock_validate_arch.assert_called_once()
            mock_build_cmd.assert_called_once()
            self.mock_subprocess_executor.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_backup_task_failure(self):
        """Test backup task execution failure."""
        job = CompositeJobInfo(
            id="test-job",
            db_job_id=123,
            job_type="scheduled_backup",
            repository_id=1
        )
        
        task = CompositeJobTaskInfo(
            task_type="backup",
            task_name="Test Backup"
        )
        
        repo_data = {
            "id": 1,
            "name": "test-repo",
            "path": "/repo/path", 
            "passphrase": "test_pass"
        }
        
        with patch.object(self.manager, '_get_repository_data', return_value=repo_data), \
             patch('app.utils.security.build_secure_borg_command') as mock_build_cmd, \
             patch('app.utils.security.validate_compression'), \
             patch('app.utils.security.validate_archive_name'):
            
            mock_build_cmd.return_value = (["borg", "create"], {"BORG_PASSPHRASE": "test"})
            
            # Setup failed subprocess
            mock_process = AsyncMock()
            mock_process.returncode = 1
            mock_process.wait = AsyncMock(return_value=None)
            
            # Mock async iterator for stdout
            async def mock_stdout_lines():
                yield b"error output\n"
                yield b"backup failed\n"
            
            mock_process.stdout = mock_stdout_lines()
            self.mock_subprocess_executor.return_value = mock_process
            
            result = await self.manager._execute_backup_task(job, task, 0)
            
            assert result is False
            assert task.error == "Backup failed with return code 1"

    @pytest.mark.asyncio
    async def test_execute_prune_task_success(self):
        """Test successful prune task execution."""
        job = CompositeJobInfo(
            id="test-job",
            db_job_id=123,
            job_type="scheduled_backup",
            repository_id=1
        )
        
        task = CompositeJobTaskInfo(
            task_type="prune",
            task_name="Test Prune",
            keep_daily=7,
            keep_weekly=4,
            show_stats=True
        )
        
        repo_data = {
            "id": 1,
            "name": "test-repo",
            "path": "/repo/path",
            "passphrase": "test_pass"
        }
        
        with patch.object(self.manager, '_get_repository_data', return_value=repo_data), \
             patch('app.utils.security.build_secure_borg_command') as mock_build_cmd:
            
            mock_build_cmd.return_value = (["borg", "prune"], {"BORG_PASSPHRASE": "test"})
            
            # Setup successful subprocess
            mock_process = AsyncMock()
            mock_process.returncode = 0
            mock_process.wait = AsyncMock(return_value=None)
            
            # Mock async iterator for stdout
            async def mock_stdout_lines():
                yield b"prune output\n"
                yield b"prune completed\n"
            
            mock_process.stdout = mock_stdout_lines()
            self.mock_subprocess_executor.return_value = mock_process
            
            result = await self.manager._execute_prune_task(job, task, 0)
            
            assert result is True
            mock_build_cmd.assert_called_once()
            # Verify that retention policy arguments were included
            call_args = mock_build_cmd.call_args[1]['additional_args']
            assert '--keep-daily' in call_args
            assert '7' in call_args
            assert '--keep-weekly' in call_args
            assert '4' in call_args
            assert '--stats' in call_args

    @pytest.mark.asyncio
    async def test_execute_check_task_success(self):
        """Test successful check task execution."""
        job = CompositeJobInfo(
            id="test-job",
            db_job_id=123,
            job_type="scheduled_backup",
            repository_id=1
        )
        
        task = CompositeJobTaskInfo(
            task_type="check",
            task_name="Test Check",
            check_type="full",
            verify_data=True
        )
        
        repo_data = {
            "id": 1,
            "name": "test-repo",
            "path": "/repo/path",
            "passphrase": "test_pass"
        }
        
        with patch.object(self.manager, '_get_repository_data', return_value=repo_data), \
             patch('app.utils.security.build_secure_borg_command') as mock_build_cmd:
            
            mock_build_cmd.return_value = (["borg", "check"], {"BORG_PASSPHRASE": "test"})
            
            # Setup successful subprocess
            mock_process = AsyncMock()
            mock_process.returncode = 0
            mock_process.wait = AsyncMock(return_value=None)
            
            # Mock async iterator for stdout
            async def mock_stdout_lines():
                yield b"check output\n"
                yield b"check completed\n"
            
            mock_process.stdout = mock_stdout_lines()
            self.mock_subprocess_executor.return_value = mock_process
            
            result = await self.manager._execute_check_task(job, task, 0)
            
            assert result is True
            mock_build_cmd.assert_called_once()
            call_args = mock_build_cmd.call_args[1]['additional_args']
            assert '--verify-data' in call_args

    @pytest.mark.asyncio
    async def test_execute_cloud_sync_task_s3_success(self):
        """Test successful S3 cloud sync task execution."""
        job = CompositeJobInfo(
            id="test-job",
            db_job_id=123,
            job_type="scheduled_backup",
            repository_id=1
        )
        job.schedule = Mock()
        job.schedule.cloud_sync_config_id = 456
        
        task = CompositeJobTaskInfo(
            task_type="cloud_sync",
            task_name="Test Cloud Sync"
        )
        
        repo_data = {
            "id": 1,
            "name": "test-repo",
            "path": "/repo/path",
            "passphrase": "test_pass"
        }
        
        # Mock cloud sync config
        mock_config = Mock()
        mock_config.enabled = True
        mock_config.provider = "s3"
        mock_config.name = "test-s3"
        mock_config.bucket_name = "test-bucket"
        mock_config.path_prefix = "backups/"
        mock_config.get_credentials.return_value = ("access_key", "secret_key")
        
        self.mock_db_session.query.return_value.filter.return_value.first.return_value = mock_config
        
        # Mock progress generator
        async def mock_progress_generator():
            yield {"type": "log", "stream": "stdout", "message": "Starting sync"}
            yield {"type": "completed", "status": "success", "message": "Sync completed"}
        
        self.mock_rclone_service.sync_repository_to_s3.return_value = mock_progress_generator()
        
        with patch.object(self.manager, '_get_repository_data', return_value=repo_data):
            result = await self.manager._execute_cloud_sync_task(job, task, 0)
            
            assert result is True
            self.mock_rclone_service.sync_repository_to_s3.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_cloud_sync_task_no_config(self):
        """Test cloud sync task with no configuration."""
        job = CompositeJobInfo(
            id="test-job",
            db_job_id=123,
            job_type="scheduled_backup",
            repository_id=1
        )
        job.schedule = None  # No schedule
        
        task = CompositeJobTaskInfo(
            task_type="cloud_sync",
            task_name="Test Cloud Sync"
        )
        
        repo_data = {
            "id": 1,
            "name": "test-repo",
            "path": "/repo/path",
            "passphrase": "test_pass"
        }
        
        with patch.object(self.manager, '_get_repository_data', return_value=repo_data):
            result = await self.manager._execute_cloud_sync_task(job, task, 0)
            
            assert result is True  # Should succeed but be skipped
            assert task.status == "skipped"

    @pytest.mark.asyncio
    async def test_execute_notification_task_pushover_success(self):
        """Test successful Pushover notification task."""
        job = CompositeJobInfo(
            id="test-job",
            db_job_id=123,
            job_type="scheduled_backup",
            repository_id=1
        )
        
        task = CompositeJobTaskInfo(
            task_type="notification",
            task_name="Test Notification",
            config_id=789
        )
        
        # Add a completed task to simulate successful job
        completed_task = CompositeJobTaskInfo(
            task_type="backup",
            task_name="Backup",
            status="completed"
        )
        job.tasks = [completed_task, task]
        
        repo_data = {
            "id": 1,
            "name": "test-repo",
            "path": "/repo/path",
            "passphrase": "test_pass"
        }
        
        # Mock notification config
        mock_config = Mock()
        mock_config.enabled = True
        mock_config.provider = "pushover"
        mock_config.notify_on_success = True
        mock_config.notify_on_failure = False
        mock_config.encrypted_user_key = b"encrypted_user"
        mock_config.encrypted_app_token = b"encrypted_token"
        
        self.mock_db_session.query.return_value.filter.return_value.first.return_value = mock_config
        
        # Mock the _send_pushover_notification method directly
        with patch.object(self.manager, '_get_repository_data', return_value=repo_data), \
             patch.object(self.manager, '_send_pushover_notification', new_callable=AsyncMock) as mock_send:
            
            mock_send.return_value = True
            
            result = await self.manager._execute_notification_task(job, task, 1)
            
            assert result is True
            mock_send.assert_called_once()

    @pytest.mark.asyncio 
    async def test_execute_task_unknown_type(self):
        """Test execution of unknown task type."""
        job = CompositeJobInfo(
            id="test-job",
            db_job_id=123,
            job_type="scheduled_backup",
            repository_id=1
        )
        
        task = CompositeJobTaskInfo(
            task_type="unknown_task",
            task_name="Unknown Task"
        )
        
        result = await self.manager._execute_task(job, task, 0)
        
        assert result is False

    @pytest.mark.asyncio
    async def test_execute_composite_job_success(self):
        """Test successful composite job execution."""
        # Create a job with tasks
        task_definitions = [
            {"type": "backup", "name": "Backup Task"},
            {"type": "prune", "name": "Prune Task"}
        ]
        
        # Setup database mocks for job creation
        mock_db_job = Mock()
        mock_db_job.id = 123
        self.mock_db_session.add = Mock()
        self.mock_db_session.commit = Mock()
        self.mock_db_session.refresh = Mock()
        
        with patch('app.services.composite_job_manager.Job', return_value=mock_db_job), \
             patch('app.services.composite_job_manager.JobTask'), \
             patch.object(self.manager, '_execute_task', new_callable=AsyncMock) as mock_execute:
            
            # Mock successful task execution
            mock_execute.return_value = True
            
            job_id = await self.manager.create_composite_job(
                JobType.SCHEDULED_BACKUP,
                task_definitions,
                self.mock_repository
            )
            
            # Wait a bit for the async execution to start
            await asyncio.sleep(0.1)
            
            # Verify the job was created and is running
            assert job_id in self.manager.jobs
            job = self.manager.jobs[job_id]
            assert len(job.tasks) == 2

    def test_subscribe_unsubscribe_events(self):
        """Test event subscription and unsubscription."""
        # Subscribe to events
        queue = self.manager.subscribe_to_events()
        
        assert queue in self.manager._event_queues
        assert len(self.manager._event_queues) == 1
        
        # Unsubscribe
        self.manager.unsubscribe_from_events(queue)
        
        assert queue not in self.manager._event_queues
        assert len(self.manager._event_queues) == 0

    def test_broadcast_task_output(self):
        """Test task output broadcasting."""
        # Subscribe to events
        queue = self.manager.subscribe_to_events()
        
        # Broadcast output
        self.manager._broadcast_task_output("test-job", 0, "test output")
        
        # Check that event was queued
        assert not queue.empty()
        event = queue.get_nowait()
        
        assert event["type"] == "task_output"
        assert event["job_id"] == "test-job"
        assert event["task_index"] == 0
        assert event["line"] == "test output"

    def test_mark_remaining_tasks_as_skipped(self):
        """Test marking remaining tasks as skipped."""
        job = CompositeJobInfo(
            id="test-job",
            db_job_id=123,
            job_type="scheduled_backup",
            repository_id=1
        )
        
        # Add tasks
        for i in range(3):
            task = CompositeJobTaskInfo(
                task_type="backup",
                task_name=f"Task {i}",
                status="pending"
            )
            job.tasks.append(task)
        
        # Mock the database update
        with patch.object(self.manager, '_update_task_status'):
            self.manager._mark_remaining_tasks_as_skipped(job, 1)
            
            # First task should remain pending, others should be skipped
            assert job.tasks[0].status == "pending"
            assert job.tasks[1].status == "skipped"
            assert job.tasks[2].status == "skipped"

    @pytest.mark.asyncio
    async def test_repo_placeholder_tasks(self):
        """Test placeholder repository task implementations."""
        job = CompositeJobInfo(
            id="test-job",
            db_job_id=123,
            job_type="scheduled_backup",
            repository_id=1
        )
        
        task = CompositeJobTaskInfo(
            task_type="repo_scan",
            task_name="Repository Scan"
        )
        
        # Test all placeholder tasks
        assert await self.manager._execute_repo_scan_task(job, task, 0) is True
        assert await self.manager._execute_repo_init_task(job, task, 0) is True
        assert await self.manager._execute_repo_list_task(job, task, 0) is True
        assert await self.manager._execute_repo_info_task(job, task, 0) is True


class TestCompositeJobInfo:
    """Test CompositeJobInfo data class."""
    
    def test_is_composite(self):
        """Test is_composite method."""
        job = CompositeJobInfo(
            id="test-job",
            db_job_id=123,
            job_type="scheduled_backup"
        )
        
        assert job.is_composite() is True

    def test_get_current_task_valid_index(self):
        """Test getting current task with valid index."""
        job = CompositeJobInfo(
            id="test-job",
            db_job_id=123,
            job_type="scheduled_backup"
        )
        
        task1 = CompositeJobTaskInfo(task_type="backup", task_name="Task 1")
        task2 = CompositeJobTaskInfo(task_type="prune", task_name="Task 2")
        job.tasks = [task1, task2]
        job.current_task_index = 1
        
        current = job.get_current_task()
        assert current is task2

    def test_get_current_task_invalid_index(self):
        """Test getting current task with invalid index."""
        job = CompositeJobInfo(
            id="test-job",
            db_job_id=123,
            job_type="scheduled_backup"
        )
        
        job.tasks = []
        job.current_task_index = 0
        
        current = job.get_current_task()
        assert current is None


class TestCompositeJobTaskInfo:
    """Test CompositeJobTaskInfo data class."""
    
    def test_initialization(self):
        """Test task info initialization."""
        task = CompositeJobTaskInfo(
            task_type="backup",
            task_name="Test Backup",
            source_path="/data",
            compression="zstd"
        )
        
        assert task.task_type == "backup"
        assert task.task_name == "Test Backup"
        assert task.status == "pending"
        assert task.source_path == "/data"
        assert task.compression == "zstd"
        assert task.started_at is None
        assert task.completed_at is None
        assert len(task.output_lines) == 0


def test_get_composite_job_manager():
    """Test global composite job manager getter."""
    from app.services.composite_job_manager import get_composite_job_manager
    
    # Should return a CompositeJobManager instance
    manager = get_composite_job_manager()
    assert isinstance(manager, CompositeJobManager)
    
    # Should return the same instance on subsequent calls
    manager2 = get_composite_job_manager()
    assert manager is manager2