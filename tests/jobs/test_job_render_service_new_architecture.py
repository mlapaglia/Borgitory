"""
Tests for JobRenderService new architecture with proper DI patterns.
Focuses on the new dataclass-based approach and catches template selection bugs.
"""

import pytest
from unittest.mock import Mock
from datetime import datetime, timezone
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from borgitory.services.jobs.job_render_service import (
    JobRenderService,
    JobDataConverter,
    JobDisplayData,
    JobStatus,
    JobStatusType,
    TaskDisplayData,
    JobProgress,
    TemplateJobData,
    TemplateJobStatus,
    convert_to_template_data,
)


class TestJobRenderServiceNewArchitecture:
    """Test JobRenderService new architecture with proper DI patterns"""

    def test_initialization_with_proper_di(self) -> None:
        """Test JobRenderService initialization with proper dependency injection"""
        mock_job_manager = Mock()
        mock_templates = Mock(spec=Jinja2Templates)
        mock_converter = Mock(spec=JobDataConverter)

        service = JobRenderService(
            job_manager=mock_job_manager,
            templates=mock_templates,
            converter=mock_converter,
        )

        assert service is not None
        assert service.job_manager == mock_job_manager
        assert service.templates == mock_templates
        assert service.converter == mock_converter

    def test_get_job_display_data_from_memory(self) -> None:
        """Test getting job display data from in-memory job manager"""
        # Create mock job manager with a running job
        mock_job_manager = Mock()
        mock_job = Mock()
        mock_job.id = "test-job-123"
        mock_job.status = "running"
        mock_job_manager.jobs = {"test-job-123": mock_job}

        # Create mock converter
        mock_converter = Mock(spec=JobDataConverter)
        expected_job_data = JobDisplayData(
            id="test-job-123",
            title="Test Job",
            status=JobStatus(JobStatusType.RUNNING, "bg-blue-100", "⟳"),
            repository_name="test-repo",
            started_at=datetime.now(timezone.utc),
            finished_at=None,
            tasks=[],
            progress=JobProgress(0, 1),
            error=None,
        )
        # The converter.convert_memory_job calls fix_failed_job_tasks, so mock that chain
        mock_converter.convert_memory_job.return_value = expected_job_data
        mock_converter.fix_failed_job_tasks.return_value = expected_job_data

        service = JobRenderService(
            job_manager=mock_job_manager,
            templates=Mock(spec=Jinja2Templates),
            converter=mock_converter,
        )

        # Mock database to return None (job not found in DB)
        mock_db = Mock(spec=Session)
        mock_db.query.return_value.options.return_value.filter.return_value.first.return_value = None

        result = service.get_job_display_data("test-job-123", mock_db)

        assert result == expected_job_data
        # The converter is called with memory_job and db_job (which is None when not found in DB)
        mock_converter.convert_memory_job.assert_called_once_with(mock_job, None)

    def test_get_job_display_data_from_database_fallback(self) -> None:
        """Test getting job display data from database when not in memory"""
        # Create mock job manager with no jobs
        mock_job_manager = Mock()
        mock_job_manager.jobs = {}

        # Create mock database job
        mock_db_job = Mock()
        mock_db_job.id = "test-job-456"
        mock_db_job.status = "completed"

        mock_db = Mock(spec=Session)
        mock_db.query.return_value.options.return_value.filter.return_value.first.return_value = mock_db_job

        # Create mock converter
        mock_converter = Mock(spec=JobDataConverter)
        expected_job_data = JobDisplayData(
            id="test-job-456",
            title="Completed Job",
            status=JobStatus(JobStatusType.COMPLETED, "bg-green-100", "✓"),
            repository_name="test-repo",
            started_at=datetime.now(timezone.utc),
            finished_at=datetime.now(timezone.utc),
            tasks=[],
            progress=JobProgress(1, 1),
            error=None,
        )
        mock_converter.convert_database_job.return_value = expected_job_data
        mock_converter.fix_failed_job_tasks.return_value = expected_job_data

        service = JobRenderService(
            job_manager=mock_job_manager,
            templates=Mock(spec=Jinja2Templates),
            converter=mock_converter,
        )

        result = service.get_job_display_data("test-job-456", mock_db)

        assert result == expected_job_data
        mock_converter.convert_database_job.assert_called_once_with(mock_db_job)

    def test_get_job_for_template_with_running_job(self) -> None:
        """Test getting job data formatted for templates"""
        # Create mock job manager with a running job
        mock_job_manager = Mock()
        mock_job = Mock()
        mock_job.id = "running-job-789"
        mock_job.status = "running"
        mock_job_manager.jobs = {"running-job-789": mock_job}

        # Create mock converter that returns JobDisplayData
        mock_converter = Mock(spec=JobDataConverter)
        job_display_data = JobDisplayData(
            id="running-job-789",
            title="Running Backup",
            status=JobStatus(JobStatusType.RUNNING, "bg-blue-100", "⟳"),
            repository_name="my-repo",
            started_at=datetime.now(timezone.utc),
            finished_at=None,
            tasks=[
                TaskDisplayData(
                    name="Backup Task",
                    type="backup",
                    status=JobStatus(JobStatusType.RUNNING, "bg-blue-100", "⟳"),
                    output="Creating backup...",
                    error=None,
                    order=0,
                    started_at=datetime.now(timezone.utc),
                    completed_at=None,
                    return_code=None,
                )
            ],
            progress=JobProgress(0, 1, "Backup Task"),
            error=None,
        )
        mock_converter.convert_memory_job.return_value = job_display_data
        mock_converter.fix_failed_job_tasks.return_value = job_display_data

        service = JobRenderService(
            job_manager=mock_job_manager,
            templates=Mock(spec=Jinja2Templates),
            converter=mock_converter,
        )

        mock_db = Mock(spec=Session)
        result = service.get_job_for_template(
            "running-job-789", mock_db, expand_details=True
        )

        assert result is not None
        assert isinstance(result, TemplateJobData)
        assert result.job.id == "running-job-789"
        assert (
            str(result.job.status) == "running"
        )  # This is key for template selection!
        assert result.expand_details is True
        assert len(result.sorted_tasks) == 1
        assert result.sorted_tasks[0].status == "running"

    def test_template_job_status_string_conversion(self) -> None:
        """Test that TemplateJobStatus converts to string properly (catches template selection bug)"""
        status = TemplateJobStatus("running")

        # This is the critical test - string conversion must work
        assert str(status) == "running"
        assert status.title() == "Running"

        # Test the comparison that was failing in the API
        assert str(status) == "running"  # This should be True
        assert status != "running"  # This should be True (object != string)

    def test_convert_to_template_data_preserves_status_strings(self) -> None:
        """Test that convert_to_template_data creates proper string statuses"""
        job_display_data = JobDisplayData(
            id="test-job",
            title="Test Job",
            status=JobStatus(JobStatusType.RUNNING, "bg-blue-100", "⟳"),
            repository_name="test-repo",
            started_at=datetime.now(timezone.utc),
            finished_at=None,
            tasks=[
                TaskDisplayData(
                    name="Test Task",
                    type="backup",
                    status=JobStatus(JobStatusType.RUNNING, "bg-blue-100", "⟳"),
                    output="Running...",
                    error=None,
                    order=0,
                    started_at=datetime.now(timezone.utc),
                    completed_at=None,
                    return_code=None,
                )
            ],
            progress=JobProgress(0, 1),
            error=None,
        )

        template_data = convert_to_template_data(job_display_data)

        # Verify job status is TemplateJobStatus (for .title() method)
        assert isinstance(template_data.job.status, TemplateJobStatus)
        assert str(template_data.job.status) == "running"

        # Verify task status is string (for template conditionals)
        assert isinstance(template_data.sorted_tasks[0].status, str)
        assert template_data.sorted_tasks[0].status == "running"

    def test_render_job_html_uses_correct_template_data(self) -> None:
        """Test that _render_job_html passes correct data to templates"""
        # Create job display data
        job_display_data = JobDisplayData(
            id="test-job",
            title="Test Job",
            status=JobStatus(JobStatusType.COMPLETED, "bg-green-100", "✓"),
            repository_name="test-repo",
            started_at=datetime.now(timezone.utc),
            finished_at=datetime.now(timezone.utc),
            tasks=[],
            progress=JobProgress(1, 1),
            error=None,
        )

        # Create mock templates
        mock_template = Mock()
        mock_template.render.return_value = "<div>rendered job</div>"
        mock_templates = Mock(spec=Jinja2Templates)
        mock_templates.get_template.return_value = mock_template

        service = JobRenderService(
            job_manager=Mock(), templates=mock_templates, converter=Mock()
        )

        service._render_job_html(job_display_data, expand_details=True)

        # Verify template was called with correct data
        mock_templates.get_template.assert_called_once_with(
            "partials/jobs/job_item.html"
        )

        # Verify render was called with TemplateJobData.__dict__
        mock_template.render.assert_called_once()
        render_args = mock_template.render.call_args[0][0]

        # Verify the render context has the expected structure
        assert "job" in render_args
        assert "job_title" in render_args
        assert "status_class" in render_args
        assert "status_icon" in render_args
        assert "expand_details" in render_args
        assert render_args["expand_details"] is True

    def test_job_data_converter_dependency_injection(self) -> None:
        """Test that JobDataConverter can be properly injected"""
        mock_job_manager = Mock()
        mock_templates = Mock(spec=Jinja2Templates)
        custom_converter = JobDataConverter()  # Use real converter

        service = JobRenderService(
            job_manager=mock_job_manager,
            templates=mock_templates,
            converter=custom_converter,
        )

        assert service.converter is custom_converter

    def test_no_import_statements_in_methods(self) -> None:
        """Test that service methods don't contain import statements (DI requirement)"""
        import inspect

        service = JobRenderService(
            job_manager=Mock(), templates=Mock(spec=Jinja2Templates), converter=Mock()
        )

        # Get all methods of the service
        methods = inspect.getmembers(service, predicate=inspect.ismethod)

        for method_name, method in methods:
            if method_name.startswith("_") or method_name in ["__init__"]:
                continue

            # Get source code of the method
            try:
                source = inspect.getsource(method)
                # Check for import statements (basic check)
                lines = source.split("\n")
                for line in lines:
                    line = line.strip()
                    if line.startswith("import ") or line.startswith("from "):
                        pytest.fail(
                            f"Method {method_name} contains import statement: {line}"
                        )
            except OSError:
                # Some methods might not have source available (built-ins, etc.)
                continue


class TestTemplateSelectionBugRegression:
    """Regression tests to catch the template selection bug we just fixed"""

    def test_template_job_status_comparison_bug(self) -> None:
        """
        Regression test for the template selection bug.

        The bug was: template_job.job.status == "running" returned False
        because TemplateJobStatus object was compared to string directly.

        This test ensures str(template_job.job.status) == "running" works.
        """
        # Create a TemplateJobStatus like the API would
        template_job_status = TemplateJobStatus("running")

        # This was the failing comparison in the API
        assert template_job_status != "running"  # Object != string (expected to fail)

        # This is the correct comparison (what we fixed)
        assert str(template_job_status) == "running"  # String conversion (should work)

        # Test all status types
        for status_value in ["running", "completed", "failed", "pending", "cancelled"]:
            template_status = TemplateJobStatus(status_value)
            assert str(template_status) == status_value
            assert template_status.title() == status_value.title()

    def test_api_template_selection_logic(self) -> None:
        """
        Test the exact logic used in the API endpoint for template selection.

        This simulates the toggle_task_details endpoint logic.
        """
        # Create a TemplateJobData with running status
        job_display_data = JobDisplayData(
            id="test-job",
            title="Test Job",
            status=JobStatus(JobStatusType.RUNNING, "bg-blue-100", "⟳"),
            repository_name="test-repo",
            started_at=datetime.now(timezone.utc),
            finished_at=None,
            tasks=[],
            progress=JobProgress(0, 1),
            error=None,
        )

        template_job = convert_to_template_data(job_display_data)

        # This is the exact logic from the API (after our fix)
        if str(template_job.job.status) == "running":
            template_name = "partials/jobs/task_item_streaming.html"
        else:
            template_name = "partials/jobs/task_item_static.html"

        # Should select the streaming template for running jobs
        assert template_name == "partials/jobs/task_item_streaming.html"

        # Test with completed job
        job_display_data.status = JobStatus(
            JobStatusType.COMPLETED, "bg-green-100", "✓"
        )
        template_job = convert_to_template_data(job_display_data)

        if str(template_job.job.status) == "running":
            template_name = "partials/jobs/task_item_streaming.html"
        else:
            template_name = "partials/jobs/task_item_static.html"

        # Should select the static template for completed jobs
        assert template_name == "partials/jobs/task_item_static.html"

    def test_template_conditional_logic(self) -> None:
        """
        Test that template conditionals work with our status strings.

        This tests the Jinja2 template logic: {% if task.status == "running" %}
        """
        # Create task display data
        task_data = TaskDisplayData(
            name="Test Task",
            type="backup",
            status=JobStatus(JobStatusType.RUNNING, "bg-blue-100", "⟳"),
            output="Running...",
            error=None,
            order=0,
            started_at=datetime.now(timezone.utc),
            completed_at=None,
            return_code=None,
        )

        job_display_data = JobDisplayData(
            id="test-job",
            title="Test Job",
            status=JobStatus(JobStatusType.RUNNING, "bg-blue-100", "⟳"),
            repository_name="test-repo",
            started_at=datetime.now(timezone.utc),
            finished_at=None,
            tasks=[task_data],
            progress=JobProgress(0, 1),
            error=None,
        )

        template_data = convert_to_template_data(job_display_data)

        # The task status should be a string for template conditionals
        task = template_data.sorted_tasks[0]
        assert isinstance(task.status, str)
        assert task.status == "running"

        # Simulate the template conditional
        if task.status == "running":
            sse_should_connect = True
        else:
            sse_should_connect = False

        assert sse_should_connect is True


class TestJobDataConverter:
    """Test the JobDataConverter class"""

    def test_converter_initialization(self) -> None:
        """Test JobDataConverter can be instantiated"""
        converter = JobDataConverter()
        assert converter is not None

    def test_converter_has_required_methods(self) -> None:
        """Test JobDataConverter has all required methods"""
        converter = JobDataConverter()

        # Check that all expected methods exist
        assert hasattr(converter, "convert_database_job")
        assert hasattr(converter, "convert_memory_job")
        assert hasattr(converter, "fix_failed_job_tasks")

        # Check they're callable
        assert callable(converter.convert_database_job)
        assert callable(converter.convert_memory_job)
        assert callable(converter.fix_failed_job_tasks)
