"""
Job Event Broadcaster - Handles SSE streaming and event distribution
"""

import asyncio
import logging
from typing import Dict, List, AsyncGenerator, Optional, Union
from datetime import datetime
from borgitory.custom_types import ConfigDict
from borgitory.utils.datetime_utils import now_utc

from borgitory.services.jobs.broadcaster.event_type import EventType
from borgitory.services.jobs.broadcaster.job_event import JobEvent

logger = logging.getLogger(__name__)


class JobEventBroadcaster:
    """Handles SSE streaming and event distribution to clients"""

    def __init__(
        self,
        max_queue_size: int = 100,
        keepalive_timeout: float = 30.0,
        cleanup_interval: float = 60.0,
    ) -> None:
        self.max_queue_size = max_queue_size
        self.keepalive_timeout = keepalive_timeout
        self.cleanup_interval = cleanup_interval

        # Client event queues for SSE streaming
        self._client_queues: List[asyncio.Queue[JobEvent]] = []
        self._client_queue_metadata: Dict[
            asyncio.Queue[JobEvent], Dict[str, Union[str, int, datetime]]
        ] = {}

        # Event history for new clients
        self._recent_events: List[JobEvent] = []
        self._max_recent_events = 50

        # Background tasks
        self._cleanup_task: Optional[asyncio.Task[None]] = None
        self._keepalive_task: Optional[asyncio.Task[None]] = None
        self._shutdown_requested = False

    async def initialize(self) -> None:
        """Initialize background tasks"""
        if not self._cleanup_task or self._cleanup_task.done():
            self._cleanup_task = asyncio.create_task(
                self._cleanup_disconnected_clients()
            )

        if not self._keepalive_task or self._keepalive_task.done():
            self._keepalive_task = asyncio.create_task(self._send_keepalives())

    def broadcast_event(
        self,
        event_type: EventType,
        job_id: Optional[str] = None,
        data: Optional[ConfigDict] = None,
    ) -> None:
        """Broadcast an event to all connected clients"""
        event = JobEvent(event_type=event_type, job_id=job_id, data=data or {})

        # Add to recent events
        self._recent_events.append(event)
        if len(self._recent_events) > self._max_recent_events:
            self._recent_events.pop(0)

        # Send to all client queues
        failed_queues = []
        sent_count = 0

        for queue in self._client_queues:
            try:
                if not queue.full():
                    queue.put_nowait(event)
                    sent_count += 1
                else:
                    logger.warning("Client queue is full, marking for cleanup")
                    failed_queues.append(queue)
            except Exception as e:
                logger.debug(f"Failed to send event to client queue: {e}")
                failed_queues.append(queue)

        # Remove failed queues
        for queue in failed_queues:
            self._remove_client_queue(queue)

        if sent_count > 0:
            logger.debug(
                f"Broadcasted {event_type.value} event to {sent_count} clients"
            )

    def subscribe_client(
        self, client_id: Optional[str] = None, send_recent_events: bool = True
    ) -> asyncio.Queue[JobEvent]:
        """Subscribe a new client to events"""
        queue: asyncio.Queue[JobEvent] = asyncio.Queue(maxsize=self.max_queue_size)

        # Store client metadata
        self._client_queue_metadata[queue] = {
            "client_id": client_id or f"client_{len(self._client_queues)}",
            "connected_at": now_utc(),
            "events_sent": 0,
        }

        self._client_queues.append(queue)

        logger.info(
            f"New client subscribed: {self._client_queue_metadata[queue]['client_id']} "
            f"(total clients: {len(self._client_queues)})"
        )

        # Send recent events to new client
        if send_recent_events:
            for event in self._recent_events[-10:]:  # Send last 10 events
                try:
                    queue.put_nowait(event)
                except asyncio.QueueFull:
                    logger.warning("New client queue is already full")
                    break

        return queue

    def unsubscribe_client(self, queue: asyncio.Queue[JobEvent]) -> bool:
        """Unsubscribe a client from events"""
        return self._remove_client_queue(queue)

    def _remove_client_queue(self, queue: asyncio.Queue[JobEvent]) -> bool:
        """Remove a client queue and its metadata"""
        try:
            if queue in self._client_queues:
                self._client_queues.remove(queue)

            if queue in self._client_queue_metadata:
                client_info = self._client_queue_metadata[queue]
                logger.info(f"Client disconnected: {client_info['client_id']}")
                del self._client_queue_metadata[queue]

            return True
        except (ValueError, KeyError):
            return False

    async def stream_events_for_client(
        self, client_queue: asyncio.Queue[JobEvent]
    ) -> AsyncGenerator[JobEvent, None]:
        """Stream events for a specific client"""
        try:
            while not self._shutdown_requested:
                try:
                    # Wait for events with timeout
                    event = await asyncio.wait_for(
                        client_queue.get(), timeout=self.keepalive_timeout
                    )

                    # Update client metadata
                    if client_queue in self._client_queue_metadata:
                        metadata = self._client_queue_metadata[client_queue]
                        if "events_sent" in metadata and isinstance(
                            metadata["events_sent"], int
                        ):
                            metadata["events_sent"] += 1

                    yield event

                except asyncio.TimeoutError:
                    # Send keepalive if no events
                    from borgitory.services.jobs.broadcaster.job_event import JobEvent

                    keepalive_event = JobEvent(
                        event_type=EventType.KEEPALIVE, data={"message": "keepalive"}
                    )
                    yield keepalive_event

        except Exception as e:
            logger.error(f"Error in client event stream: {e}")
        finally:
            # Clean up client on disconnect
            self._remove_client_queue(client_queue)

    async def stream_all_events(self) -> AsyncGenerator[JobEvent, None]:
        """Stream all events for a new client connection"""
        client_queue = self.subscribe_client()

        try:
            async for event in self.stream_events_for_client(client_queue):
                yield event
        finally:
            self.unsubscribe_client(client_queue)

    async def _cleanup_disconnected_clients(self) -> None:
        """Background task to clean up disconnected clients"""
        while not self._shutdown_requested:
            try:
                queues_to_remove = []

                for queue in self._client_queues:
                    # Check if queue is still responsive
                    if queue.full():
                        # Queue is full, likely disconnected
                        queues_to_remove.append(queue)
                        continue

                    # Check connection age and activity
                    if queue in self._client_queue_metadata:
                        metadata = self._client_queue_metadata[queue]
                        connected_at = metadata.get("connected_at")
                        if isinstance(connected_at, datetime):
                            connected_duration = (
                                now_utc() - connected_at
                            ).total_seconds()
                        else:
                            connected_duration = 0

                        # Remove clients with no activity for a long time
                        events_sent = metadata.get("events_sent", 0)
                        if connected_duration > 3600 and events_sent == 0:  # 1 hour
                            queues_to_remove.append(queue)

                # Remove identified queues
                for queue in queues_to_remove:
                    self._remove_client_queue(queue)

                await asyncio.sleep(self.cleanup_interval)

            except Exception as e:
                logger.error(f"Error in client cleanup task: {e}")
                await asyncio.sleep(self.cleanup_interval)

    async def _send_keepalives(self) -> None:
        """Background task to send periodic keepalives"""
        while not self._shutdown_requested:
            try:
                if self._client_queues:
                    self.broadcast_event(
                        EventType.KEEPALIVE,
                        data={
                            "message": "keepalive",
                            "client_count": len(self._client_queues),
                        },
                    )

                await asyncio.sleep(self.keepalive_timeout)

            except Exception as e:
                logger.error(f"Error in keepalive task: {e}")
                await asyncio.sleep(self.keepalive_timeout)

    def subscribe_to_events(self) -> asyncio.Queue[JobEvent]:
        """Subscribe to job events for streaming (compatibility method)"""
        return self.subscribe_client()

    def unsubscribe_from_events(self, queue: asyncio.Queue[JobEvent]) -> None:
        """Unsubscribe from job events (compatibility method)"""
        self.unsubscribe_client(queue)

    def get_client_stats(self) -> Dict[str, object]:
        """Get statistics about connected clients"""
        return {
            "total_clients": len(self._client_queues),
            "client_details": [
                {
                    "client_id": metadata["client_id"],
                    "connected_at": metadata["connected_at"].isoformat()
                    if isinstance(metadata["connected_at"], datetime)
                    else str(metadata["connected_at"]),
                    "events_sent": metadata["events_sent"],
                    "queue_size": queue.qsize(),
                }
                for queue, metadata in self._client_queue_metadata.items()
            ],
            "recent_events_count": len(self._recent_events),
        }

    def get_event_history(self, limit: int = 20) -> List[Dict[str, object]]:
        """Get recent event history"""
        return [event.to_dict() for event in self._recent_events[-limit:]]

    async def shutdown(self) -> None:
        """Shutdown the event broadcaster"""
        logger.info("Shutting down job event broadcaster")
        self._shutdown_requested = True

        # Cancel background tasks
        if self._cleanup_task and not self._cleanup_task.done():
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass

        if self._keepalive_task and not self._keepalive_task.done():
            self._keepalive_task.cancel()
            try:
                await self._keepalive_task
            except asyncio.CancelledError:
                pass

        # Clear all client queues
        self._client_queues.clear()
        self._client_queue_metadata.clear()
        self._recent_events.clear()

        logger.info("Job event broadcaster shutdown complete")


_global_broadcaster: Optional[JobEventBroadcaster] = None


def get_job_event_broadcaster() -> JobEventBroadcaster:
    """Get the global JobEventBroadcaster instance"""
    global _global_broadcaster
    if _global_broadcaster is None:
        _global_broadcaster = JobEventBroadcaster()
    return _global_broadcaster
