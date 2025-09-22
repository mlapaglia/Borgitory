"""Service for processing and formatting upcoming backup jobs."""

from datetime import datetime
from typing import Dict, List, Union

from .cron_description_service import CronDescriptionService
from borgitory.utils.datetime_utils import parse_datetime_string, now_utc


def format_time_until(time_diff_ms: int) -> str:
    """Format time difference in milliseconds to human readable string."""
    if time_diff_ms < 0:
        return "Overdue"

    seconds = time_diff_ms // 1000
    minutes = seconds // 60
    hours = minutes // 60
    days = hours // 24

    if days > 0:
        return f"{days}d {hours % 24}h"
    elif hours > 0:
        return f"{hours}h {minutes % 60}m"
    elif minutes > 0:
        remaining_seconds = seconds % 60
        return f"{minutes}m {remaining_seconds}s"
    else:
        return f"{seconds}s"


class UpcomingBackupsService:
    """Service for processing upcoming backup job data."""

    def __init__(self, cron_description_service: CronDescriptionService) -> None:
        self.cron_description_service = cron_description_service

    def process_jobs(self, jobs_raw: List[Dict[str, object]]) -> List[Dict[str, str]]:
        """Process raw job data into formatted upcoming backup information."""
        processed_jobs = []

        for job in jobs_raw:
            processed_job = self._process_single_job(job)
            if processed_job:
                processed_jobs.append(processed_job)

        return processed_jobs

    def _process_single_job(self, job: Dict[str, object]) -> Dict[str, str] | None:
        """Process a single job into formatted data."""
        try:
            next_run_val = job.get("next_run")
            if isinstance(next_run_val, (str, datetime)) or next_run_val is None:
                next_run = self._parse_next_run_time(next_run_val)
            else:
                next_run = None
            if not next_run:
                return None

            time_until = self._calculate_time_until(next_run)
            trigger_val = job.get("trigger", "")
            cron_description = self.cron_description_service.format_cron_trigger(
                str(trigger_val)
            )
            next_run_display = next_run.strftime("%m/%d/%Y, %I:%M:%S %p")

            name_val = job.get("name", "Unknown")
            return {
                "name": str(name_val),
                "next_run_display": next_run_display,
                "time_until": time_until,
                "cron_description": cron_description,
            }

        except Exception:
            # Log the error in production, but don't break the entire list
            return None

    def _parse_next_run_time(
        self, next_run_raw: Union[str, datetime, None]
    ) -> datetime | None:
        """Parse next run time from various formats."""
        if not next_run_raw:
            return None

        if isinstance(next_run_raw, datetime):
            return next_run_raw

        if isinstance(next_run_raw, str):
            return parse_datetime_string(next_run_raw)

        return None

    def _calculate_time_until(self, next_run: datetime) -> str:
        """Calculate time until next run."""
        now = datetime.now()
        if next_run.tzinfo:
            now = now_utc()

        time_diff_seconds = (next_run - now).total_seconds()
        time_diff_ms = int(time_diff_seconds * 1000)
        return format_time_until(time_diff_ms)
