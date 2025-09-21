"""
Tests for RepositoryStatsService class - repository statistics and analytics
"""

import pytest
import json
from unittest.mock import Mock, AsyncMock, patch
from typing import Dict, Any, List

from borgitory.services.repositories.repository_stats_service import (
    RepositoryStatsService,
    CommandExecutorInterface,
)
from borgitory.models.database import Repository


class MockCommandExecutor(CommandExecutorInterface):
    """Mock command executor for testing"""

    def __init__(self) -> None:
        self.archive_list = []
        self.archive_info_data = {}
        self.file_data = {}

    def set_archive_list(self, archives: List[str]) -> None:
        """Set the list of archives to return"""
        self.archive_list = archives

    def set_archive_info(self, archive_name: str, info: Dict[str, Any]) -> None:
        """Set archive info data for a specific archive"""
        self.archive_info_data[archive_name] = info

    def set_file_data(self, archive_name: str, files: List[Dict[str, Any]]) -> None:
        """Set file data for a specific archive"""
        self.file_data[archive_name] = files

    async def execute_borg_list(self, repository) -> List[str]:
        """Return mock archive list"""
        return self.archive_list

    async def execute_borg_info(self, repository, archive_name: str):
        """Return mock archive info"""
        return self.archive_info_data.get(archive_name, {})

    async def execute_borg_list_files(
        self, repository, archive_name: str
    ) -> List[Dict[str, Any]]:
        """Return mock file data"""
        return self.file_data.get(archive_name, [])


class TestRepositoryStatsService:
    """Test RepositoryStatsService functionality."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.mock_executor = MockCommandExecutor()
        self.service = RepositoryStatsService(command_executor=self.mock_executor)

        # Create mock repository
        self.mock_repository = Mock(spec=Repository)
        self.mock_repository.id = 1
        self.mock_repository.name = "test-repo"
        self.mock_repository.path = "/path/to/repo"
        self.mock_repository.get_passphrase.return_value = "test_passphrase"

        # Mock database session
        self.mock_db = Mock()

        # Mock progress callback
        self.progress_calls = []
        self.progress_callback = Mock(
            side_effect=lambda msg, pct: self.progress_calls.append((msg, pct))
        )

    @pytest.mark.asyncio
    async def test_get_repository_statistics_success(self) -> None:
        """Test successful repository statistics gathering."""
        # Setup mock data
        self.mock_executor.set_archive_list(["archive1", "archive2"])
        self.mock_executor.set_archive_info(
            "archive1",
            {
                "name": "archive1",
                "start": "2023-01-01T10:00:00",
                "end": "2023-01-01T10:30:00",
                "duration": 1800,
                "original_size": 1000000,
                "compressed_size": 500000,
                "deduplicated_size": 300000,
                "nfiles": 100,
            },
        )
        self.mock_executor.set_archive_info(
            "archive2",
            {
                "name": "archive2",
                "start": "2023-01-02T10:00:00",
                "end": "2023-01-02T10:30:00",
                "duration": 1800,
                "original_size": 1200000,
                "compressed_size": 600000,
                "deduplicated_size": 400000,
                "nfiles": 120,
            },
        )

        result = await self.service.get_repository_statistics(
            self.mock_repository, self.mock_db, self.progress_callback
        )

        # Verify result structure
        assert "repository_path" in result
        assert "total_archives" in result
        assert "archive_stats" in result
        assert "size_over_time" in result
        assert "dedup_compression_stats" in result
        assert "file_type_stats" in result
        assert "summary" in result

        assert result["repository_path"] == "/path/to/repo"
        assert result["total_archives"] == 2
        assert len(result["archive_stats"]) == 2

        # Verify progress callbacks were called
        assert len(self.progress_calls) > 0
        assert self.progress_calls[-1] == ("Statistics analysis complete!", 100)

    @pytest.mark.asyncio
    async def test_get_repository_statistics_no_archives(self) -> None:
        """Test statistics gathering when no archives exist."""
        # Set empty archive list
        self.mock_executor.set_archive_list([])

        result = await self.service.get_repository_statistics(
            self.mock_repository, self.mock_db, self.progress_callback
        )

        assert "error" in result
        assert result["error"] == "No archives found in repository"

    @pytest.mark.asyncio
    async def test_get_repository_statistics_exception(self) -> None:
        """Test statistics gathering handles exceptions properly."""

        # Create an executor that throws exceptions
        class ExceptionExecutor(MockCommandExecutor):
            async def execute_borg_list(self, repository):
                raise Exception("Test error")

        exception_executor = ExceptionExecutor()
        service_with_exception = RepositoryStatsService(
            command_executor=exception_executor
        )

        result = await service_with_exception.get_repository_statistics(
            self.mock_repository, self.mock_db, self.progress_callback
        )

        assert "error" in result
        assert "Test error" in result["error"]

    @pytest.mark.asyncio
    async def test_get_archive_list_success(self) -> None:
        """Test successful archive listing."""
        mock_stdout = "archive1\narchive2\narchive3\n"

        with patch("asyncio.create_subprocess_exec") as mock_subprocess, patch(
            "borgitory.services.repositories.repository_stats_service.build_secure_borg_command"
        ) as mock_build_cmd:
            # Setup mocks
            mock_build_cmd.return_value = (
                ["borg", "list", "repo", "--short"],
                {"BORG_PASSPHRASE": "test"},
            )
            mock_process = AsyncMock()
            mock_process.communicate.return_value = (mock_stdout.encode(), b"")
            mock_process.returncode = 0
            mock_subprocess.return_value = mock_process

            result = await self.service._get_archive_list(self.mock_repository)

            assert result == ["archive1", "archive2", "archive3"]
            mock_build_cmd.assert_called_once()
            mock_subprocess.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_archive_list_failure(self) -> None:
        """Test archive listing failure handling."""
        with patch("asyncio.create_subprocess_exec") as mock_subprocess, patch(
            "borgitory.services.repositories.repository_stats_service.build_secure_borg_command"
        ) as mock_build_cmd:
            # Setup mocks
            mock_build_cmd.return_value = (
                ["borg", "list", "repo", "--short"],
                {"BORG_PASSPHRASE": "test"},
            )
            mock_process = AsyncMock()
            mock_process.communicate.return_value = (b"", b"Repository not found")
            mock_process.returncode = 1
            mock_subprocess.return_value = mock_process

            result = await self.service._get_archive_list(self.mock_repository)

            assert result == []

    @pytest.mark.asyncio
    async def test_get_archive_list_exception(self) -> None:
        """Test archive listing exception handling."""
        with patch("asyncio.create_subprocess_exec") as mock_subprocess:
            mock_subprocess.side_effect = Exception("Connection error")

            result = await self.service._get_archive_list(self.mock_repository)

            assert result == []

    @pytest.mark.asyncio
    async def test_get_archive_info_success(self) -> None:
        """Test successful archive info retrieval."""
        mock_json_response = {
            "archives": [
                {
                    "start": "2023-01-01T10:00:00",
                    "end": "2023-01-01T10:30:00",
                    "duration": 1800,
                    "stats": {
                        "original_size": 1000000,
                        "compressed_size": 500000,
                        "deduplicated_size": 300000,
                        "nfiles": 100,
                    },
                }
            ],
            "cache": {
                "stats": {
                    "unique_chunks": 50,
                    "total_chunks": 200,
                    "unique_size": 400000,
                    "total_size": 800000,
                }
            },
        }

        with patch("asyncio.create_subprocess_exec") as mock_subprocess, patch(
            "borgitory.services.repositories.repository_stats_service.build_secure_borg_command"
        ) as mock_build_cmd:
            # Setup mocks
            mock_build_cmd.return_value = (
                ["borg", "info", "--json", "repo::archive1"],
                {"BORG_PASSPHRASE": "test"},
            )
            mock_process = AsyncMock()
            mock_process.communicate.return_value = (
                json.dumps(mock_json_response).encode(),
                b"",
            )
            mock_process.returncode = 0
            mock_subprocess.return_value = mock_process

            result = await self.service._get_archive_info(
                self.mock_repository, "archive1"
            )

            assert result is not None
            assert result["name"] == "archive1"
            assert result["start"] == "2023-01-01T10:00:00"
            assert result["original_size"] == 1000000
            assert result["compressed_size"] == 500000
            assert result["deduplicated_size"] == 300000
            assert result["nfiles"] == 100
            assert result["unique_chunks"] == 50

    @pytest.mark.asyncio
    async def test_get_archive_info_failure(self) -> None:
        """Test archive info retrieval failure."""
        with patch("asyncio.create_subprocess_exec") as mock_subprocess, patch(
            "borgitory.services.repositories.repository_stats_service.build_secure_borg_command"
        ) as mock_build_cmd:
            # Setup mocks
            mock_build_cmd.return_value = (
                ["borg", "info", "--json", "repo::archive1"],
                {"BORG_PASSPHRASE": "test"},
            )
            mock_process = AsyncMock()
            mock_process.communicate.return_value = (b"", b"Archive not found")
            mock_process.returncode = 1
            mock_subprocess.return_value = mock_process

            result = await self.service._get_archive_info(
                self.mock_repository, "archive1"
            )

            assert result is None

    def test_build_size_timeline(self) -> None:
        """Test size timeline chart data building."""
        archive_stats = [
            {
                "name": "archive1",
                "start": "2023-01-01T10:00:00",
                "original_size": 1000000,
                "compressed_size": 500000,
                "deduplicated_size": 300000,
            },
            {
                "name": "archive2",
                "start": "2023-01-02T10:00:00",
                "original_size": 1200000,
                "compressed_size": 600000,
                "deduplicated_size": 400000,
            },
        ]

        result = self.service._build_size_timeline(archive_stats)

        assert "labels" in result
        assert "datasets" in result
        assert len(result["labels"]) == 2
        assert len(result["datasets"]) == 3  # Original, Compressed, Deduplicated

        # Check data conversion to MB
        assert result["datasets"][0]["data"][0] == 1000000 / (1024 * 1024)  # ~0.95 MB
        assert result["datasets"][1]["data"][0] == 500000 / (1024 * 1024)  # ~0.48 MB
        assert result["datasets"][2]["data"][0] == 300000 / (1024 * 1024)  # ~0.29 MB

    def test_build_dedup_compression_stats(self) -> None:
        """Test deduplication and compression statistics building."""
        archive_stats = [
            {
                "name": "archive1",
                "start": "2023-01-01T10:00:00",
                "original_size": 1000000,
                "compressed_size": 500000,
                "deduplicated_size": 300000,
            }
        ]

        result = self.service._build_dedup_compression_stats(archive_stats)

        assert "labels" in result
        assert "datasets" in result
        assert len(result["datasets"]) == 2  # Compression and Deduplication ratios

        # Check compression ratio calculation: (1000000 - 500000) / 1000000 * 100 = 50%
        assert result["datasets"][0]["data"][0] == 50.0

        # Check deduplication ratio calculation: (500000 - 300000) / 500000 * 100 = 40%
        assert result["datasets"][1]["data"][0] == 40.0

    @pytest.mark.asyncio
    async def test_get_file_type_stats_success(self) -> None:
        """Test file type statistics gathering."""
        archives = ["archive1", "archive2"]
        mock_file_output = "1024 file1.txt\n2048 file2.jpg\n512 file3.txt\n"

        with patch("asyncio.create_subprocess_exec") as mock_subprocess, patch(
            "borgitory.services.repositories.repository_stats_service.build_secure_borg_command"
        ) as mock_build_cmd:
            # Setup mocks
            mock_build_cmd.return_value = (
                ["borg", "list", "repo::archive1"],
                {"BORG_PASSPHRASE": "test"},
            )
            mock_process = AsyncMock()
            mock_process.communicate.return_value = (mock_file_output.encode(), b"")
            mock_process.returncode = 0
            mock_subprocess.return_value = mock_process

            result = await self.service._get_file_type_stats(
                self.mock_repository, archives, self.progress_callback
            )

            assert "count_chart" in result
            assert "size_chart" in result
            assert "labels" in result["count_chart"]
            assert "datasets" in result["count_chart"]

    def test_build_file_type_chart_data(self) -> None:
        """Test file type chart data building."""
        timeline_data = {
            "labels": ["2023-01-01", "2023-01-02"],
            "count_data": {"txt": [5, 8], "jpg": [3, 4], "pdf": [1, 2]},
            "size_data": {"txt": [10.5, 15.2], "jpg": [25.0, 30.1], "pdf": [5.5, 8.0]},
        }

        result = self.service._build_file_type_chart_data(timeline_data)

        assert "count_chart" in result
        assert "size_chart" in result

        count_chart = result["count_chart"]
        assert "labels" in count_chart
        assert "datasets" in count_chart
        assert count_chart["labels"] == ["2023-01-01", "2023-01-02"]

        # Should have datasets for each file type
        assert len(count_chart["datasets"]) <= 10  # Limited to top 10

        size_chart = result["size_chart"]
        assert "labels" in size_chart
        assert "datasets" in size_chart

    def test_build_summary_stats(self) -> None:
        """Test summary statistics building."""
        archive_stats = [
            {
                "start": "2023-01-01T10:00:00",
                "original_size": 1000000000,  # 1GB
                "compressed_size": 500000000,  # 500MB
                "deduplicated_size": 300000000,  # 300MB
            },
            {
                "start": "2023-01-02T10:00:00",
                "original_size": 2000000000,  # 2GB
                "compressed_size": 1000000000,  # 1GB
                "deduplicated_size": 600000000,  # 600MB
            },
        ]

        result = self.service._build_summary_stats(archive_stats)

        assert "total_archives" in result
        assert "latest_archive_date" in result
        assert "total_original_size_gb" in result
        assert "total_compressed_size_gb" in result
        assert "total_deduplicated_size_gb" in result
        assert "overall_compression_ratio" in result
        assert "overall_deduplication_ratio" in result
        assert "space_saved_gb" in result
        assert "average_archive_size_gb" in result

        assert result["total_archives"] == 2
        assert result["latest_archive_date"] == "2023-01-02T10:00:00"
        assert result["total_original_size_gb"] == 2.79  # ~3GB in total
        assert (
            result["space_saved_gb"] == 1.96
        )  # Original - deduplicated (calculated value)

    def test_build_summary_stats_empty(self) -> None:
        """Test summary statistics with empty archive stats."""
        result = self.service._build_summary_stats([])

        # Should return a complete SummaryStats TypedDict with default values
        expected = {
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
        assert result == expected

    def test_build_summary_stats_zero_division(self) -> None:
        """Test summary statistics handles zero division properly."""
        archive_stats = [
            {
                "start": "2023-01-01T10:00:00",
                "original_size": 0,
                "compressed_size": 0,
                "deduplicated_size": 0,
            }
        ]

        result = self.service._build_summary_stats(archive_stats)

        assert result["overall_compression_ratio"] == 0
        assert result["overall_deduplication_ratio"] == 0
        assert result["average_archive_size_gb"] == 0.0
