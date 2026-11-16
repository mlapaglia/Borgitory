"""Sync streams must not leave rclone running when the consumer stops early."""

import asyncio
import sys
from unittest.mock import AsyncMock, MagicMock

from borgitory.services.cloud_providers.storage.base import CloudStorage
from borgitory.services.cloud_providers.storage.s3_storage import (
    S3Storage,
    S3StorageConfig,
)


async def _long_running_process() -> asyncio.subprocess.Process:
    return await asyncio.create_subprocess_exec(
        sys.executable,
        "-c",
        "import time\nprint('Transferred: 1 / 10, 10%, 1 B/s', flush=True)\ntime.sleep(60)",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )


async def test_ensure_process_stopped_terminates_running_process() -> None:
    process = await _long_running_process()
    await CloudStorage._ensure_process_stopped(process, grace_seconds=2)
    assert process.returncode is not None


async def test_ensure_process_stopped_ignores_finished_or_missing() -> None:
    await CloudStorage._ensure_process_stopped(None)
    process = await asyncio.create_subprocess_exec(sys.executable, "-c", "pass")
    await process.wait()
    await CloudStorage._ensure_process_stopped(process)


async def test_closing_sync_stream_kills_rclone() -> None:
    process = await _long_running_process()
    executor = MagicMock()
    executor.create_subprocess = AsyncMock(return_value=process)
    storage = S3Storage(
        S3StorageConfig(
            access_key="AKIAIOSFODNN7EXAMPLE",
            secret_key="wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
            bucket_name="bkt",
        ),
        executor,
        MagicMock(),
    )

    stream = storage.sync_repository_to_s3("/repo")
    first = await stream.__anext__()
    assert first["type"] == "started"
    await stream.__anext__()  # first progress line; rclone still "running"
    assert process.returncode is None

    await stream.aclose()
    assert process.returncode is not None
