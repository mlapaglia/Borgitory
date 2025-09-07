from unittest.mock import Mock, patch
from datetime import datetime, UTC

from app.services.job_render_service import JobRenderService
from app.models.database import Job, JobTask


class TestJobRenderService:
    """Test JobRenderService functionality"""
    
    def setup_method(self):
        """Set up test fixtures"""
        with patch('app.services.job_render_service.get_job_manager') as mock_get_manager:
            mock_job_manager = Mock()
            mock_job_manager.jobs = {}
            mock_get_manager.return_value = mock_job_manager
            
            self.job_render_service = JobRenderService()
            self.mock_job_manager = mock_job_manager
    
    def test_initialization(self):
        """Test JobRenderService initialization"""
        assert self.job_render_service is not None
        assert self.job_render_service.templates is not None
        assert self.job_render_service.job_manager is not None
    
    def test_initialization_with_custom_manager(self):
        """Test initialization with custom job manager"""
        custom_manager = Mock()
        service = JobRenderService(job_manager=custom_manager)
        assert service.job_manager == custom_manager
    
    def test_render_jobs_html_no_jobs(self):
        """Test rendering HTML when no jobs exist"""
        mock_db = Mock()
        mock_db.query.return_value.options.return_value.order_by.return_value.limit.return_value.all.return_value = []
        
        result = self.job_render_service.render_jobs_html(mock_db)
        
        assert "No job history available" in result
    
    def test_render_jobs_html_with_jobs(self):
        """Test rendering HTML with jobs"""
        mock_db = Mock()
        
        # Create mock repository
        mock_repo = Mock()
        mock_repo.name = "Test Repository"
        
        # Create mock job with UUID
        mock_job = Mock(spec=Job)
        mock_job.job_uuid = "test-uuid-123"
        mock_job.id = 1
        mock_job.status = "completed"
        mock_job.job_type = "backup"
        mock_job.type = "backup"
        mock_job.started_at = datetime.now(UTC)
        mock_job.finished_at = datetime.now(UTC)
        mock_job.error = None
        mock_job.repository = mock_repo
        mock_job.tasks = []
        mock_job.completed_tasks = 0
        mock_job.total_tasks = 0
        
        mock_db.query.return_value.options.return_value.order_by.return_value.limit.return_value.all.return_value = [mock_job]
        
        result = self.job_render_service.render_jobs_html(mock_db)
        
        assert '<div class="space-y-3">' in result
        assert '</div>' in result
    
    def test_render_jobs_html_skips_jobs_without_uuid(self):
        """Test that jobs without UUIDs are skipped"""
        mock_db = Mock()
        
        # Create mock job without UUID
        mock_job = Mock(spec=Job)
        mock_job.job_uuid = None
        mock_job.id = 1
        
        mock_db.query.return_value.options.return_value.order_by.return_value.limit.return_value.all.return_value = [mock_job]
        
        result = self.job_render_service.render_jobs_html(mock_db)
        
        # Should only contain the wrapper div, no job content
        assert result == '<div class="space-y-3"></div>'
    
    def test_render_jobs_html_with_expand(self):
        """Test rendering HTML with job expansion"""
        mock_db = Mock()
        
        # Create mock repository
        mock_repo = Mock()
        mock_repo.name = "Test Repository"
        
        # Create mock job with UUID
        mock_job = Mock(spec=Job)
        mock_job.job_uuid = "test-uuid-123"
        mock_job.id = 1
        mock_job.status = "completed"
        mock_job.job_type = "backup"
        mock_job.type = "backup"
        mock_job.started_at = datetime.now(UTC)
        mock_job.finished_at = datetime.now(UTC)
        mock_job.error = None
        mock_job.repository = mock_repo
        mock_job.tasks = []
        mock_job.completed_tasks = 0
        mock_job.total_tasks = 0
        
        mock_db.query.return_value.options.return_value.order_by.return_value.limit.return_value.all.return_value = [mock_job]
        
        result = self.job_render_service.render_jobs_html(mock_db, expand="test-uuid-123")
        
        assert '<div class="space-y-3">' in result
        assert '</div>' in result
    
    def test_render_jobs_html_error_handling(self):
        """Test error handling in render_jobs_html"""
        mock_db = Mock()
        mock_db.query.side_effect = Exception("Database error")
        
        result = self.job_render_service.render_jobs_html(mock_db)
        
        assert "Error loading jobs" in result
    
    def test_render_current_jobs_html_no_jobs(self):
        """Test rendering current jobs when none are running"""
        self.mock_job_manager.jobs = {}
        
        result = self.job_render_service.render_current_jobs_html()
        
        assert "No operations currently running" in result
    
    def test_render_current_jobs_html_with_composite_job(self):
        """Test rendering current jobs with composite job"""
        # Create mock composite job
        mock_task = Mock()
        mock_task.task_name = "Test Task"
        
        mock_job = Mock()
        mock_job.status = "running"
        mock_job.is_composite.return_value = True
        mock_job.get_current_task.return_value = mock_task
        mock_job.current_task_index = 0
        mock_job.tasks = [mock_task]
        mock_job.started_at = datetime.now(UTC)
        mock_job.job_type = "manual_backup"
        
        self.mock_job_manager.jobs = {"test-job-1": mock_job}
        
        result = self.job_render_service.render_current_jobs_html()
        
        assert "Test Task" in result
        assert "Manual Backup" in result
    
    def test_render_current_jobs_html_with_simple_job(self):
        """Test rendering current jobs with simple borg job"""
        mock_job = Mock()
        mock_job.status = "running"
        mock_job.started_at = datetime.now(UTC)
        mock_job.command = ["borg", "create", "test"]
        mock_job.current_progress = {"files": 100, "transferred": "10MB"}
        
        # Mock composite job check
        def mock_is_composite():
            return False
        
        mock_job.is_composite = mock_is_composite
        
        self.mock_job_manager.jobs = {"test-job-1": mock_job}
        
        result = self.job_render_service.render_current_jobs_html()
        
        assert "Files: 100" in result
        assert "10MB" in result
    
    def test_render_current_jobs_html_error_handling(self):
        """Test error handling in render_current_jobs_html"""
        self.mock_job_manager.jobs = {"test": "invalid"}  # Invalid job structure
        
        result = self.job_render_service.render_current_jobs_html()
        
        assert "Error loading current operations" in result
    
    def test_is_child_of_composite_job_true(self):
        """Test _is_child_of_composite_job returns True when composite job exists"""
        mock_composite_job = Mock()
        mock_composite_job.is_composite.return_value = True
        mock_composite_job.status = "running"
        
        self.mock_job_manager.jobs = {
            "composite-job": mock_composite_job,
            "simple-job": Mock()
        }
        
        result = self.job_render_service._is_child_of_composite_job("simple-job", Mock())
        
        assert result is True
    
    def test_is_child_of_composite_job_false(self):
        """Test _is_child_of_composite_job returns False when no composite job exists"""
        mock_simple_job = Mock()
        
        # Mock that doesn't have is_composite method
        self.mock_job_manager.jobs = {"simple-job": mock_simple_job}
        
        result = self.job_render_service._is_child_of_composite_job("simple-job", Mock())
        
        assert result is False
    
    def test_render_job_html_without_uuid(self):
        """Test _render_job_html skips job without UUID"""
        mock_job = Mock(spec=Job)
        mock_job.job_uuid = None
        
        result = self.job_render_service._render_job_html(mock_job)
        
        assert result == ""
    
    def test_render_job_html_completed_job(self):
        """Test _render_job_html for completed job"""
        mock_repo = Mock()
        mock_repo.name = "Test Repository"
        
        mock_job = Mock(spec=Job)
        mock_job.job_uuid = "test-uuid-123"
        mock_job.status = "completed"
        mock_job.job_type = "backup"
        mock_job.type = "backup"
        mock_job.started_at = datetime.now(UTC)
        mock_job.finished_at = datetime.now(UTC)
        mock_job.error = None
        mock_job.repository = mock_repo
        mock_job.tasks = []
        
        result = self.job_render_service._render_job_html(mock_job)
        
        assert "Test Repository" in result
        assert "✓" in result  # Completed icon
    
    def test_render_job_html_failed_job(self):
        """Test _render_job_html for failed job"""
        mock_repo = Mock()
        mock_repo.name = "Test Repository"
        
        mock_job = Mock(spec=Job)
        mock_job.job_uuid = "test-uuid-123"
        mock_job.status = "failed"
        mock_job.job_type = "backup"
        mock_job.type = "backup"
        mock_job.started_at = datetime.now(UTC)
        mock_job.finished_at = datetime.now(UTC)
        mock_job.error = "Test error"
        mock_job.repository = mock_repo
        mock_job.tasks = []
        
        result = self.job_render_service._render_job_html(mock_job)
        
        assert "Test Repository" in result
        assert "✗" in result  # Failed icon
    
    def test_render_job_html_composite_job(self):
        """Test _render_job_html for composite job with tasks"""
        mock_repo = Mock()
        mock_repo.name = "Test Repository"
        
        mock_task = Mock(spec=JobTask)
        mock_task.task_order = 0
        mock_task.task_name = "Test Task"
        mock_task.status = "completed"
        
        mock_job = Mock(spec=Job)
        mock_job.job_uuid = "test-uuid-123"
        mock_job.status = "completed"
        mock_job.job_type = "composite"
        mock_job.type = "manual_backup"
        mock_job.started_at = datetime.now(UTC)
        mock_job.finished_at = datetime.now(UTC)
        mock_job.error = None
        mock_job.repository = mock_repo
        mock_job.tasks = [mock_task]
        mock_job.completed_tasks = 1
        mock_job.total_tasks = 1
        
        result = self.job_render_service._render_job_html(mock_job)
        
        assert "Test Repository" in result
        assert "(1/1 tasks)" in result
    
    def test_get_job_for_render_not_found(self):
        """Test get_job_for_render when job doesn't exist"""
        mock_db = Mock()
        mock_db.query.return_value.options.return_value.filter.return_value.first.return_value = None
        
        self.mock_job_manager.jobs = {}
        
        result = self.job_render_service.get_job_for_render("nonexistent", mock_db)
        
        assert result is None
    
    def test_get_job_for_render_manager_job(self):
        """Test get_job_for_render for running job in manager"""
        mock_manager_job = Mock()
        mock_manager_job.status = "running"
        mock_manager_job.started_at = datetime.now(UTC)
        mock_manager_job.is_composite.return_value = True
        mock_manager_job.tasks = []
        
        self.mock_job_manager.jobs = {"test-uuid": mock_manager_job}
        
        mock_db = Mock()
        mock_db_job = Mock()
        mock_db_job.repository.name = "Test Repo"
        mock_db_job.type = "backup"
        mock_db.query.return_value.filter.return_value.first.return_value = mock_db_job
        
        result = self.job_render_service.get_job_for_render("test-uuid", mock_db)
        
        assert result is not None
        assert result["job"].id == "test-uuid"
        assert result["repository_name"] == "Test Repo"
    
    def test_get_job_for_render_database_job(self):
        """Test get_job_for_render for completed job in database"""
        mock_repo = Mock()
        mock_repo.name = "Test Repository"
        
        mock_job = Mock(spec=Job)
        mock_job.job_uuid = "test-uuid-123"
        mock_job.status = "completed"
        mock_job.job_type = "backup"
        mock_job.type = "backup"
        mock_job.started_at = datetime.now(UTC)
        mock_job.finished_at = datetime.now(UTC)
        mock_job.error = None
        mock_job.repository = mock_repo
        mock_job.tasks = []
        
        mock_db = Mock()
        mock_db.query.return_value.options.return_value.filter.return_value.first.return_value = mock_job
        
        self.mock_job_manager.jobs = {}
        
        result = self.job_render_service.get_job_for_render("test-uuid-123", mock_db)
        
        assert result is not None
        assert result["job"].id == "test-uuid-123"
        assert result["repository_name"] == "Test Repository"
    
    def test_get_job_for_render_job_without_uuid(self):
        """Test get_job_for_render skips job without UUID"""
        mock_job = Mock(spec=Job)
        mock_job.job_uuid = None  # No UUID
        
        mock_db = Mock()
        mock_db.query.return_value.options.return_value.filter.return_value.first.return_value = mock_job
        
        self.mock_job_manager.jobs = {}
        
        result = self.job_render_service.get_job_for_render("test-uuid", mock_db)
        
        assert result is None
    
    def test_format_manager_job_for_render_with_db_job(self):
        """Test _format_manager_job_for_render with corresponding database job"""
        mock_repo = Mock()
        mock_repo.name = "Test Repository"
        
        mock_db_job = Mock()
        mock_db_job.repository = mock_repo
        mock_db_job.type = "backup"
        
        mock_manager_job = Mock()
        mock_manager_job.status = "running"
        mock_manager_job.started_at = datetime.now(UTC)
        mock_manager_job.is_composite.return_value = True
        mock_manager_job.tasks = []
        
        result = self.job_render_service._format_manager_job_for_render(
            mock_manager_job, "test-uuid", mock_db_job
        )
        
        assert result is not None
        assert result["job"].id == "test-uuid"
        assert result["repository_name"] == "Test Repository"
    
    def test_format_manager_job_for_render_without_db_job(self):
        """Test _format_manager_job_for_render without database job"""
        mock_manager_job = Mock()
        mock_manager_job.status = "running"
        mock_manager_job.started_at = datetime.now(UTC)
        mock_manager_job.repository_name = "Test Repository"
        mock_manager_job.job_type = "backup"
        mock_manager_job.is_composite.return_value = False
        
        result = self.job_render_service._format_manager_job_for_render(
            mock_manager_job, "test-uuid", None
        )
        
        assert result is not None
        assert result["job"].id == "test-uuid"
        assert result["repository_name"] == "Test Repository"
    
    def test_format_manager_job_for_render_composite_with_tasks(self):
        """Test _format_manager_job_for_render with composite job with tasks"""
        # Create tasks without task_order initially
        mock_task1 = Mock(spec=['task_name', 'status', 'output_lines'])
        mock_task1.task_name = "Task 1"
        mock_task1.status = "completed"
        mock_task1.output_lines = [{"text": "Line 1"}, {"text": "Line 2"}]
        
        mock_task2 = Mock(spec=['task_name', 'status', 'output_lines'])
        mock_task2.task_name = "Task 2"
        mock_task2.status = "running"
        mock_task2.output_lines = []
        
        mock_manager_job = Mock()
        mock_manager_job.status = "running"
        mock_manager_job.started_at = datetime.now(UTC)
        mock_manager_job.repository_name = "Test Repository"
        mock_manager_job.job_type = "backup"
        mock_manager_job.is_composite.return_value = True
        mock_manager_job.tasks = [mock_task1, mock_task2]
        
        result = self.job_render_service._format_manager_job_for_render(
            mock_manager_job, "test-uuid", None
        )
        
        assert result is not None
        assert len(result["sorted_tasks"]) == 2
        # After formatting, task_order should be set
        assert hasattr(result["sorted_tasks"][0], 'task_order')
        assert hasattr(result["sorted_tasks"][1], 'task_order')
        assert result["sorted_tasks"][0].task_order == 0
        assert result["sorted_tasks"][1].task_order == 1
        assert result["sorted_tasks"][0].output == "Line 1\nLine 2"
        assert result["sorted_tasks"][1].output == ""
    
    def test_format_manager_job_for_render_error_handling(self):
        """Test error handling in _format_manager_job_for_render"""
        mock_manager_job = Mock()
        mock_manager_job.status.side_effect = Exception("Test error")
        
        result = self.job_render_service._format_manager_job_for_render(
            mock_manager_job, "test-uuid", None
        )
        
        assert result is None
    
    def test_fix_task_statuses_for_failed_job_empty_tasks(self):
        """Test _fix_task_statuses_for_failed_job with empty tasks"""
        result = self.job_render_service._fix_task_statuses_for_failed_job([])
        
        assert result == []
    
    def test_fix_task_statuses_for_failed_job_with_failed_task(self):
        """Test _fix_task_statuses_for_failed_job with explicit failed task"""
        mock_task1 = Mock()
        mock_task1.status = "completed"
        
        mock_task2 = Mock()
        mock_task2.status = "failed"
        
        mock_task3 = Mock()
        mock_task3.status = "pending"
        
        tasks = [mock_task1, mock_task2, mock_task3]
        
        result = self.job_render_service._fix_task_statuses_for_failed_job(tasks)
        
        assert result[0].status == "completed"
        assert result[1].status == "failed"
        assert result[2].status == "skipped"  # Should be marked as skipped
    
    def test_fix_task_statuses_for_failed_job_with_running_task(self):
        """Test _fix_task_statuses_for_failed_job with running task that failed"""
        mock_task1 = Mock()
        mock_task1.status = "completed"
        
        mock_task2 = Mock()
        mock_task2.status = "running"  # This should be marked as failed
        
        mock_task3 = Mock()
        mock_task3.status = "pending"
        
        tasks = [mock_task1, mock_task2, mock_task3]
        
        result = self.job_render_service._fix_task_statuses_for_failed_job(tasks)
        
        assert result[0].status == "completed"
        assert result[1].status == "failed"  # Should be marked as failed
        assert result[2].status == "skipped"  # Should be marked as skipped
    
    def test_fix_task_statuses_for_failed_job_no_explicit_failure(self):
        """Test _fix_task_statuses_for_failed_job with no explicit failed task"""
        mock_task1 = Mock()
        mock_task1.status = "completed"
        
        mock_task2 = Mock()
        mock_task2.status = "pending"  # Should be marked as failed
        
        tasks = [mock_task1, mock_task2]
        
        result = self.job_render_service._fix_task_statuses_for_failed_job(tasks)
        
        assert result[0].status == "completed"
        assert result[1].status == "failed"  # Should be marked as failed
    
    def test_global_service_instance(self):
        """Test that global service instance is created"""
        from app.services.job_render_service import job_render_service
        
        assert job_render_service is not None
        assert isinstance(job_render_service, JobRenderService)


class TestJobRenderServiceStatusStyling:
    """Test status styling functionality"""
    
    def setup_method(self):
        """Set up test fixtures"""
        with patch('app.services.job_render_service.get_job_manager') as mock_get_manager:
            mock_job_manager = Mock()
            mock_job_manager.jobs = {}
            mock_get_manager.return_value = mock_job_manager
            
            self.job_render_service = JobRenderService()
    
    def test_status_styling_completed(self):
        """Test status styling for completed jobs"""
        mock_repo = Mock()
        mock_repo.name = "Test Repository"
        
        mock_job = Mock(spec=Job)
        mock_job.job_uuid = "test-uuid"
        mock_job.status = "completed"
        mock_job.job_type = "backup"
        mock_job.type = "backup"
        mock_job.started_at = datetime.now(UTC)
        mock_job.finished_at = datetime.now(UTC)
        mock_job.error = None
        mock_job.repository = mock_repo
        mock_job.tasks = []
        
        result = self.job_render_service._render_job_html(mock_job)
        
        assert "bg-green-100" in result
        assert "✓" in result
    
    def test_status_styling_failed(self):
        """Test status styling for failed jobs"""
        mock_repo = Mock()
        mock_repo.name = "Test Repository"
        
        mock_job = Mock(spec=Job)
        mock_job.job_uuid = "test-uuid"
        mock_job.status = "failed"
        mock_job.job_type = "backup"
        mock_job.type = "backup"
        mock_job.started_at = datetime.now(UTC)
        mock_job.finished_at = datetime.now(UTC)
        mock_job.error = "Test error"
        mock_job.repository = mock_repo
        mock_job.tasks = []
        
        result = self.job_render_service._render_job_html(mock_job)
        
        assert "bg-red-100" in result
        assert "✗" in result
    
    def test_status_styling_running(self):
        """Test status styling for running jobs"""
        mock_repo = Mock()
        mock_repo.name = "Test Repository"
        
        mock_job = Mock(spec=Job)
        mock_job.job_uuid = "test-uuid"
        mock_job.status = "running"
        mock_job.job_type = "backup"
        mock_job.type = "backup"
        mock_job.started_at = datetime.now(UTC)
        mock_job.finished_at = None
        mock_job.error = None
        mock_job.repository = mock_repo
        mock_job.tasks = []
        
        result = self.job_render_service._render_job_html(mock_job)
        
        assert "bg-blue-100" in result
        assert "⟳" in result
    
    def test_status_styling_unknown(self):
        """Test status styling for unknown status"""
        mock_repo = Mock()
        mock_repo.name = "Test Repository"
        
        mock_job = Mock(spec=Job)
        mock_job.job_uuid = "test-uuid"
        mock_job.status = "unknown"
        mock_job.job_type = "backup"
        mock_job.type = "backup"
        mock_job.started_at = datetime.now(UTC)
        mock_job.finished_at = None
        mock_job.error = None
        mock_job.repository = mock_repo
        mock_job.tasks = []
        
        result = self.job_render_service._render_job_html(mock_job)
        
        assert "bg-gray-100" in result
        assert "◦" in result