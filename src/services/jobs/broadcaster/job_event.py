from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Optional

from services.jobs.broadcaster.event_type import EventType


@dataclass
class JobEvent:
    """Represents a job event"""

    event_type: EventType
    job_id: Optional[str] = None
    data: Dict[str, Any] = None
    timestamp: datetime = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()
        if self.data is None:
            self.data = {}

    def to_dict(self) -> Dict[str, Any]:
        """Convert event to dictionary format"""
        return {
            "type": self.event_type.value,
            "job_id": self.job_id,
            "data": self.data,
            "timestamp": self.timestamp.isoformat(),
        }
