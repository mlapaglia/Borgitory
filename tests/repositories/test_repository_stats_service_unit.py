"""
Unit tests for RepositoryStatsService using proper Dependency Injection.

These tests focus on testing the service logic by injecting mock dependencies
rather than mocking the entire service, providing better code coverage.
"""

from contextlib import asynccontextmanager
import pytest
from unittest.mock import AsyncMock, Mock, patch
from typing import List, Dict
from sqlalchemy.orm import Session

from borgitory.services.repositories.repository_stats_service import (
    RepositoryStatsService,
    CommandExecutorInterface,
    ArchiveInfo,
)
from borgitory.models.database import Repository


class MockCommandExecutor(CommandExecutorInterface):
    """Mock implementation of CommandExecutorInterface for testing"""

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

    async def execute_borg_list(self, repository: Repository) -> List[str]:
        """Mock execute_borg_list"""
        if self.should_raise_exception:
            raise Exception(self.exception_message)
        return self.archive_list

    async def execute_borg_info(
        self, repository: Repository, archive_name: str
    ) -> ArchiveInfo:
        """Mock execute_borg_info"""
        if self.should_raise_exception:
            raise Exception(self.exception_message)
        return self.archive_info_responses.get(archive_name, {})

    async def execute_borg_list_files(
        self, repository: Repository, archive_name: str
    ) -> List[Dict[str, object]]:
        """Mock execute_borg_list_files"""
        if self.should_raise_exception:
            raise Exception(self.exception_message)
        return self.file_list_responses.get(archive_name, [])


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
        self.mock_db = Mock(spec=Session)

    def create_sample_archive_info(
        self, name: str, start: str = "2024-01-01T10:00:00"
    ) -> ArchiveInfo:
        """Helper to create sample archive info"""
        return {
            "name": name,
            "start": start,
            "end": "2024-01-01T11:00:00",
            "duration": 3600.0,
            "original_size": 1024 * 1024 * 100,  # 100 MB
            "compressed_size": 1024 * 1024 * 80,  # 80 MB
            "deduplicated_size": 1024 * 1024 * 60,  # 60 MB
            "nfiles": 1000,
        }

    @pytest.mark.asyncio
    async def test_get_repository_statistics_success(self) -> None:
        """Test successful repository statistics gathering"""
        # Set up mock data
        archives = ["backup-2024-01-01", "backup-2024-01-02"]
        self.mock_executor.set_archive_list(archives)

        for archive in archives:
            self.mock_executor.set_archive_info(
                archive, self.create_sample_archive_info(archive)
            )

        # Mock database queries to return empty results (no job history)
        self.mock_db.query.return_value.join.return_value.filter.return_value.all.return_value = []

        # Execute the method
        result = await self.stats_service.get_repository_statistics(
            self.mock_repository, self.mock_db
        )

        # Verify results
        assert "error" not in result
        assert result["repository_path"] == "/test/repo"
        assert result["total_archives"] == 2
        assert len(result["archive_stats"]) == 2

        # Verify chart data structures exist
        assert "size_over_time" in result
        assert "dedup_compression_stats" in result
        assert "summary" in result

        # Verify summary statistics
        summary = result["summary"]
        assert summary["total_archives"] == 2
        assert summary["total_original_size_gb"] > 0
        assert summary["overall_compression_ratio"] > 0

    @pytest.mark.asyncio
    async def test_get_repository_statistics_no_archives(self) -> None:
        """Test when repository has no archives"""
        self.mock_executor.set_archive_list([])

        result = await self.stats_service.get_repository_statistics(
            self.mock_repository, self.mock_db
        )

        assert "error" in result
        assert result["error"] == "No archives found in repository"

    @pytest.mark.asyncio
    async def test_get_repository_statistics_archive_info_failure(self) -> None:
        """Test when archive info retrieval fails"""
        archives = ["backup-2024-01-01"]
        self.mock_executor.set_archive_list(archives)
        # Don't set archive info, so it returns empty dict

        result = await self.stats_service.get_repository_statistics(
            self.mock_repository, self.mock_db
        )

        assert "error" in result
        assert result["error"] == "Could not retrieve archive information"

    @pytest.mark.asyncio
    async def test_get_repository_statistics_with_progress_callback(self) -> None:
        """Test statistics gathering with progress callback"""
        archives = ["backup-2024-01-01"]
        self.mock_executor.set_archive_list(archives)
        self.mock_executor.set_archive_info(
            archives[0], self.create_sample_archive_info(archives[0])
        )

        # Mock database queries
        self.mock_db.query.return_value.join.return_value.filter.return_value.all.return_value = []

        # Track progress calls
        progress_calls = []

        def progress_callback(message: str, percentage: int) -> None:
            progress_calls.append((message, percentage))

        result = await self.stats_service.get_repository_statistics(
            self.mock_repository, self.mock_db, progress_callback
        )

        # Verify progress was reported
        assert len(progress_calls) > 0
        assert any("Initializing" in call[0] for call in progress_calls)
        assert any(call[1] == 100 for call in progress_calls)  # Should reach 100%
        assert "error" not in result

    @pytest.mark.asyncio
    async def test_get_repository_statistics_exception_handling(self) -> None:
        """Test exception handling in statistics gathering"""
        self.mock_executor.set_exception(True, "Test exception")

        result = await self.stats_service.get_repository_statistics(
            self.mock_repository, self.mock_db
        )

        assert "error" in result
        assert "Test exception" in result["error"]

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

    @pytest.mark.asyncio
    async def test_get_archive_list(self) -> None:
        """Test _get_archive_list method"""
        expected_archives = ["backup-1", "backup-2", "backup-3"]
        self.mock_executor.set_archive_list(expected_archives)

        result = await self.stats_service._get_archive_list(self.mock_repository)

        assert result == expected_archives

    @pytest.mark.asyncio
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

    @pytest.mark.asyncio
    async def test_get_archive_info_not_found(self) -> None:
        """Test _get_archive_info when archive is not found"""
        # Don't set any archive info

        result = await self.stats_service._get_archive_info(
            self.mock_repository, "nonexistent"
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_get_archive_info_exception(self) -> None:
        """Test _get_archive_info exception handling"""
        self.mock_executor.set_exception(True, "Archive info exception")

        result = await self.stats_service._get_archive_info(
            self.mock_repository, "test-archive"
        )

        assert result is None


class TestSubprocessCommandExecutor:
    """Test the actual SubprocessCommandExecutor (integration-style tests)"""

    def setup_method(self) -> None:
        """Set up test fixtures"""
        from borgitory.services.repositories.repository_stats_service import (
            SubprocessCommandExecutor,
        )

        self.executor = SubprocessCommandExecutor()
        self.mock_repository = Mock(spec=Repository)
        self.mock_repository.path = (
            "/nonexistent/repo"  # Use nonexistent path to avoid actual borg calls
        )
        self.mock_repository.get_passphrase.return_value = "test_passphrase"
        self.mock_repository.get_keyfile_content.return_value = None

    @pytest.mark.asyncio
    async def test_execute_borg_list_failure(self) -> None:
        """Test execute_borg_list when borg command fails (expected with nonexistent repo)"""
        result = await self.executor.execute_borg_list(self.mock_repository)

        # Should return empty list when command fails
        assert result == []

    @pytest.mark.asyncio
    async def test_execute_borg_info_failure(self) -> None:
        """Test execute_borg_info when borg command fails (expected with nonexistent repo)"""
        result = await self.executor.execute_borg_info(
            self.mock_repository, "test-archive"
        )

        # Should return empty dict when command fails
        assert result == {}

    @pytest.mark.asyncio
    async def test_execute_borg_list_files_failure(self) -> None:
        """Test execute_borg_list_files when borg command fails (expected with nonexistent repo)"""
        result = await self.executor.execute_borg_list_files(
            self.mock_repository, "test-archive"
        )

        # Should return empty list when command fails
        assert result == []


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

        self.mock_db = Mock(spec=Session)

    @pytest.mark.asyncio
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
            {
                "name": archives[0],
                "start": "2024-01-01T10:00:00",
                "end": "2024-01-01T11:30:00",
                "duration": 5400.0,  # 1.5 hours
                "original_size": 1024 * 1024 * 1024,  # 1 GB
                "compressed_size": 1024 * 1024 * 800,  # 800 MB
                "deduplicated_size": 1024 * 1024 * 600,  # 600 MB
                "nfiles": 5000,
            },
            {
                "name": archives[1],
                "start": "2024-01-02T10:00:00",
                "end": "2024-01-02T10:45:00",
                "duration": 2700.0,  # 45 minutes
                "original_size": 1024 * 1024 * 1200,  # 1.2 GB
                "compressed_size": 1024 * 1024 * 900,  # 900 MB
                "deduplicated_size": 1024 * 1024 * 650,  # 650 MB (good dedup)
                "nfiles": 6000,
            },
            {
                "name": archives[2],
                "start": "2024-01-03T10:00:00",
                "end": "2024-01-03T12:00:00",
                "duration": 7200.0,  # 2 hours
                "original_size": 1024 * 1024 * 800,  # 800 MB
                "compressed_size": 1024 * 1024 * 700,  # 700 MB (poor compression)
                "deduplicated_size": 1024 * 1024 * 500,  # 500 MB
                "nfiles": 4000,
            },
        ]

        for i, archive in enumerate(archives):
            self.mock_executor.set_archive_info(archive, archive_infos[i])

        # Mock database queries for job statistics
        self.mock_db.query.return_value.join.return_value.filter.return_value.all.return_value = []

        # Execute the full workflow
        result = await self.stats_service.get_repository_statistics(
            self.mock_repository, self.mock_db
        )

        # Comprehensive assertions
        assert "error" not in result
        assert result["total_archives"] == 3
        assert len(result["archive_stats"]) == 3

        # Verify timeline data
        timeline = result["size_over_time"]
        assert len(timeline["labels"]) == 3
        assert len(timeline["datasets"]) == 3
        assert all(len(dataset["data"]) == 3 for dataset in timeline["datasets"])

        # Verify dedup/compression stats
        dedup_stats = result["dedup_compression_stats"]
        assert len(dedup_stats["labels"]) == 3
        assert len(dedup_stats["datasets"]) == 2

        # Verify summary calculations
        summary = result["summary"]
        assert summary["total_archives"] == 3
        # Total original size should be ~3GB
        assert 2.5 < summary["total_original_size_gb"] < 3.5
        # Should have reasonable compression ratio
        assert 0 < summary["overall_compression_ratio"] < 50
        # Should have reasonable deduplication ratio
        assert 0 < summary["overall_deduplication_ratio"] < 50
        # Space saved should be positive
        assert summary["space_saved_gb"] > 0

    @pytest.mark.asyncio
    async def test_get_execution_time_stats(self) -> None:
        """Test execution time statistics calculation"""
        from datetime import datetime
        from unittest.mock import MagicMock

        # Mock database query results
        mock_task1 = MagicMock()
        mock_task1.task_type = "backup"
        mock_task1.started_at = datetime(2024, 1, 1, 10, 0, 0)
        mock_task1.completed_at = datetime(2024, 1, 1, 11, 0, 0)  # 1 hour

        mock_task2 = MagicMock()
        mock_task2.task_type = "backup"
        mock_task2.started_at = datetime(2024, 1, 2, 10, 0, 0)
        mock_task2.completed_at = datetime(2024, 1, 2, 10, 30, 0)  # 30 minutes

        mock_task3 = MagicMock()
        mock_task3.task_type = "prune"
        mock_task3.started_at = datetime(2024, 1, 3, 10, 0, 0)
        mock_task3.completed_at = datetime(2024, 1, 3, 10, 15, 0)  # 15 minutes

        self.mock_db.query.return_value.join.return_value.filter.return_value.all.return_value = [
            mock_task1,
            mock_task2,
            mock_task3,
        ]

        result = await self.stats_service._get_execution_time_stats(
            self.mock_repository, self.mock_db
        )

        assert len(result) == 2  # backup and prune

        # Find backup stats
        backup_stats = next((s for s in result if s["task_type"] == "backup"), None)
        assert backup_stats is not None
        assert backup_stats["total_executions"] == 2
        assert backup_stats["average_duration_minutes"] == 45.0  # (60 + 30) / 2
        assert backup_stats["min_duration_minutes"] == 30.0
        assert backup_stats["max_duration_minutes"] == 60.0

        # Find prune stats
        prune_stats = next((s for s in result if s["task_type"] == "prune"), None)
        assert prune_stats is not None
        assert prune_stats["total_executions"] == 1
        assert prune_stats["average_duration_minutes"] == 15.0

    @pytest.mark.asyncio
    async def test_get_execution_time_stats_exception(self) -> None:
        """Test execution time stats exception handling"""
        self.mock_db.query.side_effect = Exception("Database error")

        result = await self.stats_service._get_execution_time_stats(
            self.mock_repository, self.mock_db
        )

        assert result == []

    def test_build_execution_time_chart(self) -> None:
        """Test execution time chart building"""
        execution_stats = [
            {
                "task_type": "backup",
                "average_duration_minutes": 45.0,
                "total_executions": 2,
                "min_duration_minutes": 30.0,
                "max_duration_minutes": 60.0,
            },
            {
                "task_type": "prune",
                "average_duration_minutes": 15.0,
                "total_executions": 1,
                "min_duration_minutes": 15.0,
                "max_duration_minutes": 15.0,
            },
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

    @pytest.mark.asyncio
    async def test_get_success_failure_stats(self) -> None:
        """Test success/failure statistics calculation"""
        from unittest.mock import MagicMock

        # Mock database query results
        mock_task1 = MagicMock()
        mock_task1.task_type = "backup"
        mock_task1.status = "completed"

        mock_task2 = MagicMock()
        mock_task2.task_type = "backup"
        mock_task2.status = "completed"

        mock_task3 = MagicMock()
        mock_task3.task_type = "backup"
        mock_task3.status = "failed"

        mock_task4 = MagicMock()
        mock_task4.task_type = "prune"
        mock_task4.status = "completed"

        self.mock_db.query.return_value.join.return_value.filter.return_value.all.return_value = [
            mock_task1,
            mock_task2,
            mock_task3,
            mock_task4,
        ]

        result = await self.stats_service._get_success_failure_stats(
            self.mock_repository, self.mock_db
        )

        assert len(result) == 2  # backup and prune

        # Find backup stats
        backup_stats = next((s for s in result if s["task_type"] == "backup"), None)
        assert backup_stats is not None
        assert backup_stats["successful_count"] == 2
        assert backup_stats["failed_count"] == 1
        assert backup_stats["success_rate"] == 66.67  # 2/3 * 100

        # Find prune stats
        prune_stats = next((s for s in result if s["task_type"] == "prune"), None)
        assert prune_stats is not None
        assert prune_stats["successful_count"] == 1
        assert prune_stats["failed_count"] == 0
        assert prune_stats["success_rate"] == 100.0

    def test_build_success_failure_chart(self) -> None:
        """Test success/failure chart building"""
        success_failure_stats = [
            {
                "task_type": "backup",
                "successful_count": 2,
                "failed_count": 1,
                "success_rate": 66.67,
            },
            {
                "task_type": "prune",
                "successful_count": 1,
                "failed_count": 0,
                "success_rate": 100.0,
            },
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

    @pytest.mark.asyncio
    async def test_get_timeline_success_failure_data(self) -> None:
        """Test timeline success/failure data calculation"""
        from unittest.mock import MagicMock
        from datetime import date

        # Mock database query results
        mock_result1 = MagicMock()
        mock_result1.date = date(2024, 1, 1)
        mock_result1.status = "completed"

        mock_result2 = MagicMock()
        mock_result2.date = date(2024, 1, 1)
        mock_result2.status = "failed"

        mock_result3 = MagicMock()
        mock_result3.date = date(2024, 1, 2)
        mock_result3.status = "completed"

        self.mock_db.query.return_value.join.return_value.filter.return_value.order_by.return_value.all.return_value = [
            mock_result1,
            mock_result2,
            mock_result3,
        ]

        result = await self.stats_service._get_timeline_success_failure_data(
            self.mock_repository, self.mock_db
        )

        assert len(result["labels"]) == 2  # Two dates
        assert "2024-01-01" in result["labels"]
        assert "2024-01-02" in result["labels"]
        assert len(result["datasets"]) == 2  # Successful and Failed
        assert result["datasets"][0]["label"] == "Successful Backups"
        assert result["datasets"][1]["label"] == "Failed Backups"

    def test_build_file_type_chart_data(self) -> None:
        """Test file type chart data building"""
        timeline_data = {
            "labels": ["2024-01-01", "2024-01-02"],
            "count_data": {
                "txt": [10, 15],
                "jpg": [5, 8],
                "pdf": [2, 3],
            },
            "size_data": {
                "txt": [1.5, 2.0],  # MB
                "jpg": [10.0, 12.0],  # MB
                "pdf": [5.0, 6.0],  # MB
            },
        }

        chart_data = self.stats_service._build_file_type_chart_data(timeline_data)

        assert "count_chart" in chart_data
        assert "size_chart" in chart_data

        count_chart = chart_data["count_chart"]
        assert len(count_chart["labels"]) == 2
        assert len(count_chart["datasets"]) <= 10  # Limited to top 10

        size_chart = chart_data["size_chart"]
        assert len(size_chart["labels"]) == 2
        assert len(size_chart["datasets"]) <= 10  # Limited to top 10

    @pytest.mark.asyncio
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
        async def mock_secure_borg_command(*args, **kwargs):
            yield (["borg", "list"], {}, None)

        with patch(
            "borgitory.services.repositories.repository_stats_service.secure_borg_command",
            mock_secure_borg_command,
        ), patch("asyncio.create_subprocess_exec", return_value=mock_process):
            result = await self.stats_service._get_file_type_stats(
                self.mock_repository, archives
            )

            assert "count_chart" in result
            assert "size_chart" in result

            count_chart = result["count_chart"]
            assert len(count_chart["labels"]) > 0
            assert len(count_chart["datasets"]) > 0
