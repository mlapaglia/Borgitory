"""
Unit tests for RepositoryStatsService using proper Dependency Injection.

These tests focus on testing the service logic by injecting mock dependencies
rather than mocking the entire service, providing better code coverage.
"""

import asyncio
from contextlib import asynccontextmanager
import pytest
from unittest.mock import AsyncMock, Mock, patch

from sqlalchemy.ext.asyncio import AsyncSession
from borgitory.protocols.command_executor_protocol import (
    CommandResult as ExecutorCommandResult,
)
from typing import Any, AsyncGenerator, List, Dict, Tuple

from borgitory.services.repositories.repository_stats_service import (
    ExecutionTimeStats,
    FileTypeTimelineData,
    RepositoryStatsService,
    ArchiveInfo,
    SuccessFailureStats,
)
from borgitory.protocols.command_executor_protocol import (
    CommandExecutorProtocol,
    CommandResult,
)
from borgitory.models.database import Repository


class MockCommandExecutor(CommandExecutorProtocol):
    """Mock implementation of CommandExecutorProtocol for testing"""

    def __init__(self) -> None:
        self.archive_list: List[str] = []
        self.archive_info_responses: Dict[str, ArchiveInfo] = {}
        self.file_list_responses: Dict[str, List[Dict[str, object]]] = {}
        self.should_raise_exception = False
        self.exception_message = "Mock exception"

    def set_archive_list(self, archives: List[str]) -> None:
        """Set the list of archives to return"""
        self.archive_list = archives

    def set_archive_info(self, archive_name: str, info: ArchiveInfo) -> None:
        """Set archive info response for a specific archive"""
        self.archive_info_responses[archive_name] = info

    def set_file_list(self, archive_name: str, files: List[Dict[str, object]]) -> None:
        """Set file list response for a specific archive"""
        self.file_list_responses[archive_name] = files

    def set_exception(
        self, should_raise: bool, message: str = "Mock exception"
    ) -> None:
        """Configure whether to raise exceptions"""
        self.should_raise_exception = should_raise
        self.exception_message = message

    async def execute_command(
        self,
        command: List[str],
        env: Dict[str, str] | None = None,
        cwd: str | None = None,
        timeout: float | None = None,
        input_data: str | None = None,
    ) -> CommandResult:
        """Mock execute_command"""
        if self.should_raise_exception:
            raise Exception(self.exception_message)

        # Simulate different borg commands
        if len(command) >= 2 and command[0] == "borg" and command[1] == "list":
            if "--short" in command:
                # borg list --short
                stdout = "\n".join(self.archive_list)
                return CommandResult(
                    command=command,
                    return_code=0,
                    stdout=stdout,
                    stderr="",
                    success=True,
                    execution_time=0.1,
                )
        elif len(command) >= 2 and command[0] == "borg" and command[1] == "info":
            # borg info --json
            if "--json" in command:
                # Extract archive name from command
                archive_name = None
                for arg in command:
                    if "::" in arg:
                        archive_name = arg.split("::")[-1]
                        break

                if archive_name and archive_name in self.archive_info_responses:
                    import json

                    info = self.archive_info_responses[archive_name]
                    # Convert ArchiveInfo format to the borg info JSON format
                    borg_format = {
                        "name": info["name"],
                        "start": info["start"],
                        "end": info["end"],
                        "duration": info["duration"],
                        "stats": {
                            "original_size": info["original_size"],
                            "compressed_size": info["compressed_size"],
                            "deduplicated_size": info["deduplicated_size"],
                            "nfiles": info["nfiles"],
                        },
                    }
                    response = {"archives": [borg_format]}
                    stdout = json.dumps(response)
                    return CommandResult(
                        command=command,
                        return_code=0,
                        stdout=stdout,
                        stderr="",
                        success=True,
                        execution_time=0.1,
                    )

        # Default failure response
        return CommandResult(
            command=command,
            return_code=1,
            stdout="",
            stderr="Command not mocked",
            success=False,
            execution_time=0.1,
            error="Command not mocked",
        )

    async def create_subprocess(
        self,
        command: List[str],
        env: Dict[str, str] | None = None,
        cwd: str | None = None,
        stdout: int | None = None,
        stderr: int | None = None,
        stdin: int | None = None,
    ) -> asyncio.subprocess.Process:
        """Mock create_subprocess - not implemented for this test"""
        raise NotImplementedError("create_subprocess not implemented in mock")

    def get_platform_name(self) -> str:
        """Mock get_platform_name"""
        return "test"


class TestRepositoryStatsService:
    """Test RepositoryStatsService with proper DI"""

    def setup_method(self) -> None:
        """Set up test fixtures"""
        self.mock_executor = MockCommandExecutor()
        self.stats_service = RepositoryStatsService(command_executor=self.mock_executor)

        # Create a mock repository
        self.mock_repository = Mock(spec=Repository)
        self.mock_repository.id = 1
        self.mock_repository.path = "/test/repo"
        self.mock_repository.get_passphrase.return_value = "test_passphrase"
        self.mock_repository.get_keyfile_content.return_value = None

        # Create a mock database session
        self.mock_db = Mock(spec=AsyncSession)

    def create_sample_archive_info(
        self, name: str, start: str = "2024-01-01T10:00:00"
    ) -> ArchiveInfo:
        """Helper to create sample archive info"""
        return ArchiveInfo(
            name=name,
            start=start,
            end="2024-01-01T11:00:00",
            duration=3600.0,
            original_size=1024 * 1024 * 100,  # 100 MB
            compressed_size=1024 * 1024 * 80,  # 80 MB
            deduplicated_size=1024 * 1024 * 60,  # 60 MB
            nfiles=1000,
        )

    async def test_get_repository_statistics_success(self) -> None:
        """Test successful repository statistics gathering"""
        # Set up mock data
        archives = ["backup-2024-01-01", "backup-2024-01-02"]
        self.mock_executor.set_archive_list(archives)

        for archive in archives:
            self.mock_executor.set_archive_info(
                archive, self.create_sample_archive_info(archive)
            )

        # Mock database queries to return empty results (no job history) using SQLAlchemy 2.0 pattern
        from unittest.mock import MagicMock

        mock_result = Mock()
        empty_list = []
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = empty_list
        mock_scalars.__iter__.return_value = iter(empty_list)
        mock_result.scalars.return_value = mock_scalars
        self.mock_db.execute = AsyncMock(return_value=mock_result)

        # Execute the method
        result = await self.stats_service.get_repository_statistics(
            self.mock_repository, self.mock_db
        )

        # Verify results
        assert result.repository_path == "/test/repo"
        assert result.total_archives == 2
        assert len(result.archive_stats) == 2

        # Verify chart data structures exist
        assert result.size_over_time is not None
        assert result.dedup_compression_stats is not None
        assert result.summary is not None

    async def test_get_repository_statistics_no_archives_raises_error(self) -> None:
        """Test that ValueError is raised when no archives are found"""
        # Mock empty archive list
        self.mock_executor.execute_command = AsyncMock(
            return_value=ExecutorCommandResult(
                command=["borg", "list", "/test/repo", "--short"],
                return_code=0,
                stdout="",
                stderr="",
                success=True,
                execution_time=1.0,
            )
        )

        # Execute and expect ValueError
        with pytest.raises(ValueError, match="No archives found in repository"):
            await self.stats_service.get_repository_statistics(
                self.mock_repository, self.mock_db
            )

    async def test_get_repository_statistics_no_archive_info_raises_error(self) -> None:
        """Test that ValueError is raised when archive info cannot be retrieved"""

        # Mock different responses for different commands
        def mock_execute_command(
            command: List[str], **kwargs: Any
        ) -> ExecutorCommandResult:
            if "borg list" in " ".join(command):
                return ExecutorCommandResult(
                    command=command,
                    return_code=0,
                    stdout="archive1\narchive2",
                    stderr="",
                    success=True,
                    execution_time=1.0,
                )
            elif "borg info" in " ".join(command):
                return ExecutorCommandResult(
                    command=command,
                    return_code=1,
                    stdout="",
                    stderr="Archive not found",
                    success=False,
                    execution_time=1.0,
                )
            else:
                return ExecutorCommandResult(
                    command=command,
                    return_code=0,
                    stdout="",
                    stderr="",
                    success=True,
                    execution_time=1.0,
                )

        self.mock_executor.execute_command = AsyncMock(side_effect=mock_execute_command)

        # Execute and expect ValueError
        with pytest.raises(ValueError, match="Could not retrieve archive information"):
            await self.stats_service.get_repository_statistics(
                self.mock_repository, self.mock_db
            )

    async def test_get_repository_statistics_no_archives(self) -> None:
        """Test when repository has no archives"""
        self.mock_executor.set_archive_list([])

        # Should raise ValueError
        with pytest.raises(ValueError, match="No archives found in repository"):
            await self.stats_service.get_repository_statistics(
                self.mock_repository, self.mock_db
            )

    async def test_get_repository_statistics_archive_info_failure(self) -> None:
        """Test when archive info retrieval fails"""
        archives = ["backup-2024-01-01"]
        self.mock_executor.set_archive_list(archives)
        # Don't set archive info, so it returns empty dict

        # Should raise ValueError
        with pytest.raises(ValueError, match="Could not retrieve archive information"):
            await self.stats_service.get_repository_statistics(
                self.mock_repository, self.mock_db
            )

    async def test_get_repository_statistics_exception_handling(self) -> None:
        """Test exception handling in statistics gathering"""
        self.mock_executor.set_exception(True, "Test exception")

        # Should raise the exception
        with pytest.raises(Exception, match="Test exception"):
            await self.stats_service.get_repository_statistics(
                self.mock_repository, self.mock_db
            )

    def test_build_size_timeline(self) -> None:
        """Test size timeline building"""
        archive_stats = [
            self.create_sample_archive_info("backup-1", "2024-01-01T10:00:00"),
            self.create_sample_archive_info("backup-2", "2024-01-02T10:00:00"),
        ]

        timeline = self.stats_service._build_size_timeline(archive_stats)

        assert len(timeline["labels"]) == 2
        assert len(timeline["datasets"]) == 3  # Original, Compressed, Deduplicated
        assert timeline["datasets"][0]["label"] == "Original Size"
        assert len(timeline["datasets"][0]["data"]) == 2
        assert all(isinstance(x, float) for x in timeline["datasets"][0]["data"])

    def test_build_dedup_compression_stats(self) -> None:
        """Test deduplication and compression statistics building"""
        archive_stats = [
            self.create_sample_archive_info("backup-1", "2024-01-01T10:00:00"),
            self.create_sample_archive_info("backup-2", "2024-01-02T10:00:00"),
        ]

        dedup_stats = self.stats_service._build_dedup_compression_stats(archive_stats)

        assert len(dedup_stats["labels"]) == 2
        assert len(dedup_stats["datasets"]) == 2  # Compression and Deduplication ratios
        assert dedup_stats["datasets"][0]["label"] == "Compression Ratio %"
        assert all(
            isinstance(x, (int, float)) for x in dedup_stats["datasets"][0]["data"]
        )

    def test_build_summary_stats(self) -> None:
        """Test summary statistics building"""
        archive_stats = [
            self.create_sample_archive_info("backup-1", "2024-01-01T10:00:00"),
            self.create_sample_archive_info("backup-2", "2024-01-02T10:00:00"),
        ]

        summary = self.stats_service._build_summary_stats(archive_stats)

        assert summary["total_archives"] == 2
        assert summary["total_original_size_gb"] > 0
        assert summary["total_compressed_size_gb"] > 0
        assert summary["total_deduplicated_size_gb"] > 0
        assert summary["overall_compression_ratio"] > 0
        assert summary["overall_deduplication_ratio"] > 0
        assert summary["space_saved_gb"] > 0
        assert summary["average_archive_size_gb"] > 0

    def test_build_summary_stats_empty(self) -> None:
        """Test summary statistics with empty archive list"""
        summary = self.stats_service._build_summary_stats([])

        assert summary["total_archives"] == 0
        assert summary["total_original_size_gb"] == 0.0
        assert summary["overall_compression_ratio"] == 0.0

    async def test_get_archive_list(self) -> None:
        """Test _get_archive_list method"""
        expected_archives = ["backup-1", "backup-2", "backup-3"]
        self.mock_executor.set_archive_list(expected_archives)

        result = await self.stats_service._get_archive_list(self.mock_repository)

        assert result == expected_archives

    async def test_get_archive_info(self) -> None:
        """Test _get_archive_info method"""
        archive_name = "backup-test"
        expected_info = self.create_sample_archive_info(archive_name)
        self.mock_executor.set_archive_info(archive_name, expected_info)

        result = await self.stats_service._get_archive_info(
            self.mock_repository, archive_name
        )

        assert result is not None
        assert result["name"] == archive_name
        assert result["original_size"] == expected_info["original_size"]
        assert result["compressed_size"] == expected_info["compressed_size"]

    async def test_get_archive_info_not_found(self) -> None:
        """Test _get_archive_info when archive is not found"""
        # Don't set any archive info

        result = await self.stats_service._get_archive_info(
            self.mock_repository, "nonexistent"
        )

        assert result is None

    async def test_get_archive_info_exception(self) -> None:
        """Test _get_archive_info exception handling"""
        self.mock_executor.set_exception(True, "Archive info exception")

        result = await self.stats_service._get_archive_info(
            self.mock_repository, "test-archive"
        )

        assert result is None


class TestRepositoryStatsServiceIntegration:
    """Integration tests that test the service with real-ish data flow"""

    def setup_method(self) -> None:
        """Set up test fixtures"""
        self.mock_executor = MockCommandExecutor()
        self.stats_service = RepositoryStatsService(command_executor=self.mock_executor)

        self.mock_repository = Mock(spec=Repository)
        self.mock_repository.id = 1
        self.mock_repository.path = "/test/repo"
        self.mock_repository.get_passphrase.return_value = "test_passphrase"
        self.mock_repository.get_keyfile_content.return_value = None

        self.mock_db = Mock(spec=AsyncSession)

    async def test_full_statistics_workflow(self) -> None:
        """Test the complete statistics gathering workflow"""
        # Set up a realistic scenario with multiple archives
        archives = [
            "backup-2024-01-01_10-00-00",
            "backup-2024-01-02_10-00-00",
            "backup-2024-01-03_10-00-00",
        ]
        self.mock_executor.set_archive_list(archives)

        # Create varied archive info to test calculations
        archive_infos = [
            ArchiveInfo(
                name=archives[0],
                start="2024-01-01T10:00:00",
                end="2024-01-01T11:30:00",
                duration=5400.0,  # 1.5 hours
                original_size=1024 * 1024 * 1024,  # 1 GB
                compressed_size=1024 * 1024 * 800,  # 800 MB
                deduplicated_size=1024 * 1024 * 600,  # 600 MB
                nfiles=5000,
            ),
            ArchiveInfo(
                name=archives[1],
                start="2024-01-02T10:00:00",
                end="2024-01-02T10:45:00",
                duration=2700.0,  # 45 minutes
                original_size=1024 * 1024 * 1200,  # 1.2 GB
                compressed_size=1024 * 1024 * 900,  # 900 MB
                deduplicated_size=1024 * 1024 * 650,  # 650 MB (good dedup)
                nfiles=6000,
            ),
            ArchiveInfo(
                name=archives[2],
                start="2024-01-03T10:00:00",
                end="2024-01-03T12:00:00",
                duration=7200.0,  # 2 hours
                original_size=1024 * 1024 * 800,  # 800 MB
                compressed_size=1024 * 1024 * 700,  # 700 MB (poor compression)
                deduplicated_size=1024 * 1024 * 500,  # 500 MB
                nfiles=4000,
            ),
        ]

        for i, archive in enumerate(archives):
            self.mock_executor.set_archive_info(archive, archive_infos[i])

        # Mock database queries for job statistics using SQLAlchemy 2.0 pattern
        from unittest.mock import MagicMock

        mock_result = Mock()
        empty_list = []
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = empty_list
        mock_scalars.__iter__.return_value = iter(empty_list)
        mock_result.scalars.return_value = mock_scalars
        self.mock_db.execute = AsyncMock(return_value=mock_result)

        # Execute the full workflow
        result = await self.stats_service.get_repository_statistics(
            self.mock_repository, self.mock_db
        )

        # Comprehensive assertions
        assert result.total_archives == 3
        assert len(result.archive_stats) == 3

        # Verify timeline data
        timeline = result.size_over_time
        assert len(timeline["labels"]) == 3
        assert len(timeline["datasets"]) == 3
        assert all(len(dataset["data"]) == 3 for dataset in timeline["datasets"])

        # Verify dedup/compression stats
        dedup_stats = result.dedup_compression_stats
        assert len(dedup_stats["labels"]) == 3
        assert len(dedup_stats["datasets"]) == 2

        # Verify summary calculations
        summary = result.summary
        assert summary["total_archives"] == 3
        # Total original size should be ~3GB
        assert 2.5 < summary["total_original_size_gb"] < 3.5
        # Should have reasonable compression ratio
        assert 0 < summary["overall_compression_ratio"] < 50
        # Should have reasonable deduplication ratio
        assert 0 < summary["overall_deduplication_ratio"] < 50
        # Space saved should be positive
        assert summary["space_saved_gb"] > 0

    async def test_get_execution_time_stats_exception(self) -> None:
        """Test execution time stats exception handling"""
        # Mock using SQLAlchemy 2.0 pattern
        self.mock_db.execute = AsyncMock(side_effect=Exception("Database error"))

        result = await self.stats_service._get_execution_time_stats(
            self.mock_repository, self.mock_db
        )

        assert result == []

    def test_build_execution_time_chart(self) -> None:
        """Test execution time chart building"""
        execution_stats = [
            ExecutionTimeStats(
                task_type="backup",
                average_duration_minutes=45.0,
                total_executions=2,
                min_duration_minutes=30.0,
                max_duration_minutes=60.0,
            ),
            ExecutionTimeStats(
                task_type="prune",
                average_duration_minutes=15.0,
                total_executions=1,
                min_duration_minutes=15.0,
                max_duration_minutes=15.0,
            ),
        ]

        chart_data = self.stats_service._build_execution_time_chart(execution_stats)

        assert len(chart_data["labels"]) == 2
        assert "Backup" in chart_data["labels"]
        assert "Prune" in chart_data["labels"]
        assert len(chart_data["datasets"]) == 3  # Average, Min, Max
        assert chart_data["datasets"][0]["label"] == "Average Duration (minutes)"

    def test_build_execution_time_chart_empty(self) -> None:
        """Test execution time chart with empty data"""
        chart_data = self.stats_service._build_execution_time_chart([])

        assert chart_data["labels"] == []
        assert chart_data["datasets"] == []

    def test_build_success_failure_chart(self) -> None:
        """Test success/failure chart building"""
        success_failure_stats = [
            SuccessFailureStats(
                task_type="backup",
                successful_count=2,
                failed_count=1,
                success_rate=66.67,
            ),
            SuccessFailureStats(
                task_type="prune",
                successful_count=1,
                failed_count=0,
                success_rate=100.0,
            ),
        ]

        chart_data = self.stats_service._build_success_failure_chart(
            success_failure_stats
        )

        assert len(chart_data["labels"]) == 2
        assert len(chart_data["datasets"]) == 3  # Successful, Failed, Success Rate
        assert chart_data["datasets"][0]["label"] == "Successful"
        assert chart_data["datasets"][1]["label"] == "Failed"
        assert chart_data["datasets"][2]["label"] == "Success Rate (%)"

    def test_build_success_failure_chart_empty(self) -> None:
        """Test success/failure chart with empty data"""
        chart_data = self.stats_service._build_success_failure_chart([])

        assert chart_data["labels"] == []
        assert chart_data["datasets"] == []

    def test_build_file_type_chart_data(self) -> None:
        """Test file type chart data building"""
        timeline_data = FileTypeTimelineData(
            labels=["2024-01-01", "2024-01-02"],
            count_data={
                "txt": [10, 15],
                "jpg": [5, 8],
                "pdf": [2, 3],
            },
            size_data={
                "txt": [1.5, 2.0],  # MB
                "jpg": [10.0, 12.0],  # MB
                "pdf": [5.0, 6.0],  # MB
            },
        )

        chart_data = self.stats_service._build_file_type_chart_data(timeline_data)

        assert "count_chart" in chart_data
        assert "size_chart" in chart_data

        count_chart = chart_data["count_chart"]
        assert len(count_chart["labels"]) == 2
        assert len(count_chart["datasets"]) <= 10  # Limited to top 10

        size_chart = chart_data["size_chart"]
        assert len(size_chart["labels"]) == 2
        assert len(size_chart["datasets"]) <= 10  # Limited to top 10

    async def test_get_file_type_stats_integration(self) -> None:
        """Test _get_file_type_stats method with mocked command execution"""
        archives = ["backup-2024-01-01", "backup-2024-01-02"]

        # Mock the secure_borg_command context manager properly
        mock_process = AsyncMock()
        mock_process.returncode = 0
        mock_process.communicate.return_value = (
            b"1024 /home/user/file1.txt\n2048 /home/user/image.jpg\n512 /home/user/doc.pdf\n",
            b"",
        )

        @asynccontextmanager
        async def mock_secure_borg_command(
            *args: Any, **kwargs: Any
        ) -> AsyncGenerator[Tuple[List[str], Dict[str, str], Any], None]:
            yield (["borg", "list"], {}, None)

        # Replace the mock executor's create_subprocess method with a proper AsyncMock
        self.mock_executor.create_subprocess = AsyncMock(return_value=mock_process)

        with patch(
            "borgitory.services.repositories.repository_stats_service.create_borg_command"
        ) as mock_create_borg:
            # Mock create_borg_command to return command structure
            mock_borg_cmd = Mock()
            mock_borg_cmd.command = ["borg", "list"]
            mock_borg_cmd.environment = {}
            mock_create_borg.return_value = mock_borg_cmd

            result = await self.stats_service._get_file_type_stats(
                self.mock_repository, archives
            )

            assert "count_chart" in result
            assert "size_chart" in result

            count_chart = result["count_chart"]
            assert len(count_chart["labels"]) > 0
            assert len(count_chart["datasets"]) > 0
