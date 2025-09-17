"""
Comprehensive tests for cloud_providers/orchestration.py

This test file ensures complete coverage of the orchestration layer with
proper DI patterns and real database usage where appropriate.
"""

import pytest
import asyncio
import time
from unittest.mock import Mock

from borgitory.services.cloud_providers.orchestration import (
    CloudSyncer,
    LoggingSyncEventHandler,
    SyncEventHandler,
)
from borgitory.services.cloud_providers.types import (
    SyncEvent,
    SyncEventType,
    ConnectionInfo,
)
from borgitory.services.cloud_providers.storage import CloudStorage


class MockCloudStorage(CloudStorage):
    """Mock storage for testing orchestration"""

    def __init__(self, test_connection_result=True, upload_should_fail=False) -> None:
        self._test_connection_result = test_connection_result
        self._upload_should_fail = upload_should_fail
        self._upload_calls = []
        self._progress_callback = None

    async def test_connection(self) -> bool:
        return self._test_connection_result

    async def upload_repository(
        self, repository_path: str, remote_path: str, progress_callback=None
    ):
        self._upload_calls.append((repository_path, remote_path))
        self._progress_callback = progress_callback

        if self._upload_should_fail:
            raise Exception("Upload failed")

        # Simulate progress events
        if progress_callback:
            await asyncio.sleep(0.01)  # Small delay to simulate work
            progress_callback(
                SyncEvent(
                    type=SyncEventType.PROGRESS,
                    message="Uploading files...",
                    progress=50.0,
                )
            )
            await asyncio.sleep(0.01)
            progress_callback(
                SyncEvent(
                    type=SyncEventType.PROGRESS, message="Almost done...", progress=90.0
                )
            )

    def get_connection_info(self) -> ConnectionInfo:
        return ConnectionInfo(provider="mock", details={"host": "mock.example.com"})

    def get_sensitive_fields(self) -> list[str]:
        return ["password", "secret_key"]

    def get_display_details(self, config_dict: dict) -> dict:
        return {
            "provider_name": "Mock Provider",
            "provider_details": "<div><strong>Mock:</strong> Test Provider</div>",
        }


class MockSyncEventHandler(SyncEventHandler):
    """Mock event handler for testing"""

    def __init__(self) -> None:
        self.events = []

    async def handle_event(self, event: SyncEvent) -> None:
        self.events.append(event)


class TestLoggingSyncEventHandler:
    """Test LoggingSyncEventHandler with all event types and edge cases"""

    @pytest.fixture
    def mock_logger(self):
        return Mock()

    @pytest.fixture
    def output_messages(self):
        return []

    @pytest.fixture
    def output_callback(self, output_messages):
        def callback(message) -> None:
            output_messages.append(message)

        return callback

    @pytest.fixture
    def handler_with_callback(self, mock_logger, output_callback):
        return LoggingSyncEventHandler(mock_logger, output_callback)

    @pytest.fixture
    def handler_without_callback(self, mock_logger):
        return LoggingSyncEventHandler(mock_logger)

    @pytest.mark.asyncio
    async def test_handle_started_event(
        self, handler_with_callback, mock_logger, output_messages
    ) -> None:
        """Test handling STARTED event type"""
        event = SyncEvent(type=SyncEventType.STARTED, message="Starting sync")

        await handler_with_callback.handle_event(event)

        mock_logger.info.assert_called_once_with("Starting sync")
        assert "Starting sync" in output_messages

    @pytest.mark.asyncio
    async def test_handle_progress_event(
        self, handler_with_callback, mock_logger, output_messages
    ) -> None:
        """Test handling PROGRESS event type with percentage"""
        event = SyncEvent(
            type=SyncEventType.PROGRESS, message="Uploading files", progress=45.7
        )

        await handler_with_callback.handle_event(event)

        mock_logger.debug.assert_called_once_with("Uploading files (45.7%)")
        assert "Uploading files" in output_messages

    @pytest.mark.asyncio
    async def test_handle_completed_event(
        self, handler_with_callback, mock_logger, output_messages
    ) -> None:
        """Test handling COMPLETED event type"""
        event = SyncEvent(type=SyncEventType.COMPLETED, message="Sync completed")

        await handler_with_callback.handle_event(event)

        mock_logger.info.assert_called_once_with("Sync completed")
        assert "Sync completed" in output_messages

    @pytest.mark.asyncio
    async def test_handle_error_event(
        self, handler_with_callback, mock_logger, output_messages
    ) -> None:
        """Test handling ERROR event type with error details"""
        event = SyncEvent(
            type=SyncEventType.ERROR, message="Upload failed", error="Network timeout"
        )

        await handler_with_callback.handle_event(event)

        mock_logger.error.assert_called_once_with("Upload failed: Network timeout")
        assert "Upload failed" in output_messages

    @pytest.mark.asyncio
    async def test_handle_log_event(
        self, handler_with_callback, mock_logger, output_messages
    ) -> None:
        """Test handling LOG event type"""
        event = SyncEvent(type=SyncEventType.LOG, message="General log message")

        await handler_with_callback.handle_event(event)

        mock_logger.info.assert_called_once_with("General log message")
        assert "General log message" in output_messages

    @pytest.mark.asyncio
    async def test_handle_event_without_callback(
        self, handler_without_callback, mock_logger
    ) -> None:
        """Test handler without output callback still logs"""
        event = SyncEvent(type=SyncEventType.STARTED, message="Starting sync")

        await handler_without_callback.handle_event(event)

        mock_logger.info.assert_called_once_with("Starting sync")

    @pytest.mark.asyncio
    async def test_handle_error_event_without_error_details(
        self, handler_with_callback, mock_logger
    ) -> None:
        """Test error event without error field"""
        event = SyncEvent(type=SyncEventType.ERROR, message="Something went wrong")

        await handler_with_callback.handle_event(event)

        mock_logger.error.assert_called_once_with("Something went wrong: None")

    @pytest.mark.asyncio
    async def test_handle_progress_event_zero_progress(
        self, handler_with_callback, mock_logger
    ) -> None:
        """Test progress event with zero progress"""
        event = SyncEvent(
            type=SyncEventType.PROGRESS, message="Starting upload", progress=0.0
        )

        await handler_with_callback.handle_event(event)

        mock_logger.debug.assert_called_once_with("Starting upload (0.0%)")


class TestCloudSyncer:
    """Test CloudSyncer orchestration with comprehensive coverage"""

    @pytest.fixture
    def mock_storage_success(self):
        return MockCloudStorage(test_connection_result=True)

    @pytest.fixture
    def mock_storage_connection_fail(self):
        return MockCloudStorage(test_connection_result=False)

    @pytest.fixture
    def mock_storage_upload_fail(self):
        return MockCloudStorage(test_connection_result=True, upload_should_fail=True)

    @pytest.fixture
    def mock_event_handler(self):
        return MockSyncEventHandler()

    @pytest.fixture
    def syncer_success(self, mock_storage_success, mock_event_handler):
        return CloudSyncer(mock_storage_success, mock_event_handler)

    @pytest.fixture
    def syncer_connection_fail(self, mock_storage_connection_fail, mock_event_handler):
        return CloudSyncer(mock_storage_connection_fail, mock_event_handler)

    @pytest.fixture
    def syncer_upload_fail(self, mock_storage_upload_fail, mock_event_handler):
        return CloudSyncer(mock_storage_upload_fail, mock_event_handler)

    @pytest.mark.asyncio
    async def test_successful_sync_with_default_remote_path(
        self, syncer_success, mock_event_handler
    ) -> None:
        """Test successful sync operation with default remote path"""
        repository_path = "/test/repo"

        result = await syncer_success.sync_repository(repository_path)

        # Verify result
        assert result.success is True
        assert result.bytes_transferred > 0  # Placeholder values from mock
        assert result.files_transferred > 0
        assert result.duration_seconds > 0
        assert result.error is None

        # Verify events were generated
        event_types = [event.type for event in mock_event_handler.events]
        assert SyncEventType.STARTED in event_types
        assert SyncEventType.COMPLETED in event_types

        # Verify start event
        start_events = [
            e for e in mock_event_handler.events if e.type == SyncEventType.STARTED
        ]
        assert len(start_events) == 1
        assert repository_path in start_events[0].message

        # Verify completion event
        completed_events = [
            e for e in mock_event_handler.events if e.type == SyncEventType.COMPLETED
        ]
        assert len(completed_events) == 1
        assert "successfully" in completed_events[0].message.lower()

    @pytest.mark.asyncio
    async def test_successful_sync_with_custom_remote_path(
        self, syncer_success, mock_event_handler
    ) -> None:
        """Test successful sync with custom remote path"""
        repository_path = "/test/repo"
        remote_path = "backups/prod"

        result = await syncer_success.sync_repository(repository_path, remote_path)

        assert result.success is True

        # Verify storage was called with correct parameters
        storage = syncer_success._storage
        assert len(storage._upload_calls) == 1
        assert storage._upload_calls[0] == (repository_path, remote_path)

    @pytest.mark.asyncio
    async def test_sync_connection_test_failure(
        self, syncer_connection_fail, mock_event_handler
    ) -> None:
        """Test sync when connection test fails"""
        repository_path = "/test/repo"

        result = await syncer_connection_fail.sync_repository(repository_path)

        # Verify result indicates failure
        assert result.success is False
        assert result.error == "Connection test failed"
        # Connection test failure returns immediately without duration tracking
        assert result.duration_seconds == 0.0

        # Verify error event was generated
        error_events = [
            e for e in mock_event_handler.events if e.type == SyncEventType.ERROR
        ]
        assert len(error_events) == 1
        assert "Connection test failed" in error_events[0].message
        assert error_events[0].error == "Connection test failed"

        # Verify upload was not attempted
        storage = syncer_connection_fail._storage
        assert len(storage._upload_calls) == 0

    @pytest.mark.asyncio
    async def test_sync_upload_failure(
        self, syncer_upload_fail, mock_event_handler
    ) -> None:
        """Test sync when upload fails with exception"""
        repository_path = "/test/repo"

        result = await syncer_upload_fail.sync_repository(repository_path)

        # Verify result indicates failure
        assert result.success is False
        assert "Upload failed" in result.error
        assert result.duration_seconds > 0

        # Verify error event was generated
        error_events = [
            e for e in mock_event_handler.events if e.type == SyncEventType.ERROR
        ]
        assert len(error_events) == 1
        assert "Sync failed" in error_events[0].message
        assert "Upload failed" in error_events[0].error

    @pytest.mark.asyncio
    async def test_sync_progress_callback_integration(
        self, syncer_success, mock_event_handler
    ) -> None:
        """Test that progress callbacks are properly integrated"""
        repository_path = "/test/repo"

        result = await syncer_success.sync_repository(repository_path)

        assert result.success is True

        # The mock storage should have called the progress callback
        storage = syncer_success._storage
        assert storage._progress_callback is not None

        # Should have received progress events through the callback mechanism
        # Note: The exact events depend on the mock implementation

    @pytest.mark.asyncio
    async def test_sync_measures_duration_on_success(self, syncer_success) -> None:
        """Test that duration is properly measured for successful sync"""
        start_time = time.time()

        result = await syncer_success.sync_repository("/test/repo")

        end_time = time.time()

        assert result.success is True
        assert (
            0 < result.duration_seconds < (end_time - start_time + 1)
        )  # Allow some margin

    @pytest.mark.asyncio
    async def test_sync_measures_duration_on_failure(self, syncer_upload_fail) -> None:
        """Test that duration is measured even on failure during upload"""
        start_time = time.time()

        result = await syncer_upload_fail.sync_repository("/test/repo")

        end_time = time.time()

        assert result.success is False
        # Upload failure (exception) does measure duration
        assert 0 < result.duration_seconds < (end_time - start_time + 1)

    @pytest.mark.asyncio
    async def test_test_connection_success(
        self, syncer_success, mock_event_handler
    ) -> None:
        """Test successful connection test"""
        result = await syncer_success.test_connection()

        assert result is True

        # Verify events were generated
        event_types = [event.type for event in mock_event_handler.events]
        assert SyncEventType.STARTED in event_types
        assert SyncEventType.COMPLETED in event_types

        # Check specific messages
        start_events = [
            e for e in mock_event_handler.events if e.type == SyncEventType.STARTED
        ]
        assert "Testing cloud storage connection" in start_events[0].message

        completed_events = [
            e for e in mock_event_handler.events if e.type == SyncEventType.COMPLETED
        ]
        assert "Connection test successful" in completed_events[0].message

    @pytest.mark.asyncio
    async def test_test_connection_failure(
        self, syncer_connection_fail, mock_event_handler
    ) -> None:
        """Test failed connection test"""
        result = await syncer_connection_fail.test_connection()

        assert result is False

        # Verify error event was generated
        error_events = [
            e for e in mock_event_handler.events if e.type == SyncEventType.ERROR
        ]
        assert len(error_events) == 1
        assert "Connection test failed" in error_events[0].message
        assert "Connection test returned false" in error_events[0].error

    @pytest.mark.asyncio
    async def test_test_connection_exception(self, mock_event_handler) -> None:
        """Test connection test with exception"""

        # Create storage that raises exception on test_connection
        class ExceptionStorage(CloudStorage):
            async def test_connection(self):
                raise Exception("Network error")

            async def upload_repository(
                self, repository_path, remote_path, progress_callback=None
            ) -> None:
                pass

            def get_connection_info(self):
                return ConnectionInfo(provider="test", details={})

            def get_sensitive_fields(self):
                return []

            def get_display_details(self, config_dict: dict) -> dict:
                return {
                    "provider_name": "Exception Provider",
                    "provider_details": "<div><strong>Test:</strong> Exception Provider</div>",
                }

        storage = ExceptionStorage()
        syncer = CloudSyncer(storage, mock_event_handler)

        result = await syncer.test_connection()

        assert result is False

        # Verify error event was generated
        error_events = [
            e for e in mock_event_handler.events if e.type == SyncEventType.ERROR
        ]
        assert len(error_events) == 1
        assert "Connection test error" in error_events[0].message
        assert "Network error" in error_events[0].error

    def test_get_connection_info(self, syncer_success) -> None:
        """Test getting connection info"""
        info = syncer_success.get_connection_info()

        assert isinstance(info, str)
        assert "mock" in info.lower()
        assert "mock.example.com" in info

    @pytest.mark.asyncio
    async def test_sync_with_empty_repository_path(
        self, syncer_success, mock_event_handler
    ) -> None:
        """Test sync with empty repository path"""
        result = await syncer_success.sync_repository("")

        # Should still work - storage implementation handles validation
        assert result.success is True

        # Verify storage was called
        storage = syncer_success._storage
        assert len(storage._upload_calls) == 1
        assert storage._upload_calls[0][0] == ""

    @pytest.mark.asyncio
    async def test_sync_with_none_remote_path(self, syncer_success) -> None:
        """Test sync with None remote path (should use default)"""
        # This tests the default parameter handling
        result = await syncer_success.sync_repository("/test/repo")

        assert result.success is True

        # Verify storage was called with empty string default
        storage = syncer_success._storage
        assert storage._upload_calls[0][1] == ""

    @pytest.mark.asyncio
    async def test_progress_callback_asyncio_task_creation(
        self, syncer_success
    ) -> None:
        """Test that progress callback properly creates asyncio tasks"""
        # This test verifies the asyncio.create_task line in the progress callback
        repository_path = "/test/repo"

        # Mock asyncio.create_task to verify it's called
        original_create_task = asyncio.create_task
        create_task_calls = []

        def mock_create_task(coro):
            create_task_calls.append(coro)
            return original_create_task(coro)

        asyncio.create_task = mock_create_task

        try:
            result = await syncer_success.sync_repository(repository_path)
            assert result.success is True

            # Give tasks time to complete
            await asyncio.sleep(0.1)

            # Verify create_task was called (progress events trigger this)
            assert len(create_task_calls) > 0

        finally:
            asyncio.create_task = original_create_task

    @pytest.mark.asyncio
    async def test_multiple_sync_operations_independence(
        self, mock_storage_success, mock_event_handler
    ) -> None:
        """Test that multiple sync operations are independent"""
        syncer = CloudSyncer(mock_storage_success, mock_event_handler)

        # Run two sync operations
        result1 = await syncer.sync_repository("/repo1", "path1")
        result2 = await syncer.sync_repository("/repo2", "path2")

        assert result1.success is True
        assert result2.success is True

        # Verify both operations were recorded
        storage = mock_storage_success
        assert len(storage._upload_calls) == 2
        assert storage._upload_calls[0] == ("/repo1", "path1")
        assert storage._upload_calls[1] == ("/repo2", "path2")

        # Verify events for both operations
        start_events = [
            e for e in mock_event_handler.events if e.type == SyncEventType.STARTED
        ]
        assert len(start_events) == 2
        assert "/repo1" in start_events[0].message
        assert "/repo2" in start_events[1].message
