"""
Recovery service for handling crashed or interrupted backup jobs.

This service handles cleanup when the application restarts after being
shut down or crashed while backup jobs were running.
"""

import logging

from borgitory.models.database import Repository
from borgitory.utils.datetime_utils import now_utc
from borgitory.utils.security import secure_borg_command
from borgitory.utils.db_session import get_db_session
import asyncio

logger = logging.getLogger(__name__)


class RecoveryService:
    """Service to recover from application crashes during backup operations"""

    async def recover_stale_jobs(self) -> None:
        """
        Find backup jobs that were running when the app was shut down and clean them up.
        This should be called on application startup.

        All backup operations (manual and scheduled) use the job system.
        Legacy jobs are only used for utility operations (scan, list archives, etc.)
        which don't need recovery - they can simply be re-run if needed.
        """
        logger.info("Starting recovery: checking for interrupted jobs...")

        await self.recover_database_job_records()

        logger.info(
            "Recovery complete - all interrupted backup jobs cancelled and locks released"
        )

    async def recover_database_job_records(self) -> None:
        """
        Find database Job records that are marked as 'running' and mark them as failed.
        This handles the case where the app restarted and jobs are cleared from memory,
        but database records still show 'running' status.
        """
        try:
            logger.info("Checking database for interrupted job records...")

            with get_db_session() as db:
                from borgitory.models.database import Job, JobTask

                # Find all jobs in database marked as running or pending (interrupted before completion)
                interrupted_jobs = (
                    db.query(Job).filter(Job.status.in_(["running", "pending"])).all()
                )

                if not interrupted_jobs:
                    logger.info("No interrupted database job records found")
                    return

                logger.info(
                    f"Found {len(interrupted_jobs)} interrupted database job records"
                )

                for job in interrupted_jobs:
                    logger.info(
                        f"Cancelling database job record {job.id} ({job.job_type}) - was running since {job.started_at}"
                    )

                    # Mark job as failed
                    job.status = "failed"
                    job.finished_at = now_utc()
                    job.error = f"Error: Job cancelled on startup - was running when application shut down (started: {job.started_at})"

                    # Mark all running tasks as failed
                    running_tasks = (
                        db.query(JobTask)
                        .filter(
                            JobTask.job_id == job.id,
                            JobTask.status.in_(["pending", "running", "in_progress"]),
                        )
                        .all()
                    )

                    for task in running_tasks:
                        task.status = "failed"
                        task.completed_at = now_utc()
                        task.error = "Task cancelled on startup - job was interrupted by application shutdown"
                        logger.info(f"  Task '{task.task_name}' marked as failed")

                    # Release repository lock if this was a backup job
                    if (
                        job.job_type in ["manual_backup", "scheduled_backup", "backup"]
                        and job.repository_id
                    ):
                        repository = (
                            db.query(Repository)
                            .filter(Repository.id == job.repository_id)
                            .first()
                        )
                        if repository:
                            logger.info(
                                f"Releasing repository lock for: {repository.name}"
                            )
                            await self._release_repository_lock(repository)
                        else:
                            logger.warning(
                                f"Repository {job.repository_id} not found in database for job {job.id}"
                            )
                    else:
                        logger.debug(
                            f"Job {job.id} is not a backup job or has no repository_id - skipping lock release"
                        )

                logger.info("All interrupted database job records cancelled")

        except Exception as e:
            logger.error(f"Error recovering database job records: {e}")

    async def _release_repository_lock(self, repository: Repository) -> None:
        """Use borg break-lock to release any stale locks on a repository"""
        try:
            logger.info(f"Attempting to release lock on repository: {repository.name}")

            async with secure_borg_command(
                base_command="borg break-lock",
                repository_path=repository.path,
                passphrase=repository.get_passphrase(),
                keyfile_content=repository.get_keyfile_content(),
                additional_args=[],
            ) as (command, env, _):
                # Execute the break-lock command with a timeout
                process = await asyncio.create_subprocess_exec(
                    *command,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    env=env,
                )

                try:
                    stdout, stderr = await asyncio.wait_for(
                        process.communicate(), timeout=30
                    )

                    if process.returncode == 0:
                        logger.info(
                            f"Successfully released lock on repository: {repository.name}"
                        )
                    else:
                        # Log the error but don't fail - lock might not exist
                        stderr_text = stderr.decode() if stderr else "No error details"
                        logger.warning(
                            f"Break-lock returned {process.returncode} for {repository.name}: {stderr_text}"
                        )

                except asyncio.TimeoutError:
                    logger.warning(
                        f"Break-lock timed out for repository: {repository.name}"
                    )
                    process.kill()

        except Exception as e:
            logger.error(f"Error releasing lock for repository {repository.name}: {e}")
