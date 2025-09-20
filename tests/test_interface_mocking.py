"""
Test that mock implementations can be created for each protocol interface.

This validates that our interfaces enable proper testing with mocks.
"""

import pytest
from unittest.mock import Mock, AsyncMock
from typing import List, Dict, Any, Optional

from borgitory.interfaces.command_runner import CommandRunner, CommandResult
from borgitory.interfaces.volume_service import VolumeService
from borgitory.interfaces.job_manager import JobManager


class MockCommandRunner:
    """Mock implementation of CommandRunner protocol"""

    async def run_command(
        self,
        command: List[str],
        env: Optional[Dict[str, str]] = None,
        timeout: Optional[int] = None,
    ) -> CommandResult:
        return CommandResult(
            success=True,
            return_code=0,
            stdout="mock output",
            stderr="",
            duration=1.0,
            error=None,
        )


class MockVolumeService:
    """Mock implementation of VolumeService protocol"""

    async def get_mounted_volumes(self) -> List[str]:
        return ["/mnt/volume1", "/mnt/volume2"]

    async def get_volume_info(self) -> Dict[str, Any]:
        return {"total_volumes": 2, "available_space": "100GB"}


class MockJobManager:
    """Mock implementation of JobManager protocol"""

    async def start_borg_command(
        self,
        command: List[str],
        env: Optional[Dict[str, str]] = None,
        is_backup: bool = False,
    ) -> str:
        return "mock-job-id-123"

    async def create_composite_job(
        self,
        job_type: str,
        task_definitions: List[Dict[str, Any]],
        repository: Any,
        schedule: Optional[Any] = None,
        cloud_sync_config_id: Optional[int] = None,
    ) -> str:
        return "mock-composite-job-id-456"

    def get_job_status(self, job_id: str) -> Optional[Dict[str, Any]]:
        return {"status": "completed", "progress": 100}

    async def get_job_output_stream(
        self, job_id: str, last_n_lines: Optional[int] = None
    ) -> Dict[str, Any]:
        return {"lines": ["line1", "line2"], "progress": {}}

    async def cancel_job(self, job_id: str) -> bool:
        return True

    def cleanup_job(self, job_id: str) -> bool:
        return True

    def get_queue_stats(self) -> Dict[str, Any]:
        return {"running": 1, "queued": 0}


def test_mock_command_runner_implements_protocol():
    """Test that mock CommandRunner can be used as protocol"""
    mock_runner: CommandRunner = MockCommandRunner()

    # Should be able to call protocol methods
    assert hasattr(mock_runner, "run_command")
    assert callable(getattr(mock_runner, "run_command"))


def test_mock_volume_service_implements_protocol():
    """Test that mock VolumeService can be used as protocol"""
    mock_service: VolumeService = MockVolumeService()

    # Should be able to call protocol methods
    assert hasattr(mock_service, "get_mounted_volumes")
    assert hasattr(mock_service, "get_volume_info")


def test_mock_job_manager_implements_protocol():
    """Test that mock JobManager can be used as protocol"""
    mock_manager: JobManager = MockJobManager()

    # Should be able to call protocol methods
    assert hasattr(mock_manager, "start_borg_command")
    assert hasattr(mock_manager, "create_composite_job")
    assert hasattr(mock_manager, "get_job_status")


@pytest.mark.asyncio
async def test_mock_command_runner_functionality():
    """Test that mock CommandRunner works functionally"""
    runner: CommandRunner = MockCommandRunner()
    result = await runner.run_command(["echo", "hello"])
    assert result.success is True
    assert result.return_code == 0
    assert result.stdout == "mock output"


@pytest.mark.asyncio
async def test_mock_volume_service_functionality():
    """Test that mock VolumeService works functionally"""
    service: VolumeService = MockVolumeService()

    volumes = await service.get_mounted_volumes()
    assert isinstance(volumes, list)
    assert len(volumes) == 2

    info = await service.get_volume_info()
    assert isinstance(info, dict)
    assert "total_volumes" in info


@pytest.mark.asyncio
async def test_mock_job_manager_functionality():
    """Test that mock JobManager works functionally"""
    manager: JobManager = MockJobManager()

    job_id = await manager.start_borg_command(["borg", "create"])
    assert job_id == "mock-job-id-123"

    status = manager.get_job_status(job_id)
    assert status is not None
    assert status["status"] == "completed"


def test_unittest_mock_with_protocols():
    """Test that unittest.Mock can be used with protocols"""
    # Create mocks for each protocol
    mock_command_runner = Mock(spec=CommandRunner)
    mock_volume_service = Mock(spec=VolumeService)
    mock_job_manager = Mock(spec=JobManager)

    # Configure mock behaviors
    mock_command_runner.run_command = AsyncMock(
        return_value=CommandResult(
            success=True, return_code=0, stdout="test", stderr="", duration=1.0
        )
    )

    mock_volume_service.get_mounted_volumes = AsyncMock(return_value=["/mnt/test"])
    mock_volume_service.get_volume_info = AsyncMock(return_value={"test": "data"})

    mock_job_manager.start_borg_command = AsyncMock(return_value="test-job-id")
    mock_job_manager.get_job_status.return_value = {"status": "running"}

    # Should be able to assign to protocol types
    runner: CommandRunner = mock_command_runner
    volume: VolumeService = mock_volume_service
    manager: JobManager = mock_job_manager

    # Verify they have the expected attributes
    assert hasattr(runner, "run_command")
    assert hasattr(volume, "get_mounted_volumes")
    assert hasattr(manager, "start_borg_command")


if __name__ == "__main__":
    pytest.main([__file__])
