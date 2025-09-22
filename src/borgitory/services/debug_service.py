import asyncio
import platform
import sys
import os
import logging
from typing import Dict, Optional, TypedDict, List
from sqlalchemy.orm import Session

from borgitory.models.database import Repository, Job
from borgitory.protocols import VolumeServiceProtocol, JobManagerProtocol
from borgitory.protocols.environment_protocol import EnvironmentProtocol

logger = logging.getLogger(__name__)


class SystemInfo(TypedDict, total=False):
    """System information structure"""

    # Success fields
    platform: str
    system: str
    release: str
    version: str
    architecture: str
    processor: str
    hostname: str
    python_version: str
    python_executable: str
    # Error field
    error: str


class ApplicationInfo(TypedDict, total=False):
    """Application information structure"""

    # Success fields
    borgitory_version: Optional[str]
    debug_mode: bool
    startup_time: str
    working_directory: str
    # Error field
    error: str


class DatabaseInfo(TypedDict, total=False):
    """Database information structure"""

    # Success fields
    repository_count: int
    total_jobs: int
    jobs_today: int
    database_type: str
    database_url: str
    database_size: str
    database_size_bytes: int
    # Common fields
    database_accessible: bool
    # Error field
    error: str


class ToolInfo(TypedDict, total=False):
    """Tool version information structure"""

    # Success fields
    version: str
    accessible: bool
    # Error field
    error: str


class VolumeDebugInfo(TypedDict, total=False):
    """Volume debug information structure"""

    # Success fields
    mounted_volumes: List[str]
    total_mounted_volumes: int
    # Error field
    error: str


class JobManagerInfo(TypedDict, total=False):
    """Job manager information structure"""

    # Success fields
    active_jobs: int
    total_jobs: int
    job_manager_running: bool
    # Error/unavailable fields
    error: str
    status: str


class DebugInfo(TypedDict):
    """Comprehensive debug information structure

    Each field contains the specific TypedDict for that section.
    All TypedDicts use total=False to handle error cases with {"error": str}.
    """

    system: SystemInfo
    application: ApplicationInfo
    database: DatabaseInfo
    volumes: VolumeDebugInfo
    tools: Dict[str, ToolInfo]
    environment: Dict[str, str]
    job_manager: JobManagerInfo


class DebugService:
    """Service to gather system and application debug information"""

    def __init__(
        self,
        volume_service: VolumeServiceProtocol,
        job_manager: JobManagerProtocol,
        environment: EnvironmentProtocol,
    ) -> None:
        self.volume_service = volume_service
        self.job_manager = job_manager
        self.environment = environment

    async def get_debug_info(self, db: Session) -> DebugInfo:
        """Gather comprehensive debug information"""
        # Each method now handles its own exceptions and returns the appropriate TypedDict
        debug_info: DebugInfo = {
            "system": await self._get_system_info(),
            "application": await self._get_application_info(),
            "database": self._get_database_info(db),
            "volumes": await self._get_volume_info(),
            "tools": await self._get_tool_versions(),
            "environment": self._get_environment_info(),
            "job_manager": self._get_job_manager_info(),
        }

        return debug_info

    async def _get_system_info(self) -> SystemInfo:
        """Get system information"""
        try:
            system_info: SystemInfo = {
                "platform": platform.platform(),
                "system": platform.system(),
                "release": platform.release(),
                "version": platform.version(),
                "architecture": platform.architecture()[0],
                "processor": platform.processor(),
                "hostname": platform.node(),
                "python_version": sys.version,
                "python_executable": sys.executable,
            }
            return system_info
        except Exception as e:
            logger.error(f"Error getting system info: {str(e)}")
            return {"error": str(e)}

    async def _get_application_info(self) -> ApplicationInfo:
        """Get application information"""
        try:
            app_info: ApplicationInfo = {
                "borgitory_version": self.environment.get_env("BORGITORY_VERSION"),
                "debug_mode": (
                    self.environment.get_env("DEBUG", "false") or "false"
                ).lower()
                == "true",
                "startup_time": self.environment.now_utc().isoformat(),
                "working_directory": self.environment.get_cwd(),
            }
            return app_info
        except Exception as e:
            logger.error(f"Error getting application info: {str(e)}")
            return {"error": str(e)}

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

            return {
                "repository_count": repository_count,
                "total_jobs": total_jobs,
                "jobs_today": recent_jobs,
                "database_type": db_type,
                "database_url": database_url,
                "database_size": database_size,
                "database_size_bytes": database_size_bytes,
                "database_accessible": True,
            }
        except Exception as e:
            return {"error": str(e), "database_accessible": False}

    async def _get_volume_info(self) -> VolumeDebugInfo:
        """Get volume mount information"""
        try:
            volume_info = await self.volume_service.get_volume_info()
            mounted_volumes = volume_info.get("mounted_volumes", [])
            if not isinstance(mounted_volumes, list):
                mounted_volumes = []

            volume_debug_info: VolumeDebugInfo = {
                "mounted_volumes": mounted_volumes,
                "total_mounted_volumes": len(mounted_volumes),
            }
            return volume_debug_info

        except Exception as e:
            error_info: VolumeDebugInfo = {
                "error": str(e),
                "mounted_volumes": [],
                "total_mounted_volumes": 0,
            }
            return error_info

    async def _get_tool_versions(self) -> Dict[str, ToolInfo]:
        """Get versions of external tools"""
        tools: Dict[str, ToolInfo] = {}

        try:
            process = await asyncio.create_subprocess_exec(
                "borg",
                "--version",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, stderr = await process.communicate()

            if process.returncode == 0:
                tools["borg"] = {"version": stdout.decode().strip(), "accessible": True}
            else:
                tools["borg"] = {
                    "error": stderr.decode().strip() if stderr else "Command failed",
                    "accessible": False,
                }
        except Exception as e:
            tools["borg"] = {"error": str(e), "accessible": False}

        try:
            process = await asyncio.create_subprocess_exec(
                "rclone",
                "version",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, stderr = await process.communicate()

            if process.returncode == 0:
                version_output = stdout.decode().strip()
                # Extract just the version line
                version_line = (
                    version_output.split("\n")[0] if version_output else "Unknown"
                )
                tools["rclone"] = {"version": version_line, "accessible": True}
            else:
                tools["rclone"] = {
                    "error": stderr.decode().strip() if stderr else "Not installed",
                    "accessible": False,
                }
        except Exception as e:
            tools["rclone"] = {"error": str(e), "accessible": False}

        try:
            process = await asyncio.create_subprocess_exec(
                "dpkg",
                "-l",
                "fuse3",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, stderr = await process.communicate()

            if process.returncode == 0:
                output = stdout.decode().strip()
                # Parse dpkg output to get version
                lines = output.split("\n")
                for line in lines:
                    if line.startswith("ii") and "fuse3" in line:
                        parts = line.split()
                        if len(parts) >= 3:
                            version = parts[2]
                            tools["fuse3"] = {
                                "version": f"fuse3 {version}",
                                "accessible": True,
                            }
                            break
                else:
                    tools["fuse3"] = {
                        "error": "Package info not found",
                        "accessible": False,
                    }
            else:
                tools["fuse3"] = {
                    "error": stderr.decode().strip()
                    if stderr
                    else "Package not installed",
                    "accessible": False,
                }
        except Exception as e:
            tools["fuse3"] = {"error": str(e), "accessible": False}

        try:
            process = await asyncio.create_subprocess_exec(
                "dpkg",
                "-l",
                "python3-pyfuse3",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, stderr = await process.communicate()

            if process.returncode == 0:
                output = stdout.decode().strip()
                # Parse dpkg output to get version
                lines = output.split("\n")
                for line in lines:
                    if line.startswith("ii") and "python3-pyfuse3" in line:
                        parts = line.split()
                        if len(parts) >= 3:
                            version = parts[2]
                            tools["python3-pyfuse3"] = {
                                "version": f"python3-pyfuse3 {version}",
                                "accessible": True,
                            }
                            break
                else:
                    tools["python3-pyfuse3"] = {
                        "error": "Package info not found",
                        "accessible": False,
                    }
            else:
                tools["python3-pyfuse3"] = {
                    "error": stderr.decode().strip()
                    if stderr
                    else "Package not installed",
                    "accessible": False,
                }
        except Exception as e:
            tools["python3-pyfuse3"] = {"error": str(e), "accessible": False}

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

            return {
                "active_jobs": active_jobs_count,
                "total_jobs": total_jobs,
                "job_manager_running": True,
            }
        except Exception as e:
            return {"error": str(e), "job_manager_running": False}
