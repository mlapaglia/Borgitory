"""
Owned fire-and-forget asyncio tasks.

``asyncio.create_task`` only keeps a weak reference to the task, so a task
nobody holds can be garbage-collected mid-flight, and an exception it raises is
never observed. ``BackgroundTaskSet`` keeps a strong reference until the task
finishes, logs failures, and can cancel everything on shutdown.
"""

import asyncio
import logging
from typing import Any, Coroutine, Optional, Set, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


class BackgroundTaskSet:
    def __init__(self, owner: str) -> None:
        self._owner = owner
        self._tasks: Set["asyncio.Task[Any]"] = set()

    def spawn(
        self, coro: Coroutine[Any, Any, T], *, name: Optional[str] = None
    ) -> "asyncio.Task[T]":
        task = asyncio.create_task(coro, name=name)
        self._tasks.add(task)
        task.add_done_callback(self._on_done)
        return task

    def _on_done(self, task: "asyncio.Task[Any]") -> None:
        self._tasks.discard(task)
        if task.cancelled():
            return
        exc = task.exception()
        if exc is not None:
            logger.error(
                "Background task %r owned by %s failed",
                task.get_name(),
                self._owner,
                exc_info=exc,
            )

    def __len__(self) -> int:
        return len(self._tasks)

    async def cancel_all(self, timeout: float = 10.0) -> None:
        """Cancel all pending tasks and wait (bounded) for them to finish."""
        pending = [t for t in self._tasks if not t.done()]
        if not pending:
            return
        logger.info("Cancelling %d background task(s) of %s", len(pending), self._owner)
        for task in pending:
            task.cancel()
        _, still_running = await asyncio.wait(pending, timeout=timeout)
        if still_running:
            logger.warning(
                "%d background task(s) of %s did not stop within %.0fs",
                len(still_running),
                self._owner,
                timeout,
            )


# Tasks spawned by components without their own lifecycle (task executors,
# cloud sync orchestration). Cancelled from the application lifespan.
background_tasks = BackgroundTaskSet("borgitory")
