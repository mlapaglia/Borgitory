"""
Base cloud storage interface and configuration.

This module defines the abstract interface that all cloud storage providers
must implement, ensuring consistency across different providers.
"""

import asyncio
from abc import ABC, abstractmethod
from typing import AsyncGenerator, Callable, Dict, Optional, Union
from pydantic import BaseModel, ConfigDict

from borgitory.services.rclone_types import ProgressData
from ..types import SyncEvent, ConnectionInfo


class CloudStorageConfig(BaseModel):
    """
    Base configuration for all cloud storage implementations.

    Each provider should extend this with provider-specific fields.
    """

    model_config = ConfigDict(extra="forbid")  # Prevent unknown fields


class CloudStorage(ABC):
    """
    Abstract interface for cloud storage operations.

    This interface is designed to be:
    - Easy to implement for new providers
    - Simple to mock and test
    - Free of async generator complexity
    - Focused on single responsibility
    """

    @abstractmethod
    async def upload_repository(
        self,
        repository_path: str,
        remote_path: str,
        progress_callback: Optional[Callable[[SyncEvent], None]] = None,
    ) -> None:
        pass

    @abstractmethod
    async def test_connection(self) -> bool:
        pass

    @abstractmethod
    def get_connection_info(self) -> ConnectionInfo:
        pass

    @abstractmethod
    def get_sensitive_fields(self) -> list[str]:
        pass

    @abstractmethod
    def get_display_details(self, config_dict: Dict[str, object]) -> Dict[str, object]:
        pass

    async def _merge_async_generators(
        self, *async_generators: AsyncGenerator[ProgressData, None]
    ) -> AsyncGenerator[ProgressData, None]:
        """Concurrently merge multiple async generators using an asyncio.Queue."""
        queue: asyncio.Queue[tuple[bool, ProgressData | None]] = asyncio.Queue()

        async def producer(gen: AsyncGenerator[ProgressData, None]) -> None:
            async for item in gen:
                await queue.put((False, item))
            await queue.put((True, None))

        tasks = [asyncio.create_task(producer(g)) for g in async_generators]
        finished = 0
        try:
            while finished < len(tasks):
                is_sentinel, item = await queue.get()
                if is_sentinel:
                    finished += 1
                else:
                    yield item  # type: ignore[misc]
        finally:
            for t in tasks:
                if not t.done():
                    t.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

    def parse_rclone_progress(
        self, line: str
    ) -> Optional[Dict[str, Union[str, int, float]]]:
        if "Transferred:" in line:
            try:
                parts = line.split()
                if len(parts) >= 6:
                    transferred = parts[1]
                    total = parts[4].rstrip(",")
                    percentage = parts[5].rstrip("%,")
                    speed = parts[6] if len(parts) > 6 else "0"

                    return {
                        "transferred": transferred,
                        "total": total,
                        "percentage": float(percentage)
                        if percentage.replace(".", "").isdigit()
                        else 0,
                        "speed": speed,
                    }
            except (IndexError, ValueError):
                pass

        if "ETA" in line:
            try:
                eta_part = line.split("ETA")[-1].strip()
                return {"eta": eta_part}
            except (ValueError, KeyError):
                pass

        return None
