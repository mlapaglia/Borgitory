"""
Integration tests for JobRenderService to achieve full coverage.
These tests use real dependencies and minimal mocking to exercise actual code paths.
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import Mock
from sqlalchemy.orm import Session
from fastapi.templating import Jinja2Templates

from borgitory.services.jobs.job_render_service import (
    JobRenderService,
    JobDataConverter,
    JobDisplayData,
    JobStatus,
    JobStatusType,
    TaskDisplayData,
    JobProgress,
)
from borgitory.models.database import Job, JobTask, Repository
from borgitory.models.enums import JobType
from borgitory.services.jobs.job_manager import BorgJob, BorgJobTask


class TestJobDataConverterCoverage:
    """Test JobDataConverter methods with real data"""

    def test_convert_database_job_with_tasks(self) -> None:
        """Test convert_database_job with a complete database job"""
        # Create a real Repository object
        repository = Repository(
            name="test-repo",
            path="/test/repo",
            encrypted_passphrase="encrypted_test",
        )
        repository.id = 1

        # Create a real Job object with tasks
        db_job = Job(
            id="test-job-123",
            type=JobType.BACKUP,
            status="completed",
            started_at=datetime(2023, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
            finished_at=datetime(2023, 1, 1, 12, 30, 0, tzinfo=timezone.utc),
            completed_tasks=2,
            total_tasks=2,
            repository=repository,
            error=None,
        )

        # Add tasks
        task1 = JobTask(
            id=1,
            job_id="test-job-123",
            task_name="Backup Files",
            task_type="backup",
            task_order=0,
            status="completed",
            started_at=datetime(2023, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
            completed_at=datetime(2023, 1, 1, 12, 15, 0, tzinfo=timezone.utc),
            output="Files backed up successfully",
            return_code=0,
        )

        task2 = JobTask(
            id=2,
            job_id="test-job-123",
            task_name="Sync to Cloud",
            task_type="cloud_sync",
            task_order=1,
            status="completed",
            started_at=datetime(2023, 1, 1, 12, 15, 0, tzinfo=timezone.utc),
            completed_at=datetime(2023, 1, 1, 12, 30, 0, tzinfo=timezone.utc),
            output="Sync completed",
            return_code=0,
        )

        db_job.tasks = [task1, task2]

        # Convert using the real converter
        converter = JobDataConverter()
        result = converter.convert_database_job(db_job)

        # Verify the conversion
        assert result.id == "test-job-123"
        assert result.title == "Backup - test-repo (2/2 tasks)"
        assert result.status.type == JobStatusType.COMPLETED
        assert result.repository_name == "test-repo"
        assert len(result.tasks) == 2
        assert result.progress.completed_tasks == 2
        assert result.progress.total_tasks == 2

        # Verify task conversion
        assert result.tasks[0].name == "Backup Files"
        assert result.tasks[0].type == "backup"
        assert result.tasks[0].status.type == JobStatusType.COMPLETED
        assert result.tasks[0].output == "Files backed up successfully"
        assert result.tasks[0].order == 0

        assert result.tasks[1].name == "Sync to Cloud"
        assert result.tasks[1].type == "cloud_sync"
        assert result.tasks[1].status.type == JobStatusType.COMPLETED

    def test_convert_database_job_no_tasks(self) -> None:
        """Test convert_database_job with no tasks"""
        repository = Repository(
            name="empty-repo",
            path="/empty/repo",
            encrypted_passphrase="encrypted_test",
        )
        repository.id = 1

        db_job = Job(
            id="empty-job",
            type=JobType.PRUNE,
            status="pending",
            started_at=datetime.now(timezone.utc),
            repository=repository,
            tasks=[],  # No tasks
        )

        converter = JobDataConverter()
        result = converter.convert_database_job(db_job)

        assert result.id == "empty-job"
        assert result.title == "Prune - empty-repo"
        assert result.status.type == JobStatusType.PENDING
        assert len(result.tasks) == 0
        assert result.progress.total_tasks == 0

    def test_convert_memory_job_with_tasks(self) -> None:
        """Test convert_memory_job with running tasks"""
        # Create a mock repository for the db_job
        repository = Repository(
            name="memory-repo",
            path="/memory/repo",
            encrypted_passphrase="encrypted_test",
        )
        repository.id = 1

        db_job = Job(
            id="memory-job",
            type=JobType.BACKUP,
            status="running",
            repository=repository,
        )

        # Create BorgJobTask objects
        task1 = BorgJobTask(
            task_name="Running Backup",
            task_type="backup",
            status="running",
            output_lines=["Starting backup...", "Processing files..."],
        )
        task1.started_at = datetime.now(timezone.utc)

        task2 = BorgJobTask(
            task_name="Pending Sync",
            task_type="cloud_sync",
            status="pending",
            output_lines=[],
        )

        # Create BorgJob
        memory_job = BorgJob(
            id="memory-job",
            started_at=datetime.now(timezone.utc),
            job_type="backup",
            status="running",
            tasks=[task1, task2],
        )
        memory_job.current_task_index = 0

        # Mock get_current_task method
        def mock_get_current_task():
            return task1

        memory_job.get_current_task = mock_get_current_task

        converter = JobDataConverter()
        result = converter.convert_memory_job(memory_job, db_job)

        assert result.id == "memory-job"
        assert result.title.startswith("Backup - memory-repo")
        assert result.status.type == JobStatusType.RUNNING
        assert len(result.tasks) == 2
        assert result.progress.current_task_name == "Running Backup"

        # Verify task conversion
        assert result.tasks[0].name == "Running Backup"
        assert result.tasks[0].status.type == JobStatusType.RUNNING
        assert result.tasks[0].output == "Starting backup...\nProcessing files..."

        assert result.tasks[1].name == "Pending Sync"
        assert result.tasks[1].status.type == JobStatusType.PENDING

    def test_fix_failed_job_tasks_with_failed_job(self) -> None:
        """Test fix_failed_job_tasks with a failed job scenario"""
        # Create job data with mixed task statuses
        failed_task = TaskDisplayData(
            name="Failed Task",
            type="backup",
            status=JobStatus.from_status_string("failed"),
            output="Error occurred",
            error="Backup failed",
            order=1,
            started_at=datetime.now(timezone.utc),
            completed_at=None,
            return_code=1,
        )

        pending_task = TaskDisplayData(
            name="Pending Task",
            type="cloud_sync",
            status=JobStatus.from_status_string("pending"),
            output="",
            error=None,
            order=2,
            started_at=None,
            completed_at=None,
            return_code=None,
        )

        running_task = TaskDisplayData(
            name="Running Task",
            type="notification",
            status=JobStatus.from_status_string("running"),
            output="Sending...",
            error=None,
            order=3,
            started_at=datetime.now(timezone.utc),
            completed_at=None,
            return_code=None,
        )

        job_data = JobDisplayData(
            id="failed-job",
            title="Failed Job",
            status=JobStatus.from_status_string("failed"),
            repository_name="test-repo",
            started_at=datetime.now(timezone.utc),
            finished_at=None,
            tasks=[failed_task, pending_task, running_task],
            progress=JobProgress(0, 3),
            error="Job failed",
        )

        converter = JobDataConverter()
        result = converter.fix_failed_job_tasks(job_data)

        # Verify failed task remains failed
        assert result.tasks[0].status.type == JobStatusType.FAILED

        # Verify subsequent tasks are marked as skipped
        assert (
            result.tasks[1].status.type == JobStatusType.CANCELLED
        )  # Should be skipped
        assert (
            result.tasks[2].status.type == JobStatusType.CANCELLED
        )  # Should be skipped

    def test_fix_failed_job_tasks_with_running_task_in_failed_job(self) -> None:
        """Test fix_failed_job_tasks converts running task to failed in failed job"""
        running_task = TaskDisplayData(
            name="Running Task",
            type="backup",
            status=JobStatus.from_status_string("running"),
            output="In progress...",
            error=None,
            order=0,
            started_at=datetime.now(timezone.utc),
            completed_at=None,
            return_code=None,
        )

        pending_task = TaskDisplayData(
            name="Pending Task",
            type="cloud_sync",
            status=JobStatus.from_status_string("pending"),
            output="",
            error=None,
            order=1,
            started_at=None,
            completed_at=None,
            return_code=None,
        )

        job_data = JobDisplayData(
            id="failed-job-2",
            title="Failed Job 2",
            status=JobStatus.from_status_string("failed"),
            repository_name="test-repo",
            started_at=datetime.now(timezone.utc),
            finished_at=None,
            tasks=[running_task, pending_task],
            progress=JobProgress(0, 2),
            error="Job failed during execution",
        )

        converter = JobDataConverter()
        result = converter.fix_failed_job_tasks(job_data)

        # Verify running task is converted to failed
        assert result.tasks[0].status.type == JobStatusType.FAILED

        # Verify subsequent task is skipped
        assert (
            result.tasks[1].status.type == JobStatusType.CANCELLED
        )  # Should be skipped

    def test_fix_failed_job_tasks_with_completed_job(self) -> None:
        """Test fix_failed_job_tasks doesn't modify completed jobs"""
        task = TaskDisplayData(
            name="Completed Task",
            type="backup",
            status=JobStatus.from_status_string("completed"),
            output="Success",
            error=None,
            order=0,
            started_at=datetime.now(timezone.utc),
            completed_at=datetime.now(timezone.utc),
            return_code=0,
        )

        job_data = JobDisplayData(
            id="completed-job",
            title="Completed Job",
            status=JobStatus.from_status_string("completed"),
            repository_name="test-repo",
            started_at=datetime.now(timezone.utc),
            finished_at=datetime.now(timezone.utc),
            tasks=[task],
            progress=JobProgress(1, 1),
            error=None,
        )

        converter = JobDataConverter()
        result = converter.fix_failed_job_tasks(job_data)

        # Should be unchanged
        assert result.tasks[0].status.type == JobStatusType.COMPLETED
        assert result is job_data  # Should return the same object


class TestJobRenderServiceCoverage:
    """Test JobRenderService methods with real dependencies"""

    @pytest.fixture
    def mock_templates(self) -> Mock:
        """Create a mock Jinja2Templates that returns predictable HTML"""
        templates = Mock(spec=Jinja2Templates)

        # Mock get_template to return a mock template
        mock_template = Mock()
        mock_template.render.return_value = "<div>Mocked HTML</div>"
        templates.get_template.return_value = mock_template

        return templates

    @pytest.fixture
    def mock_job_manager(self) -> Mock:
        """Create a mock job manager with some jobs"""
        job_manager = Mock()
        job_manager.jobs = {}

        # Mock stream_all_job_updates as async generator
        async def mock_stream():
            yield {"type": "job_status_changed", "job_id": "test"}

        job_manager.stream_all_job_updates = mock_stream
        return job_manager

    @pytest.fixture
    def mock_db_session(self) -> Mock:
        """Create a mock database session"""
        session = Mock(spec=Session)
        return session

    def test_render_jobs_html_with_jobs(
        self, mock_templates: Mock, mock_job_manager: Mock, mock_db_session: Mock
    ) -> None:
        """Test render_jobs_html with database jobs"""
        # Setup mock database query
        repository = Repository(
            name="test-repo", path="/test", encrypted_passphrase="encrypted_test"
        )
        repository.id = 1

        db_job = Job(
            id="db-job-1",
            type=JobType.BACKUP,
            status="completed",
            started_at=datetime.now(timezone.utc),
            finished_at=datetime.now(timezone.utc),
            repository=repository,
            tasks=[],
        )

        # Mock the query chain
        mock_query = Mock()
        mock_query.options.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.all.return_value = [db_job]

        mock_db_session.query.return_value = mock_query

        # Create service and test
        service = JobRenderService(
            job_manager=mock_job_manager,
            templates=mock_templates,
        )

        result = service.render_jobs_html(mock_db_session, expand="")

        # Verify database was queried
        mock_db_session.query.assert_called_once_with(Job)

        # Verify HTML was generated
        assert isinstance(result, str)
        assert len(result) > 0

    def test_render_jobs_html_empty_state(
        self, mock_templates: Mock, mock_job_manager: Mock, mock_db_session: Mock
    ) -> None:
        """Test render_jobs_html with no jobs returns empty state"""
        # Mock empty query result
        mock_query = Mock()
        mock_query.options.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.all.return_value = []

        mock_db_session.query.return_value = mock_query

        service = JobRenderService(
            job_manager=mock_job_manager,
            templates=mock_templates,
        )

        service.render_jobs_html(mock_db_session)

        # Verify empty state template was used
        mock_templates.get_template.assert_called_with("partials/jobs/empty_state.html")

    def test_render_jobs_html_error_handling(
        self, mock_templates: Mock, mock_job_manager: Mock, mock_db_session: Mock
    ) -> None:
        """Test render_jobs_html error handling"""
        # Make database query raise an exception
        mock_db_session.query.side_effect = Exception("Database error")

        service = JobRenderService(
            job_manager=mock_job_manager,
            templates=mock_templates,
        )

        service.render_jobs_html(mock_db_session)

        # Verify error template was used
        mock_templates.get_template.assert_called_with("partials/jobs/error_state.html")

    def test_render_current_jobs_html_with_running_jobs(
        self, mock_templates: Mock, mock_job_manager: Mock
    ) -> None:
        """Test render_current_jobs_html with running jobs"""
        # Create a running job in the job manager
        running_job = BorgJob(
            id="running-job-1",
            started_at=datetime.now(timezone.utc),
            job_type="backup",
            status="running",
            tasks=[],
        )

        mock_job_manager.jobs = {"running-job-1": running_job}

        service = JobRenderService(
            job_manager=mock_job_manager,
            templates=mock_templates,
        )

        service.render_current_jobs_html()

        # Verify template was called with current jobs
        mock_templates.get_template.assert_called_with(
            "partials/jobs/current_jobs_list.html"
        )

        # Verify render was called with job data
        call_args = mock_templates.get_template.return_value.render.call_args
        assert call_args is not None
        render_kwargs = call_args[1] if call_args[1] else call_args[0]
        assert "current_jobs" in render_kwargs

    def test_render_current_jobs_html_no_running_jobs(
        self, mock_templates: Mock, mock_job_manager: Mock
    ) -> None:
        """Test render_current_jobs_html with no running jobs"""
        # Job manager has no jobs
        mock_job_manager.jobs = {}

        service = JobRenderService(
            job_manager=mock_job_manager,
            templates=mock_templates,
        )

        service.render_current_jobs_html()

        # Verify template was still called
        mock_templates.get_template.assert_called_with(
            "partials/jobs/current_jobs_list.html"
        )

    def test_render_current_jobs_html_error_handling(
        self, mock_templates: Mock, mock_job_manager: Mock
    ) -> None:
        """Test render_current_jobs_html error handling"""
        # Make job manager raise an exception
        mock_job_manager.jobs = Mock()
        mock_job_manager.jobs.items.side_effect = Exception("Job manager error")

        service = JobRenderService(
            job_manager=mock_job_manager,
            templates=mock_templates,
        )

        service.render_current_jobs_html()

        # Verify error template was used
        mock_templates.get_template.assert_called_with("partials/jobs/error_state.html")

    @pytest.mark.asyncio
    async def test_stream_current_jobs_html(
        self, mock_templates: Mock, mock_job_manager: Mock
    ) -> None:
        """Test stream_current_jobs_html async generator"""
        # Setup job manager with no jobs initially
        mock_job_manager.jobs = {}

        # Create async generator that yields one event then stops
        async def mock_stream():
            yield {"type": "job_status_changed", "job_id": "test"}

        mock_job_manager.stream_all_job_updates = mock_stream

        service = JobRenderService(
            job_manager=mock_job_manager,
            templates=mock_templates,
        )

        # Collect results from async generator
        results = []
        async for html_chunk in service.stream_current_jobs_html():
            results.append(html_chunk)
            # Break after first few chunks to avoid infinite loop
            if len(results) >= 2:
                break

        # Verify we got initial HTML and at least one update
        assert len(results) >= 1
        assert all("data:" in chunk for chunk in results)

    @pytest.mark.asyncio
    async def test_stream_current_jobs_html_error_handling(
        self, mock_templates: Mock, mock_job_manager: Mock
    ) -> None:
        """Test stream_current_jobs_html error handling"""

        # Make job manager stream raise an exception
        async def mock_stream_error():
            raise Exception("Stream error")

        mock_job_manager.stream_all_job_updates = mock_stream_error

        service = JobRenderService(
            job_manager=mock_job_manager,
            templates=mock_templates,
        )

        # The generator should handle the error gracefully
        results = []
        try:
            async for html_chunk in service.stream_current_jobs_html():
                results.append(html_chunk)
                break  # Just get the first chunk
        except Exception:
            # Should not raise an exception
            pytest.fail("stream_current_jobs_html should handle errors gracefully")

        # Should still get initial HTML even if streaming fails
        assert len(results) >= 1
