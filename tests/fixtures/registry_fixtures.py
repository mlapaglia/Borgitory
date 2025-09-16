"""
Pytest fixtures for provider registry testing.

These fixtures provide isolated registry instances for testing,
preventing cross-test contamination and enabling reliable test execution.
"""

import pytest
from typing import List


@pytest.fixture
def clean_registry():
    """
    Create a fresh, empty registry for testing.

    This fixture provides a completely clean registry with no providers registered.
    Use this when you need to test registry behavior from scratch.

    Returns:
        ProviderRegistry: Empty registry instance
    """
    from src.services.cloud_providers.registry_factory import RegistryFactory

    return RegistryFactory.create_empty_registry()


@pytest.fixture
def production_registry():
    """
    Create a registry with all production providers registered.

    This fixture provides a registry that matches the production environment,
    with all real cloud providers (S3, SFTP, SMB) registered.

    Returns:
        ProviderRegistry: Registry with all production providers
    """
    from src.services.cloud_providers.registry_factory import RegistryFactory

    return RegistryFactory.create_production_registry()


@pytest.fixture
def s3_only_registry():
    """
    Create a registry with only S3 provider registered.

    Returns:
        ProviderRegistry: Registry with only S3 provider
    """
    from src.services.cloud_providers.registry_factory import RegistryFactory

    return RegistryFactory.create_test_registry(["s3"])


@pytest.fixture
def sftp_only_registry():
    """
    Create a registry with only SFTP provider registered.

    Returns:
        ProviderRegistry: Registry with only SFTP provider
    """
    from src.services.cloud_providers.registry_factory import RegistryFactory

    return RegistryFactory.create_test_registry(["sftp"])


@pytest.fixture
def smb_only_registry():
    """
    Create a registry with only SMB provider registered.

    Returns:
        ProviderRegistry: Registry with only SMB provider
    """
    from src.services.cloud_providers.registry_factory import RegistryFactory

    return RegistryFactory.create_test_registry(["smb"])


@pytest.fixture
def multi_provider_registry():
    """
    Create a registry with S3 and SFTP providers (common test scenario).

    Returns:
        ProviderRegistry: Registry with S3 and SFTP providers
    """
    from src.services.cloud_providers.registry_factory import RegistryFactory

    return RegistryFactory.create_test_registry(["s3", "sftp"])


def create_test_registry_with_providers(providers: List[str]):
    """
    Helper function to create a test registry with specific providers.

    Args:
        providers: List of provider names to register

    Returns:
        ProviderRegistry: Registry with specified providers
    """
    from src.services.cloud_providers.registry_factory import RegistryFactory

    return RegistryFactory.create_test_registry(providers)


@pytest.fixture
def isolated_job_dependencies():
    """
    Create JobManagerDependencies with an isolated registry for testing.

    This fixture provides a complete set of job manager dependencies
    with a clean, isolated registry that won't interfere with other tests.

    Returns:
        JobManagerDependencies: Dependencies with isolated registry
    """
    from src.services.jobs.job_manager import JobManagerDependencies
    from src.services.cloud_providers.registry_factory import RegistryFactory
    from unittest.mock import Mock

    # Create isolated registry
    registry = RegistryFactory.create_test_registry(["s3", "sftp", "smb"])

    # Create minimal dependencies for testing
    return JobManagerDependencies(
        provider_registry=registry,
        db_session_factory=lambda: Mock(),
        subprocess_executor=Mock(),
        rclone_service=Mock(),
        http_client_factory=Mock(),
        encryption_service=Mock(),
        storage_factory=Mock(),
    )


@pytest.fixture
def job_executor_with_registry():
    """
    Create a JobExecutor with an isolated registry for testing.

    Returns:
        tuple: (JobExecutor, ProviderRegistry) for testing
    """
    from src.services.jobs.job_executor import JobExecutor
    from src.services.cloud_providers.registry_factory import RegistryFactory

    registry = RegistryFactory.create_test_registry(["s3", "sftp", "smb"])
    executor = JobExecutor()

    return executor, registry
