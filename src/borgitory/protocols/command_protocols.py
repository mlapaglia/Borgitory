"""
Protocol interfaces for command execution services.
"""

from typing import (
    Protocol,
    Dict,
    Optional,
    List,
    Callable,
    TYPE_CHECKING,
    runtime_checkable,
)
import asyncio

if TYPE_CHECKING:
    from sqlalchemy.orm import Session
    from borgitory.services.rclone_service import RcloneService
    from borgitory.services.cloud_providers import StorageFactory
    from borgitory.services.encryption_service import EncryptionService
    from borgitory.services.cloud_providers.registry import ProviderRegistry


class CommandResult:
    """Result of a command execution."""

    def __init__(
        self,
        success: bool,
        return_code: int,
        stdout: str,
        stderr: str,
        duration: float,
        error: Optional[str] = None,
    ):
        self.success = success
        self.return_code = return_code
        self.stdout = stdout
        self.stderr = stderr
        self.duration = duration
        self.error = error


class ProcessResult:
    """Result of a process execution."""

    def __init__(
        self,
        return_code: int,
        stdout: bytes,
        stderr: bytes,
        error: Optional[str] = None,
    ):
        self.return_code = return_code
        self.stdout = stdout
        self.stderr = stderr
        self.error = error


@runtime_checkable
class CommandRunnerProtocol(Protocol):
    """Protocol for command execution services."""

    async def run_command(
        self,
        command: List[str],
        env: Optional[Dict[str, str]] = None,
        timeout: Optional[int] = None,
    ) -> CommandResult:
        """Execute a command and return the result."""
        ...


class ProcessExecutorProtocol(Protocol):
    """Protocol for process execution services."""

    async def start_process(
        self,
        command: List[str],
        env: Optional[Dict[str, str]] = None,
        cwd: Optional[str] = None,
    ) -> asyncio.subprocess.Process:
        """Start a process and return the process handle."""
        ...

    async def monitor_process_output(
        self,
        process: asyncio.subprocess.Process,
        output_callback: Optional[Callable[[str], None]] = None,
        progress_callback: Optional[Callable[[Dict[str, object]], None]] = None,
    ) -> "ProcessResult":
        """Monitor a process and return the result when complete."""
        ...

    async def execute_prune_task(
        self,
        repository_path: str,
        passphrase: str,
        keyfile_content: Optional[str] = None,
        keep_within: Optional[str] = None,
        keep_secondly: Optional[int] = None,
        keep_minutely: Optional[int] = None,
        keep_hourly: Optional[int] = None,
        keep_daily: Optional[int] = None,
        keep_weekly: Optional[int] = None,
        keep_monthly: Optional[int] = None,
        keep_yearly: Optional[int] = None,
        show_stats: bool = True,
        show_list: bool = False,
        save_space: bool = False,
        force_prune: bool = False,
        dry_run: bool = False,
        output_callback: Optional[Callable[[str], None]] = None,
    ) -> "ProcessResult":
        """Execute a borg prune task."""
        ...

    async def execute_cloud_sync_task(
        self,
        repository_path: str,
        cloud_sync_config_id: int,
        db_session_factory: Callable[[], "Session"],
        rclone_service: "RcloneService",
        encryption_service: "EncryptionService",
        storage_factory: "StorageFactory",
        provider_registry: "ProviderRegistry",
        output_callback: Optional[Callable[[str], None]] = None,
    ) -> "ProcessResult":
        """Execute a cloud sync task."""
        ...

    async def terminate_process(
        self, process: asyncio.subprocess.Process, timeout: float = 5.0
    ) -> bool:
        """Terminate a process gracefully."""
        ...
