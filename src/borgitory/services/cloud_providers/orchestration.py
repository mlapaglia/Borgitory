"""
Cloud sync orchestration layer.

This module provides the business logic for coordinating cloud sync operations
with clean separation of concerns and easy testability.
"""

import asyncio
import time
from abc import ABC, abstractmethod
from typing import Callable, Optional
import logging

from .types import SyncEvent, SyncEventType, SyncResult
from .storage import CloudStorage


class SyncEventHandler(ABC):
    """
    Abstract interface for handling sync events.

    This allows different ways of handling events (logging, UI updates, etc.)
    while keeping the orchestration layer clean and testable.
    """

    @abstractmethod
    async def handle_event(self, event: SyncEvent) -> None:
        """
        Handle a sync event.

        Args:
            event: The sync event to handle
        """
        pass


class LoggingSyncEventHandler(SyncEventHandler):
    """Event handler that logs sync events"""

    def __init__(
        self,
        logger: logging.Logger,
        output_callback: Optional[Callable[[str], None]] = None,
    ) -> None:
        """
        Initialize logging event handler.

        Args:
            logger: Logger instance for writing log messages
            output_callback: Optional callback for real-time output
        """
        self._logger = logger
        self._output_callback = output_callback

    async def handle_event(self, event: SyncEvent) -> None:
        """Handle event by logging and optionally calling output callback"""
        if event.type == SyncEventType.STARTED:
            self._logger.info(event.message)
        elif event.type == SyncEventType.PROGRESS:
            self._logger.debug(f"{event.message} ({event.progress:.1f}%)")
        elif event.type == SyncEventType.COMPLETED:
            self._logger.info(event.message)
        elif event.type == SyncEventType.ERROR:
            self._logger.error(f"{event.message}: {event.error}")
        elif event.type == SyncEventType.LOG:
            self._logger.info(event.message)

        if self._output_callback:
            self._output_callback(event.message)


class CloudSyncer:
    """
    Orchestrates cloud sync operations.

    This class contains the core business logic for syncing repositories
    to cloud storage. It's designed to be easily testable with clear
    dependencies and simple return types.
    """

    def __init__(self, storage: CloudStorage, event_handler: SyncEventHandler) -> None:
        """
        Initialize cloud syncer.

        Args:
            storage: Cloud storage implementation
            event_handler: Handler for sync events
        """
        self._storage = storage
        self._event_handler = event_handler

    async def sync_repository(
        self, repository_path: str, remote_path: str = ""
    ) -> SyncResult:
        """
        Sync a repository to cloud storage.

        This method orchestrates the entire sync process:
        1. Test connection
        2. Upload repository
        3. Handle success/failure
        4. Return simple result

        Args:
            repository_path: Local path to the repository
            remote_path: Remote path prefix for storage

        Returns:
            SyncResult indicating success/failure and details
        """
        start_time = time.time()

        try:
            await self._event_handler.handle_event(
                SyncEvent(
                    type=SyncEventType.STARTED,
                    message=f"Starting sync of repository {repository_path}",
                )
            )

            if not await self._storage.test_connection():
                error_msg = "Connection test failed"
                await self._event_handler.handle_event(
                    SyncEvent(
                        type=SyncEventType.ERROR, message=error_msg, error=error_msg
                    )
                )
                return SyncResult.error_result(error_msg)

            # Upload repository with progress tracking
            bytes_transferred = 0
            files_transferred = 0

            def progress_callback(event: SyncEvent) -> None:
                nonlocal bytes_transferred, files_transferred

                # Extract metrics from progress events if available
                # This would be enhanced based on actual rclone output parsing
                if event.type == SyncEventType.PROGRESS:
                    # In a real implementation, we'd parse rclone output for actual numbers
                    bytes_transferred += 1024  # Placeholder
                    files_transferred += 1  # Placeholder

                asyncio.create_task(self._event_handler.handle_event(event))

            await self._storage.upload_repository(
                repository_path, remote_path, progress_callback
            )

            duration = time.time() - start_time

            await self._event_handler.handle_event(
                SyncEvent(
                    type=SyncEventType.COMPLETED,
                    message=f"Repository sync completed successfully in {duration:.1f}s",
                )
            )

            return SyncResult.success_result(
                bytes_transferred=bytes_transferred,
                files_transferred=files_transferred,
                duration_seconds=duration,
            )

        except Exception as e:
            error_msg = f"Sync failed: {str(e)}"
            duration = time.time() - start_time

            await self._event_handler.handle_event(
                SyncEvent(type=SyncEventType.ERROR, message=error_msg, error=str(e))
            )

            result = SyncResult.error_result(error_msg)
            result.duration_seconds = duration
            return result

    async def test_connection(self) -> bool:
        """
        Test connection to cloud storage.

        Returns:
            True if connection successful, False otherwise
        """
        try:
            await self._event_handler.handle_event(
                SyncEvent(
                    type=SyncEventType.STARTED,
                    message="Testing cloud storage connection",
                )
            )

            success = await self._storage.test_connection()

            if success:
                await self._event_handler.handle_event(
                    SyncEvent(
                        type=SyncEventType.COMPLETED,
                        message="Connection test successful",
                    )
                )
            else:
                await self._event_handler.handle_event(
                    SyncEvent(
                        type=SyncEventType.ERROR,
                        message="Connection test failed",
                        error="Connection test returned false",
                    )
                )

            return success

        except Exception as e:
            await self._event_handler.handle_event(
                SyncEvent(
                    type=SyncEventType.ERROR,
                    message=f"Connection test error: {str(e)}",
                    error=str(e),
                )
            )
            return False

    def get_connection_info(self) -> str:
        """
        Get connection information for display.

        Returns:
            String representation of connection info
        """
        return str(self._storage.get_connection_info())
