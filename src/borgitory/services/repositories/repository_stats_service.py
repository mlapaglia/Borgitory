import asyncio
import json
import logging
from abc import ABC, abstractmethod
from typing import Dict, List, Callable, Optional, TypedDict
from sqlalchemy.orm import Session

from borgitory.models.database import Repository
from borgitory.utils.security import build_secure_borg_command

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
            command, env = build_secure_borg_command(
                base_command="borg list",
                repository_path=str(repository.path),
                passphrase=repository.get_passphrase(),
                additional_args=["--short"],
            )
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
            command, env = build_secure_borg_command(
                base_command="borg info",
                repository_path="",
                passphrase=repository.get_passphrase(),
                additional_args=["--json", f"{repository.path}::{archive_name}"],
            )
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
            command, env = build_secure_borg_command(
                base_command="borg list",
                repository_path="",
                passphrase=repository.get_passphrase(),
                additional_args=["--json-lines", f"{repository.path}::{archive_name}"],
            )
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
        try:
            command, env = build_secure_borg_command(
                base_command="borg list",
                repository_path=str(repository.path),
                passphrase=repository.get_passphrase(),
                additional_args=["--short"],
            )

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
                logger.error(f"Borg list failed: {stderr.decode()}")
                return []

        except Exception as e:
            logger.error(f"Error listing archives: {str(e)}")
            return []

    async def _get_archive_info(
        self, repository: Repository, archive_name: str
    ) -> Dict[str, object] | None:
        """Get detailed information for a specific archive"""
        try:
            command, env = build_secure_borg_command(
                base_command="borg info",
                repository_path="",
                passphrase=repository.get_passphrase(),
                additional_args=["--json", f"{repository.path}::{archive_name}"],
            )

            process = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
            )

            stdout, stderr = await process.communicate()

            if process.returncode == 0:
                info_data = json.loads(stdout.decode())

                # Extract relevant statistics
                archive_info = info_data.get("archives", [{}])[0]
                cache_info = info_data.get("cache", {})

                return {
                    "name": archive_name,
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
                    "unique_chunks": cache_info.get("stats", {}).get(
                        "unique_chunks", 0
                    ),
                    "total_chunks": cache_info.get("stats", {}).get("total_chunks", 0),
                    "unique_size": cache_info.get("stats", {}).get("unique_size", 0),
                    "total_size": cache_info.get("stats", {}).get("total_size", 0),
                }
            else:
                logger.error(f"Borg info failed for {archive_name}: {stderr.decode()}")
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
                command, env = build_secure_borg_command(
                    base_command="borg list",
                    repository_path="",
                    passphrase=repository.get_passphrase(),
                    additional_args=[
                        f"{repository.path}::{archive_name}",
                        "--format={size} {path}{NL}",
                    ],
                )

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
