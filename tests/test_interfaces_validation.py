"""
Test that existing services implement the protocol interfaces.

This validates that our protocol definitions match the actual service implementations.
"""

import pytest

from borgitory.interfaces.command_runner import CommandRunner
from borgitory.interfaces.volume_service import VolumeService
from borgitory.interfaces.storage_service import StorageService
from borgitory.interfaces.job_manager import JobManager, JobExecutor
from borgitory.interfaces.borg_service import BorgService

from borgitory.services.simple_command_runner import SimpleCommandRunner
from borgitory.services.volumes.volume_service import (
    VolumeService as ConcreteVolumeService,
)
from borgitory.services.cloud_providers.service import CloudSyncService
from borgitory.services.jobs.job_manager import JobManager as ConcreteJobManager
from borgitory.services.jobs.job_executor import JobExecutor as ConcreteJobExecutor
from borgitory.services.borg_service import BorgService as ConcreteBorgService


def test_simple_command_runner_implements_protocol():
    """Verify SimpleCommandRunner implements CommandRunner protocol"""
    runner: CommandRunner = SimpleCommandRunner()
    assert isinstance(runner, SimpleCommandRunner)

    # Check that the required method exists
    assert hasattr(runner, "run_command")
    assert callable(getattr(runner, "run_command"))


def test_volume_service_implements_protocol():
    """Verify VolumeService implements VolumeService protocol"""
    service: VolumeService = ConcreteVolumeService()
    assert isinstance(service, ConcreteVolumeService)

    # Check that required methods exist
    assert hasattr(service, "get_mounted_volumes")
    assert callable(getattr(service, "get_mounted_volumes"))
    assert hasattr(service, "get_volume_info")
    assert callable(getattr(service, "get_volume_info"))


def test_cloud_sync_service_implements_protocol():
    """Verify CloudSyncService implements StorageService protocol"""
    from borgitory.services.cloud_providers.service import StorageFactory
    from borgitory.services.rclone_service import RcloneService

    storage_factory = StorageFactory(RcloneService())
    service: StorageService = CloudSyncService(storage_factory)
    assert isinstance(service, CloudSyncService)

    # Check that required methods exist
    assert hasattr(service, "execute_sync")
    assert callable(getattr(service, "execute_sync"))
    assert hasattr(service, "test_connection")
    assert callable(getattr(service, "test_connection"))


def test_job_executor_implements_protocol():
    """Verify JobExecutor implements JobExecutor protocol"""
    executor: JobExecutor = ConcreteJobExecutor()
    assert isinstance(executor, ConcreteJobExecutor)

    # Check that required methods exist
    assert hasattr(executor, "start_process")
    assert callable(getattr(executor, "start_process"))
    assert hasattr(executor, "monitor_process_output")
    assert callable(getattr(executor, "monitor_process_output"))


def test_job_manager_implements_protocol():
    """Verify JobManager implements JobManager protocol"""
    # JobManager requires dependencies, so we'll create a minimal instance
    from borgitory.services.jobs.job_manager import (
        JobManagerConfig,
        JobManagerDependencies,
    )

    config = JobManagerConfig()
    dependencies = JobManagerDependencies()
    manager: JobManager = ConcreteJobManager(config, dependencies)
    assert isinstance(manager, ConcreteJobManager)

    # Check that required methods exist
    assert hasattr(manager, "start_borg_command")
    assert callable(getattr(manager, "start_borg_command"))
    assert hasattr(manager, "create_composite_job")
    assert callable(getattr(manager, "create_composite_job"))
    assert hasattr(manager, "get_job_status")
    assert callable(getattr(manager, "get_job_status"))


def test_borg_service_implements_protocol():
    """Verify BorgService implements BorgService protocol"""
    service: BorgService = ConcreteBorgService()
    assert isinstance(service, ConcreteBorgService)

    # Check that required methods exist
    assert hasattr(service, "initialize_repository")
    assert callable(getattr(service, "initialize_repository"))
    assert hasattr(service, "create_backup")
    assert callable(getattr(service, "create_backup"))
    assert hasattr(service, "list_archives")
    assert callable(getattr(service, "list_archives"))
    assert hasattr(service, "get_repo_info")
    assert callable(getattr(service, "get_repo_info"))
    assert hasattr(service, "scan_for_repositories")
    assert callable(getattr(service, "scan_for_repositories"))


def test_protocol_methods_match_implementations():
    """Test that protocol method signatures match implementations"""
    # This is a more advanced test that could check method signatures
    # For now, we'll just verify the basic structure is correct

    # CommandRunner
    runner = SimpleCommandRunner()
    assert hasattr(runner, "run_command")

    # VolumeService
    volume_service = ConcreteVolumeService()
    assert hasattr(volume_service, "get_mounted_volumes")
    assert hasattr(volume_service, "get_volume_info")

    # BorgService
    borg_service = ConcreteBorgService()
    assert hasattr(borg_service, "initialize_repository")
    assert hasattr(borg_service, "create_backup")
    assert hasattr(borg_service, "list_archives")
    assert hasattr(borg_service, "get_repo_info")
    assert hasattr(borg_service, "scan_for_repositories")


if __name__ == "__main__":
    pytest.main([__file__])
