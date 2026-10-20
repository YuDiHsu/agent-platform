"""Turn due daily routines into background tickets. Implements: REQ-011, TC-M4-01."""

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import or_, select, update

from app.db.models import ChatMessage, ChatSession, HeartbeatRoutine, TaskTicket
from app.db.session import database_session
from app.orchestrator.dag import MAX_HOPS
from app.workers.ticket_worker import BACKGROUND_LANE


async def fire_due_heartbeats(now: datetime) -> int:
    """Create one background ticket per routine whose daily time has passed today; return how many fired."""

    async with database_session() as db:
        routines = (await db.scalars(select(HeartbeatRoutine).where(HeartbeatRoutine.is_enabled.is_(True)))).all()
        due = [(routine.id, _local_day(routine, now)) for routine in routines if _is_due(routine, now)]
    fired = 0
    for routine_id, day in due:
        if await _fire(routine_id, day):
            fired += 1
    return fired


def _local_day(routine: HeartbeatRoutine, now: datetime) -> str:
    return now.astimezone(ZoneInfo(routine.timezone)).date().isoformat()


def _is_due(routine: HeartbeatRoutine, now: datetime) -> bool:
    local = now.astimezone(ZoneInfo(routine.timezone))
    last = routine.last_fired_on
    return local.strftime("%H:%M") >= routine.daily_time and (last is None or last < local.date().isoformat())


async def _fire(routine_id: object, day: str) -> bool:
    async with database_session() as db:
        claimed = await db.scalar(
            update(HeartbeatRoutine)
            .where(
                HeartbeatRoutine.id == routine_id,
                HeartbeatRoutine.is_enabled.is_(True),
                or_(HeartbeatRoutine.last_fired_on.is_(None), HeartbeatRoutine.last_fired_on < day),
            )
            .values(last_fired_on=day)
            .returning(HeartbeatRoutine.id)
        )
        if claimed is None:
            return False
        routine = await db.get(HeartbeatRoutine, routine_id)
        assert routine is not None
        chat = ChatSession(
            user_id=routine.user_id,
            title=f"{routine.title} {day}",
            status="ACTIVE",
            goal_statement=routine.instructions,
        )
        db.add(chat)
        await db.flush()
        ancestry = [routine.instructions]
        ticket = TaskTicket(
            session_id=chat.id,
            requester_user_id=routine.user_id,
            assigned_role_code=routine.role_code,
            title=routine.title,
            status="PENDING",
            execution_lane=BACKGROUND_LANE,
            hop_count=0,
            max_hops=MAX_HOPS,
            goal_ancestry=ancestry,
            input_instructions=routine.instructions,
        )
        db.add(ticket)
        await db.flush()
        chat.dag_snapshot = [
            {
                "step_id": 1,
                "ticket_id": str(ticket.id),
                "target_role_code": routine.role_code,
                "task_title": routine.title,
                "detailed_instructions": routine.instructions,
                "depends_on_steps": [],
                "goal_ancestry": ancestry,
                "status": "PENDING",
            }
        ]
        chat.updated_at = datetime.now(UTC)
        db.add(
            ChatMessage(
                session_id=chat.id,
                role_code="USER",
                event_type="user_message",
                content=routine.instructions,
                payload={"heartbeat_routine_id": str(routine.id)},
            )
        )
        return True
