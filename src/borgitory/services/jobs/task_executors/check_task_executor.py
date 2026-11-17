"""
Check Task Executor - Handles repository check task execution
"""

import logging
from datetime import timedelta
from typing import Dict, List, Mapping, Optional
from borgitory.protocols.command_protocols import ProcessExecutorProtocol
from borgitory.protocols.job_event_broadcaster_protocol import (
    JobEventBroadcasterProtocol,
)
from borgitory.protocols.job_output_manager_protocol import JobOutputManagerProtocol
from borgitory.protocols.job_database_manager_protocol import JobDatabaseManagerProtocol
from borgitory.utils.datetime_utils import now_utc
from borgitory.services.repositories.repository_environment import (
    build_repository_env_overrides_from_data,
)
from borgitory.utils.security import create_borg_command
from borgitory.services.jobs.job_models import BorgJob, BorgJobTask, TaskStatusEnum

logger = logging.getLogger(__name__)

# Slack when comparing job start times, so a cron job firing a moment earlier than
# the one N days ago still counts as due
CHECK_FREQUENCY_GRACE = timedelta(hours=1)


def _positive_int(value: object) -> Optional[int]:
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        return None
    try:
        number = int(value)
    except ValueError:
        return None
    return number if number > 0 else None


def build_check_args(params: Mapping[str, object]) -> List[str]:
    """Translate check task parameters into `borg check` options.

    Accepts the keys emitted by TaskDefinitionBuilder (check_type, repair_mode, ...)
    as well as the older repository_only/archives_only/repair booleans.
    """
    args: List[str] = []

    check_type = params.get("check_type")
    check_type = getattr(check_type, "value", check_type)

    if check_type == "repository_only" or params.get("repository_only"):
        args.append("--repository-only")
    elif check_type == "archives_only" or params.get("archives_only"):
        args.append("--archives-only")

    if params.get("verify_data"):
        args.append("--verify-data")
    if params.get("repair_mode") or params.get("repair"):
        args.append("--repair")
    if params.get("save_space"):
        args.append("--save-space")

    max_duration = _positive_int(params.get("max_duration"))
    if max_duration is not None:
        args.extend(["--max-duration", str(max_duration)])

    archive_glob = params.get("archive_glob")
    archive_prefix = params.get("archive_prefix")
    if isinstance(archive_glob, str) and archive_glob:
        args.extend(["--glob-archives", archive_glob])
    elif isinstance(archive_prefix, str) and archive_prefix:
        # --prefix is deprecated in borg 1.2+; a prefix is the glob "<prefix>*"
        args.extend(["--glob-archives", f"{archive_prefix}*"])

    first_n = _positive_int(params.get("first_n_archives"))
    last_n = _positive_int(params.get("last_n_archives"))
    if first_n is not None:
        args.extend(["--first", str(first_n)])
    elif last_n is not None:
        args.extend(["--last", str(last_n)])

    return args


class CheckTaskExecutor:
    """Handles repository check task execution"""

    def __init__(
        self,
        job_executor: ProcessExecutorProtocol,
        output_manager: JobOutputManagerProtocol,
        event_broadcaster: JobEventBroadcasterProtocol,
        database_manager: JobDatabaseManagerProtocol,
    ):
        self.job_executor = job_executor
        self.output_manager = output_manager
        self.event_broadcaster = event_broadcaster
        self.database_manager = database_manager

    async def _frequency_skip_reason(
        self, job: BorgJob, params: Mapping[str, object]
    ) -> Optional[str]:
        """Why the check isn't due yet, or None when it should run.

        A policy with frequency_days runs only when the last job that checked this
        repository successfully with the same policy started at least that many days
        before this job (less a small grace for scheduler jitter). Failed checks don't
        count, so a failure is retried on the next run.
        """
        frequency_days = _positive_int(params.get("frequency_days"))
        check_config_id = _positive_int(params.get("check_config_id"))
        if frequency_days is None or check_config_id is None or not job.repository_id:
            return None

        last_check = await self.database_manager.get_last_successful_check_job_start(
            job.repository_id, check_config_id
        )
        if last_check is None:
            return None

        next_due = last_check + timedelta(days=frequency_days)
        if job.started_at >= next_due - CHECK_FREQUENCY_GRACE:
            return None

        return (
            f"Check skipped: policy runs at most every {frequency_days} "
            f"day{'s' if frequency_days != 1 else ''}. Last successful check was in a "
            f"job started {last_check:%Y-%m-%d %H:%M} UTC; next due from "
            f"{next_due:%Y-%m-%d %H:%M} UTC."
        )

    async def execute_check_task(
        self, job: BorgJob, task: BorgJobTask, task_index: int = 0
    ) -> bool:
        """Execute a repository check task"""
        try:
            params = task.parameters

            if job.repository_id is None:
                task.status = TaskStatusEnum.FAILED
                task.error = "Repository ID is missing"
                return False
            repo_data = await self.database_manager.get_repository_data(
                job.repository_id
            )
            if not repo_data:
                task.status = TaskStatusEnum.FAILED
                task.return_code = 1
                task.error = "Repository not found"
                task.completed_at = now_utc()
                return False

            skip_reason = await self._frequency_skip_reason(job, params)
            if skip_reason:
                logger.info(f"Skipping check task for job {job.id}: {skip_reason}")
                task.status = TaskStatusEnum.SKIPPED
                task.completed_at = now_utc()
                task.output_lines.append(skip_reason)
                self.output_manager.append_output_line(
                    job.id, skip_reason, "stdout", {}
                )
                return True

            repository_path = repo_data.get("path") or params.get("repository_path")
            passphrase = str(
                repo_data.get("passphrase") or params.get("passphrase") or ""
            )
            keyfile_content = repo_data.get("keyfile_content")
            if keyfile_content is not None and not isinstance(keyfile_content, str):
                keyfile_content = None  # Ensure it's str or None

            def task_output_callback(line: str) -> None:
                task.output_lines.append(line)
                # Provide default progress since callback now only receives line
                progress: Dict[str, object] = {}
                self.output_manager.append_output_line(job.id, line, "stdout", progress)

            additional_args = build_check_args(params)

            if repository_path:
                additional_args.append(str(repository_path))

            environment_overrides = build_repository_env_overrides_from_data(repo_data)
            if "--repair" in additional_args:
                # Without this borg asks for interactive confirmation and the job hangs
                environment_overrides["BORG_CHECK_I_KNOW_WHAT_I_AM_DOING"] = "YES"

            borg_command = create_borg_command(
                base_command="borg check",
                repository_path="",  # Already in additional_args
                passphrase=passphrase,
                additional_args=additional_args,
                environment_overrides=environment_overrides,
            )
            process = await self.job_executor.start_process(
                borg_command.command, borg_command.environment
            )

            result = await self.job_executor.monitor_process_output(
                process, output_callback=task_output_callback
            )

            task.return_code = result.return_code
            task.status = (
                TaskStatusEnum.COMPLETED
                if result.return_code == 0
                else TaskStatusEnum.FAILED
            )
            task.completed_at = now_utc()

            if result.stdout:
                full_output = result.stdout.decode("utf-8", errors="replace").strip()
                if full_output:
                    for line in full_output.split("\n"):
                        if line.strip():
                            task.output_lines.append(line)
                            self.output_manager.append_output_line(
                                job.id, line, "stdout", {}
                            )

            if result.error:
                task.error = result.error
            elif result.return_code != 0:
                if result.stdout:
                    output_text = result.stdout.decode(
                        "utf-8", errors="replace"
                    ).strip()
                    error_lines = output_text.split("\n")[-5:] if output_text else []
                    stderr_text = (
                        "\n".join(error_lines) if error_lines else "No output captured"
                    )
                else:
                    stderr_text = "No output captured"
                task.error = (
                    f"Check failed with return code {result.return_code}: {stderr_text}"
                )

            return bool(result.return_code == 0)

        except Exception as e:
            logger.error(f"Error executing check task for job {job.id}: {str(e)}")
            task.status = TaskStatusEnum.FAILED
            task.return_code = 1
            task.error = str(e)
            task.completed_at = now_utc()
            return False
