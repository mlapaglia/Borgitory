"""
Protocol for JobEventBroadcaster - defines the interface for event broadcasting
"""

import asyncio
from typing import Dict, List, AsyncGenerator, Optional, Protocol
import uuid

from borgitory.custom_types import ConfigDict
from borgitory.services.jobs.broadcaster.event_type import EventType
from borgitory.services.jobs.broadcaster.job_event import JobEvent


class JobEventBroadcasterProtocol(Protocol):
    """Protocol defining the interface for job event broadcasting"""

    def broadcast_event(
        self,
        event_type: EventType,
        job_id: Optional[uuid.UUID] = None,
        data: Optional[ConfigDict] = None,
    ) -> None:
        """Broadcast an event to all connected clients"""
        ...

    def subscribe_client(
        self, client_id: Optional[str] = None, send_recent_events: bool = True
    ) -> asyncio.Queue[JobEvent]:
        """Subscribe a new client to events"""
        ...

    def unsubscribe_client(self, queue: asyncio.Queue[JobEvent]) -> bool:
        """Unsubscribe a client from events"""
        ...

    def stream_events_for_client(
        self, client_queue: asyncio.Queue[JobEvent]
    ) -> AsyncGenerator[JobEvent, None]:
        """Stream events for a specific client"""
        ...

    def stream_all_events(self) -> AsyncGenerator[JobEvent, None]:
        """Stream all events for a new client connection"""
        ...

    def subscribe_to_events(self) -> asyncio.Queue[JobEvent]:
        """Subscribe to job events for streaming (compatibility method)"""
        ...

    def unsubscribe_from_events(self, queue: asyncio.Queue[JobEvent]) -> None:
        """Unsubscribe from job events (compatibility method)"""
        ...

    def get_client_stats(self) -> Dict[str, object]:
        """Get statistics about connected clients"""
        ...

    def get_event_history(self, limit: int = 20) -> List[Dict[str, object]]:
        """Get recent event history"""
        ...

    async def initialize(self) -> None:
        """Initialize background tasks"""
        ...

    async def shutdown(self) -> None:
        """Shutdown the event broadcaster"""
        ...
