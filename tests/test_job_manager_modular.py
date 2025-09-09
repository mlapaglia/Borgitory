"""
Tests for ModularBorgJobManager - integration tests for the refactored modular architecture
"""
import pytest
from unittest.mock import AsyncMock, Mock, patch
from datetime import datetime, UTC

from app.services.job_manager_modular import (
    ModularBorgJobManager,
    BorgJob
)
from app.services.job_manager_dependencies import (
    JobManagerConfig,
    JobManagerFactory
)


class TestModularBorgJobManager:
    """Test ModularBorgJobManager functionality"""
    
    def setup_method(self):
        """Set up test fixtures with mocked dependencies"""
        # Create test config
        self.config = JobManagerConfig(
            max_concurrent_backups=2,
            max_output_lines_per_job=100,
            auto_cleanup_delay_seconds=1
        )
        
        # Create mocked dependencies
        self.mock_dependencies = JobManagerFactory.create_for_testing(
            mock_subprocess=AsyncMock(),
            mock_db_session=Mock(),
            mock_rclone_service=Mock()
        )
        
        # Create job manager with mocked dependencies
        self.job_manager = ModularBorgJobManager(
            config=self.config,
            dependencies=self.mock_dependencies
        )
    
    @pytest.mark.asyncio
    async def test_initialization(self):
        """Test job manager initialization"""
        assert not self.job_manager._initialized
        
        await self.job_manager.initialize()
        
        assert self.job_manager._initialized
        assert self.job_manager.executor is not None
        assert self.job_manager.output_manager is not None
        assert self.job_manager.queue_manager is not None
        assert self.job_manager.event_broadcaster is not None
    
    @pytest.mark.asyncio
    async def test_start_borg_command_simple(self):
        """Test starting a simple Borg command"""
        command = ["borg", "info", "repo"]
        
        # Mock process execution
        mock_process = AsyncMock()
        mock_process.pid = 12345
        self.mock_dependencies.subprocess_executor.return_value = mock_process
        
        with patch.object(self.job_manager.executor, 'start_process', return_value=mock_process), \
             patch.object(self.job_manager.executor, 'monitor_process_output') as mock_monitor:
            
            mock_monitor.return_value = AsyncMock(return_code=0, error=None)
            
            job_id = await self.job_manager.start_borg_command(command, is_backup=False)
            
            assert job_id is not None
            assert job_id in self.job_manager.jobs
            
            job = self.job_manager.jobs[job_id]
            assert job.command == command
            assert job.job_type == "simple"
            assert job.status in ["running", "queued", "completed"]  # May complete quickly in test environment
    
    @pytest.mark.asyncio
    async def test_start_borg_command_backup(self):
        """Test starting a backup command (queued)"""
        command = ["borg", "create", "repo::archive", "/path"]
        
        job_id = await self.job_manager.start_borg_command(command, is_backup=True)
        
        assert job_id is not None
        assert job_id in self.job_manager.jobs
        
        job = self.job_manager.jobs[job_id]
        assert job.command == command
        assert job.job_type == "simple"
        assert job.status == "queued"
    
    @pytest.mark.asyncio
    async def test_create_composite_job(self):
        """Test creating a composite job with multiple tasks"""
        # Mock repository
        mock_repository = Mock()
        mock_repository.id = 1
        mock_repository.name = "test-repo"
        
        task_definitions = [
            {"type": "backup", "name": "Backup task", "source_path": "/data"},
            {"type": "prune", "name": "Prune task", "keep_daily": 7},
        ]
        
        job_id = await self.job_manager.create_composite_job(
            job_type="manual_backup",
            task_definitions=task_definitions,
            repository=mock_repository
        )
        
        assert job_id is not None
        assert job_id in self.job_manager.jobs
        
        job = self.job_manager.jobs[job_id]
        assert job.job_type == "composite"
        assert len(job.tasks) == 2
        assert job.tasks[0].task_type == "backup"
        assert job.tasks[1].task_type == "prune"
        assert job.repository_id == 1
    
    @pytest.mark.asyncio
    async def test_get_job_status(self):
        """Test getting job status"""
        # Create a simple job
        job = BorgJob(
            id="test-job-123",
            status="running",
            started_at=datetime.now(UTC),
            job_type="simple"
        )
        self.job_manager.jobs["test-job-123"] = job
        
        status = self.job_manager.get_job_status("test-job-123")
        
        assert status is not None
        assert status["status"] == "running"
        assert status["running"] is True
        assert status["completed"] is False
        assert status["return_code"] is None
    
    @pytest.mark.asyncio
    async def test_get_job_status_nonexistent(self):
        """Test getting status for nonexistent job"""
        status = self.job_manager.get_job_status("nonexistent")
        
        assert status is None
    
    @pytest.mark.asyncio
    async def test_get_job_output_stream(self):
        """Test getting job output stream"""
        job_id = "test-job-output"
        
        # Create job output
        self.job_manager.output_manager.create_job_output(job_id)
        await self.job_manager.output_manager.add_output_line(
            job_id, "Test output line"
        )
        
        output_stream = await self.job_manager.get_job_output_stream(job_id)
        
        assert "lines" in output_stream
        assert "progress" in output_stream
        assert len(output_stream["lines"]) == 1
        assert output_stream["lines"][0]["text"] == "Test output line"
    
    @pytest.mark.asyncio
    async def test_cancel_job(self):
        """Test cancelling a running job"""
        job_id = "test-job-cancel"
        mock_process = AsyncMock()
        mock_process.returncode = None
        
        # Add job and process
        job = BorgJob(
            id=job_id,
            status="running",
            started_at=datetime.now(UTC),
            job_type="simple"
        )
        self.job_manager.jobs[job_id] = job
        self.job_manager._processes[job_id] = mock_process
        
        # Mock the executor terminate method
        with patch.object(self.job_manager.executor, 'terminate_process', return_value=True) as mock_terminate:
            result = await self.job_manager.cancel_job(job_id)
            
            assert result is True
            mock_terminate.assert_called_once_with(mock_process)
    
    @pytest.mark.asyncio
    async def test_cancel_job_nonexistent(self):
        """Test cancelling nonexistent job"""
        result = await self.job_manager.cancel_job("nonexistent")
        
        assert result is False
    
    def test_cleanup_job(self):
        """Test cleaning up job from memory"""
        job_id = "test-job-cleanup"
        
        # Create job and output
        job = BorgJob(
            id=job_id,
            status="completed",
            started_at=datetime.now(UTC),
            job_type="simple"
        )
        self.job_manager.jobs[job_id] = job
        self.job_manager.output_manager.create_job_output(job_id)
        
        result = self.job_manager.cleanup_job(job_id)
        
        assert result is True
        assert job_id not in self.job_manager.jobs
        assert self.job_manager.output_manager.get_job_output(job_id) is None
    
    def test_cleanup_job_nonexistent(self):
        """Test cleaning up nonexistent job"""
        result = self.job_manager.cleanup_job("nonexistent")
        
        assert result is False
    
    def test_get_queue_stats(self):
        """Test getting queue statistics"""
        stats = self.job_manager.get_queue_stats()
        
        assert "max_concurrent_backups" in stats
        assert "running_backups" in stats
        assert "queued_backups" in stats
        assert "available_slots" in stats
        assert "queue_size" in stats
        
        assert stats["max_concurrent_backups"] == 2
    
    @pytest.mark.asyncio
    async def test_auto_cleanup_job(self):
        """Test automatic job cleanup after delay"""
        job_id = "test-job-auto-cleanup"
        
        # Create completed job
        job = BorgJob(
            id=job_id,
            status="completed",
            started_at=datetime.now(UTC),
            completed_at=datetime.now(UTC),
            job_type="simple"
        )
        self.job_manager.jobs[job_id] = job
        
        # Trigger auto cleanup with very short delay
        await self.job_manager._auto_cleanup_job(job_id, 0.1)
        
        # Job should be cleaned up
        assert job_id not in self.job_manager.jobs
    
    @pytest.mark.asyncio
    async def test_shutdown(self):
        """Test job manager shutdown"""
        await self.job_manager.initialize()
        
        # Add some jobs and processes
        job = BorgJob(
            id="test-job",
            status="running",
            started_at=datetime.now(UTC),
            job_type="simple"
        )
        self.job_manager.jobs["test-job"] = job
        
        mock_process = AsyncMock()
        self.job_manager._processes["test-job"] = mock_process
        
        with patch.object(self.job_manager.executor, 'terminate_process') as mock_terminate:
            await self.job_manager.shutdown()
            
            assert self.job_manager._shutdown_requested is True
            assert len(self.job_manager.jobs) == 0
            assert len(self.job_manager._processes) == 0
            mock_terminate.assert_called_once_with(mock_process)


class TestJobManagerFactory:
    """Test JobManagerFactory functionality"""
    
    def test_create_dependencies_default(self):
        """Test creating default dependencies"""
        dependencies = JobManagerFactory.create_dependencies()
        
        assert dependencies.job_executor is not None
        assert dependencies.output_manager is not None
        assert dependencies.queue_manager is not None
        assert dependencies.event_broadcaster is not None
        assert dependencies.database_manager is not None
        assert dependencies.cloud_coordinator is not None
    
    def test_create_dependencies_custom_config(self):
        """Test creating dependencies with custom config"""
        config = JobManagerConfig(
            max_concurrent_backups=3,
            max_output_lines_per_job=500
        )
        
        dependencies = JobManagerFactory.create_dependencies(config=config)
        
        assert dependencies.queue_manager.max_concurrent_backups == 3
        assert dependencies.output_manager.max_lines_per_job == 500
    
    def test_create_for_testing(self):
        """Test creating dependencies for testing"""
        mock_subprocess = AsyncMock()
        mock_db = Mock()
        
        dependencies = JobManagerFactory.create_for_testing(
            mock_subprocess=mock_subprocess,
            mock_db_session=mock_db
        )
        
        assert dependencies.subprocess_executor == mock_subprocess
        assert dependencies.db_session_factory == mock_db
        assert dependencies.job_executor is not None
        assert dependencies.output_manager is not None
    
    def test_create_minimal(self):
        """Test creating minimal dependencies"""
        dependencies = JobManagerFactory.create_minimal()
        
        # Should have reduced configuration
        assert dependencies.queue_manager.max_concurrent_backups == 1
        assert dependencies.queue_manager.max_concurrent_operations == 2
        assert dependencies.output_manager.max_lines_per_job == 100