"""Background turns that outlive the browser connection. Implements: ADR-0003."""

import asyncio
from collections.abc import Coroutine
from typing import Any

_tasks: set[asyncio.Task[None]] = set()


def spawn(work: Coroutine[Any, Any, None]) -> asyncio.Task[None]:
    """Schedule work on the event loop without tying it to the HTTP request."""

    task = asyncio.create_task(work)
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)
    return task


async def drain_background() -> None:
    pending = list(_tasks)
    if pending:
        await asyncio.gather(*pending, return_exceptions=True)
