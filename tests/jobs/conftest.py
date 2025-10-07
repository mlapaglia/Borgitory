"""
Shared fixtures for job manager tests
"""

import pytest
from unittest.mock import Mock, AsyncMock


# Module-level mock fixtures that can be used by all test classes
@pytest.fixture
def mock_job_executor() -> Mock:
    """Create a mock job executor with all needed methods"""
    executor = Mock()
    executor.start_process = AsyncMock()
    executor.monitor_process_output = AsyncMock()
    executor.execute_command = AsyncMock()
    executor.execute_prune_task = AsyncMock()
    executor.execute_cloud_sync_task = AsyncMock()
    return executor


@pytest.fixture
def mock_database_manager() -> Mock:
    """Create a mock database manager"""
    db_manager = Mock()
    db_manager.get_repository_data = AsyncMock()
    db_manager.update_job_status = AsyncMock()
    db_manager.update_task_status = AsyncMock()
    db_manager.create_job = AsyncMock()
    db_manager.create_task = AsyncMock()
    db_manager.create_database_job = AsyncMock()
    return db_manager


@pytest.fixture
def mock_output_manager() -> Mock:
    """Create a mock output manager"""
    output_manager = Mock()
    output_manager.create_job_output = Mock()
    output_manager.add_output_line = AsyncMock()
    output_manager.stream_job_output = Mock()
    output_manager.get_job_output = Mock()
    return output_manager


@pytest.fixture
def mock_queue_manager() -> Mock:
    """Create a mock queue manager"""
    queue_manager = Mock()
    queue_manager.add_job = Mock()
    queue_manager.get_next_job = Mock()
    queue_manager.remove_job = Mock()
    queue_manager.initialize = AsyncMock()
    return queue_manager


@pytest.fixture
def mock_event_broadcaster() -> Mock:
    """Create a mock event broadcaster"""
    broadcaster = Mock()
    broadcaster.broadcast_job_update = Mock()
    broadcaster.broadcast_task_update = Mock()
    broadcaster.initialize = AsyncMock()
    return broadcaster


@pytest.fixture
def mock_secure_borg_command() -> Mock:
    """Create a mock secure borg command context manager"""
    mock_cm = Mock()
    mock_cm.__aenter__ = AsyncMock(
        return_value=(
            ["borg", "create", "repo::test-archive", "/tmp"],
            {"BORG_PASSPHRASE": "test"},
            None,
        )
    )
    mock_cm.__aexit__ = AsyncMock(return_value=None)
    return mock_cm


@pytest.fixture
def mock_notification_service() -> Mock:
    """Create a mock notification service"""
    notification_service = Mock()
    notification_service.load_config_from_storage = Mock()
    notification_service.send_notification = AsyncMock()
    return notification_service
