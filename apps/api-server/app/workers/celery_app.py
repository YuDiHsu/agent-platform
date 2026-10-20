"""Celery worker and beat schedule for background tickets. Implements: REQ-011, ADR-0002.

Run with ``celery -A app.workers.celery_app worker`` and ``celery -A app.workers.celery_app beat``.
"""

import asyncio
import os
import socket
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import TypeVar

from celery import Celery

from app.core.config import settings

T = TypeVar("T")

HEARTBEAT_TICK_SECONDS = 60.0
TICKET_SWEEP_SECONDS = 15.0
_MAX_TICKETS_PER_SWEEP = 20

celery_app = Celery("eamp", broker=settings.REDIS_URL, backend=None)
celery_app.conf.update(
    timezone="UTC",
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_ignore_result=True,
    beat_schedule={
        "fire-due-heartbeats": {"task": "eamp.fire_due_heartbeats", "schedule": HEARTBEAT_TICK_SECONDS},
        "sweep-background-tickets": {"task": "eamp.sweep_background_tickets", "schedule": TICKET_SWEEP_SECONDS},
    },
)


def _worker_id() -> str:
    return f"celery-{socket.gethostname()}-{os.getpid()}"


def _run(work: Callable[[], Awaitable[T]]) -> T:
    """Run one coroutine on a fresh loop and drop loop-bound pools before the loop closes."""

    async def wrapped() -> T:
        from app.db.session import get_engine, reset_engine
        from app.tool_bus.http_pool import get_http_client, set_http_client
        from app.tool_bus.ws_rpc_manager import ws_rpc_manager

        try:
            return await work()
        finally:
            await ws_rpc_manager.aclose()
            await get_http_client().aclose()
            set_http_client(None)
            await get_engine().dispose()
            reset_engine()

    return asyncio.run(wrapped())


def fire_due_heartbeats_task() -> int:
    from app.workers.heartbeat_cron import fire_due_heartbeats

    return _run(lambda: fire_due_heartbeats(datetime.now(UTC)))


def sweep_background_tickets_task() -> int:
    from app.llm.gemma_client import GemmaSGLangClient
    from app.workers.ticket_worker import run_next_background_ticket

    async def sweep() -> int:
        llm = GemmaSGLangClient()
        ran = 0
        while ran < _MAX_TICKETS_PER_SWEEP:
            if await run_next_background_ticket(llm, worker_id=_worker_id()) is None:
                break
            ran += 1
        return ran

    return _run(sweep)


celery_app.task(name="eamp.fire_due_heartbeats")(fire_due_heartbeats_task)
celery_app.task(name="eamp.sweep_background_tickets")(sweep_background_tickets_task)
