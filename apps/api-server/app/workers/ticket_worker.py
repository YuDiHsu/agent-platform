"""Atomic background ticket checkout and execution. Implements: REQ-002, REQ-011, TC-M4-01."""

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal
from uuid import UUID

from sqlalchemy import and_, or_, select

from app.db.models import BACKGROUND_LANE, ChatSession, TaskTicket
from app.db.session import database_session
from app.llm.gemma_client import GemmaSGLangClient

logger = logging.getLogger(__name__)

STALE_LOCK_AFTER = timedelta(minutes=30)

RunOutcome = Literal["completed", "waiting_browser", "waiting_hitl", "failed"]

_NOTICES: dict[RunOutcome, tuple[str, str]] = {
    "completed": ("HEARTBEAT_COMPLETED", "背景工作已完成"),
    "waiting_browser": ("LOCAL_MOUNT_OFFLINE", "背景工作需要本機資料夾：請開啟平台頁面或啟動本機 Daemon"),
    "waiting_hitl": ("HITL_REQUIRED", "背景工作等待你的審批"),
    "failed": ("HEARTBEAT_FAILED", "背景工作執行失敗"),
}


@dataclass(frozen=True)
class BackgroundRun:
    ticket_id: UUID
    session_id: UUID
    outcome: RunOutcome


@dataclass(frozen=True)
class ClaimedTicket:
    ticket_id: UUID
    session_id: UUID
    user_id: UUID
    role_code: str
    instructions: str
    worker_id: str


async def claim_background_ticket(worker_id: str) -> ClaimedTicket | None:
    """Take the oldest PENDING background ticket, or one whose worker died holding it, that no one else has locked."""

    now = datetime.now(UTC)
    async with database_session() as db:
        ticket = await db.scalar(
            select(TaskTicket)
            .where(
                TaskTicket.execution_lane == BACKGROUND_LANE,
                or_(
                    TaskTicket.status == "PENDING",
                    and_(TaskTicket.status == "IN_PROGRESS", TaskTicket.locked_at < now - STALE_LOCK_AFTER),
                ),
            )
            .order_by(TaskTicket.created_at, TaskTicket.id)
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        if ticket is None:
            return None
        if ticket.status == "IN_PROGRESS":
            logger.warning("reclaiming ticket %s from stale worker %s", ticket.id, ticket.locked_by_worker)
        ticket.status = "IN_PROGRESS"
        ticket.locked_by_worker = worker_id
        ticket.locked_at = now
        return ClaimedTicket(
            ticket_id=ticket.id,
            session_id=ticket.session_id,
            user_id=ticket.requester_user_id,
            role_code=ticket.assigned_role_code,
            instructions=ticket.input_instructions,
            worker_id=worker_id,
        )


async def run_next_background_ticket(llm: GemmaSGLangClient, *, worker_id: str) -> BackgroundRun | None:
    """Claim one background ticket, run it to completion or hibernation, and leave the user a notice."""

    from app.orchestrator.supervisor import ChatTurn
    from app.workers.notifications import notify

    claimed = await claim_background_ticket(worker_id)
    if claimed is None:
        return None
    turn = ChatTurn(llm, user_id=claimed.user_id, session_id=claimed.session_id, message=claimed.instructions)
    try:
        await turn.run_claimed_ticket(ticket_id=claimed.ticket_id, instructions=claimed.instructions)
    except Exception:
        logger.exception("background ticket %s failed", claimed.ticket_id)
        await _fail(claimed)
    outcome, session_title = await _outcome(claimed.session_id)
    kind, title = _NOTICES[outcome]
    await notify(user_id=claimed.user_id, session_id=claimed.session_id, kind=kind, title=title, body=session_title)
    return BackgroundRun(ticket_id=claimed.ticket_id, session_id=claimed.session_id, outcome=outcome)


async def _fail(claimed: ClaimedTicket) -> None:
    async with database_session() as db:
        ticket = await db.get(TaskTicket, claimed.ticket_id)
        if ticket is not None and ticket.status == "IN_PROGRESS":
            ticket.status = "FAILED"
            ticket.error_log = "背景 Worker 執行例外"
            ticket.locked_by_worker = None
            ticket.locked_at = None
        chat = await db.get(ChatSession, claimed.session_id)
        if chat is not None:
            chat.status = "FAILED"


async def _outcome(session_id: UUID) -> tuple[RunOutcome, str]:
    """How the run ended, and the session title to show in the notice."""

    async with database_session() as db:
        chat = await db.get(ChatSession, session_id)
    if chat is None:
        return "failed", ""
    if chat.status == "COMPLETED":
        return "completed", chat.title
    if chat.status == "HIBERNATING" and chat.hold_reason == "WAITING_BROWSER":
        return "waiting_browser", chat.title
    if chat.status == "HIBERNATING" and chat.hold_reason == "WAITING_HITL":
        return "waiting_hitl", chat.title
    return "failed", chat.title
