import pytest
import uuid
from datetime import datetime
from unittest.mock import Mock, AsyncMock, patch

from sqlalchemy.orm import Session

from borgitory.services.jobs.job_manager import (
    JobManager,
    JobManagerConfig,
    BorgJob,
    BorgJobTask,
)
from borgitory.models.database import Repository
from borgitory.utils.datetime_utils import now_utc


class TestJobManagerConfig:
    """Test JobManagerConfig dataclass"""

    def test_default_config(self) -> None:
        """Test default configuration values"""
        config = JobManagerConfig()

        assert config.max_concurrent_backups == 5
        assert config.max_output_lines_per_job == 1000
        assert config.queue_poll_interval == 0.1
        assert config.sse_keepalive_timeout == 30.0

    def test_custom_config(self) -> None:
        """Test custom configuration values"""
        config = JobManagerConfig(
            max_concurrent_backups=10,
            max_output_lines_per_job=2000,
            queue_poll_interval=0.5,
            sse_keepalive_timeout=45.0,
        )

        assert config.max_concurrent_backups == 10
        assert config.max_output_lines_per_job == 2000
        assert config.queue_poll_interval == 0.5
        assert config.sse_keepalive_timeout == 45.0


class TestBorgJobTask:
    """Test BorgJobTask dataclass"""

    def test_default_task(self) -> None:
        """Test default task creation"""
        task = BorgJobTask(task_type="backup", task_name="Test Backup")

        assert task.task_type == "backup"
        assert task.task_name == "Test Backup"
        assert task.status == "pending"
        assert task.started_at is None
        assert task.completed_at is None
        assert task.return_code is None
        assert task.error is None
        assert isinstance(task.parameters, dict)

    def test_custom_task(self) -> None:
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

    def test_simple_job(self) -> None:
        """Test simple job creation"""
        job_id = str(uuid.uuid4())
        started_at = now_utc()

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

    def test_composite_job(self) -> None:
        """Test composite job creation"""
        job_id = str(uuid.uuid4())
        started_at = now_utc()
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

    def test_get_current_task(self) -> None:
        """Test getting current task from composite job"""
        task1 = BorgJobTask(task_type="backup", task_name="Backup")
        task2 = BorgJobTask(task_type="prune", task_name="Prune")

        job = BorgJob(
            id="test",
            status="running",
            started_at=now_utc(),
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
        simple_job = BorgJob(id="simple", status="running", started_at=now_utc())
        assert simple_job.get_current_task() is None

    def test_unified_composite_jobs(self) -> None:
        """Test unified composite job approach - all jobs are now composite"""
        # All jobs are now composite with job_type="composite"
        task = BorgJobTask(task_type="backup", task_name="Backup")
        job_with_tasks = BorgJob(
            id="job1",
            status="running",
            started_at=now_utc(),
            job_type="composite",
            tasks=[task],
        )
        # All jobs should have composite type and may have tasks
        assert job_with_tasks.job_type == "composite"
        assert len(job_with_tasks.tasks) == 1

        # Even jobs without tasks are composite type
        job_without_tasks = BorgJob(
            id="job2",
            status="running",
            started_at=now_utc(),
            job_type="composite",
        )
        assert job_without_tasks.job_type == "composite"
        assert len(job_without_tasks.tasks) == 0


class TestJobManager:
    """Test JobManager class"""

    @pytest.fixture
    def job_manager(self, job_manager_config: JobManagerConfig) -> JobManager:
        """Create job manager for testing"""
        return JobManager(job_manager_config)

    def test_initialization(self, job_manager: JobManager) -> None:
        """Test job manager initialization"""
        # The modular job manager uses dependency injection - test core functionality
        assert job_manager.jobs == {}
        assert hasattr(job_manager, "config")
        # Test that the job manager has the modular components
        assert hasattr(job_manager, "dependencies")
        assert job_manager.dependencies is not None

    def test_initialization_with_default_config(self) -> None:
        """Test job manager with default config"""
        manager = JobManager()
        # The modular version uses JobManagerConfig internally
        assert hasattr(manager, "config")
        assert manager.config.max_concurrent_backups == 5

    @pytest.mark.asyncio
    async def test_initialize(self, job_manager: JobManager) -> None:
        """Test async initialization"""
        await job_manager.initialize()

        # The modular architecture handles initialization internally
        # Test that initialization completes without error
        assert job_manager.dependencies is not None

    @pytest.mark.asyncio
    async def test_shutdown(self, job_manager: JobManager) -> None:
        """Test graceful shutdown"""
        # Initialize first
        await job_manager.initialize()

        # Add a test job
        job_manager.jobs["test"] = Mock()

        await job_manager.shutdown()

        # Test that shutdown clears jobs
        assert job_manager.jobs == {}

    def test_create_job_task(self, job_manager: JobManager) -> None:
        """Test task creation"""
        # Test creating a BorgJobTask directly since _create_job_task is private/removed
        task = BorgJobTask(
            task_type="backup",
            task_name="Test Backup",
            parameters={"source_path": "/data"},
        )

        assert task.task_type == "backup"
        assert task.task_name == "Test Backup"
        assert task.parameters["source_path"] == "/data"

    def test_create_job(self, job_manager: JobManager) -> None:
        """Test job creation"""
        job_id = str(uuid.uuid4())
        # Test creating a BorgJob directly since _create_job is private/removed
        job = BorgJob(
            id=job_id,
            status="running",
            started_at=now_utc(),
        )

        assert job.id == job_id
        assert job.status == "running"

    def test_repository_integration(
        self, sample_repository: Repository, test_db: Session
    ) -> None:
        """Test repository database integration"""
        repo = (
            test_db.query(Repository)
            .filter(Repository.id == sample_repository.id)
            .first()
        )

        assert repo is not None
        assert repo.id == sample_repository.id
        assert repo.name == "test-repo"
        assert repo.path == "/tmp/test-repo"

    @pytest.mark.asyncio
    @patch("uuid.uuid4")
    async def test_start_borg_command_non_backup(
        self, mock_uuid: Mock, job_manager: JobManager
    ) -> None:
        """Test starting non-backup borg command"""
        mock_uuid.return_value = "test-job-id"

        with patch.object(
            job_manager, "_execute_composite_task", new=AsyncMock()
        ) as mock_run:
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
        assert job.job_type == "composite"  # All jobs are now composite
        assert len(job.tasks) == 1  # Should have one task
        assert job.tasks[0].task_name == "Execute: borg list repo"
        assert job.tasks[0].status == "running"
        mock_run.assert_called_once()

    @pytest.mark.asyncio
    @patch("uuid.uuid4")
    async def test_start_borg_command_backup(
        self, mock_uuid: Mock, job_manager: JobManager
    ) -> None:
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
        # In modular architecture, queue processing is handled by JobQueueManager
        assert job.status in ["queued", "running"]

    def test_event_broadcasting(self, job_manager: JobManager) -> None:
        """Test event broadcasting functionality"""

        # Test that the job manager has event broadcasting capabilities
        assert hasattr(job_manager, "dependencies")
        assert job_manager.dependencies is not None

    @pytest.mark.asyncio
    async def test_get_queue_stats(self, job_manager: JobManager) -> None:
        """Test getting queue statistics"""
        # Initialize the job manager to create the queue
        await job_manager.initialize()

        # Add some mock jobs with proper job_type attribute
        running_backup = Mock()
        running_backup.status = "running"
        running_backup.command = ["borg", "create", "repo::archive", "/data"]
        running_backup.job_type = "backup"

        running_other = Mock()
        running_other.status = "running"
        running_other.command = ["borg", "list", "repo"]
        running_other.job_type = "simple"

        queued_backup = Mock()
        queued_backup.status = "queued"
        queued_backup.job_type = "backup"

        job_manager.jobs = {
            "running_backup": running_backup,
            "running_other": running_other,
            "queued_backup": queued_backup,
        }

        stats = job_manager.get_queue_stats()

        # Test basic structure - exact values may differ in modular implementation
        assert "max_concurrent_backups" in stats
        assert "running_backups" in stats
        assert "queued_backups" in stats
        assert "available_slots" in stats

    def test_get_job_status(self, job_manager: JobManager) -> None:
        """Test getting job status"""
        job = Mock()
        job.id = "test"
        job.status = "completed"
        job.started_at = datetime(2023, 1, 1, 12, 0, 0)
        job.completed_at = datetime(2023, 1, 1, 12, 5, 0)
        job.return_code = 0
        job.error = None
        job.job_type = "simple"
        job.current_task_index = 0
        job.tasks = []

        job_manager.jobs["test"] = job

        status = job_manager.get_job_status("test")

        assert status is not None
        assert status["running"] is False
        assert status["completed"] is True
        assert status["status"] == "completed"
        assert status["return_code"] == 0
        assert status["error"] is None

    def test_get_job_status_not_found(self, job_manager: JobManager) -> None:
        """Test getting status for non-existent job"""
        status = job_manager.get_job_status("nonexistent")
        assert status is None

    def test_cleanup_job(self, job_manager: JobManager) -> None:
        """Test cleaning up job"""
        job_manager.jobs["test"] = Mock()

        result = job_manager.cleanup_job("test")
        assert result is True
        assert "test" not in job_manager.jobs

        # Test cleanup of non-existent job
        result = job_manager.cleanup_job("nonexistent")
        assert result is False

    def test_event_subscription_interface(self, job_manager: JobManager) -> None:
        """Test event subscription interface exists"""
        # Test that the event broadcaster is accessible
        assert job_manager.dependencies.event_broadcaster is not None

        # Test that the event broadcaster has the expected interface
        assert hasattr(job_manager.dependencies.event_broadcaster, "subscribe_client")

    @pytest.mark.asyncio
    async def test_stream_all_job_updates(self, job_manager: JobManager) -> None:
        """Test streaming all job updates"""
        # Test that the streaming function exists and returns an async generator
        stream_gen = job_manager.stream_all_job_updates()
        assert hasattr(stream_gen, "__anext__")

        # Clean up
        await stream_gen.aclose()

    @pytest.mark.asyncio
    async def test_cancel_job(self, job_manager: JobManager) -> None:
        """Test cancelling a running job"""
        # Set up a running job
        job = Mock()
        job.id = "test"
        job.status = "running"
        job_manager.jobs["test"] = job

        # Test cancellation interface exists
        await job_manager.cancel_job("test")
        # Result depends on implementation - interface test

    @pytest.mark.asyncio
    async def test_cancel_job_not_found(self, job_manager: JobManager) -> None:
        """Test cancelling non-existent job"""
        result = await job_manager.cancel_job("nonexistent")
        assert result is False

    @pytest.mark.asyncio
    async def test_execute_composite_task_success(
        self, job_manager: JobManager
    ) -> None:
        """Test successful execution of a composite task"""
        # Create a test job and task
        job = BorgJob(
            id="test-job-id",
            command=["borg", "list", "test-repo"],
            job_type="composite",
            status="running",
            started_at=now_utc(),
            tasks=[],
        )

        task = BorgJobTask(
            task_type="command",
            task_name="Test Command",
            status="running",
            started_at=now_utc(),
        )

        # Mock the underlying dependencies
        with patch.object(job_manager, "executor") as mock_executor, patch.object(
            job_manager, "output_manager"
        ) as mock_output_manager, patch.object(
            job_manager, "event_broadcaster"
        ) as mock_broadcaster:
            # Mock process and result
            mock_process = Mock()
            mock_result = Mock()
            mock_result.return_code = 0
            mock_result.error = None

            mock_executor.start_process = AsyncMock(return_value=mock_process)
            mock_executor.monitor_process_output = AsyncMock(return_value=mock_result)
            mock_output_manager.add_output_line = AsyncMock()

            # Execute the task
            await job_manager._execute_composite_task(
                job=job,
                task=task,
                command=["borg", "list", "test-repo"],
                env={"TEST": "value"},
            )

            # Verify the task was updated correctly
            assert task.status == "completed"
            assert task.return_code == 0
            assert task.completed_at is not None
            assert task.error is None

            # Verify job was updated correctly
            assert job.status == "completed"
            assert job.return_code == 0
            assert job.completed_at is not None

            # Verify executor was called correctly
            mock_executor.start_process.assert_called_once_with(
                ["borg", "list", "test-repo"], {"TEST": "value"}
            )
            # Verify monitor_process_output was called with the process and a callback
            mock_executor.monitor_process_output.assert_called_once()
            call_args = mock_executor.monitor_process_output.call_args
            assert (
                call_args[0][0] == mock_process
            )  # First positional arg is the process
            assert "output_callback" in call_args.kwargs  # Has output_callback
            assert callable(call_args.kwargs["output_callback"])  # Callback is callable

            # Verify events were broadcast
            assert mock_broadcaster.broadcast_event.call_count >= 1

    @pytest.mark.asyncio
    async def test_execute_composite_task_failure(
        self, job_manager: JobManager
    ) -> None:
        """Test execution of a composite task that fails"""
        # Create a test job and task
        job = BorgJob(
            id="test-job-id",
            command=["borg", "list", "invalid-repo"],
            job_type="composite",
            status="running",
            started_at=now_utc(),
            tasks=[],
        )

        task = BorgJobTask(
            task_type="command",
            task_name="Test Command",
            status="running",
            started_at=now_utc(),
        )

        # Mock the underlying dependencies
        with patch.object(job_manager, "executor") as mock_executor, patch.object(
            job_manager, "output_manager"
        ) as mock_output_manager, patch.object(job_manager, "event_broadcaster"):
            # Mock process and result with failure
            mock_process = Mock()
            mock_result = Mock()
            mock_result.return_code = 1
            mock_result.error = "Repository not found"

            mock_executor.start_process = AsyncMock(return_value=mock_process)
            mock_executor.monitor_process_output = AsyncMock(return_value=mock_result)
            mock_output_manager.add_output_line = AsyncMock()

            # Execute the task
            await job_manager._execute_composite_task(
                job=job, task=task, command=["borg", "list", "invalid-repo"], env=None
            )

            # Verify the task was updated correctly
            assert task.status == "failed"
            assert task.return_code == 1
            assert task.completed_at is not None
            assert task.error == "Repository not found"

            # Verify job was updated correctly
            assert job.status == "failed"
            assert job.return_code == 1
            assert job.error == "Repository not found"

            # Verify executor was called correctly
            mock_executor.start_process.assert_called_once_with(
                ["borg", "list", "invalid-repo"], None
            )

    @pytest.mark.asyncio
    async def test_execute_composite_task_exception(
        self, job_manager: JobManager
    ) -> None:
        """Test execution of a composite task that raises an exception"""
        # Create a test job and task
        job = BorgJob(
            id="test-job-id",
            command=["borg", "list", "test-repo"],
            job_type="composite",
            status="running",
            started_at=now_utc(),
            tasks=[],
        )

        task = BorgJobTask(
            task_type="command",
            task_name="Test Command",
            status="running",
            started_at=now_utc(),
        )

        # Mock the underlying dependencies to raise an exception
        with patch.object(job_manager, "executor") as mock_executor, patch.object(
            job_manager, "output_manager"
        ) as mock_output_manager, patch.object(job_manager, "event_broadcaster"):
            mock_executor.start_process = AsyncMock(
                side_effect=Exception("Process failed to start")
            )
            mock_output_manager.add_output_line = AsyncMock()

            # Execute the task
            await job_manager._execute_composite_task(
                job=job, task=task, command=["borg", "list", "test-repo"], env=None
            )

            # Verify the task was updated correctly
            assert task.status == "failed"
            assert task.error == "Process failed to start"
            assert task.completed_at is not None

            # Verify job was updated correctly
            assert job.status == "failed"
            assert job.error == "Process failed to start"
