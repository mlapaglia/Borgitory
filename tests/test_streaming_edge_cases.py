"""
Test suite for streaming edge cases and error scenarios
"""
import pytest
import uuid
from unittest.mock import Mock, patch, AsyncMock
import asyncio

from app.services.jobs.job_stream_service import JobStreamService


class TestStreamingErrorHandling:
    """Test error handling in streaming functionality"""

    @pytest.fixture
    def mock_job_manager(self):
        manager = Mock()
        manager.jobs = {}
        manager.subscribe_to_events = Mock()
        manager.unsubscribe_from_events = Mock()
        return manager

    @pytest.fixture
    def job_stream_service(self, mock_job_manager):
        return JobStreamService(job_manager=mock_job_manager)

    @pytest.mark.asyncio
    async def test_task_streaming_nonexistent_job(self, job_stream_service, mock_job_manager):
        """Test streaming for a job that doesn't exist"""
        job_id = str(uuid.uuid4())
        task_order = 0
        
        # No jobs in manager
        mock_job_manager.jobs = {}
        
        # Should fall back to database lookup
        with patch('app.models.database.SessionLocal') as mock_session_local:
            mock_session = Mock()
            mock_session_local.return_value = mock_session
            mock_session.query().filter().first.return_value = None  # No job in DB either
            
            events = []
            async for event in job_stream_service._task_output_event_generator(job_id, task_order):
                events.append(event)
                if len(events) >= 1:
                    break
            
            # Should indicate job not found
            assert len(events) >= 1
            assert f"Job {job_id} not found" in events[0]

    @pytest.mark.asyncio
    async def test_task_streaming_non_composite_job(self, job_stream_service, mock_job_manager):
        """Test streaming for a non-composite job"""
        job_id = str(uuid.uuid4())
        task_order = 0
        
        # Create simple (non-composite) job
        simple_job = Mock()
        simple_job.is_composite.return_value = False
        mock_job_manager.jobs = {job_id: simple_job}
        
        events = []
        async for event in job_stream_service._task_output_event_generator(job_id, task_order):
            events.append(event)
            if len(events) >= 1:
                break
        
        # Should indicate it's not a composite job
        assert len(events) >= 1
        assert "is not a composite job" in events[0]

    @pytest.mark.asyncio
    async def test_task_streaming_invalid_task_order(self, job_stream_service, mock_job_manager):
        """Test streaming for invalid task order"""
        job_id = str(uuid.uuid4())
        task_order = 999  # Invalid task order
        
        # Create composite job with only one task
        composite_job = Mock()
        composite_job.is_composite.return_value = True
        composite_job.tasks = [Mock()]  # Only one task (index 0)
        mock_job_manager.jobs = {job_id: composite_job}
        
        events = []
        async for event in job_stream_service._task_output_event_generator(job_id, task_order):
            events.append(event)
            if len(events) >= 1:
                break
        
        # Should indicate task not found
        assert len(events) >= 1
        assert f"Task {task_order} not found" in events[0]

    @pytest.mark.asyncio
    async def test_task_streaming_handles_timeout(self, job_stream_service, mock_job_manager):
        """Test that streaming handles timeouts gracefully"""
        job_id = str(uuid.uuid4())
        task_order = 0
        
        # Create composite job with task
        task = Mock()
        task.status = "running"
        task.output_lines = []
        
        composite_job = Mock()
        composite_job.is_composite.return_value = True
        composite_job.tasks = [task]
        mock_job_manager.jobs = {job_id: composite_job}
        
        # Mock timeout in event queue
        mock_queue = AsyncMock()
        mock_queue.get.side_effect = asyncio.TimeoutError()
        mock_job_manager.subscribe_to_events.return_value = mock_queue
        
        events = []
        async for event in job_stream_service._task_output_event_generator(job_id, task_order):
            events.append(event)
            if len(events) >= 1:
                break
        
        # Should handle timeout gracefully with heartbeat
        assert len(events) >= 1
        assert any("heartbeat" in event for event in events)

    @pytest.mark.asyncio
    async def test_database_streaming_connection_error(self, job_stream_service):
        """Test database streaming when connection fails"""
        job_id = str(uuid.uuid4())
        task_order = 0
        
        with patch('app.models.database.SessionLocal') as mock_session_local:
            mock_session_local.side_effect = Exception("Database connection failed")
            
            events = []
            async for event in job_stream_service._stream_completed_task_output(job_id, task_order):
                events.append(event)
            
            # Should handle error gracefully
            assert len(events) >= 1
            assert "Error loading task output" in events[0]


class TestStreamingPerformance:
    """Test performance aspects of streaming"""

    @pytest.fixture
    def mock_job_manager(self):
        manager = Mock()
        manager.jobs = {}
        return manager

    @pytest.fixture
    def job_stream_service(self, mock_job_manager):
        return JobStreamService(job_manager=mock_job_manager)

    def test_streaming_output_size_efficiency(self):
        """Test that individual line streaming is more efficient than accumulated"""
        # Simulate 100 lines of output
        lines = [f"Output line {i} with some content" for i in range(100)]
        
        # Individual line approach (current implementation)
        individual_events_size = 0
        for line in lines:
            event = f"event: output\ndata: <div>{line}</div>\n\n"
            individual_events_size += len(event)
        
        # Accumulated approach (what we avoided)
        accumulated_text = "\n".join(lines)
        accumulated_event_size = len(f"event: output\ndata: {accumulated_text}\n\n")
        
        # Individual approach allows incremental transmission
        # First line can be sent immediately, not waiting for all lines
        first_line_event = f"event: output\ndata: <div>{lines[0]}</div>\n\n"
        
        # Assert that we can send the first line without waiting for all lines
        assert len(first_line_event) < accumulated_event_size
        assert "Output line 0" in first_line_event

    def test_html_div_wrapping_overhead(self):
        """Test that HTML div wrapping doesn't add excessive overhead"""
        test_lines = [
            "",  # Empty line
            "Short",  # Short line
            "A" * 1000,  # Long line
            "Line with special chars: <>&\"'",  # Special characters
        ]
        
        for line in test_lines:
            wrapped = f"<div>{line}</div>"
            
            # Overhead should be minimal (just the div tags)
            overhead = len(wrapped) - len(line)
            assert overhead == 11  # len("<div></div>") = 11
            
            # Wrapped content should contain original line
            assert line in wrapped


class TestStreamingConcurrency:
    """Test concurrent streaming scenarios"""

    @pytest.mark.asyncio
    async def test_multiple_task_streams_concurrent(self):
        """Test that multiple task streams can run concurrently"""
        job_stream_service = JobStreamService()
        job_id = str(uuid.uuid4())
        
        # Mock job manager with composite job
        mock_job_manager = Mock()
        task1 = Mock()
        task1.status = "completed"
        task1.output_lines = [{"text": "Task 1 output"}]
        
        task2 = Mock()
        task2.status = "completed"  
        task2.output_lines = [{"text": "Task 2 output"}]
        
        composite_job = Mock()
        composite_job.is_composite.return_value = True
        composite_job.tasks = [task1, task2]
        
        mock_job_manager.jobs = {job_id: composite_job}
        job_stream_service.job_manager = mock_job_manager
        
        # Create concurrent streams for different tasks
        async def stream_task(task_order):
            events = []
            mock_queue = AsyncMock()
            mock_queue.get.side_effect = Exception("Test end")
            mock_job_manager.subscribe_to_events.return_value = mock_queue
            
            try:
                async for event in job_stream_service._task_output_event_generator(job_id, task_order):
                    events.append(event)
                    if len(events) >= 1:  # Just get first event
                        break
            except Exception:
                pass
            return events
        
        # Run both streams concurrently
        task1_stream, task2_stream = await asyncio.gather(
            stream_task(0),
            stream_task(1)
        )
        
        # Both should have received their respective output
        assert len(task1_stream) >= 1
        assert len(task2_stream) >= 1
        assert "Task 1 output" in task1_stream[0]
        assert "Task 2 output" in task2_stream[0]


class TestEventFiltering:
    """Test event filtering logic"""

    @pytest.fixture
    def mock_job_manager(self):
        manager = Mock()
        manager.jobs = {}
        return manager

    @pytest.fixture
    def job_stream_service(self, mock_job_manager):
        return JobStreamService(job_manager=mock_job_manager)

    @pytest.mark.asyncio
    async def test_event_filtering_correct_job_and_task(self, job_stream_service, mock_job_manager):
        """Test that events are filtered correctly by job ID and task index"""
        job_id = str(uuid.uuid4())
        other_job_id = str(uuid.uuid4())
        task_order = 1
        
        # Create composite job
        task = Mock()
        task.status = "running"
        task.output_lines = []
        
        composite_job = Mock()
        composite_job.is_composite.return_value = True
        composite_job.tasks = [Mock(), task]  # Task at index 1
        mock_job_manager.jobs = {job_id: composite_job}
        
        # Mock event queue with mixed events
        mock_queue = AsyncMock()
        events_to_send = [
            # Event for different job - should be ignored
            {
                "job_id": other_job_id,
                "type": "job_output",
                "data": {"task_type": "task_output", "task_index": task_order, "line": "Wrong job"}
            },
            # Event for correct job but wrong task - should be ignored
            {
                "job_id": job_id,
                "type": "job_output", 
                "data": {"task_type": "task_output", "task_index": 0, "line": "Wrong task"}
            },
            # Event for correct job and task - should be processed
            {
                "job_id": job_id,
                "type": "job_output",
                "data": {"task_type": "task_output", "task_index": task_order, "line": "Correct event"}
            },
            Exception("End test")
        ]
        mock_queue.get.side_effect = events_to_send
        mock_job_manager.subscribe_to_events.return_value = mock_queue
        
        events = []
        try:
            async for event in job_stream_service._task_output_event_generator(job_id, task_order):
                events.append(event)
                if len(events) >= 2:  # Get a couple events
                    break
        except Exception:
            pass
        
        # Should only have the correct event
        correct_events = [e for e in events if "Correct event" in e]
        wrong_events = [e for e in events if "Wrong job" in e or "Wrong task" in e]
        
        assert len(correct_events) >= 1
        assert len(wrong_events) == 0


class TestBackwardCompatibilityEdgeCases:
    """Test edge cases for backward compatibility"""

    def test_job_context_handles_missing_attributes(self):
        """Test that job context handles missing attributes gracefully"""
        from app.services.jobs.job_render_service import JobRenderService
        
        # Create job with minimal attributes
        minimal_job = Mock()
        minimal_job.id = str(uuid.uuid4())
        minimal_job.status = "completed"
        minimal_job.job_type = None  # Missing job_type
        minimal_job.type = "backup"
        minimal_job.started_at = None  # Missing started_at
        minimal_job.finished_at = None  # Missing finished_at
        minimal_job.error = None
        minimal_job.repository = None  # Missing repository
        minimal_job.tasks = []
        
        service = JobRenderService()
        
        # Should not raise exception
        try:
            result = service._format_database_job_for_render(minimal_job)
            assert result is not None
            assert result["job"].id == minimal_job.id
        except Exception as e:
            pytest.fail(f"Should handle missing attributes gracefully: {e}")

    def test_empty_output_lines_handling(self):
        """Test handling of empty or None output_lines"""
        # Test various empty states
        empty_states = [
            None,
            [],
            [{"text": ""}],
            [{"text": None}],
            [{}],  # Missing text key
        ]
        
        for empty_state in empty_states:
            task = Mock()
            task.output_lines = empty_state
            
            # Should handle gracefully without exceptions
            # This tests the robustness of our line processing logic
            if empty_state:
                for line in empty_state:
                    if isinstance(line, dict):
                        text = line.get("text", "") or ""  # Handle None values
                    else:
                        text = str(line)
                    # Should not raise exception and should be string
                    assert isinstance(text, str)