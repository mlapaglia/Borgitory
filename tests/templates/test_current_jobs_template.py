"""
Tests for current jobs list template to ensure proper rendering without spinner.

This test module verifies that the current jobs template renders correctly
and does not include the spinner animation.
"""

import pytest
from jinja2 import Environment, FileSystemLoader
from pathlib import Path


class TestCurrentJobsTemplate:
    """Test the current jobs list template rendering"""

    @pytest.fixture
    def jinja_env(self) -> Environment:
        """Create Jinja2 environment with template directory"""
        template_dir = (
            Path(__file__).parent.parent.parent / "src" / "borgitory" / "templates"
        )
        return Environment(loader=FileSystemLoader(str(template_dir)))

    @pytest.fixture
    def sample_job_data(self) -> list[dict]:
        """Sample job data for template testing"""
        return [
            {
                "id": "test-job-123",
                "type": "Backup",
                "status": "running",
                "started_at": "10:30:45",
                "progress_info": "Task 1/3",
            },
            {
                "id": "test-job-456",
                "type": "Cleanup",
                "status": "running",
                "started_at": "10:32:12",
                "progress_info": "Pruning archives",
            },
        ]

    def test_current_jobs_template_renders_without_spinner(
        self, jinja_env: Environment, sample_job_data: list[dict]
    ) -> None:
        """Test that current jobs template renders without spinner animation"""
        template = jinja_env.get_template("partials/jobs/current_jobs_list.html")

        rendered = template.render(
            current_jobs=sample_job_data,
            message="No operations currently running.",
            padding="4",
        )

        # Verify spinner classes are NOT present
        assert "animate-spin" not in rendered, (
            "Template should not contain spinner animation class"
        )
        assert "rounded-full h-4 w-4 border-b-2" not in rendered, (
            "Template should not contain spinner styling"
        )

        # Verify job data is rendered
        assert "test-job-123" in rendered, "Should render first job ID"
        assert "test-job-456" in rendered, "Should render second job ID"
        assert "Backup" in rendered, "Should render job types"
        assert "Cleanup" in rendered, "Should render job types"
        assert "10:30:45" in rendered, "Should render start times"
        assert "Task 1/3" in rendered, "Should render progress info"

    def test_current_jobs_template_with_no_jobs(self, jinja_env: Environment) -> None:
        """Test that template shows empty state when no jobs"""
        template = jinja_env.get_template("partials/jobs/current_jobs_list.html")

        rendered = template.render(
            current_jobs=[], message="No operations currently running.", padding="4"
        )

        # Should include empty state
        assert "No operations currently running." in rendered, (
            "Should show empty state message"
        )

        # Should not contain spinner
        assert "animate-spin" not in rendered, "Empty state should not contain spinner"

    def test_current_jobs_template_structure(
        self, jinja_env: Environment, sample_job_data: list[dict]
    ) -> None:
        """Test the overall structure of the rendered template"""
        template = jinja_env.get_template("partials/jobs/current_jobs_list.html")

        rendered = template.render(
            current_jobs=sample_job_data,
            message="No operations currently running.",
            padding="4",
        )

        # Verify expected HTML structure
        assert "space-y-3" in rendered, "Should have spacing between jobs"
        assert "border-blue-200" in rendered, "Should have blue border styling"
        assert "bg-blue-50" in rendered, "Should have blue background"
        assert "flex items-center" in rendered, "Should use flexbox layout"
        assert "flex-1" in rendered, "Should have flexible layout"

        # Verify job information is displayed
        assert "font-medium text-blue-900" in rendered, "Should style job type"
        assert "text-blue-700 text-sm" in rendered, "Should style job ID"
        assert "text-xs text-blue-600" in rendered, "Should style job details"

    def test_current_jobs_template_handles_missing_progress_info(
        self, jinja_env: Environment
    ) -> None:
        """Test template handles jobs without progress info"""
        job_data = [
            {
                "id": "test-job-789",
                "type": "Check",
                "status": "running",
                "started_at": "11:00:00",
                "progress_info": None,  # No progress info
            }
        ]

        template = jinja_env.get_template("partials/jobs/current_jobs_list.html")

        rendered = template.render(
            current_jobs=job_data,
            message="No operations currently running.",
            padding="4",
        )

        # Should render without error
        assert "test-job-789" in rendered, "Should render job ID"
        assert "Check" in rendered, "Should render job type"
        assert "11:00:00" in rendered, "Should render start time"

        # Should not contain spinner
        assert "animate-spin" not in rendered, "Should not contain spinner"

    def test_empty_state_template_inclusion(self, jinja_env: Environment) -> None:
        """Test that empty state template is properly included"""
        # First verify the empty state template exists and renders
        empty_template = jinja_env.get_template("partials/jobs/empty_state.html")
        empty_rendered = empty_template.render(
            message="No operations currently running.", padding="4"
        )

        assert "No operations currently running." in empty_rendered
        assert "text-gray-500" in empty_rendered
        assert "text-center" in empty_rendered
        assert "py-4" in empty_rendered  # padding should be applied

        # Now test that main template includes it properly
        main_template = jinja_env.get_template("partials/jobs/current_jobs_list.html")
        main_rendered = main_template.render(
            current_jobs=[], message="No operations currently running.", padding="4"
        )

        # Should contain the empty state content
        assert "No operations currently running." in main_rendered
        assert "text-gray-500" in main_rendered
