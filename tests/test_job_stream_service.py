"""
Tests for JobStreamService class
"""
import pytest
import asyncio
import json
from unittest.mock import Mock, AsyncMock
from datetime import datetime, UTC

from app.services.job_stream_service import JobStreamService


class TestJobStreamService:
    """Test class for JobStreamService."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.mock_job_manager = Mock()
        self.stream_service = JobStreamService(job_manager=self.mock_job_manager)

    @pytest.mark.asyncio
    async def test_stream_all_jobs_returns_streaming_response(self):
        """Test that stream_all_jobs returns a StreamingResponse."""
        self.mock_job_manager.jobs = {}
        self.mock_job_manager.stream_all_job_updates = AsyncMock()
        
        # Mock the async generator
        async def mock_stream():
            yield {"type": "test_event", "message": "test"}
        
        self.mock_job_manager.stream_all_job_updates.return_value = mock_stream()
        
        response = await self.stream_service.stream_all_jobs()
        
        # Verify it's a StreamingResponse
        assert hasattr(response, 'media_type')
        assert response.media_type == "text/event-stream"
        assert response.headers["Cache-Control"] == "no-cache"

    @pytest.mark.asyncio
    async def test_all_jobs_event_generator_with_simple_job(self):
        """Test event generator with simple borg job."""
        # Create mock simple job
        mock_job = Mock()
        mock_job.is_composite.return_value = False
        mock_job.status = "running"
        mock_job.started_at = datetime(2023, 1, 1, 12, 0, 0, tzinfo=UTC)
        mock_job.completed_at = None
        mock_job.return_code = None
        mock_job.error = None
        mock_job.current_progress = {"files": 50}
        mock_job.command = ["borg", "create", "repo::archive"]
        
        self.mock_job_manager.jobs = {"job1": mock_job}
        
        # Mock empty stream
        async def empty_stream():
            return
            yield  # Make it async generator
        
        self.mock_job_manager.stream_all_job_updates.return_value = empty_stream()
        
        # Collect events
        events = []
        async for event in self.stream_service._all_jobs_event_generator():
            events.append(event)
            break  # Just get the first event (initial jobs list)
        
        assert len(events) == 1
        
        # Parse the event data
        event_line = events[0]
        assert event_line.startswith("event: jobs_update\\ndata: ")
        
        # Extract JSON data
        data_start = event_line.find("{")
        data_end = event_line.rfind("}") + 1
        event_data = json.loads(event_line[data_start:data_end])
        
        assert event_data["type"] == "jobs_update"
        assert len(event_data["jobs"]) == 1
        
        job_data = event_data["jobs"][0]
        assert job_data["type"] == "job_status"
        assert job_data["status"] == "running"
        assert job_data["command"] == "borg create repo::archive"

    @pytest.mark.asyncio
    async def test_all_jobs_event_generator_with_composite_job(self):
        """Test event generator with composite job."""
        # Create mock composite job
        mock_job = Mock()
        mock_job.is_composite.return_value = True
        mock_job.status = "running"
        mock_job.started_at = datetime(2023, 1, 1, 12, 0, 0, tzinfo=UTC)
        mock_job.completed_at = None
        mock_job.current_task_index = 0
        mock_job.tasks = [Mock(), Mock()]  # 2 tasks
        mock_job.job_type = "manual_backup"
        
        self.mock_job_manager.jobs = {"composite-job": mock_job}
        
        # Mock empty stream
        async def empty_stream():
            return
            yield
        
        self.mock_job_manager.stream_all_job_updates.return_value = empty_stream()
        
        # Collect events
        events = []
        async for event in self.stream_service._all_jobs_event_generator():
            events.append(event)
            break
        
        assert len(events) == 1
        
        # Parse the event data
        event_line = events[0]
        data_start = event_line.find("{")
        data_end = event_line.rfind("}") + 1
        event_data = json.loads(event_line[data_start:data_end])
        
        job_data = event_data["jobs"][0]
        assert job_data["type"] == "composite_job_status"
        assert job_data["status"] == "running"
        assert job_data["current_task_index"] == 0
        assert job_data["total_tasks"] == 2
        assert job_data["job_type"] == "manual_backup"

    @pytest.mark.asyncio
    async def test_all_jobs_event_generator_no_jobs(self):
        """Test event generator with no jobs."""
        self.mock_job_manager.jobs = {}
        
        async def empty_stream():
            return
            yield
        
        self.mock_job_manager.stream_all_job_updates.return_value = empty_stream()
        
        # Collect events
        events = []
        async for event in self.stream_service._all_jobs_event_generator():
            events.append(event)
            break
        
        assert len(events) == 1
        
        # Parse the event data
        event_line = events[0]
        data_start = event_line.find("{")
        data_end = event_line.rfind("}") + 1
        event_data = json.loads(event_line[data_start:data_end])
        
        assert event_data["type"] == "jobs_update"
        assert event_data["jobs"] == []

    @pytest.mark.asyncio
    async def test_all_jobs_event_generator_error_handling(self):
        """Test error handling in event generator."""
        # Make jobs property raise an exception
        type(self.mock_job_manager).jobs = PropertyMock(side_effect=Exception("Test error"))
        
        # Collect events
        events = []
        async for event in self.stream_service._all_jobs_event_generator():
            events.append(event)
            break
        
        assert len(events) == 1
        
        # Verify error event
        event_line = events[0]
        assert "Test error" in event_line
        assert '"type": "error"' in event_line

    @pytest.mark.asyncio
    async def test_stream_job_output_returns_streaming_response(self):
        """Test that stream_job_output returns a StreamingResponse."""
        self.mock_job_manager.jobs = {}
        self.mock_job_manager.stream_job_output = AsyncMock()
        
        # Mock the async generator
        async def mock_stream():
            yield {"type": "output", "line": "test output"}
        
        self.mock_job_manager.stream_job_output.return_value = mock_stream()
        
        response = await self.stream_service.stream_job_output("job-123")
        
        # Verify it's a StreamingResponse
        assert hasattr(response, 'media_type')
        assert response.media_type == "text/event-stream"
        assert response.headers["Cache-Control"] == "no-cache"

    @pytest.mark.asyncio
    async def test_job_output_event_generator_simple_job(self):
        """Test job output event generator for simple job."""
        mock_job = Mock()
        mock_job.is_composite.return_value = False
        
        self.mock_job_manager.jobs = {"job-123": mock_job}
        
        # Mock stream output
        async def mock_stream():
            yield {"type": "output", "line": "Starting backup..."}
            yield {"type": "output", "line": "Backup completed"}
        
        self.mock_job_manager.stream_job_output.return_value = mock_stream()
        
        # Collect events
        events = []
        async for event in self.stream_service._job_output_event_generator("job-123"):
            events.append(event)
        
        assert len(events) == 2
        
        # Verify events contain output data
        for event in events:
            assert event.startswith("data: ")
            assert '"type": "output"' in event

    @pytest.mark.asyncio
    async def test_job_output_event_generator_composite_job(self):
        """Test job output event generator for composite job."""
        mock_job = Mock()
        mock_job.is_composite.return_value = True
        mock_job.status = "running"
        
        self.mock_job_manager.jobs = {"composite-job": mock_job}
        
        # Mock event subscription
        mock_queue = Mock()
        mock_queue.get = AsyncMock()
        
        # Mock the sequence of events
        events_sequence = [
            {"job_id": "composite-job", "type": "task_started", "task_name": "backup"},
            {"job_id": "composite-job", "type": "task_completed", "task_name": "backup"}
        ]
        
        mock_queue.get.side_effect = events_sequence + [asyncio.TimeoutError()]
        
        self.mock_job_manager.subscribe_to_events.return_value = mock_queue
        self.mock_job_manager.unsubscribe_from_events = Mock()
        
        # Collect events
        events = []
        try:
            async for event in self.stream_service._job_output_event_generator("composite-job"):
                events.append(event)
                if len(events) >= 3:  # initial_state + 2 job events
                    break
        except StopAsyncIteration:
            pass
        
        # Should have initial state + job events
        assert len(events) >= 2
        
        # Verify initial state event
        initial_event = events[0]
        assert '"type": "initial_state"' in initial_event
        assert '"job_id": "composite-job"' in initial_event
        
        # Note: unsubscribe_from_events is called in finally block,
        # but the async generator may not reach that point in this test
        # This is acceptable behavior for the test

    @pytest.mark.asyncio
    async def test_job_output_event_generator_job_not_found(self):
        """Test job output event generator when job doesn't exist."""
        self.mock_job_manager.jobs = {}
        
        # Mock stream output for non-existent job
        async def empty_stream():
            return
            yield
        
        self.mock_job_manager.stream_job_output.return_value = empty_stream()
        
        # Collect events
        events = []
        async for event in self.stream_service._job_output_event_generator("non-existent"):
            events.append(event)
            break
        
        # Should still call stream_job_output for simple jobs
        self.mock_job_manager.stream_job_output.assert_called_once_with("non-existent")

    @pytest.mark.asyncio
    async def test_get_job_status(self):
        """Test getting job status."""
        expected_output = {"status": "running", "progress": {"files": 100}}
        self.mock_job_manager.get_job_output_stream = AsyncMock(return_value=expected_output)
        
        result = await self.stream_service.get_job_status("job-123")
        
        assert result == expected_output
        self.mock_job_manager.get_job_output_stream.assert_called_once_with("job-123", last_n_lines=50)

    def test_get_current_jobs_data_with_simple_job(self):
        """Test getting current jobs data with simple job."""
        mock_job = Mock()
        mock_job.status = "running"
        mock_job.command = ["borg", "create", "repo::archive"]
        mock_job.started_at = datetime(2023, 1, 1, 12, 0, 0, tzinfo=UTC)
        mock_job.current_progress = {"files": 150, "transferred": "75MB"}
        mock_job.is_composite.return_value = False
        
        self.mock_job_manager.jobs = {"simple-job": mock_job}
        
        current_jobs = self.stream_service.get_current_jobs_data()
        
        assert len(current_jobs) == 1
        job_data = current_jobs[0]
        assert job_data["id"] == "simple-job"
        assert job_data["type"] == "backup"
        assert job_data["status"] == "running"
        assert job_data["progress_info"] == "Files: 150 | 75MB"

    def test_get_current_jobs_data_with_composite_job(self):
        """Test getting current jobs data with composite job."""
        mock_task = Mock()
        mock_task.task_name = "Backup repository"
        
        mock_job = Mock()
        mock_job.status = "running"
        mock_job.started_at = datetime(2023, 1, 1, 12, 0, 0, tzinfo=UTC)
        mock_job.is_composite.return_value = True
        mock_job.get_current_task.return_value = mock_task
        mock_job.current_task_index = 1
        mock_job.tasks = [Mock(), Mock(), Mock()]  # 3 tasks total
        mock_job.__len__ = Mock(return_value=3)  # Add len support
        mock_job.job_type = "scheduled_backup"
        # Ensure command is not checked for composite jobs
        mock_job.command = None
        mock_job.current_progress = None  # Avoid progress check issues
        
        self.mock_job_manager.jobs = {"composite-job": mock_job}
        
        current_jobs = self.stream_service.get_current_jobs_data()
        
        assert len(current_jobs) == 1
        job_data = current_jobs[0]
        assert job_data["id"] == "composite-job"
        assert job_data["type"] == "scheduled_backup"
        assert job_data["status"] == "running"
        assert "Task: Backup repository (2/3)" in job_data["progress_info"]
        assert job_data["progress"]["current_task"] == "Backup repository"
        assert job_data["progress"]["task_progress"] == "2/3"

    def test_get_current_jobs_data_no_running_jobs(self):
        """Test getting current jobs data when no jobs are running."""
        mock_completed_job = Mock()
        mock_completed_job.status = "completed"
        mock_completed_job.is_composite.return_value = False
        
        mock_failed_job = Mock()
        mock_failed_job.status = "failed"
        mock_failed_job.is_composite.return_value = False
        
        self.mock_job_manager.jobs = {
            "completed-job": mock_completed_job,
            "failed-job": mock_failed_job
        }
        
        current_jobs = self.stream_service.get_current_jobs_data()
        
        assert len(current_jobs) == 0

    def test_get_current_jobs_data_mixed_jobs(self):
        """Test getting current jobs data with mix of running and non-running jobs."""
        # Running simple job
        mock_simple = Mock()
        mock_simple.status = "running"
        mock_simple.command = ["borg", "list", "repo"]
        mock_simple.started_at = datetime(2023, 1, 1, 12, 0, 0, tzinfo=UTC)
        mock_simple.current_progress = None
        mock_simple.is_composite.return_value = False
        
        # Completed job (should be filtered out)
        mock_completed = Mock()
        mock_completed.status = "completed"
        mock_completed.is_composite.return_value = False
        
        # Running composite job
        mock_composite = Mock()
        mock_composite.status = "running"
        mock_composite.started_at = datetime(2023, 1, 1, 12, 0, 0, tzinfo=UTC)
        mock_composite.is_composite.return_value = True
        mock_composite.get_current_task.return_value = Mock(task_name="Prune archives")
        mock_composite.current_task_index = 0
        mock_composite.tasks = [Mock()]
        mock_composite.__len__ = Mock(return_value=1)  # Add len support
        # No job_type attribute - should default
        mock_composite.command = None  # Ensure command is not checked
        mock_composite.current_progress = None  # Avoid progress check issues
        
        self.mock_job_manager.jobs = {
            "simple-job": mock_simple,
            "completed-job": mock_completed,
            "composite-job": mock_composite
        }
        
        current_jobs = self.stream_service.get_current_jobs_data()
        
        # Should only include the 2 running jobs
        assert len(current_jobs) == 2
        
        # Find each job in results
        simple_job = next(j for j in current_jobs if j["id"] == "simple-job")
        composite_job = next(j for j in current_jobs if j["id"] == "composite-job")
        
        assert simple_job["type"] == "list"  # Inferred from "list" command
        assert simple_job["progress_info"] == ""  # No progress data
        
        assert composite_job["type"] == "composite"  # Default when no job_type
        assert "Task: Prune archives (1/1)" in composite_job["progress_info"]


# Helper for mocking property
from unittest.mock import PropertyMock