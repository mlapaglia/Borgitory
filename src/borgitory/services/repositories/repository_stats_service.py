import asyncio
import json
import logging
from abc import ABC, abstractmethod
from typing import Dict, List, Callable, Optional, TypedDict
from sqlalchemy.orm import Session

from borgitory.models.database import Repository
from borgitory.utils.datetime_utils import now_utc
from borgitory.utils.security import secure_borg_command

logger = logging.getLogger(__name__)


# TypedDict definitions for repository statistics
class FileTypeTimelineData(TypedDict):
    """Internal structure for file type timeline data"""

    labels: List[str]
    count_data: Dict[str, List[int]]
    size_data: Dict[str, List[float]]


class ArchiveInfo(TypedDict, total=False):
    """Individual archive information structure"""

    # Success fields
    name: str
    start: str
    end: str
    duration: float
    original_size: int
    compressed_size: int
    deduplicated_size: int
    nfiles: int
    unique_chunks: int
    total_chunks: int
    unique_size: int
    total_size: int


class ChartDatasetRequired(TypedDict):
    """Required fields for Chart dataset"""

    label: str
    data: List[float]
    borderColor: str
    backgroundColor: str
    fill: bool


class ChartDataset(ChartDatasetRequired, total=False):
    """Chart dataset structure for Chart.js with optional fields"""

    yAxisID: str
    borderWidth: int
    type: str
    pointRadius: int


class TimelineChartData(TypedDict):
    """Timeline chart data structure"""

    labels: List[str]
    datasets: List[ChartDataset]


class DedupCompressionChartData(TypedDict):
    """Deduplication and compression chart data structure"""

    labels: List[str]
    datasets: List[ChartDataset]


class FileTypeChartData(TypedDict):
    """File type chart data structure"""

    count_chart: TimelineChartData
    size_chart: TimelineChartData


class ExecutionTimeStats(TypedDict):
    """Job execution time statistics structure"""

    task_type: str
    average_duration_minutes: float
    total_executions: int
    min_duration_minutes: float
    max_duration_minutes: float


class ExecutionTimeChartData(TypedDict):
    """Chart data for execution times"""

    labels: List[str]
    datasets: List[ChartDataset]


class SuccessFailureStats(TypedDict):
    """Success/failure statistics structure"""

    task_type: str
    successful_count: int
    failed_count: int
    success_rate: float


class SuccessFailureChartData(TypedDict):
    """Chart data for success/failure rates"""

    labels: List[str]
    datasets: List[ChartDataset]


class TimelineSuccessFailureData(TypedDict):
    """Timeline data for success/failure over time"""

    labels: List[str]
    datasets: List[ChartDataset]


class SummaryStats(TypedDict):
    """Summary statistics structure"""

    total_archives: int
    latest_archive_date: str
    total_original_size_gb: float
    total_compressed_size_gb: float
    total_deduplicated_size_gb: float
    overall_compression_ratio: float
    overall_deduplication_ratio: float
    space_saved_gb: float
    average_archive_size_gb: float


class RepositoryStats(TypedDict, total=False):
    """Complete repository statistics structure"""

    # Success fields
    repository_path: str
    total_archives: int
    archive_stats: List[ArchiveInfo]
    size_over_time: TimelineChartData
    dedup_compression_stats: DedupCompressionChartData
    file_type_stats: FileTypeChartData
    execution_time_stats: List[ExecutionTimeStats]
    execution_time_chart: ExecutionTimeChartData
    success_failure_stats: List[SuccessFailureStats]
    success_failure_chart: SuccessFailureChartData
    timeline_success_failure: TimelineSuccessFailureData
    summary: SummaryStats
    # Error field
    error: str


class CommandExecutorInterface(ABC):
    """Abstract interface for executing Borg commands"""

    @abstractmethod
    async def execute_borg_list(self, repository: Repository) -> List[str]:
        """Execute borg list command to get archive names"""
        pass

    @abstractmethod
    async def execute_borg_info(
        self, repository: Repository, archive_name: str
    ) -> ArchiveInfo:
        """Execute borg info command to get archive details"""
        pass

    @abstractmethod
    async def execute_borg_list_files(
        self, repository: Repository, archive_name: str
    ) -> List[Dict[str, object]]:
        """Execute borg list command to get file details from an archive"""
        pass


class SubprocessCommandExecutor(CommandExecutorInterface):
    """Concrete implementation using subprocess for command execution"""

    async def execute_borg_list(self, repository: Repository) -> List[str]:
        """Execute borg list command to get archive names"""
        try:
            async with secure_borg_command(
                base_command="borg list",
                repository_path=str(repository.path),
                passphrase=repository.get_passphrase(),
                keyfile_content=repository.get_keyfile_content(),
                additional_args=["--short"],
            ) as (command, env, _):
                process = await asyncio.create_subprocess_exec(
                    *command,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    env=env,
                )
                stdout, stderr = await process.communicate()
                if process.returncode == 0:
                    archives = [
                        line.strip()
                        for line in stdout.decode().strip().split("\n")
                        if line.strip()
                    ]
                    return archives
                else:
                    logger.error(f"Failed to list archives: {stderr.decode()}")
                    return []
        except Exception as e:
            logger.error(f"Exception while listing archives: {e}")
            return []

    async def execute_borg_info(
        self, repository: Repository, archive_name: str
    ) -> ArchiveInfo:
        """Execute borg info command to get archive details"""
        try:
            async with secure_borg_command(
                base_command="borg info",
                repository_path="",
                passphrase=repository.get_passphrase(),
                keyfile_content=repository.get_keyfile_content(),
                additional_args=["--json", f"{repository.path}::{archive_name}"],
            ) as (command, env, _):
                process = await asyncio.create_subprocess_exec(
                    *command,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    env=env,
                )
                stdout, stderr = await process.communicate()
                if process.returncode == 0:
                    info_data = json.loads(stdout.decode())
                    archive_info = info_data.get("archives", [{}])[0]
                    result: ArchiveInfo = {
                        "name": archive_info.get("name", archive_name),
                        "start": archive_info.get("start", ""),
                        "end": archive_info.get("end", ""),
                        "duration": archive_info.get("duration", 0),
                        "original_size": archive_info.get("stats", {}).get(
                            "original_size", 0
                        ),
                        "compressed_size": archive_info.get("stats", {}).get(
                            "compressed_size", 0
                        ),
                        "deduplicated_size": archive_info.get("stats", {}).get(
                            "deduplicated_size", 0
                        ),
                        "nfiles": archive_info.get("stats", {}).get("nfiles", 0),
                    }
                    return result
                else:
                    logger.error(f"Failed to get archive info: {stderr.decode()}")
                    return {}
        except Exception as e:
            logger.error(f"Exception while getting archive info: {e}")
            return {}

    async def execute_borg_list_files(
        self, repository: Repository, archive_name: str
    ) -> List[Dict[str, object]]:
        """Execute borg list command to get file details from an archive"""
        try:
            async with secure_borg_command(
                base_command="borg list",
                repository_path="",
                passphrase=repository.get_passphrase(),
                keyfile_content=repository.get_keyfile_content(),
                additional_args=["--json-lines", f"{repository.path}::{archive_name}"],
            ) as (command, env, _):
                process = await asyncio.create_subprocess_exec(
                    *command,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    env=env,
                )
                stdout, stderr = await process.communicate()
                if process.returncode == 0:
                    files = []
                    for line in stdout.decode().strip().split("\n"):
                        if line.strip():
                            try:
                                file_info = json.loads(line)
                                files.append(file_info)
                            except json.JSONDecodeError:
                                continue
                    return files
                else:
                    logger.error(f"Failed to list files: {stderr.decode()}")
                    return []
        except Exception as e:
            logger.error(f"Exception while listing files: {e}")
            return []


class RepositoryStatsService:
    """Service to gather repository statistics from Borg commands"""

    def __init__(
        self, command_executor: Optional[CommandExecutorInterface] = None
    ) -> None:
        self.command_executor = command_executor or SubprocessCommandExecutor()

    async def get_repository_statistics(
        self,
        repository: Repository,
        db: Session,
        progress_callback: Optional[Callable[[str, int], None]] = None,
    ) -> RepositoryStats:
        """Gather comprehensive repository statistics"""
        try:
            if progress_callback:
                progress_callback("Initializing repository analysis...", 5)

            # Get list of all archives
            if progress_callback:
                progress_callback("Scanning repository for archives...", 10)
            archives = await self.command_executor.execute_borg_list(repository)
            if not archives:
                return {"error": "No archives found in repository"}

            if progress_callback:
                progress_callback(
                    f"Found {len(archives)} archives. Analyzing archive details...", 15
                )

            # Get detailed info for each archive
            archive_stats = []
            for i, archive in enumerate(archives):
                if progress_callback:
                    # Progress from 15% to 60% during archive analysis
                    archive_progress = 15 + int((i / len(archives)) * 45)
                    progress_callback(
                        f"Analyzing archive {i + 1}/{len(archives)}: {archive}",
                        archive_progress,
                    )
                archive_info = await self.command_executor.execute_borg_info(
                    repository, archive
                )
                if archive_info:
                    archive_stats.append(archive_info)

            if not archive_stats:
                return {"error": "Could not retrieve archive information"}

            # Sort archives by date
            archive_stats.sort(key=lambda x: str(x.get("start", "")))

            if progress_callback:
                progress_callback("Building size and compression statistics...", 65)

            # Get file type statistics
            if progress_callback:
                progress_callback("Analyzing file types and extensions...", 70)
            file_type_stats = await self._get_file_type_stats(
                repository, archives, progress_callback
            )

            if progress_callback:
                progress_callback("Calculating job execution time statistics...", 80)

            # Get execution time statistics
            execution_time_stats = await self._get_execution_time_stats(repository, db)
            execution_time_chart = self._build_execution_time_chart(
                execution_time_stats
            )

            if progress_callback:
                progress_callback("Calculating success/failure statistics...", 85)

            # Get success/failure statistics
            success_failure_stats = await self._get_success_failure_stats(
                repository, db
            )
            success_failure_chart = self._build_success_failure_chart(
                success_failure_stats
            )
            timeline_success_failure = await self._get_timeline_success_failure_data(
                repository, db
            )

            if progress_callback:
                progress_callback("Finalizing statistics and building charts...", 90)

            # Build statistics
            stats: RepositoryStats = {
                "repository_path": repository.path,
                "total_archives": len(archive_stats),
                "archive_stats": archive_stats,
                "size_over_time": self._build_size_timeline(archive_stats),
                "dedup_compression_stats": self._build_dedup_compression_stats(
                    archive_stats
                ),
                "file_type_stats": file_type_stats,
                "execution_time_stats": execution_time_stats,
                "execution_time_chart": execution_time_chart,
                "success_failure_stats": success_failure_stats,
                "success_failure_chart": success_failure_chart,
                "timeline_success_failure": timeline_success_failure,
                "summary": self._build_summary_stats(archive_stats),
            }

            if progress_callback:
                progress_callback("Statistics analysis complete!", 100)

            return stats

        except Exception as e:
            logger.error(f"Error getting repository statistics: {str(e)}")
            return {"error": str(e)}

    async def _get_archive_list(self, repository: Repository) -> List[str]:
        """Get list of all archives in repository"""
        return await self.command_executor.execute_borg_list(repository)

    async def _get_archive_info(
        self, repository: Repository, archive_name: str
    ) -> Dict[str, object] | None:
        """Get detailed information for a specific archive"""
        try:
            archive_info = await self.command_executor.execute_borg_info(
                repository, archive_name
            )
            if archive_info:
                # Convert ArchiveInfo to the dict format expected by this method
                return {
                    "name": archive_info.get("name", archive_name),
                    "start": archive_info.get("start", ""),
                    "end": archive_info.get("end", ""),
                    "duration": archive_info.get("duration", 0),
                    "original_size": archive_info.get("original_size", 0),
                    "compressed_size": archive_info.get("compressed_size", 0),
                    "deduplicated_size": archive_info.get("deduplicated_size", 0),
                    "nfiles": archive_info.get("nfiles", 0),
                    "unique_chunks": archive_info.get("unique_chunks", 0),
                    "total_chunks": archive_info.get("total_chunks", 0),
                    "unique_size": archive_info.get("unique_size", 0),
                    "total_size": archive_info.get("total_size", 0),
                }
            return None
        except Exception as e:
            logger.error(f"Error getting archive info for {archive_name}: {str(e)}")
            return None

    def _build_size_timeline(
        self, archive_stats: List[ArchiveInfo]
    ) -> TimelineChartData:
        """Build size over time data for charting"""
        timeline_data: TimelineChartData = {
            "labels": [],
            "datasets": [
                {
                    "label": "Original Size",
                    "data": [],
                    "borderColor": "rgb(59, 130, 246)",
                    "backgroundColor": "rgba(59, 130, 246, 0.1)",
                    "fill": False,
                },
                {
                    "label": "Compressed Size",
                    "data": [],
                    "borderColor": "rgb(16, 185, 129)",
                    "backgroundColor": "rgba(16, 185, 129, 0.1)",
                    "fill": False,
                },
                {
                    "label": "Deduplicated Size",
                    "data": [],
                    "borderColor": "rgb(245, 101, 101)",
                    "backgroundColor": "rgba(245, 101, 101, 0.1)",
                    "fill": False,
                },
            ],
        }

        for archive in archive_stats:
            # Use archive name or start time as label
            label = str(archive.get("start", archive.get("name", "")))[
                :10
            ]  # First 10 chars for date
            timeline_data["labels"].append(label)

            # Convert bytes to MB for better readability
            timeline_data["datasets"][0]["data"].append(
                float(archive.get("original_size", 0) or 0) / (1024 * 1024)
            )
            timeline_data["datasets"][1]["data"].append(
                float(archive.get("compressed_size", 0) or 0) / (1024 * 1024)
            )
            timeline_data["datasets"][2]["data"].append(
                float(archive.get("deduplicated_size", 0) or 0) / (1024 * 1024)
            )

        return timeline_data

    def _build_dedup_compression_stats(
        self, archive_stats: List[ArchiveInfo]
    ) -> DedupCompressionChartData:
        """Build deduplication and compression statistics"""
        dedup_data: DedupCompressionChartData = {
            "labels": [],
            "datasets": [
                {
                    "label": "Compression Ratio %",
                    "data": [],
                    "borderColor": "rgb(139, 92, 246)",
                    "backgroundColor": "rgba(139, 92, 246, 0.1)",
                    "fill": False,
                    "yAxisID": "y",
                },
                {
                    "label": "Deduplication Ratio %",
                    "data": [],
                    "borderColor": "rgb(245, 158, 11)",
                    "backgroundColor": "rgba(245, 158, 11, 0.1)",
                    "fill": False,
                    "yAxisID": "y1",
                },
            ],
        }

        for archive in archive_stats:
            label = archive.get("start", archive.get("name", ""))[:10]
            dedup_data["labels"].append(label)

            # Calculate compression ratio
            original = archive.get("original_size", 0)
            compressed = archive.get("compressed_size", 0)
            compression_ratio = (
                ((original - compressed) / original * 100) if original > 0 else 0
            )

            # Calculate deduplication ratio
            deduplicated = archive.get("deduplicated_size", 0)
            dedup_ratio = (
                ((compressed - deduplicated) / compressed * 100)
                if compressed > 0
                else 0
            )

            dedup_data["datasets"][0]["data"].append(round(compression_ratio, 2))
            dedup_data["datasets"][1]["data"].append(round(dedup_ratio, 2))

        return dedup_data

    async def _get_file_type_stats(
        self,
        repository: Repository,
        archives: List[str],
        progress_callback: Optional[Callable[[str, int], None]] = None,
    ) -> FileTypeChartData:
        """Get file type statistics over time"""
        file_type_timeline: FileTypeTimelineData = {
            "labels": [],
            "count_data": {},
            "size_data": {},
        }

        # Limit to recent archives for performance (last 10)
        recent_archives = archives[-10:] if len(archives) > 10 else archives

        for i, archive_name in enumerate(recent_archives):
            if progress_callback:
                # Progress from 70% to 85% during file type analysis
                file_progress = 70 + int((i / len(recent_archives)) * 15)
                progress_callback(
                    f"Analyzing file types in archive {i + 1}/{len(recent_archives)}: {archive_name}",
                    file_progress,
                )
            try:
                # Get file listing with sizes
                async with secure_borg_command(
                    base_command="borg list",
                    repository_path="",
                    passphrase=repository.get_passphrase(),
                    keyfile_content=repository.get_keyfile_content(),
                    additional_args=[
                        f"{repository.path}::{archive_name}",
                        "--format={size} {path}{NL}",
                    ],
                ) as (command, env, _):
                    process = await asyncio.create_subprocess_exec(
                        *command,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE,
                        env=env,
                    )

                    stdout, stderr = await process.communicate()

                    if process.returncode == 0:
                        # Parse file types and sizes
                        ext_count: Dict[str, int] = {}
                        ext_size: Dict[str, int] = {}

                        for line in stdout.decode().strip().split("\n"):
                            if not line.strip():
                                continue
                            parts = line.strip().split(" ", 1)
                            if len(parts) == 2:
                                try:
                                    size = int(parts[0])
                                    path = parts[1]

                                    # Extract file extension
                                    if "." in path and not path.endswith("/"):
                                        ext = path.split(".")[-1].lower()
                                        if (
                                            ext and len(ext) <= 10
                                        ):  # Reasonable extension length
                                            ext_count[ext] = ext_count.get(ext, 0) + 1
                                            ext_size[ext] = ext_size.get(ext, 0) + size
                                except (ValueError, IndexError):
                                    continue

                        # Add to timeline
                        archive_date = (
                            archive_name.split("backup-")[-1][:10]
                            if "backup-" in archive_name
                            else archive_name[:10]
                        )
                        file_type_timeline["labels"].append(archive_date)

                        # Store data for each extension
                        for ext in ext_count:
                            if ext not in file_type_timeline["count_data"]:
                                file_type_timeline["count_data"][ext] = []
                                file_type_timeline["size_data"][ext] = []
                            file_type_timeline["count_data"][ext].append(ext_count[ext])
                            file_type_timeline["size_data"][ext].append(
                                round(ext_size[ext] / (1024 * 1024), 2)
                            )  # Convert to MB

                        # Fill missing data points for consistency
                        for ext in file_type_timeline["count_data"]:
                            while len(file_type_timeline["count_data"][ext]) < len(
                                file_type_timeline["labels"]
                            ):
                                file_type_timeline["count_data"][ext].insert(-1, 0)
                                file_type_timeline["size_data"][ext].insert(-1, 0)

            except Exception as e:
                logger.error(
                    f"Error analyzing file types for archive {archive_name}: {str(e)}"
                )
                continue

        return self._build_file_type_chart_data(file_type_timeline)

    def _build_file_type_chart_data(
        self, timeline_data: FileTypeTimelineData
    ) -> FileTypeChartData:
        """Build chart data for file types"""
        # Color palette for different file types
        colors = [
            "rgb(59, 130, 246)",  # Blue
            "rgb(16, 185, 129)",  # Green
            "rgb(245, 101, 101)",  # Red
            "rgb(139, 92, 246)",  # Purple
            "rgb(245, 158, 11)",  # Yellow
            "rgb(236, 72, 153)",  # Pink
            "rgb(14, 165, 233)",  # Light Blue
            "rgb(34, 197, 94)",  # Light Green
            "rgb(168, 85, 247)",  # Violet
            "rgb(251, 146, 60)",  # Orange
        ]

        # Get top 10 extensions by average size
        avg_sizes = {}
        for ext, sizes in timeline_data["size_data"].items():
            if sizes:
                avg_sizes[ext] = sum(sizes) / len(sizes)

        top_extensions = sorted(avg_sizes.items(), key=lambda x: x[1], reverse=True)[
            :10
        ]

        count_datasets: List[ChartDataset] = []
        size_datasets: List[ChartDataset] = []

        for i, (ext, _) in enumerate(top_extensions):
            color = colors[i % len(colors)]

            count_datasets.append(
                {
                    "label": f".{ext} files",
                    "data": [float(x) for x in timeline_data["count_data"][ext]],
                    "borderColor": color,
                    "backgroundColor": color.replace("rgb", "rgba").replace(
                        ")", ", 0.1)"
                    ),
                    "fill": False,
                }
            )

            size_datasets.append(
                {
                    "label": f".{ext} size (MB)",
                    "data": timeline_data["size_data"][ext],
                    "borderColor": color,
                    "backgroundColor": color.replace("rgb", "rgba").replace(
                        ")", ", 0.1)"
                    ),
                    "fill": False,
                }
            )

        result: FileTypeChartData = {
            "count_chart": {
                "labels": timeline_data["labels"],
                "datasets": count_datasets,
            },
            "size_chart": {
                "labels": timeline_data["labels"],
                "datasets": size_datasets,
            },
        }
        return result

    def _build_summary_stats(self, archive_stats: List[ArchiveInfo]) -> SummaryStats:
        """Build overall summary statistics"""
        if not archive_stats:
            return {
                "total_archives": 0,
                "latest_archive_date": "",
                "total_original_size_gb": 0.0,
                "total_compressed_size_gb": 0.0,
                "total_deduplicated_size_gb": 0.0,
                "overall_compression_ratio": 0.0,
                "overall_deduplication_ratio": 0.0,
                "space_saved_gb": 0.0,
                "average_archive_size_gb": 0.0,
            }

        latest_archive = archive_stats[-1]
        total_original = sum(
            archive.get("original_size", 0) for archive in archive_stats
        )
        total_compressed = sum(
            archive.get("compressed_size", 0) for archive in archive_stats
        )
        total_deduplicated = sum(
            archive.get("deduplicated_size", 0) for archive in archive_stats
        )

        summary: SummaryStats = {
            "total_archives": len(archive_stats),
            "latest_archive_date": latest_archive.get("start", ""),
            "total_original_size_gb": round(total_original / (1024**3), 2),
            "total_compressed_size_gb": round(total_compressed / (1024**3), 2),
            "total_deduplicated_size_gb": round(total_deduplicated / (1024**3), 2),
            "overall_compression_ratio": round(
                ((total_original - total_compressed) / total_original * 100), 2
            )
            if total_original > 0
            else 0,
            "overall_deduplication_ratio": round(
                ((total_compressed - total_deduplicated) / total_compressed * 100), 2
            )
            if total_compressed > 0
            else 0,
            "space_saved_gb": round(
                (total_original - total_deduplicated) / (1024**3), 2
            ),
            "average_archive_size_gb": round(
                (total_original / len(archive_stats)) / (1024**3), 2
            )
            if archive_stats
            else 0,
        }
        return summary

    async def _get_execution_time_stats(
        self, repository: Repository, db: Session
    ) -> List[ExecutionTimeStats]:
        """Calculate execution time statistics for different task types"""
        from borgitory.models.database import Job, JobTask
        from sqlalchemy import and_
        from collections import defaultdict

        try:
            # Query completed jobs and tasks for this repository
            completed_tasks = (
                db.query(JobTask.task_type, JobTask.started_at, JobTask.completed_at)
                .join(Job, Job.id == JobTask.job_id)
                .filter(
                    and_(
                        Job.repository_id == repository.id,
                        JobTask.status == "completed",
                        JobTask.started_at.isnot(None),
                        JobTask.completed_at.isnot(None),
                    )
                )
                .all()
            )

            # Group by task type and calculate durations in Python
            task_durations = defaultdict(list)
            for task in completed_tasks:
                if task.started_at and task.completed_at:
                    # Calculate duration in minutes
                    duration = (
                        task.completed_at - task.started_at
                    ).total_seconds() / 60.0
                    # Only include positive durations (completed_at > started_at)
                    if duration > 0:
                        task_durations[task.task_type].append(duration)

            execution_stats: List[ExecutionTimeStats] = []
            for task_type, durations in task_durations.items():
                if durations:  # Only include task types with valid durations
                    stat_entry: ExecutionTimeStats = {
                        "task_type": task_type,
                        "average_duration_minutes": round(
                            sum(durations) / len(durations), 2
                        ),
                        "total_executions": len(durations),
                        "min_duration_minutes": round(min(durations), 2),
                        "max_duration_minutes": round(max(durations), 2),
                    }
                    execution_stats.append(stat_entry)

            return execution_stats

        except Exception as e:
            logger.error(f"Error calculating execution time stats: {str(e)}")
            return []

    def _build_execution_time_chart(
        self, execution_stats: List[ExecutionTimeStats]
    ) -> ExecutionTimeChartData:
        """Build execution time chart data"""
        if not execution_stats:
            return {"labels": [], "datasets": []}

        # Sort by average duration for better visualization
        sorted_stats = sorted(
            execution_stats, key=lambda x: x["average_duration_minutes"], reverse=True
        )

        # Color palette for different task types
        colors = [
            "rgb(59, 130, 246)",  # Blue - backup
            "rgb(16, 185, 129)",  # Green - cloud_sync
            "rgb(245, 101, 101)",  # Red - prune
            "rgb(139, 92, 246)",  # Purple - check
            "rgb(245, 158, 11)",  # Yellow - notification
            "rgb(236, 72, 153)",  # Pink - hook
            "rgb(14, 165, 233)",  # Light Blue
            "rgb(34, 197, 94)",  # Light Green
            "rgb(168, 85, 247)",  # Violet
            "rgb(251, 146, 60)",  # Orange
        ]

        labels = [stat["task_type"].replace("_", " ").title() for stat in sorted_stats]
        avg_data = [stat["average_duration_minutes"] for stat in sorted_stats]
        min_data = [stat["min_duration_minutes"] for stat in sorted_stats]
        max_data = [stat["max_duration_minutes"] for stat in sorted_stats]

        datasets: List[ChartDataset] = [
            {
                "label": "Average Duration (minutes)",
                "data": avg_data,
                "borderColor": colors[0],
                "backgroundColor": colors[0]
                .replace("rgb", "rgba")
                .replace(")", ", 0.2)"),
                "fill": False,
                "borderWidth": 2,
                "type": "bar",
            },
            {
                "label": "Min Duration (minutes)",
                "data": min_data,
                "borderColor": colors[1],
                "backgroundColor": colors[1]
                .replace("rgb", "rgba")
                .replace(")", ", 0.1)"),
                "fill": False,
                "type": "line",
                "pointRadius": 4,
            },
            {
                "label": "Max Duration (minutes)",
                "data": max_data,
                "borderColor": colors[2],
                "backgroundColor": colors[2]
                .replace("rgb", "rgba")
                .replace(")", ", 0.1)"),
                "fill": False,
                "type": "line",
                "pointRadius": 4,
            },
        ]

        chart_data: ExecutionTimeChartData = {"labels": labels, "datasets": datasets}

        return chart_data

    async def _get_success_failure_stats(
        self, repository: Repository, db: Session
    ) -> List[SuccessFailureStats]:
        """Calculate success/failure statistics for different task types"""
        from borgitory.models.database import Job, JobTask
        from sqlalchemy import and_
        from collections import defaultdict

        try:
            # Query all completed and failed tasks for this repository
            task_results = (
                db.query(JobTask.task_type, JobTask.status)
                .join(Job, Job.id == JobTask.job_id)
                .filter(
                    and_(
                        Job.repository_id == repository.id,
                        JobTask.status.in_(["completed", "failed"]),
                    )
                )
                .all()
            )

            # Group by task type and count successes/failures
            task_counts: defaultdict[str, dict[str, int]] = defaultdict(
                lambda: {"successful": 0, "failed": 0}
            )
            for task in task_results:
                if task.status == "completed":
                    task_counts[task.task_type]["successful"] += 1
                elif task.status == "failed":
                    task_counts[task.task_type]["failed"] += 1

            success_failure_stats: List[SuccessFailureStats] = []
            for task_type, counts in task_counts.items():
                total = counts["successful"] + counts["failed"]
                success_rate = (counts["successful"] / total * 100) if total > 0 else 0

                stat_entry: SuccessFailureStats = {
                    "task_type": task_type,
                    "successful_count": counts["successful"],
                    "failed_count": counts["failed"],
                    "success_rate": round(success_rate, 2),
                }
                success_failure_stats.append(stat_entry)

            return success_failure_stats

        except Exception as e:
            logger.error(f"Error calculating success/failure stats: {str(e)}")
            return []

    def _build_success_failure_chart(
        self, success_failure_stats: List[SuccessFailureStats]
    ) -> SuccessFailureChartData:
        """Build success/failure rate chart data"""
        if not success_failure_stats:
            return {"labels": [], "datasets": []}

        # Sort by success rate for better visualization
        sorted_stats = sorted(
            success_failure_stats, key=lambda x: x["success_rate"], reverse=True
        )

        labels = [stat["task_type"].replace("_", " ").title() for stat in sorted_stats]
        successful_data = [float(stat["successful_count"]) for stat in sorted_stats]
        failed_data = [float(stat["failed_count"]) for stat in sorted_stats]
        success_rate_data = [stat["success_rate"] for stat in sorted_stats]

        datasets: List[ChartDataset] = [
            {
                "label": "Successful",
                "data": successful_data,
                "borderColor": "rgb(34, 197, 94)",
                "backgroundColor": "rgba(34, 197, 94, 0.8)",
                "fill": False,
                "type": "bar",
            },
            {
                "label": "Failed",
                "data": failed_data,
                "borderColor": "rgb(239, 68, 68)",
                "backgroundColor": "rgba(239, 68, 68, 0.8)",
                "fill": False,
                "type": "bar",
            },
            {
                "label": "Success Rate (%)",
                "data": success_rate_data,
                "borderColor": "rgb(59, 130, 246)",
                "backgroundColor": "rgba(59, 130, 246, 0.1)",
                "fill": False,
                "type": "line",
                "yAxisID": "y1",
                "pointRadius": 4,
            },
        ]

        chart_data: SuccessFailureChartData = {"labels": labels, "datasets": datasets}

        return chart_data

    async def _get_timeline_success_failure_data(
        self, repository: Repository, db: Session
    ) -> TimelineSuccessFailureData:
        """Get timeline data for successful vs failed backups over time"""
        from borgitory.models.database import Job, JobTask
        from sqlalchemy import and_, func
        from collections import defaultdict
        from datetime import timedelta

        try:
            # Get backup tasks from the last 30 days
            thirty_days_ago = now_utc() - timedelta(days=30)

            backup_results = (
                db.query(func.date(JobTask.completed_at).label("date"), JobTask.status)
                .join(Job, Job.id == JobTask.job_id)
                .filter(
                    and_(
                        Job.repository_id == repository.id,
                        JobTask.task_type.in_(["backup", "scheduled_backup"]),
                        JobTask.status.in_(["completed", "failed"]),
                        JobTask.completed_at >= thirty_days_ago,
                        JobTask.completed_at.isnot(None),
                    )
                )
                .order_by("date")
                .all()
            )

            # Group by date and count successes/failures
            daily_counts: defaultdict[str, dict[str, int]] = defaultdict(
                lambda: {"successful": 0, "failed": 0}
            )
            for result in backup_results:
                date_str = str(result.date) if result.date else "unknown"
                if result.status == "completed":
                    daily_counts[date_str]["successful"] += 1
                elif result.status == "failed":
                    daily_counts[date_str]["failed"] += 1

            # Sort dates and create chart data
            sorted_dates = sorted(daily_counts.keys())
            labels = sorted_dates
            successful_data = [
                float(daily_counts[date]["successful"]) for date in sorted_dates
            ]
            failed_data = [float(daily_counts[date]["failed"]) for date in sorted_dates]

            datasets: List[ChartDataset] = [
                {
                    "label": "Successful Backups",
                    "data": successful_data,
                    "borderColor": "rgb(34, 197, 94)",
                    "backgroundColor": "rgba(34, 197, 94, 0.2)",
                    "fill": True,
                    "type": "line",
                },
                {
                    "label": "Failed Backups",
                    "data": failed_data,
                    "borderColor": "rgb(239, 68, 68)",
                    "backgroundColor": "rgba(239, 68, 68, 0.2)",
                    "fill": True,
                    "type": "line",
                },
            ]

            chart_data: TimelineSuccessFailureData = {
                "labels": labels,
                "datasets": datasets,
            }

            return chart_data

        except Exception as e:
            logger.error(f"Error calculating timeline success/failure data: {str(e)}")
            return {"labels": [], "datasets": []}
