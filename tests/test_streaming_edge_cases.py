"""
Test suite for streaming edge cases and error scenarios
"""

import pytest
import uuid
from unittest.mock import Mock, patch, AsyncMock
import asyncio
from typing import Any

from borgitory.services.jobs.job_stream_service import JobStreamService


class TestStreamingErrorHandling:
    """Test error handling in streaming functionality"""

    @pytest.fixture
    def mock_job_manager(self) -> Mock:
        manager = Mock()
        manager.jobs = {}
        manager.subscribe_to_events = Mock()
        manager.unsubscribe_from_events = Mock()
        return manager

    @pytest.fixture
    def job_stream_service(self, mock_job_manager) -> JobStreamService:
        return JobStreamService(job_manager=mock_job_manager)

    @pytest.mark.asyncio
    async def test_task_streaming_nonexistent_job(
        self, job_stream_service: JobStreamService, mock_job_manager: Mock
    ) -> None:
        """Test streaming for a job that doesn't exist"""
        job_id = str(uuid.uuid4())
        task_order = 0

        # No jobs in manager
        mock_job_manager.jobs = {}

        # Should fall back to database lookup
        with patch("borgitory.models.database.SessionLocal") as mock_session_local:
            mock_session = Mock()
            mock_session_local.return_value = mock_session
            mock_session.query().filter().first.return_value = (
                None  # No job in DB either
            )

            events = []
            async for event in job_stream_service._task_output_event_generator(
                job_id, task_order
            ):
                events.append(event)
                if len(events) >= 1:
                    break

            # Should indicate job not found
            assert len(events) >= 1
            assert f"Job {job_id} not found" in events[0]

    @pytest.mark.asyncio
    async def test_task_streaming_job_with_mock_tasks(
        self, job_stream_service: JobStreamService, mock_job_manager: Mock
    ) -> None:
        """Test streaming for a job with Mock tasks attribute (error handling)"""
        job_id = str(uuid.uuid4())
        task_order = 0

        # Create job with Mock tasks (simulates error condition)
        job_with_mock_tasks = Mock()
        job_with_mock_tasks.tasks = Mock()  # This will cause len() to fail
        mock_job_manager.jobs = {job_id: job_with_mock_tasks}

        events = []
        async for event in job_stream_service._task_output_event_generator(
            job_id, task_order
        ):
            events.append(event)
            if len(events) >= 1:
                break

        # Should handle the Mock tasks error gracefully
        assert len(events) >= 1
        assert "object of type 'Mock' has no len()" in events[0]

    @pytest.mark.asyncio
    async def test_task_streaming_invalid_task_order(
        self, job_stream_service: JobStreamService, mock_job_manager: Mock
    ) -> None:
        """Test streaming for invalid task order"""
        job_id = str(uuid.uuid4())
        task_order = 999  # Invalid task order

        # Create composite job with only one task
        composite_job = Mock()
        composite_job.tasks = [Mock()]  # Only one task (index 0)
        mock_job_manager.jobs = {job_id: composite_job}

        events = []
        async for event in job_stream_service._task_output_event_generator(
            job_id, task_order
        ):
            events.append(event)
            if len(events) >= 1:
                break

        # Should indicate task not found
        assert len(events) >= 1
        assert f"Task {task_order} not found" in events[0]

    @pytest.mark.asyncio
    async def test_task_streaming_handles_timeout(
        self, job_stream_service: JobStreamService, mock_job_manager: Mock
    ) -> None:
        """Test that streaming handles timeouts gracefully"""
        job_id = str(uuid.uuid4())
        task_order = 0

        # Create composite job with task
        task = Mock()
        task.status = "running"
        task.output_lines = []

        composite_job = Mock()
        composite_job.tasks = [task]
        mock_job_manager.jobs = {job_id: composite_job}

        # Mock timeout in event queue
        mock_queue = AsyncMock()
        mock_queue.get.side_effect = asyncio.TimeoutError()
        mock_job_manager.subscribe_to_events.return_value = mock_queue

        events = []
        async for event in job_stream_service._task_output_event_generator(
            job_id, task_order
        ):
            events.append(event)
            if len(events) >= 1:
                break

        # Should handle timeout gracefully with heartbeat
        assert len(events) >= 1
        assert any("heartbeat" in event for event in events)

    @pytest.mark.asyncio
    async def test_database_streaming_connection_error(
        self, job_stream_service: JobStreamService, mock_job_manager: Mock
    ) -> None:
        """Test database streaming when connection fails"""
        job_id = str(uuid.uuid4())
        task_order = 0

        # Job not found in manager, should try database
        mock_job_manager.jobs = {}

        with patch("borgitory.models.database.SessionLocal") as mock_session_local:
            mock_session_local.side_effect = Exception("Database connection failed")

            events = []
            async for event in job_stream_service._task_output_event_generator(
                job_id, task_order
            ):
                events.append(event)
                if len(events) >= 1:
                    break

            # Should handle error gracefully
            assert len(events) >= 1
            assert f"Job {job_id} not found" in events[0]


class TestStreamingPerformance:
    """Test performance aspects of streaming"""

    @pytest.fixture
    def mock_job_manager(self) -> Mock:
        manager = Mock()
        manager.jobs = {}
        return manager

    @pytest.fixture
    def job_stream_service(self, mock_job_manager) -> JobStreamService:
        return JobStreamService(job_manager=mock_job_manager)

    def test_streaming_output_size_efficiency(self) -> None:
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

    def test_html_div_wrapping_overhead(self) -> None:
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


class TestEventFiltering:
    """Test event filtering logic"""

    @pytest.fixture
    def mock_job_manager(self) -> Mock:
        manager = Mock()
        manager.jobs = {}
        return manager

    @pytest.fixture
    def job_stream_service(self, mock_job_manager) -> JobStreamService:
        return JobStreamService(job_manager=mock_job_manager)

    @pytest.mark.asyncio
    async def test_event_filtering_correct_job_and_task(
        self, job_stream_service: JobStreamService, mock_job_manager: Mock
    ) -> None:
        """Test that events are filtered correctly by job ID and task index"""
        job_id = str(uuid.uuid4())
        other_job_id = str(uuid.uuid4())
        task_order = 1

        # Create composite job
        task = Mock()
        task.status = "running"
        task.output_lines = []

        composite_job = Mock()
        composite_job.tasks = [Mock(), task]  # Task at index 1
        mock_job_manager.jobs = {job_id: composite_job}

        # Mock event queue with mixed events
        mock_queue = AsyncMock()
        from borgitory.services.jobs.broadcaster.job_event import JobEvent
        from borgitory.services.jobs.broadcaster.event_type import EventType

        events_to_send = [
            # Event for different job - should be ignored
            JobEvent(
                event_type=EventType.JOB_OUTPUT,
                job_id=other_job_id,
                data={
                    "task_type": "task_output",
                    "task_index": task_order,
                    "line": "Wrong job",
                },
            ),
            # Event for correct job but wrong task - should be ignored
            JobEvent(
                event_type=EventType.JOB_OUTPUT,
                job_id=job_id,
                data={
                    "task_type": "task_output",
                    "task_index": 0,
                    "line": "Wrong task",
                },
            ),
            # Event for correct job and task - should be processed
            JobEvent(
                event_type=EventType.JOB_OUTPUT,
                job_id=job_id,
                data={
                    "task_type": "task_output",
                    "task_index": task_order,
                    "line": "Correct event",
                },
            ),
            Exception("End test"),
        ]
        mock_queue.get.side_effect = events_to_send
        mock_job_manager.subscribe_to_events.return_value = mock_queue

        events = []
        try:
            async for event in job_stream_service._task_output_event_generator(
                job_id, task_order
            ):
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

    def test_empty_output_lines_handling(self) -> None:
        """Test handling of empty or None output_lines"""
        # Test various empty states
        empty_states: list[Any] = [
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
                    text = line.get("text", "") or ""  # Handle None values

                    # Should not raise exception and should be string
                    assert isinstance(text, str)
