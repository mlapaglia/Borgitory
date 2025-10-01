import platform
import subprocess
import sys
import os
import logging
from typing import Dict, Optional
from sqlalchemy.orm import Session
from importlib.metadata import version, PackageNotFoundError

from borgitory.models.database import Repository, Job
from borgitory.protocols import JobManagerProtocol
from borgitory.protocols.environment_protocol import EnvironmentProtocol
from borgitory.protocols.command_executor_protocol import CommandExecutorProtocol

logger = logging.getLogger(__name__)


class SystemInfo:
    """System information structure"""

    def __init__(self) -> None:
        # Success fields
        self.platform: str = ""
        self.system: str = ""
        self.release: str = ""
        self.version: str = ""
        self.architecture: str = ""
        self.processor: str = ""
        self.hostname: str = ""
        self.python_version: str = ""
        self.python_executable: str = ""
        # Error field
        self.error: str = ""


class ApplicationInfo:
    """Application information structure"""

    def __init__(self) -> None:
        # Success fields
        self.borgitory_version: Optional[str] = None
        self.debug_mode: bool = False
        self.startup_time: str = ""
        self.working_directory: str = ""
        # Error field
        self.error: str = ""


class DatabaseInfo:
    """Database information structure"""

    def __init__(self) -> None:
        # Success fields
        self.repository_count: int = 0
        self.total_jobs: int = 0
        self.jobs_today: int = 0
        self.database_type: str = ""
        self.database_url: str = ""
        self.database_size: str = ""
        self.database_size_bytes: int = 0
        # Common fields
        self.database_accessible: bool = False
        # Error field
        self.error: str = ""


class ToolInfo:
    """Tool version information structure"""

    def __init__(self) -> None:
        # Success fields
        self.version: str = ""
        self.accessible: bool = False
        # Error field
        self.error: str = ""


class JobManagerInfo:
    """Job manager information structure"""

    def __init__(self) -> None:
        # Success fields
        self.active_jobs: int = 0
        self.total_jobs: int = 0
        self.job_manager_running: bool = False
        # Error/unavailable fields
        self.error: str = ""
        self.status: str = ""


class WSLInfo:
    """WSL (Windows Subsystem for Linux) information structure"""

    def __init__(self) -> None:
        # Success fields
        self.wsl_available: bool = False
        self.wsl_version: str = ""
        self.default_distribution: str = ""
        self.installed_distributions: list[str] = []
        self.wsl_kernel_version: str = ""
        self.windows_version: str = ""
        self.wsl_path_accessible: bool = False
        self.mount_points: list[str] = []
        # Error field
        self.error: str = ""


class DebugInfo:
    """Comprehensive debug information structure"""

    def __init__(self) -> None:
        self.system: SystemInfo = SystemInfo()
        self.application: ApplicationInfo = ApplicationInfo()
        self.database: DatabaseInfo = DatabaseInfo()
        self.tools: Dict[str, ToolInfo] = {}
        self.environment: Dict[str, str] = {}
        self.job_manager: JobManagerInfo = JobManagerInfo()
        self.wsl: WSLInfo = WSLInfo()


class DebugService:
    """Service to gather system and application debug information"""

    def __init__(
        self,
        job_manager: JobManagerProtocol,
        environment: EnvironmentProtocol,
        command_executor: CommandExecutorProtocol,
    ) -> None:
        self.job_manager = job_manager
        self.environment = environment
        self.command_executor = command_executor

    def _get_borgitory_version(self) -> str:
        """Get Borgitory version from package metadata"""
        try:
            return version("borgitory")
        except PackageNotFoundError:
            return "unknown"

    async def _run_command(
        self, command: list[str], timeout: float = 30.0
    ) -> tuple[int, str, str]:
        """
        Run command using WSL executor on Windows or direct subprocess on other platforms.

        Args:
            command: Command to run
            timeout: Command timeout

        Returns:
            Tuple of (return_code, stdout, stderr)
        """
        result = await self.command_executor.execute_command(command, timeout=timeout)
        return result.return_code, result.stdout, result.stderr

    async def get_debug_info(self, db: Session) -> DebugInfo:
        """Gather comprehensive debug information"""
        debug_info = DebugInfo()
        debug_info.system = await self._get_system_info()
        debug_info.application = await self._get_application_info()
        debug_info.database = self._get_database_info(db)
        debug_info.tools = await self._get_tool_versions()
        debug_info.environment = self._get_environment_info()
        debug_info.job_manager = self._get_job_manager_info()
        debug_info.wsl = await self._get_wsl_info()

        return debug_info

    async def _get_system_info(self) -> SystemInfo:
        """Get system information"""
        system_info = SystemInfo()
        try:
            system_info.platform = platform.platform()
            system_info.system = platform.system()
            system_info.release = platform.release()
            system_info.version = platform.version()
            system_info.architecture = platform.architecture()[0]
            system_info.processor = platform.processor()
            system_info.hostname = platform.node()
            system_info.python_version = sys.version
            system_info.python_executable = sys.executable
            return system_info
        except Exception as e:
            logger.error(f"Error getting system info: {str(e)}")
            system_info.error = str(e)
            return system_info

    async def _get_application_info(self) -> ApplicationInfo:
        """Get application information"""
        app_info = ApplicationInfo()
        try:
            app_info.borgitory_version = self._get_borgitory_version()
            debug_env = self.environment.get_env("DEBUG", "false") or "false"
            app_info.debug_mode = debug_env.lower() == "true"
            app_info.startup_time = self.environment.now_utc().isoformat()
            app_info.working_directory = self.environment.get_cwd()
            return app_info
        except Exception as e:
            logger.error(f"Error getting application info: {str(e)}")
            app_info.error = str(e)
            return app_info

    def _get_database_info(self, db: Session) -> DatabaseInfo:
        """Get database information"""
        try:
            database_url = self.environment.get_database_url()

            repository_count = db.query(Repository).count()
            total_jobs = db.query(Job).count()
            # Use started_at instead of created_at for Job model
            today_start = self.environment.now_utc().replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            recent_jobs = db.query(Job).filter(Job.started_at >= today_start).count()

            # Get database file size (for SQLite)
            database_size = "Unknown"
            database_size_bytes = 0
            try:
                if database_url.startswith("sqlite:///"):
                    # Extract file path from SQLite URL (sqlite:///path/to/file.db)
                    db_path = database_url[10:]  # Remove "sqlite:///" prefix
                    if os.path.exists(db_path):
                        database_size_bytes = os.path.getsize(db_path)
                        # Convert to human readable format
                        if database_size_bytes < 1024:
                            database_size = f"{database_size_bytes} B"
                        elif database_size_bytes < 1024 * 1024:
                            database_size = f"{database_size_bytes / 1024:.1f} KB"
                        elif database_size_bytes < 1024 * 1024 * 1024:
                            database_size = (
                                f"{database_size_bytes / (1024 * 1024):.1f} MB"
                            )
                        else:
                            database_size = (
                                f"{database_size_bytes / (1024 * 1024 * 1024):.1f} GB"
                            )
                    else:
                        database_size = f"File not found: {db_path}"
                elif database_url.startswith("sqlite://"):
                    # Handle relative path format (sqlite://path/to/file.db)
                    db_path = database_url[9:]  # Remove "sqlite://" prefix
                    if os.path.exists(db_path):
                        database_size_bytes = os.path.getsize(db_path)
                        # Convert to human readable format
                        if database_size_bytes < 1024:
                            database_size = f"{database_size_bytes} B"
                        elif database_size_bytes < 1024 * 1024:
                            database_size = f"{database_size_bytes / 1024:.1f} KB"
                        elif database_size_bytes < 1024 * 1024 * 1024:
                            database_size = (
                                f"{database_size_bytes / (1024 * 1024):.1f} MB"
                            )
                        else:
                            database_size = (
                                f"{database_size_bytes / (1024 * 1024 * 1024):.1f} GB"
                            )
                    else:
                        database_size = f"File not found: {db_path}"
            except Exception as size_error:
                database_size = f"Error: {str(size_error)}"

            # Determine database type from URL
            if database_url.startswith("sqlite"):
                db_type = "SQLite"
            elif database_url.startswith("postgresql"):
                db_type = "PostgreSQL"
            elif database_url.startswith("mysql"):
                db_type = "MySQL"
            else:
                db_type = "Unknown"

            db_info = DatabaseInfo()
            db_info.repository_count = repository_count
            db_info.total_jobs = total_jobs
            db_info.jobs_today = recent_jobs
            db_info.database_type = db_type
            db_info.database_url = database_url
            db_info.database_size = database_size
            db_info.database_size_bytes = database_size_bytes
            db_info.database_accessible = True
            return db_info
        except Exception as e:
            db_info = DatabaseInfo()
            db_info.error = str(e)
            db_info.database_accessible = False
            return db_info

    async def _get_tool_versions(self) -> Dict[str, ToolInfo]:
        """Get versions of external tools"""
        tools: Dict[str, ToolInfo] = {}

        try:
            return_code, stdout, stderr = await self._run_command(["borg", "--version"])

            if return_code == 0:
                borg_info = ToolInfo()
                borg_info.version = stdout.strip()
                borg_info.accessible = True
                tools["borg"] = borg_info
            else:
                borg_info = ToolInfo()
                borg_info.error = stderr.strip() if stderr else "Command failed"
                borg_info.accessible = False
                tools["borg"] = borg_info
        except Exception as e:
            borg_info = ToolInfo()
            borg_info.error = str(e)
            borg_info.accessible = False
            tools["borg"] = borg_info

        try:
            return_code, stdout, stderr = await self._run_command(["rclone", "version"])

            if return_code == 0:
                version_output = stdout.strip()
                # Extract just the version line
                version_line = (
                    version_output.split("\n")[0] if version_output else "Unknown"
                )
                rclone_info = ToolInfo()
                rclone_info.version = version_line
                rclone_info.accessible = True
                tools["rclone"] = rclone_info
            else:
                rclone_info = ToolInfo()
                rclone_info.error = stderr.strip() if stderr else "Not installed"
                rclone_info.accessible = False
                tools["rclone"] = rclone_info
        except Exception as e:
            rclone_info = ToolInfo()
            rclone_info.error = str(e)
            rclone_info.accessible = False
            tools["rclone"] = rclone_info

        try:
            return_code, stdout, stderr = await self._run_command(
                ["dpkg", "-l", "fuse3"]
            )

            if return_code == 0:
                output = stdout.strip()
                # Parse dpkg output to get version
                lines = output.split("\n")
                for line in lines:
                    if line.startswith("ii") and "fuse3" in line:
                        parts = line.split()
                        if len(parts) >= 3:
                            version = parts[2]
                            fuse3_info = ToolInfo()
                            fuse3_info.version = f"fuse3 {version}"
                            fuse3_info.accessible = True
                            tools["fuse3"] = fuse3_info
                            break
                else:
                    fuse3_info = ToolInfo()
                    fuse3_info.error = "Package info not found"
                    fuse3_info.accessible = False
                    tools["fuse3"] = fuse3_info
            else:
                fuse3_info = ToolInfo()
                fuse3_info.error = stderr.strip() if stderr else "Package not installed"
                fuse3_info.accessible = False
                tools["fuse3"] = fuse3_info
        except Exception as e:
            fuse3_info = ToolInfo()
            fuse3_info.error = str(e)
            fuse3_info.accessible = False
            tools["fuse3"] = fuse3_info

        return tools

    def _get_environment_info(self) -> Dict[str, str]:
        """Get environment variables (sanitized)"""
        try:
            env_info: Dict[str, str] = {}

            # List of environment variables that are safe to display
            safe_env_vars = [
                "PATH",
                "HOME",
                "USER",
                "SHELL",
                "LANG",
                "LC_ALL",
                "PYTHONPATH",
                "VIRTUAL_ENV",
                "CONDA_DEFAULT_ENV",
                "DATABASE_URL",
                "DEBUG",
            ]

            for var in safe_env_vars:
                value = self.environment.get_env(var)
                if value:
                    # Sanitize sensitive information
                    if (
                        "PASSWORD" in var.upper()
                        or "SECRET" in var.upper()
                        or "KEY" in var.upper()
                    ):
                        env_info[var] = "***HIDDEN***"
                    elif var == "DATABASE_URL" and "sqlite" not in value.lower():
                        # Hide connection details for non-sqlite databases
                        env_info[var] = "***HIDDEN***"
                    else:
                        env_info[var] = value

            return env_info
        except Exception as e:
            logger.error(f"Error getting environment info: {str(e)}")
            return {"error": str(e)}

    def _get_job_manager_info(self) -> JobManagerInfo:
        """Get job manager information"""
        try:
            # Count active jobs by checking job statuses
            active_jobs_count = 0
            total_jobs = (
                len(self.job_manager.jobs) if hasattr(self.job_manager, "jobs") else 0
            )

            if hasattr(self.job_manager, "jobs"):
                for job in self.job_manager.jobs.values():
                    if hasattr(job, "status") and job.status == "running":
                        active_jobs_count += 1

            job_info = JobManagerInfo()
            job_info.active_jobs = active_jobs_count
            job_info.total_jobs = total_jobs
            job_info.job_manager_running = True
            return job_info
        except Exception as e:
            job_info = JobManagerInfo()
            job_info.error = str(e)
            job_info.job_manager_running = False
            return job_info

    async def _get_wsl_info(self) -> WSLInfo:
        """Get comprehensive WSL (Windows Subsystem for Linux) information"""
        wsl_info = WSLInfo()

        try:
            # Check if we're on Windows first
            os_env = self.environment.get_env("OS", "") or ""
            if not os_env.startswith("Windows") and platform.system() != "Windows":
                wsl_info.error = "Not running on Windows - WSL not applicable"
                return wsl_info

            # Check if WSL is available
            try:
                # Check WSL by reading /proc/version (we're running inside WSL)
                return_code, stdout, stderr = await self._run_command(
                    ["cat", "/proc/version"]
                )

                if return_code == 0:
                    proc_version = stdout.strip()

                    # Check if this is WSL
                    if (
                        "microsoft" in proc_version.lower()
                        or "wsl" in proc_version.lower()
                    ):
                        wsl_info.wsl_available = True

                        # Parse WSL version from /proc/version
                        # Example: "Linux version 6.6.87.2-microsoft-standard-WSL2"
                        if "wsl2" in proc_version.lower():
                            wsl_info.wsl_version = "WSL 2"
                        elif "microsoft" in proc_version.lower():
                            wsl_info.wsl_version = "WSL"
                        else:
                            wsl_info.wsl_version = "WSL (unknown version)"

                        # Get distribution info from /etc/os-release
                        try:
                            (
                                distro_return_code,
                                distro_stdout,
                                distro_stderr,
                            ) = await self._run_command(["cat", "/etc/os-release"])

                            if distro_return_code == 0:
                                for line in distro_stdout.split("\n"):
                                    if line.startswith("PRETTY_NAME="):
                                        distro_name = (
                                            line.split("=", 1)[1].strip().strip('"')
                                        )
                                        wsl_info.default_distribution = distro_name
                                        break
                                else:
                                    wsl_info.default_distribution = (
                                        "Unknown Linux Distribution"
                                    )
                            else:
                                wsl_info.default_distribution = (
                                    "Unknown Linux Distribution"
                                )
                        except Exception:
                            wsl_info.default_distribution = "Unknown Linux Distribution"
                else:
                    wsl_info.error = f"WSL not available: {stderr.strip()}"
                    return wsl_info

            except FileNotFoundError:
                wsl_info.error = "WSL command not found - WSL not installed"
                return wsl_info
            except Exception as e:
                wsl_info.error = f"Error checking WSL status: {str(e)}"
                return wsl_info

            # Get list of installed distributions
            try:
                return_code, stdout, stderr = await self._run_command(
                    ["wsl.exe", "-l", "-v"]
                )

                if return_code == 0:
                    distro_output = stdout.strip()
                    distributions = []
                    lines = distro_output.split("\n")
                    for line in lines[1:]:  # Skip header line
                        if line.strip():
                            # Parse WSL list output (format: NAME STATE VERSION)
                            # Remove null characters and extra whitespace
                            clean_line = line.replace("\x00", "").strip()
                            if clean_line:
                                parts = clean_line.split()
                                if parts:
                                    distro_name = (
                                        parts[0].replace("*", "").strip()
                                    )  # Remove default marker
                                    if distro_name and distro_name not in [
                                        "NAME",
                                        "Windows",
                                        "Subsystem",
                                    ]:
                                        distributions.append(distro_name)
                    wsl_info.installed_distributions = distributions

            except Exception as e:
                logger.warning(f"Could not get WSL distributions: {e}")

            # Get WSL kernel version
            try:
                return_code, stdout, stderr = await self._run_command(
                    ["wsl", "--version"]
                )

                if return_code == 0:
                    version_output = stdout.strip()
                    for line in version_output.split("\n"):
                        if "WSL version:" in line:
                            wsl_info.wsl_version = line.split(":", 1)[1].strip()
                        elif "Kernel version:" in line:
                            wsl_info.wsl_kernel_version = line.split(":", 1)[1].strip()

            except Exception as e:
                logger.warning(f"Could not get WSL version details: {e}")

            # Get Windows version for compatibility info
            wsl_info.windows_version = self._get_windows_version()

            # Test WSL path accessibility
            try:
                # Try to access /mnt directory which should contain Windows drives
                return_code, stdout, stderr = await self._run_command(["ls", "/mnt"])

                if return_code == 0:
                    wsl_info.wsl_path_accessible = True
                    # Parse mount points
                    mount_output = stdout.strip()
                    mount_points = []
                    for line in mount_output.split("\n"):
                        if line.strip():
                            mount_points.append(f"/mnt/{line.strip()}")
                    wsl_info.mount_points = mount_points
                else:
                    wsl_info.wsl_path_accessible = False
                    logger.warning(f"WSL path access failed: {stderr.strip()}")

            except Exception as e:
                wsl_info.wsl_path_accessible = False
                logger.warning(f"Could not test WSL path accessibility: {e}")

            return wsl_info

        except Exception as e:
            wsl_info.error = f"Unexpected error gathering WSL info: {str(e)}"
            logger.error(f"Error in _get_wsl_info: {e}")
            return wsl_info

    def _get_windows_version(self) -> str:
        """Get Windows version information using cross-platform methods."""
        try:
            # Method 1: Use platform.platform() which works cross-platform
            platform_info = platform.platform()
            if "Windows" in platform_info:
                return platform_info

            # Method 2: Try subprocess to get Windows version (if on Windows)
            if platform.system() == "Windows":
                try:
                    result = subprocess.run(
                        ["cmd", "/c", "ver"], capture_output=True, text=True, timeout=5
                    )
                    if result.returncode == 0 and result.stdout:
                        # Extract version from output like "Microsoft Windows [Version 10.0.19045.5011]"
                        version_line = result.stdout.strip()
                        if "Version" in version_line:
                            return version_line
                except Exception:
                    pass

                # Method 3: Try systeminfo command
                try:
                    result = subprocess.run(
                        ["systeminfo", "/fo", "csv"],
                        capture_output=True,
                        text=True,
                        timeout=10,
                    )
                    if result.returncode == 0 and result.stdout:
                        lines = result.stdout.split("\n")
                        if len(lines) >= 2:
                            # Parse CSV output to get OS Name and Version
                            headers = lines[0].split(",")
                            values = lines[1].split(",")
                            for i, header in enumerate(headers):
                                if "OS Name" in header and i < len(values):
                                    os_name = values[i].strip('"')
                                    return os_name
                except Exception:
                    pass

            # Fallback to basic platform info
            return f"{platform.system()} {platform.release()}"

        except Exception as e:
            logger.warning(f"Could not get Windows version: {e}")
            return "Unknown"
