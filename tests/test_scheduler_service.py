import pytest
from unittest.mock import Mock, AsyncMock, patch
from datetime import datetime, UTC

from app.services.scheduler_service import SchedulerService, execute_scheduled_backup
from app.models.database import Schedule, CleanupConfig, RepositoryCheckConfig


class TestSchedulerService:
    """Test SchedulerService functionality"""
    
    def setup_method(self):
        """Set up test fixtures"""
        self.scheduler_service = SchedulerService()
    
    @pytest.mark.asyncio
    async def test_start_scheduler(self):
        """Test starting the scheduler"""
        with patch.object(self.scheduler_service.scheduler, 'start') as mock_start, \
             patch.object(self.scheduler_service, '_reload_schedules', new_callable=AsyncMock) as mock_reload:
            
            await self.scheduler_service.start()
            
            mock_start.assert_called_once()
            mock_reload.assert_called_once()
            assert self.scheduler_service._running is True
    
    @pytest.mark.asyncio
    async def test_start_scheduler_already_running(self):
        """Test starting scheduler when already running"""
        self.scheduler_service._running = True
        
        with patch.object(self.scheduler_service.scheduler, 'start') as mock_start:
            await self.scheduler_service.start()
            
            # Should not call start again
            mock_start.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_stop_scheduler(self):
        """Test stopping the scheduler"""
        self.scheduler_service._running = True
        
        with patch.object(self.scheduler_service.scheduler, 'shutdown') as mock_shutdown:
            await self.scheduler_service.stop()
            
            mock_shutdown.assert_called_once_with(wait=True)
            assert self.scheduler_service._running is False
    
    @pytest.mark.asyncio
    async def test_stop_scheduler_not_running(self):
        """Test stopping scheduler when not running"""
        self.scheduler_service._running = False
        
        with patch.object(self.scheduler_service.scheduler, 'shutdown') as mock_shutdown:
            await self.scheduler_service.stop()
            
            # Should not call shutdown if not running
            mock_shutdown.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_add_schedule_success(self):
        """Test successfully adding a schedule"""
        self.scheduler_service._running = True
        schedule_id = 123
        schedule_name = "Daily Backup"
        cron_expression = "0 2 * * *"  # Daily at 2 AM
        
        with patch.object(self.scheduler_service.scheduler, 'add_job') as mock_add_job, \
             patch.object(self.scheduler_service.scheduler, 'remove_job') as mock_remove_job, \
             patch.object(self.scheduler_service, '_update_next_run_time', new_callable=AsyncMock) as mock_update:
            
            # Mock remove_job to raise exception (job doesn't exist)
            mock_remove_job.side_effect = Exception("Job not found")
            
            job_id = await self.scheduler_service.add_schedule(
                schedule_id, schedule_name, cron_expression
            )
            
            assert job_id == f"backup_schedule_{schedule_id}"
            mock_add_job.assert_called_once()
            mock_update.assert_called_once_with(schedule_id, job_id)
    
    @pytest.mark.asyncio
    async def test_add_schedule_invalid_cron(self):
        """Test adding schedule with invalid cron expression"""
        self.scheduler_service._running = True
        schedule_id = 123
        schedule_name = "Daily Backup"
        cron_expression = "invalid cron"
        
        with pytest.raises(Exception) as exc_info:
            await self.scheduler_service.add_schedule(
                schedule_id, schedule_name, cron_expression
            )
        
        assert "Failed to add schedule" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_add_schedule_scheduler_not_running(self):
        """Test adding schedule when scheduler is not running"""
        self.scheduler_service._running = False
        
        with pytest.raises(RuntimeError) as exc_info:
            await self.scheduler_service.add_schedule(123, "Test", "0 2 * * *")
        
        assert "Scheduler is not running" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_remove_schedule_success(self):
        """Test successfully removing a schedule"""
        self.scheduler_service._running = True
        schedule_id = 123
        
        with patch.object(self.scheduler_service.scheduler, 'remove_job') as mock_remove:
            await self.scheduler_service.remove_schedule(schedule_id)
            
            mock_remove.assert_called_once_with(f"backup_schedule_{schedule_id}")
    
    @pytest.mark.asyncio
    async def test_remove_schedule_not_found(self):
        """Test removing a schedule that doesn't exist"""
        self.scheduler_service._running = True
        schedule_id = 123
        
        with patch.object(self.scheduler_service.scheduler, 'remove_job') as mock_remove:
            mock_remove.side_effect = Exception("Job not found")
            
            # Should not raise exception
            await self.scheduler_service.remove_schedule(schedule_id)
    
    @pytest.mark.asyncio
    async def test_update_schedule_enabled(self):
        """Test updating an enabled schedule"""
        self.scheduler_service._running = True
        schedule_id = 123
        schedule_name = "Updated Backup"
        cron_expression = "0 3 * * *"
        enabled = True
        
        with patch.object(self.scheduler_service, 'remove_schedule', new_callable=AsyncMock) as mock_remove, \
             patch.object(self.scheduler_service, 'add_schedule', new_callable=AsyncMock) as mock_add:
            
            await self.scheduler_service.update_schedule(
                schedule_id, schedule_name, cron_expression, enabled
            )
            
            mock_remove.assert_called_once_with(schedule_id)
            mock_add.assert_called_once_with(schedule_id, schedule_name, cron_expression)
    
    @pytest.mark.asyncio
    async def test_update_schedule_disabled(self):
        """Test updating a disabled schedule"""
        self.scheduler_service._running = True
        schedule_id = 123
        schedule_name = "Disabled Backup"
        cron_expression = "0 3 * * *"
        enabled = False
        
        with patch.object(self.scheduler_service, 'remove_schedule', new_callable=AsyncMock) as mock_remove, \
             patch.object(self.scheduler_service, 'add_schedule', new_callable=AsyncMock) as mock_add:
            
            await self.scheduler_service.update_schedule(
                schedule_id, schedule_name, cron_expression, enabled
            )
            
            mock_remove.assert_called_once_with(schedule_id)
            # Should not add when disabled
            mock_add.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_get_scheduled_jobs(self):
        """Test getting scheduled jobs"""
        self.scheduler_service._running = True
        
        # Mock jobs
        mock_job1 = Mock()
        mock_job1.id = "backup_schedule_123"
        mock_job1.name = "Daily Backup"
        mock_job1.next_run_time = datetime.now(UTC)
        mock_job1.trigger = "cron"
        
        mock_job2 = Mock()
        mock_job2.id = "other_job_456"  # Should be filtered out
        
        with patch.object(self.scheduler_service.scheduler, 'get_jobs') as mock_get_jobs:
            mock_get_jobs.return_value = [mock_job1, mock_job2]
            
            jobs = await self.scheduler_service.get_scheduled_jobs()
            
            assert len(jobs) == 1
            assert jobs[0]["id"] == "backup_schedule_123"
            assert jobs[0]["name"] == "Daily Backup"
            assert jobs[0]["next_run"] == mock_job1.next_run_time
    
    @pytest.mark.asyncio
    async def test_get_scheduled_jobs_scheduler_not_running(self):
        """Test getting jobs when scheduler is not running"""
        self.scheduler_service._running = False
        
        jobs = await self.scheduler_service.get_scheduled_jobs()
        
        assert jobs == []
    
    @pytest.mark.asyncio
    async def test_reload_schedules_success(self):
        """Test successfully reloading schedules from database"""
        mock_db = Mock()
        mock_schedule1 = Mock()
        mock_schedule1.id = 123
        mock_schedule1.name = "Schedule 1"
        mock_schedule1.cron_expression = "0 2 * * *"
        
        mock_schedule2 = Mock()
        mock_schedule2.id = 456
        mock_schedule2.name = "Schedule 2"
        mock_schedule2.cron_expression = "0 4 * * *"
        
        mock_db.query.return_value.filter.return_value.all.return_value = [mock_schedule1, mock_schedule2]
        
        with patch('app.services.scheduler_service.get_db_session') as mock_get_db, \
             patch.object(self.scheduler_service, '_add_schedule_internal', new_callable=AsyncMock) as mock_add:
            
            mock_get_db.return_value.__enter__.return_value = mock_db
            
            await self.scheduler_service._reload_schedules()
            
            assert mock_add.call_count == 2
            mock_add.assert_any_call(123, "Schedule 1", "0 2 * * *", persist=False)
            mock_add.assert_any_call(456, "Schedule 2", "0 4 * * *", persist=False)
    
    @pytest.mark.asyncio
    async def test_update_next_run_time_success(self):
        """Test updating next run time in database"""
        schedule_id = 123
        job_id = "backup_schedule_123"
        next_run_time = datetime.now(UTC)
        
        mock_job = Mock()
        mock_job.next_run_time = next_run_time
        
        mock_db = Mock()
        mock_schedule = Mock()
        mock_db.query.return_value.filter.return_value.first.return_value = mock_schedule
        
        with patch.object(self.scheduler_service.scheduler, 'get_job') as mock_get_job, \
             patch('app.services.scheduler_service.get_db_session') as mock_get_db:
            
            mock_get_job.return_value = mock_job
            mock_get_db.return_value.__enter__.return_value = mock_db
            
            await self.scheduler_service._update_next_run_time(schedule_id, job_id)
            
            assert mock_schedule.next_run == next_run_time
    
    def test_handle_job_event_success(self):
        """Test handling successful job event"""
        mock_event = Mock()
        mock_event.job_id = "backup_schedule_123"
        mock_event.exception = None
        
        # Should not raise exception
        self.scheduler_service._handle_job_event(mock_event)
    
    def test_handle_job_event_failure(self):
        """Test handling failed job event"""
        mock_event = Mock()
        mock_event.job_id = "backup_schedule_123"
        mock_event.exception = Exception("Job failed")
        
        # Should not raise exception
        self.scheduler_service._handle_job_event(mock_event)


class TestExecuteScheduledBackup:
    """Test execute_scheduled_backup function"""
    
    @pytest.mark.asyncio
    async def test_execute_scheduled_backup_success(self):
        """Test successful scheduled backup execution"""
        schedule_id = 123
        
        # Mock database objects
        mock_db = Mock()
        mock_repository = Mock()
        mock_repository.id = 1  # Set proper integer ID
        mock_repository.name = "Test Repository"
        
        mock_schedule = Mock()
        mock_schedule.id = schedule_id
        mock_schedule.name = "Test Schedule"
        mock_schedule.repository_id = 1
        mock_schedule.repository = mock_repository
        mock_schedule.source_path = "/test/source"
        mock_schedule.cloud_sync_config_id = None
        mock_schedule.cleanup_config_id = None
        mock_schedule.check_config_id = None
        mock_schedule.notification_config_id = None
        
        mock_db.query.return_value.filter.return_value.first.return_value = mock_schedule
        
        with patch('app.services.scheduler_service.get_db_session') as mock_get_db, \
             patch('app.services.job_service.JobService.create_backup_job', new_callable=AsyncMock) as mock_create_job:
            
            mock_get_db.return_value.__enter__.return_value = mock_db
            mock_create_job.return_value = {"job_id": "job-uuid-123", "status": "started"}
            
            await execute_scheduled_backup(schedule_id)
            
            # Verify schedule last_run was updated
            assert mock_schedule.last_run is not None
            mock_db.commit.assert_called_once()
            
            # Verify backup job was created via JobService
            mock_create_job.assert_called_once()
            args = mock_create_job.call_args
            backup_request = args[0][0]  # First positional arg is BackupRequest
            assert backup_request.repository_id == 1
            assert backup_request.source_path == "/test/source"
            assert backup_request.compression == "zstd"
            assert not backup_request.dry_run
    
    @pytest.mark.asyncio
    async def test_execute_scheduled_backup_with_cleanup(self):
        """Test scheduled backup with cleanup task"""
        schedule_id = 123
        
        # Mock database objects
        mock_db = Mock()
        mock_repository = Mock()
        mock_repository.name = "Test Repository"
        mock_repository.id = 1
        
        mock_cleanup_config = Mock()
        mock_cleanup_config.strategy = "simple"
        mock_cleanup_config.keep_within_days = 30
        mock_cleanup_config.show_list = True
        mock_cleanup_config.show_stats = True
        mock_cleanup_config.save_space = False
        
        mock_schedule = Mock()
        mock_schedule.id = schedule_id
        mock_schedule.name = "Test Schedule"
        mock_schedule.repository_id = 1
        mock_schedule.repository = mock_repository
        mock_schedule.source_path = "/test/source"
        mock_schedule.cloud_sync_config_id = None
        mock_schedule.cleanup_config_id = 1
        mock_schedule.check_config_id = None
        mock_schedule.notification_config_id = None
        
        # Setup query mocks
        def mock_query_side_effect(model):
            if model == Schedule:
                return Mock(filter=Mock(return_value=Mock(first=Mock(return_value=mock_schedule))))
            elif model == CleanupConfig:
                return Mock(filter=Mock(return_value=Mock(first=Mock(return_value=mock_cleanup_config))))
            return Mock()
        
        mock_db.query.side_effect = mock_query_side_effect
        
        with patch('app.services.scheduler_service.get_db_session') as mock_get_db, \
             patch('app.services.job_service.JobService') as mock_job_service_class:
            
            mock_get_db.return_value.__enter__.return_value = mock_db
            
            # Mock JobService instance and its create_backup_job method
            mock_job_service = AsyncMock()
            mock_job_service.create_backup_job.return_value = {"job_id": "job-uuid-123", "status": "started"}
            mock_job_service_class.return_value = mock_job_service
            
            await execute_scheduled_backup(schedule_id)
            
            # Verify backup job was created with correct JobType
            mock_job_service.create_backup_job.assert_called_once()
            call_args = mock_job_service.create_backup_job.call_args
            # Third argument should be JobType.SCHEDULED_BACKUP
            from app.models.enums import JobType
            assert call_args[0][2] == JobType.SCHEDULED_BACKUP
    
    @pytest.mark.asyncio
    async def test_execute_scheduled_backup_with_check(self):
        """Test scheduled backup with repository check task"""
        schedule_id = 123
        
        # Mock database objects
        mock_db = Mock()
        mock_repository = Mock()
        mock_repository.name = "Test Repository"
        mock_repository.id = 1
        
        mock_check_config = Mock()
        mock_check_config.name = "Full Check"
        mock_check_config.check_type = "full"
        mock_check_config.verify_data = True
        mock_check_config.repair_mode = False
        mock_check_config.save_space = False
        mock_check_config.max_duration = 3600
        mock_check_config.archive_prefix = None
        mock_check_config.archive_glob = None
        mock_check_config.first_n_archives = None
        mock_check_config.last_n_archives = None
        
        mock_schedule = Mock()
        mock_schedule.id = schedule_id
        mock_schedule.name = "Test Schedule"
        mock_schedule.repository_id = 1
        mock_schedule.repository = mock_repository
        mock_schedule.source_path = "/test/source"
        mock_schedule.cloud_sync_config_id = None
        mock_schedule.cleanup_config_id = None
        mock_schedule.check_config_id = 1
        mock_schedule.notification_config_id = None
        
        # Setup query mocks
        def mock_query_side_effect(model):
            if model == Schedule:
                return Mock(filter=Mock(return_value=Mock(first=Mock(return_value=mock_schedule))))
            elif model == RepositoryCheckConfig:
                return Mock(filter=Mock(return_value=Mock(first=Mock(return_value=mock_check_config))))
            return Mock()
        
        mock_db.query.side_effect = mock_query_side_effect
        
        with patch('app.services.scheduler_service.get_db_session') as mock_get_db, \
             patch('app.services.job_service.JobService') as mock_job_service_class:
            
            mock_get_db.return_value.__enter__.return_value = mock_db
            
            # Mock JobService instance and its create_backup_job method
            mock_job_service = AsyncMock()
            mock_job_service.create_backup_job.return_value = {"job_id": "job-uuid-123", "status": "started"}
            mock_job_service_class.return_value = mock_job_service
            
            await execute_scheduled_backup(schedule_id)
            
            # Verify backup job was created with correct JobType
            mock_job_service.create_backup_job.assert_called_once()
            call_args = mock_job_service.create_backup_job.call_args
            # Third argument should be JobType.SCHEDULED_BACKUP
            from app.models.enums import JobType
            assert call_args[0][2] == JobType.SCHEDULED_BACKUP
    
    @pytest.mark.asyncio
    async def test_execute_scheduled_backup_with_cloud_sync(self):
        """Test scheduled backup with cloud sync task"""
        schedule_id = 123
        
        # Mock database objects
        mock_db = Mock()
        mock_repository = Mock()
        mock_repository.name = "Test Repository"
        mock_repository.id = 1
        
        mock_schedule = Mock()
        mock_schedule.id = schedule_id
        mock_schedule.name = "Test Schedule"
        mock_schedule.repository_id = 1
        mock_schedule.repository = mock_repository
        mock_schedule.source_path = "/test/source"
        mock_schedule.cloud_sync_config_id = 1  # Has cloud sync
        mock_schedule.cleanup_config_id = None
        mock_schedule.check_config_id = None
        mock_schedule.notification_config_id = None
        
        mock_db.query.return_value.filter.return_value.first.return_value = mock_schedule
        
        with patch('app.services.scheduler_service.get_db_session') as mock_get_db, \
             patch('app.services.job_service.JobService') as mock_job_service_class:
            
            mock_get_db.return_value.__enter__.return_value = mock_db
            
            # Mock JobService instance and its create_backup_job method
            mock_job_service = AsyncMock()
            mock_job_service.create_backup_job.return_value = {"job_id": "job-uuid-123", "status": "started"}
            mock_job_service_class.return_value = mock_job_service
            
            await execute_scheduled_backup(schedule_id)
            
            # Verify backup job was created with correct JobType
            mock_job_service.create_backup_job.assert_called_once()
            call_args = mock_job_service.create_backup_job.call_args
            # Third argument should be JobType.SCHEDULED_BACKUP
            from app.models.enums import JobType
            assert call_args[0][2] == JobType.SCHEDULED_BACKUP
    
    @pytest.mark.asyncio
    async def test_execute_scheduled_backup_schedule_not_found(self):
        """Test scheduled backup when schedule doesn't exist"""
        schedule_id = 999
        
        mock_db = Mock()
        mock_db.query.return_value.filter.return_value.first.return_value = None
        
        with patch('app.services.scheduler_service.get_db_session') as mock_get_db:
            mock_get_db.return_value.__enter__.return_value = mock_db
            
            # Should not raise exception
            await execute_scheduled_backup(schedule_id)
    
    @pytest.mark.asyncio
    async def test_execute_scheduled_backup_repository_not_found(self):
        """Test scheduled backup when repository doesn't exist"""
        schedule_id = 123
        
        mock_db = Mock()
        mock_schedule = Mock()
        mock_schedule.id = schedule_id
        mock_schedule.repository = None  # No repository
        
        mock_db.query.return_value.filter.return_value.first.return_value = mock_schedule
        
        with patch('app.services.scheduler_service.get_db_session') as mock_get_db:
            mock_get_db.return_value.__enter__.return_value = mock_db
            
            # Should not raise exception
            await execute_scheduled_backup(schedule_id)
    
    @pytest.mark.asyncio
    async def test_execute_scheduled_backup_composite_job_failure(self):
        """Test scheduled backup when composite job creation fails"""
        schedule_id = 123
        
        mock_db = Mock()
        mock_repository = Mock()
        mock_repository.name = "Test Repository"
        mock_repository.id = 1
        mock_repository.id = 1
        
        mock_schedule = Mock()
        mock_schedule.id = schedule_id
        mock_schedule.name = "Test Schedule"
        mock_schedule.repository_id = 1
        mock_schedule.repository = mock_repository
        mock_schedule.source_path = "/test/source"
        mock_schedule.cloud_sync_config_id = None
        mock_schedule.cleanup_config_id = None
        mock_schedule.check_config_id = None
        mock_schedule.notification_config_id = None
        
        mock_db.query.return_value.filter.return_value.first.return_value = mock_schedule
        
        with patch('app.services.scheduler_service.get_db_session') as mock_get_db, \
             patch('app.services.job_service.JobService') as mock_job_service_class:
            
            mock_get_db.return_value.__enter__.return_value = mock_db
            
            # Mock JobService instance and its create_backup_job method
            mock_job_service = AsyncMock()
            mock_job_service.create_backup_job.side_effect = Exception("Job creation failed")
            mock_job_service_class.return_value = mock_job_service
            
            # Should re-raise the exception
            with pytest.raises(Exception) as exc_info:
                await execute_scheduled_backup(schedule_id)
            
            assert "Job creation failed" in str(exc_info.value)