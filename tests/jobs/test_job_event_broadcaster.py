"""
Tests for JobEventBroadcaster - SSE streaming and event distribution
"""

import pytest
import asyncio
from unittest.mock import patch

from borgitory.services.jobs.broadcaster.job_event_broadcaster import (
    JobEventBroadcaster,
    EventType,
    JobEvent,
)


class TestJobEventBroadcaster:
    """Test JobEventBroadcaster functionality"""

    def setup_method(self) -> None:
        """Set up test fixtures"""
        self.broadcaster = JobEventBroadcaster(
            max_queue_size=5, keepalive_timeout=1.0, cleanup_interval=0.5
        )

    def test_job_event_creation(self) -> None:
        """Test JobEvent creation and serialization"""
        event = JobEvent(
            event_type=EventType.JOB_STARTED,
            job_id="test-job-123",
            data={"status": "running"},
        )

        event_dict = event.to_dict()

        assert event_dict["type"] == "job_started"
        assert event_dict["job_id"] == "test-job-123"
        assert event_dict["data"]["status"] == "running"
        assert "timestamp" in event_dict

    def test_job_event_defaults(self) -> None:
        """Test JobEvent with default values"""
        event = JobEvent(event_type=EventType.KEEPALIVE)

        event_dict = event.to_dict()

        assert event_dict["type"] == "keepalive"
        assert event_dict["job_id"] is None
        assert event_dict["data"] == {}
        assert event_dict["timestamp"] is not None

    def test_subscribe_client(self) -> None:
        """Test client subscription"""
        queue = self.broadcaster.subscribe_client(client_id="test-client-1")

        assert queue is not None
        assert len(self.broadcaster._client_queues) == 1
        assert queue in self.broadcaster._client_queues
        assert queue in self.broadcaster._client_queue_metadata

        metadata = self.broadcaster._client_queue_metadata[queue]
        assert metadata["client_id"] == "test-client-1"
        assert "connected_at" in metadata
        assert metadata["events_sent"] == 0

    def test_subscribe_client_auto_id(self) -> None:
        """Test client subscription with auto-generated ID"""
        queue = self.broadcaster.subscribe_client()

        metadata = self.broadcaster._client_queue_metadata[queue]
        assert metadata["client_id"] == "client_0"

    def test_unsubscribe_client(self) -> None:
        """Test client unsubscription"""
        queue = self.broadcaster.subscribe_client(client_id="test-client-1")

        result = self.broadcaster.unsubscribe_client(queue)

        assert result is True
        assert len(self.broadcaster._client_queues) == 0
        assert queue not in self.broadcaster._client_queue_metadata

    def test_broadcast_event_no_clients(self) -> None:
        """Test broadcasting event with no subscribed clients"""
        self.broadcaster.broadcast_event(
            EventType.JOB_STARTED, job_id="test-job", data={"status": "running"}
        )

        # Should not raise error and should add to recent events
        assert len(self.broadcaster._recent_events) == 1
        assert self.broadcaster._recent_events[0].event_type == EventType.JOB_STARTED

    def test_broadcast_event_with_clients(self) -> None:
        """Test broadcasting event to subscribed clients"""
        # Subscribe two clients
        queue1 = self.broadcaster.subscribe_client(client_id="client-1")
        queue2 = self.broadcaster.subscribe_client(client_id="client-2")

        self.broadcaster.broadcast_event(
            EventType.JOB_COMPLETED, job_id="test-job", data={"result": "success"}
        )

        # Both queues should have the event
        assert queue1.qsize() == 1
        assert queue2.qsize() == 1

        # Check event content
        event1 = queue1.get_nowait()
        assert event1["type"] == "job_completed"
        assert event1["job_id"] == "test-job"
        assert event1["data"]["result"] == "success"

    def test_broadcast_event_full_queue(self) -> None:
        """Test broadcasting to full client queue"""
        # Create queue at max capacity
        queue = self.broadcaster.subscribe_client()
        for i in range(5):  # Fill to max_queue_size
            queue.put_nowait(JobEvent(event_type=EventType.KEEPALIVE, data={"test": i}))

        initial_client_count = len(self.broadcaster._client_queues)

        # Try to broadcast - should remove full queue
        self.broadcaster.broadcast_event(EventType.KEEPALIVE)

        # Queue should be removed due to being full
        assert len(self.broadcaster._client_queues) < initial_client_count

    def test_recent_events_limit(self) -> None:
        """Test recent events list respects size limit"""
        # Broadcast more events than max_recent_events (50)
        for i in range(60):
            self.broadcaster.broadcast_event(
                EventType.JOB_PROGRESS, data={"progress": i}
            )

        assert len(self.broadcaster._recent_events) == 50
        # Should keep the most recent events
        assert self.broadcaster._recent_events[-1].data["progress"] == 59

    @pytest.mark.asyncio
    async def test_stream_events_for_client(self) -> None:
        """Test streaming events for a specific client"""
        queue = asyncio.Queue(maxsize=2)
        queue.put_nowait({"type": "test", "data": "event1"})
        queue.put_nowait({"type": "test", "data": "event2"})

        stream_gen = self.broadcaster.stream_events_for_client(queue)

        # Get first two events
        event1 = await stream_gen.__anext__()
        event2 = await stream_gen.__anext__()

        assert event1["data"] == "event1"
        assert event2["data"] == "event2"

    @pytest.mark.asyncio
    async def test_stream_events_timeout_keepalive(self) -> None:
        """Test streaming events sends keepalive on timeout"""
        empty_queue = asyncio.Queue()

        stream_gen = self.broadcaster.stream_events_for_client(empty_queue)

        # Should get keepalive after timeout
        with patch("asyncio.wait_for", side_effect=asyncio.TimeoutError()):
            event = await stream_gen.__anext__()

        assert event["type"] == "keepalive"
        assert "timestamp" in event

    @pytest.mark.asyncio
    async def test_stream_all_events(self) -> None:
        """Test streaming all events creates and manages client subscription"""
        # Create a real queue with test events instead of mocking
        test_queue = asyncio.Queue(maxsize=5)
        test_queue.put_nowait({"type": "test", "data": "value"})

        # Mock subscribe_client to return our test queue
        with patch.object(
            self.broadcaster, "subscribe_client", return_value=test_queue
        ):
            stream_gen = self.broadcaster.stream_all_events()

            # Get the first event, then break to avoid timeout
            events = []
            async for event in stream_gen:
                events.append(event)
                if len(events) >= 1:
                    break

        assert len(events) == 1
        assert events[0]["type"] == "test"

    def test_get_client_stats(self) -> None:
        """Test getting client statistics"""
        # Subscribe multiple clients
        queue1 = self.broadcaster.subscribe_client(client_id="client-1")
        queue2 = self.broadcaster.subscribe_client(client_id="client-2")

        # Simulate some events sent
        self.broadcaster._client_queue_metadata[queue1]["events_sent"] = 5
        self.broadcaster._client_queue_metadata[queue2]["events_sent"] = 3

        stats = self.broadcaster.get_client_stats()

        assert stats["total_clients"] == 2
        assert len(stats["client_details"]) == 2

        client_details = {
            detail["client_id"]: detail for detail in stats["client_details"]
        }
        assert client_details["client-1"]["events_sent"] == 5
        assert client_details["client-2"]["events_sent"] == 3

    def test_get_event_history(self) -> None:
        """Test getting event history"""
        # Add some events
        for i in range(5):
            self.broadcaster.broadcast_event(EventType.JOB_PROGRESS, data={"step": i})

        # Get limited history
        history = self.broadcaster.get_event_history(limit=3)

        assert len(history) == 3
        # Should return most recent events
        assert history[-1]["data"]["step"] == 4
        assert history[0]["data"]["step"] == 2

    @pytest.mark.asyncio
    async def test_initialize(self) -> None:
        """Test broadcaster initialization"""
        await self.broadcaster.initialize()

        # Should start background tasks
        assert self.broadcaster._cleanup_task is not None
        assert self.broadcaster._keepalive_task is not None
        assert not self.broadcaster._cleanup_task.done()
        assert not self.broadcaster._keepalive_task.done()

    @pytest.mark.asyncio
    async def test_shutdown(self) -> None:
        """Test broadcaster shutdown"""
        await self.broadcaster.initialize()

        # Add some clients and events
        queue = self.broadcaster.subscribe_client()
        self.broadcaster.broadcast_event(EventType.KEEPALIVE)

        # Drain the queue to avoid unawaited coroutines
        try:
            while not queue.empty():
                queue.get_nowait()
        except asyncio.QueueEmpty:
            pass

        await self.broadcaster.shutdown()

        # Should clean up everything
        assert len(self.broadcaster._client_queues) == 0
        assert len(self.broadcaster._client_queue_metadata) == 0
        assert len(self.broadcaster._recent_events) == 0
        assert self.broadcaster._shutdown_requested is True

        # Background tasks should be cancelled
        assert self.broadcaster._cleanup_task.done()
        assert self.broadcaster._keepalive_task.done()
