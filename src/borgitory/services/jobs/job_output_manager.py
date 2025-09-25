"""
Job Output Manager - Handles job output collection, storage, and streaming
"""

import asyncio
import logging
from collections import deque
from typing import Dict, List, Optional, AsyncGenerator
from datetime import datetime
from borgitory.utils.datetime_utils import now_utc
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class OutputLine:
    """Represents a single line of job output"""

    text: str
    timestamp: str
    type: str
    metadata: Dict[str, object] = field(default_factory=dict)

    def get(self, key: str, default: object = None) -> object:
        """Dict-like access for backward compatibility"""
        if key == "text":
            return self.text
        elif key == "timestamp":
            return self.timestamp
        elif key == "type":
            return self.type
        elif key == "metadata":
            return self.metadata
        elif key in self.metadata:
            return self.metadata[key]
        return default

    def __getitem__(self, key: str) -> object:
        """Dict-like access for backward compatibility"""
        result = self.get(key)
        if result is None and key not in ["text", "timestamp", "type", "metadata"]:
            raise KeyError(key)
        return result


# Removed duplicate OutputLine definition - using the one above with dict-like interface


@dataclass
class JobOutput:
    """Container for job output data"""

    job_id: str
    lines: deque[OutputLine] = field(default_factory=deque)
    current_progress: Dict[str, object] = field(default_factory=dict)
    total_lines: int = 0
    max_lines: int = 1000

    def __post_init__(self) -> None:
        """Initialize deque with proper maxlen"""
        if not isinstance(self.lines, deque) or self.lines.maxlen != self.max_lines:
            self.lines = deque(maxlen=self.max_lines)


class JobOutputManager:
    """Manages job output collection, storage, and streaming"""

    def __init__(self, max_lines_per_job: int = 1000) -> None:
        self.max_lines_per_job = max_lines_per_job
        self._job_outputs: Dict[str, JobOutput] = {}
        self._output_locks: Dict[str, asyncio.Lock] = {}

    def create_job_output(self, job_id: str) -> JobOutput:
        """Create output container for a new job"""
        job_output = JobOutput(job_id=job_id, max_lines=self.max_lines_per_job)
        job_output.lines = deque(maxlen=self.max_lines_per_job)

        self._job_outputs[job_id] = job_output
        self._output_locks[job_id] = asyncio.Lock()

        logger.debug(f"Created output container for job {job_id}")
        return job_output

    async def add_output_line(
        self,
        job_id: str,
        text: str,
        line_type: str = "stdout",
        progress_info: Optional[Dict[str, object]] = None,
    ) -> None:
        """Add a line of output to a job"""
        if job_id not in self._job_outputs:
            self.create_job_output(job_id)

        job_output = self._job_outputs[job_id]

        async with self._output_locks[job_id]:
            output_line = OutputLine(
                text=text,
                timestamp=now_utc().isoformat(),
                type=line_type,
                metadata=progress_info or {},
            )

            job_output.lines.append(output_line)

            job_output.total_lines += 1

            # Update current progress if provided
            if progress_info:
                job_output.current_progress.update(progress_info)

    def get_job_output(self, job_id: str) -> Optional[JobOutput]:
        """Get output container for a job"""
        return self._job_outputs.get(job_id)

    async def get_job_output_stream(self, job_id: str) -> Dict[str, object]:
        """Get formatted output data for API responses"""
        job_output = self.get_job_output(job_id)
        if not job_output:
            return {"lines": [], "progress": {}, "total_lines": 0}

        async with self._output_locks.get(job_id, asyncio.Lock()):
            return {
                "lines": list(job_output.lines),
                "progress": job_output.current_progress.copy(),
                "total_lines": job_output.total_lines,
            }

    async def stream_job_output(
        self, job_id: str, follow: bool = True
    ) -> AsyncGenerator[Dict[str, object], None]:
        """Stream job output in real-time"""
        job_output = self.get_job_output(job_id)
        if not job_output:
            logger.warning(f"No output found for job {job_id}")
            return

        last_sent = 0

        while True:
            async with self._output_locks[job_id]:
                current_lines = list(job_output.lines)
                current_progress = job_output.current_progress.copy()

            # Send new lines since last check
            if len(current_lines) > last_sent:
                for line in current_lines[last_sent:]:
                    yield {"type": "output", "data": line, "progress": current_progress}
                last_sent = len(current_lines)

            if not follow:
                break

            # Small delay to prevent busy waiting
            await asyncio.sleep(0.1)

    def get_output_summary(self, job_id: str) -> Dict[str, object]:
        """Get summary of job output"""
        job_output = self.get_job_output(job_id)
        if not job_output:
            return {}

        return {
            "job_id": job_id,
            "total_lines": job_output.total_lines,
            "stored_lines": len(job_output.lines),
            "current_progress": job_output.current_progress.copy(),
            "max_lines": job_output.max_lines,
        }

    def clear_job_output(self, job_id: str) -> bool:
        """Clear output data for a job"""
        if job_id in self._job_outputs:
            del self._job_outputs[job_id]

        if job_id in self._output_locks:
            del self._output_locks[job_id]

        logger.debug(f"Cleared output for job {job_id}")
        return True

    def get_all_job_outputs(self) -> Dict[str, Dict[str, object]]:
        """Get summary of all job outputs"""
        return {job_id: self.get_output_summary(job_id) for job_id in self._job_outputs}

    async def format_output_for_display(
        self,
        job_id: str,
        max_lines: Optional[int] = None,
        filter_type: Optional[str] = None,
    ) -> List[str]:
        """Format job output for display purposes"""
        job_output = self.get_job_output(job_id)
        if not job_output:
            return []

        async with self._output_locks.get(job_id, asyncio.Lock()):
            lines = list(job_output.lines)

        # Filter by type if specified
        if filter_type:
            lines = [line for line in lines if line.get("type") == filter_type]

        # Limit number of lines if specified
        if max_lines:
            lines = lines[-max_lines:]

        return [str(line["text"]) for line in lines]

    def cleanup_old_outputs(self, max_age_seconds: int = 3600) -> int:
        """Clean up old job outputs"""
        current_time = now_utc()
        cleaned_count = 0

        job_ids_to_remove = []

        for job_id, job_output in self._job_outputs.items():
            if not job_output.lines:
                continue

            # Check age of most recent line
            try:
                last_line = list(job_output.lines)[-1]
                timestamp_str = str(last_line["timestamp"])
                last_timestamp = datetime.fromisoformat(timestamp_str)
                age_seconds = (current_time - last_timestamp).total_seconds()

                if age_seconds > max_age_seconds:
                    job_ids_to_remove.append(job_id)
            except (KeyError, ValueError, IndexError) as e:
                logger.debug(f"Error checking age for job {job_id}: {e}")
                job_ids_to_remove.append(job_id)

        # Remove old outputs
        for job_id in job_ids_to_remove:
            self.clear_job_output(job_id)
            cleaned_count += 1

        if cleaned_count > 0:
            logger.info(f"Cleaned up {cleaned_count} old job outputs")

        return cleaned_count
