from contextlib import asynccontextmanager
from typing import AsyncGenerator, Callable, Any
from anyio import create_task_group
from fastapi import Request
from functools import wraps
from inspect import signature
from borgitory.services.repositories.repository_stats_service import logger


@asynccontextmanager
async def cancel_on_disconnect(request: Request) -> AsyncGenerator[None, None]:
    """
    Async context manager for async code that needs to be cancelled if client disconnects prematurely.
    The client disconnect is monitored through the Request object.
    """
    async with create_task_group() as tg:

        async def watch_disconnect() -> None:
            while True:
                message = await request.receive()
                if message["type"] == "http.disconnect":
                    client = (
                        f"{request.client.host}:{request.client.port}"
                        if request.client
                        else "-:-"
                    )
                    logger.info(
                        f'{client} - "{request.method} {request.url.path}" 499 DISCONNECTED'
                    )
                    tg.cancel_scope.cancel()
                    break

        tg.start_soon(watch_disconnect)
        try:
            yield
        finally:
            tg.cancel_scope.cancel()


def with_cancel_on_disconnect(func: Callable[..., Any]) -> Callable[..., Any]:
    """
    Decorator that automatically wraps the endpoint logic in cancel_on_disconnect.
    The endpoint must have a 'request: Request' parameter.
    """

    @wraps(func)
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        # Find the request object
        request = None

        # Check kwargs first
        if "request" in kwargs:
            request = kwargs["request"]
        else:
            # Try to find it in positional args based on function signature
            sig = signature(func)
            params = list(sig.parameters.keys())
            if "request" in params:
                idx = params.index("request")
                if idx < len(args):
                    request = args[idx]

        if not request:
            # If no request found, just run normally
            return await func(*args, **kwargs)

        # Run with cancellation
        async with cancel_on_disconnect(request):
            return await func(*args, **kwargs)

    return wrapper
