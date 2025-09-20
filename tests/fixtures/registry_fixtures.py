"""
Pytest fixtures for provider registry testing.

These fixtures provide isolated registry instances for testing,
preventing cross-test contamination and enabling reliable test execution.
"""

import pytest
from typing import List
from unittest.mock import Mock
from borgitory.services.cloud_providers.registry_factory import (
    ProviderRegistry,
    RegistryFactory,
)
from borgitory.services.notifications.registry_factory import (
    NotificationRegistryFactory,
    NotificationProviderRegistry,
)
from borgitory.services.jobs.job_manager import JobManagerDependencies
from borgitory.services.jobs.job_executor import JobExecutor


@pytest.fixture
def clean_registry() -> ProviderRegistry:
    """
    Create a fresh, empty registry for testing.

    This fixture provides a completely clean registry with no providers registered.
    Use this when you need to test registry behavior from scratch.

    Returns:
        ProviderRegistry: Empty registry instance
    """

    return RegistryFactory.create_empty_registry()


@pytest.fixture
def production_registry() -> ProviderRegistry:
    """
    Create a registry with all production providers registered.

    This fixture provides a registry that matches the production environment,
    with all real cloud providers (S3, SFTP, SMB) registered.

    Returns:
        ProviderRegistry: Registry with all production providers
    """
    from borgitory.services.cloud_providers.registry_factory import RegistryFactory

    return RegistryFactory.create_production_registry()


@pytest.fixture
def s3_only_registry() -> ProviderRegistry:
    """
    Create a registry with only S3 provider registered.

    Returns:
        ProviderRegistry: Registry with only S3 provider
    """

    return RegistryFactory.create_test_registry(["s3"])


@pytest.fixture
def sftp_only_registry() -> ProviderRegistry:
    """
    Create a registry with only SFTP provider registered.

    Returns:
        ProviderRegistry: Registry with only SFTP provider
    """

    return RegistryFactory.create_test_registry(["sftp"])


@pytest.fixture
def smb_only_registry() -> ProviderRegistry:
    """
    Create a registry with only SMB provider registered.

    Returns:
        ProviderRegistry: Registry with only SMB provider
    """

    return RegistryFactory.create_test_registry(["smb"])


@pytest.fixture
def multi_provider_registry() -> ProviderRegistry:
    """
    Create a registry with S3 and SFTP providers (common test scenario).

    Returns:
        ProviderRegistry: Registry with S3 and SFTP providers
    """

    return RegistryFactory.create_test_registry(["s3", "sftp"])


def create_test_registry_with_providers(providers: List[str]) -> ProviderRegistry:
    """
    Helper function to create a test registry with specific providers.

    Args:
        providers: List of provider names to register

    Returns:
        ProviderRegistry: Registry with specified providers
    """

    return RegistryFactory.create_test_registry(providers)


@pytest.fixture
def isolated_job_dependencies() -> JobManagerDependencies:
    """
    Create JobManagerDependencies with an isolated registry for testing.

    This fixture provides a complete set of job manager dependencies
    with a clean, isolated registry that won't interfere with other tests.

    Returns:
        JobManagerDependencies: Dependencies with isolated registry
    """

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
def job_executor_with_registry() -> tuple[JobExecutor, ProviderRegistry]:
    """
    Create a JobExecutor with an isolated registry for testing.

    Returns:
        tuple: (JobExecutor, ProviderRegistry) for testing
    """

    registry = RegistryFactory.create_test_registry(["s3", "sftp", "smb"])
    executor = JobExecutor()

    return executor, registry


# Notification Registry Fixtures


@pytest.fixture
def clean_notification_registry() -> NotificationProviderRegistry:
    """
    Create a fresh, empty notification registry for testing.

    This fixture provides a completely clean registry with no providers registered.
    Use this when you need to test registry behavior from scratch.

    Returns:
        NotificationProviderRegistry: Empty registry instance
    """
    factory = NotificationRegistryFactory()
    return factory.create_test_registry([])


@pytest.fixture
def notification_registry() -> NotificationProviderRegistry:
    """
    Create a notification registry with all production providers for testing.

    This fixture provides a registry with all available notification providers registered.
    Use this when you need to test functionality that depends on provider availability.

    Returns:
        NotificationProviderRegistry: Registry with all providers
    """
    factory = NotificationRegistryFactory()
    return factory.create_production_registry()


@pytest.fixture
def pushover_only_notification_registry() -> NotificationProviderRegistry:
    """
    Create a notification registry with only Pushover provider for focused testing.

    Returns:
        NotificationProviderRegistry: Registry with only Pushover provider
    """
    factory = NotificationRegistryFactory()
    return factory.create_test_registry(["pushover"])


@pytest.fixture
def discord_only_notification_registry() -> NotificationProviderRegistry:
    """
    Create a notification registry with only Discord provider for focused testing.

    Returns:
        NotificationProviderRegistry: Registry with only Discord provider
    """
    factory = NotificationRegistryFactory()
    return factory.create_test_registry(["discord"])
