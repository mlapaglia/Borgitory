"""Service for processing and formatting upcoming backup jobs."""

from datetime import datetime, timezone
from typing import Any, Dict, List

from .cron_description_service import CronDescriptionService


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

    def __init__(self, cron_description_service: CronDescriptionService):
        self.cron_description_service = cron_description_service

    def process_jobs(self, jobs_raw: List[Dict[str, Any]]) -> List[Dict[str, str]]:
        """Process raw job data into formatted upcoming backup information."""
        processed_jobs = []

        for job in jobs_raw:
            processed_job = self._process_single_job(job)
            if processed_job:
                processed_jobs.append(processed_job)

        return processed_jobs

    def _process_single_job(self, job: Dict[str, Any]) -> Dict[str, str] | None:
        """Process a single job into formatted data."""
        try:
            next_run = self._parse_next_run_time(job.get("next_run"))
            if not next_run:
                return None

            time_until = self._calculate_time_until(next_run)
            cron_description = self.cron_description_service.format_cron_trigger(
                job.get("trigger", "")
            )
            next_run_display = next_run.strftime("%m/%d/%Y, %I:%M:%S %p")

            return {
                "name": job.get("name", "Unknown"),
                "next_run_display": next_run_display,
                "time_until": time_until,
                "cron_description": cron_description,
            }

        except Exception:
            # Log the error in production, but don't break the entire list
            return None

    def _parse_next_run_time(self, next_run_raw: Any) -> datetime | None:
        """Parse next run time from various formats."""
        if not next_run_raw:
            return None

        if isinstance(next_run_raw, datetime):
            return next_run_raw

        if isinstance(next_run_raw, str):
            try:
                return datetime.fromisoformat(next_run_raw.replace("Z", "+00:00"))
            except (ValueError, TypeError):
                try:
                    return datetime.fromisoformat(next_run_raw)
                except (ValueError, TypeError):
                    return None

        return None

    def _calculate_time_until(self, next_run: datetime) -> str:
        """Calculate time until next run."""
        now = datetime.now()
        if next_run.tzinfo:
            now = datetime.now(timezone.utc)

        time_diff_seconds = (next_run - now).total_seconds()
        time_diff_ms = int(time_diff_seconds * 1000)
        return format_time_until(time_diff_ms)
