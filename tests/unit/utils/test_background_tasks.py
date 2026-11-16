import asyncio
import logging

import pytest

from borgitory.utils.background_tasks import BackgroundTaskSet


async def test_keeps_reference_until_done() -> None:
    tasks = BackgroundTaskSet("test")
    gate = asyncio.Event()

    async def work() -> None:
        await gate.wait()

    tasks.spawn(work())
    assert len(tasks) == 1
    gate.set()
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    assert len(tasks) == 0


async def test_logs_exceptions(caplog: pytest.LogCaptureFixture) -> None:
    tasks = BackgroundTaskSet("test")

    async def boom() -> None:
        raise ValueError("kaboom")

    with caplog.at_level(logging.ERROR):
        task = tasks.spawn(boom(), name="boom-task")
        await asyncio.gather(task, return_exceptions=True)
        await asyncio.sleep(0)

    assert "boom-task" in caplog.text
    assert "kaboom" in caplog.text


async def test_cancel_all_cancels_pending() -> None:
    tasks = BackgroundTaskSet("test")
    started = asyncio.Event()

    async def forever() -> None:
        started.set()
        await asyncio.Event().wait()

    task = tasks.spawn(forever())
    await started.wait()
    await tasks.cancel_all(timeout=1)
    assert task.cancelled()
    assert len(tasks) == 0
