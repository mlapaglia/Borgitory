from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Optional

from borgitory.custom_types import ConfigDict
from borgitory.services.jobs.broadcaster.event_type import EventType
from borgitory.utils.datetime_utils import now_utc


@dataclass
class JobEvent:
    """Represents a job event"""

    event_type: EventType
    job_id: Optional[str] = None
    data: Optional[ConfigDict] = None
    timestamp: Optional[datetime] = None

    def __post_init__(self) -> None:
        if self.timestamp is None:
            self.timestamp = now_utc()
        if self.data is None:
            self.data = {}

    def to_dict(self) -> Dict[str, object]:
        """Convert event to dictionary format"""
        return {
            "type": self.event_type.value,
            "job_id": self.job_id,
            "data": self.data,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
        }

    def get(self, key: str, default: object = None) -> object:
        """Dict-like access for backward compatibility"""
        if key == "job_id":
            return self.job_id
        elif key == "type":
            return self.event_type.value
        elif key == "timestamp":
            return self.timestamp.isoformat() if self.timestamp else None
        elif key == "data":
            return self.data
        elif self.data and key in self.data:
            return self.data[key]
        return default

    def __getitem__(self, key: str) -> object:
        """Dict-like access for backward compatibility"""
        # Handle integer keys by converting to string (for cases like event[0])
        if isinstance(key, int):
            raise TypeError("JobEvent indices must be strings, not integers")

        result = self.get(key)
        if (
            result is None
            and key not in ["job_id", "data", "timestamp"]
            and (not self.data or key not in self.data)
        ):
            raise KeyError(key)
        return result

    def __contains__(self, key: str) -> bool:
        """Dict-like 'in' operator for backward compatibility"""
        if key in ["job_id", "type", "timestamp", "data"]:
            return True
        if self.data and key in self.data:
            return True
        return False
