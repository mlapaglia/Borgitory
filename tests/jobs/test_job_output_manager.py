"""
Tests for JobOutputManager - job output collection, storage, and streaming
"""

import pytest
from datetime import timedelta

from borgitory.services.jobs.job_output_manager import JobOutputManager
from borgitory.utils.datetime_utils import now_utc


class TestJobOutputManager:
    """Test JobOutputManager functionality"""

    def setup_method(self) -> None:
        """Set up test fixtures"""
        self.output_manager = JobOutputManager(max_lines_per_job=10)

    def test_create_job_output(self) -> None:
        """Test creating job output container"""
        job_id = "test-job-123"

        job_output = self.output_manager.create_job_output(job_id)

        assert job_output.job_id == job_id
        assert job_output.max_lines == 10
        assert len(job_output.lines) == 0
        assert job_output.total_lines == 0
        assert job_id in self.output_manager._job_outputs

    @pytest.mark.asyncio
    async def test_add_output_line(self) -> None:
        """Test adding output lines to a job"""
        job_id = "test-job-123"
        self.output_manager.create_job_output(job_id)

        await self.output_manager.add_output_line(
            job_id, "Test output line", "stdout", {"key": "value"}
        )

        job_output = self.output_manager.get_job_output(job_id)
        assert job_output.total_lines == 1
        assert len(job_output.lines) == 1

        line = list(job_output.lines)[0]
        assert line["text"] == "Test output line"
        assert line["type"] == "stdout"
        assert line["metadata"]["key"] == "value"

    @pytest.mark.asyncio
    async def test_add_output_line_auto_create(self) -> None:
        """Test adding output line automatically creates job output"""
        job_id = "test-job-456"

        await self.output_manager.add_output_line(job_id, "Auto created")

        job_output = self.output_manager.get_job_output(job_id)
        assert job_output is not None
        assert job_output.total_lines == 1

    @pytest.mark.asyncio
    async def test_add_output_line_with_progress(self) -> None:
        """Test adding output line with progress information"""
        job_id = "test-job-789"
        progress_info = {"bytes_processed": 1000, "percentage": 50}

        await self.output_manager.add_output_line(
            job_id, "Processing...", progress_info=progress_info
        )

        job_output = self.output_manager.get_job_output(job_id)
        assert job_output.current_progress["bytes_processed"] == 1000
        assert job_output.current_progress["percentage"] == 50

    @pytest.mark.asyncio
    async def test_max_lines_limit(self) -> None:
        """Test that output lines respect max limit"""
        job_id = "test-job-limit"
        self.output_manager.create_job_output(job_id)

        # Add more lines than the limit
        for i in range(15):
            await self.output_manager.add_output_line(job_id, f"Line {i}")

        job_output = self.output_manager.get_job_output(job_id)
        assert job_output.total_lines == 15  # Total count is accurate
        assert len(job_output.lines) == 10  # But only keeps max_lines

        # Should keep the most recent lines
        lines = list(job_output.lines)
        assert lines[0]["text"] == "Line 5"  # First kept line
        assert lines[-1]["text"] == "Line 14"  # Last line

    @pytest.mark.asyncio
    async def test_get_job_output_stream(self) -> None:
        """Test getting formatted job output stream"""
        job_id = "test-job-stream"

        await self.output_manager.add_output_line(job_id, "Line 1")
        await self.output_manager.add_output_line(job_id, "Line 2")

        output_stream = await self.output_manager.get_job_output_stream(job_id)

        assert len(output_stream["lines"]) == 2
        assert output_stream["total_lines"] == 2
        assert "progress" in output_stream
        assert output_stream["lines"][0]["text"] == "Line 1"
        assert output_stream["lines"][1]["text"] == "Line 2"

    @pytest.mark.asyncio
    async def test_get_job_output_stream_nonexistent(self) -> None:
        """Test getting output stream for nonexistent job"""
        output_stream = await self.output_manager.get_job_output_stream("nonexistent")

        assert output_stream["lines"] == []
        assert output_stream["total_lines"] == 0
        assert output_stream["progress"] == {}

    @pytest.mark.asyncio
    async def test_stream_job_output(self) -> None:
        """Test streaming job output"""
        job_id = "test-job-streaming"
        self.output_manager.create_job_output(job_id)

        # Add initial lines
        await self.output_manager.add_output_line(job_id, "Initial line")

        # Start streaming (non-following for test)
        stream_generator = self.output_manager.stream_job_output(job_id, follow=False)

        outputs = []
        async for output in stream_generator:
            outputs.append(output)
            break  # Just get the first output

        assert len(outputs) == 1
        assert outputs[0]["type"] == "output"
        assert outputs[0]["data"]["text"] == "Initial line"

    def test_get_output_summary(self) -> None:
        """Test getting output summary"""
        job_id = "test-job-summary"
        job_output = self.output_manager.create_job_output(job_id)
        job_output.total_lines = 5
        job_output.current_progress = {"status": "running"}

        summary = self.output_manager.get_output_summary(job_id)

        assert summary["job_id"] == job_id
        assert summary["total_lines"] == 5
        assert summary["stored_lines"] == 0  # No lines added yet
        assert summary["current_progress"]["status"] == "running"
        assert summary["max_lines"] == 10

    def test_get_output_summary_nonexistent(self) -> None:
        """Test getting summary for nonexistent job"""
        summary = self.output_manager.get_output_summary("nonexistent")

        assert summary == {}

    def test_clear_job_output(self) -> None:
        """Test clearing job output"""
        job_id = "test-job-clear"
        self.output_manager.create_job_output(job_id)

        result = self.output_manager.clear_job_output(job_id)

        assert result is True
        assert job_id not in self.output_manager._job_outputs
        assert job_id not in self.output_manager._output_locks

    def test_get_all_job_outputs(self) -> None:
        """Test getting all job output summaries"""
        self.output_manager.create_job_output("job1")
        self.output_manager.create_job_output("job2")

        all_outputs = self.output_manager.get_all_job_outputs()

        assert len(all_outputs) == 2
        assert "job1" in all_outputs
        assert "job2" in all_outputs
        assert all_outputs["job1"]["job_id"] == "job1"
        assert all_outputs["job2"]["job_id"] == "job2"

    @pytest.mark.asyncio
    async def test_format_output_for_display(self) -> None:
        """Test formatting output for display"""
        job_id = "test-job-display"

        await self.output_manager.add_output_line(job_id, "Line 1", "stdout")
        await self.output_manager.add_output_line(job_id, "Error line", "stderr")
        await self.output_manager.add_output_line(job_id, "Line 3", "stdout")

        # Get all lines
        all_lines = await self.output_manager.format_output_for_display(job_id)
        assert len(all_lines) == 3
        assert all_lines == ["Line 1", "Error line", "Line 3"]

        # Filter by type
        stdout_lines = await self.output_manager.format_output_for_display(
            job_id, filter_type="stdout"
        )
        assert len(stdout_lines) == 2
        assert stdout_lines == ["Line 1", "Line 3"]

        # Limit lines
        limited_lines = await self.output_manager.format_output_for_display(
            job_id, max_lines=2
        )
        assert len(limited_lines) == 2
        assert limited_lines == ["Error line", "Line 3"]  # Last 2 lines

    def test_cleanup_old_outputs(self) -> None:
        """Test cleaning up old job outputs"""
        # Create job outputs with different ages
        old_job = self.output_manager.create_job_output("old-job")
        new_job = self.output_manager.create_job_output("new-job")

        # Simulate old timestamp by adding a line with old timestamp
        old_timestamp = (now_utc() - timedelta(hours=2)).isoformat()
        old_job.lines.append(
            {
                "text": "Old line",
                "timestamp": old_timestamp,
                "type": "stdout",
                "metadata": {},
            }
        )

        # New job gets recent timestamp
        new_timestamp = now_utc().isoformat()
        new_job.lines.append(
            {
                "text": "New line",
                "timestamp": new_timestamp,
                "type": "stdout",
                "metadata": {},
            }
        )

        # Clean up outputs older than 1 hour
        cleaned_count = self.output_manager.cleanup_old_outputs(max_age_seconds=3600)

        assert cleaned_count == 1
        assert "old-job" not in self.output_manager._job_outputs
        assert "new-job" in self.output_manager._job_outputs
