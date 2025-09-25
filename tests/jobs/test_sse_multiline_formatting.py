"""
Tests for Server-Sent Events multi-line HTML formatting in JobRenderService.

This test module specifically covers the SSE formatting fix to prevent regression
of the blank message issue where multi-line HTML was breaking SSE format.
"""

import pytest
from unittest.mock import Mock
from borgitory.services.jobs.job_render_service import JobRenderService
from borgitory.services.jobs.job_manager import BorgJob

from borgitory.utils.datetime_utils import now_utc


class TestSSEMultilineFormatting:
    """Test proper SSE formatting of multi-line HTML content"""

    @pytest.fixture
    def mock_templates(self) -> Mock:
        """Mock templates that return multi-line HTML"""
        mock = Mock()

        # Mock template that returns multi-line HTML (like the real template does)
        mock_template = Mock()
        mock_template.render.return_value = """<div class="space-y-3">
    <div class="border border-blue-200 rounded-lg p-3 bg-blue-50">
        <div class="flex items-center">
            <div class="flex-1">
                <div class="flex items-center space-x-2">
                    <span class="font-medium text-blue-900">Backup</span>
                    <span class="text-blue-700 text-sm">#test-job-123</span>
                </div>
                <div class="text-xs text-blue-600 mt-1">
                    Started: 10:30:45 | Task 1/3
                </div>
            </div>
        </div>
    </div>
</div>"""

        mock.get_template.return_value = mock_template
        return mock

    @pytest.fixture
    def mock_job_manager_with_running_job(self) -> Mock:
        """Mock job manager with a running job"""
        mock = Mock()

        # Create a mock running job
        running_job = Mock(spec=BorgJob)
        running_job.id = "test-job-123"
        running_job.status = "running"
        running_job.started_at = now_utc()
        running_job.tasks = []

        mock.jobs = {"test-job-123": running_job}

        # Mock the stream method
        async def mock_stream():
            yield {"type": "job_status_changed", "job_id": "test-job-123"}

        mock.stream_all_job_updates = mock_stream
        return mock

    @pytest.mark.asyncio
    async def test_sse_multiline_html_formatting(
        self, mock_templates: Mock, mock_job_manager_with_running_job: Mock
    ) -> None:
        """Test that multi-line HTML is properly formatted for SSE"""
        service = JobRenderService(
            job_manager=mock_job_manager_with_running_job,
            templates=mock_templates,
        )

        # Collect SSE chunks from just the initial render
        sse_chunks = []
        initial_chunks_collected = False

        async for chunk in service.stream_current_jobs_html():
            sse_chunks.append(chunk)

            # Stop after we get the initial HTML terminator
            if chunk == "data: \n\n" and not initial_chunks_collected:
                initial_chunks_collected = True
                break

            # Safety break to avoid infinite loop
            if len(sse_chunks) >= 20:
                break

        # Verify we got multiple SSE data lines (not just one)
        assert len(sse_chunks) > 1, (
            "Should have multiple SSE chunks for multi-line HTML"
        )

        # Verify each chunk (except the last) starts with "data: " and ends with "\n"
        for i, chunk in enumerate(sse_chunks[:-1]):
            assert chunk.startswith("data: "), (
                f"Chunk {i} should start with 'data: ': {chunk!r}"
            )
            assert chunk.endswith("\n"), f"Chunk {i} should end with newline: {chunk!r}"

        # Verify the last chunk is the SSE message terminator
        assert sse_chunks[-1] == "data: \n\n", (
            f"Last chunk should be SSE terminator: {sse_chunks[-1]!r}"
        )

    @pytest.mark.asyncio
    async def test_sse_no_unescaped_newlines_in_data(
        self, mock_templates: Mock, mock_job_manager_with_running_job: Mock
    ) -> None:
        """Test that no SSE data line contains unescaped newlines"""
        service = JobRenderService(
            job_manager=mock_job_manager_with_running_job,
            templates=mock_templates,
        )

        # Collect SSE chunks
        sse_chunks = []
        async for chunk in service.stream_current_jobs_html():
            sse_chunks.append(chunk)
            if len(sse_chunks) >= 10:
                break

        # Check that no data line contains unescaped newlines
        for i, chunk in enumerate(sse_chunks):
            if chunk.startswith("data: ") and not chunk == "data: \n\n":
                # Extract the data part (everything after "data: ")
                data_part = chunk[6:]  # Remove "data: " prefix

                # The data part should not contain newlines except the trailing one
                if data_part.endswith("\n"):
                    data_content = data_part[:-1]  # Remove trailing newline
                else:
                    data_content = data_part

                assert "\n" not in data_content, (
                    f"SSE data content should not contain unescaped newlines. "
                    f"Chunk {i}: {chunk!r}"
                )
                assert "\r" not in data_content, (
                    f"SSE data content should not contain carriage returns. "
                    f"Chunk {i}: {chunk!r}"
                )

    @pytest.mark.asyncio
    async def test_sse_error_html_formatting(
        self, mock_job_manager_with_running_job: Mock
    ) -> None:
        """Test that error HTML is also properly formatted for SSE"""
        # Create mock templates that raise exception for current_jobs_list but work for error_state
        mock_templates = Mock()

        def mock_get_template(template_name):
            mock_template = Mock()
            if template_name == "partials/jobs/current_jobs_list.html":
                mock_template.render.side_effect = Exception("Template error")
            else:  # error_state.html
                mock_template.render.return_value = """<div class="text-red-500">
    <p>Error loading current operations: Template error</p>
</div>"""
            return mock_template

        mock_templates.get_template.side_effect = mock_get_template

        service = JobRenderService(
            job_manager=mock_job_manager_with_running_job,
            templates=mock_templates,
        )

        # Collect SSE chunks - should get error HTML
        sse_chunks = []
        initial_chunks_collected = False

        async for chunk in service.stream_current_jobs_html():
            sse_chunks.append(chunk)

            # Stop after we get the initial HTML terminator
            if chunk == "data: \n\n" and not initial_chunks_collected:
                initial_chunks_collected = True
                break

            # Safety break
            if len(sse_chunks) >= 10:
                break

        # Should still get properly formatted SSE chunks
        assert len(sse_chunks) > 0, "Should get error HTML chunks"

        # Verify SSE formatting even for error content
        for i, chunk in enumerate(sse_chunks[:-1]):
            assert chunk.startswith("data: "), (
                f"Error chunk {i} should start with 'data: ': {chunk!r}"
            )
            assert chunk.endswith("\n"), (
                f"Error chunk {i} should end with newline: {chunk!r}"
            )

        # Verify the last chunk is the SSE message terminator
        assert sse_chunks[-1] == "data: \n\n", (
            f"Last chunk should be SSE terminator: {sse_chunks[-1]!r}"
        )

    def test_render_current_jobs_html_multiline_output(
        self, mock_templates: Mock, mock_job_manager_with_running_job: Mock
    ) -> None:
        """Test that render_current_jobs_html produces multi-line HTML"""
        service = JobRenderService(
            job_manager=mock_job_manager_with_running_job,
            templates=mock_templates,
        )

        html_output = service.render_current_jobs_html()

        # Verify the HTML output contains multiple lines
        lines = html_output.splitlines()
        assert len(lines) > 1, "HTML output should contain multiple lines"

        # Verify it contains expected HTML structure
        html_content = "\n".join(lines)
        assert "<div" in html_content, "Should contain div elements"
        assert "space-y-3" in html_content, "Should contain expected CSS classes"

    @pytest.mark.asyncio
    async def test_sse_streaming_updates_formatting(
        self, mock_templates: Mock, mock_job_manager_with_running_job: Mock
    ) -> None:
        """Test that streaming updates also use proper SSE formatting"""
        service = JobRenderService(
            job_manager=mock_job_manager_with_running_job,
            templates=mock_templates,
        )

        # Collect chunks from both initial and update
        all_chunks = []
        terminators_seen = 0

        async for chunk in service.stream_current_jobs_html():
            all_chunks.append(chunk)

            # Count SSE message terminators
            if chunk == "data: \n\n":
                terminators_seen += 1

            # Stop after we get initial HTML + one update (2 terminators)
            if terminators_seen >= 2:
                break

            # Safety break to avoid infinite loop
            if len(all_chunks) >= 30:
                break

        # Should have chunks from both initial render and update
        assert len(all_chunks) >= 10, (
            "Should have chunks from initial and update renders"
        )

        # All chunks should follow SSE format
        for i, chunk in enumerate(all_chunks):
            if chunk != "data: \n\n":  # Skip terminator chunks
                assert chunk.startswith("data: "), (
                    f"Chunk {i} should start with 'data: ': {chunk!r}"
                )
                assert chunk.endswith("\n"), (
                    f"Chunk {i} should end with newline: {chunk!r}"
                )
