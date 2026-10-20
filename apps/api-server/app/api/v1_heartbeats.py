"""Per-user daily background routines. Implements: REQ-011, TC-M4-01."""

from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select

from app.api.deps import CurrentUser, require_user
from app.db.models import HeartbeatRoutine
from app.db.session import database_session
from app.workspace.roster import workspace_roles

router = APIRouter()

_TIME_PATTERN = r"^([01]\d|2[0-3]):[0-5]\d$"


def _known_timezone(value: str) -> str:
    try:
        ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ValueError("未知的時區") from exc
    return value


class HeartbeatCreate(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    role_code: str = Field(min_length=1, max_length=64)
    instructions: str = Field(min_length=1, max_length=4000)
    daily_time: str = Field(pattern=_TIME_PATTERN)
    timezone: str = "Asia/Taipei"

    _timezone = field_validator("timezone")(_known_timezone)


class HeartbeatPatch(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=120)
    instructions: str | None = Field(default=None, min_length=1, max_length=4000)
    daily_time: str | None = Field(default=None, pattern=_TIME_PATTERN)
    is_enabled: bool | None = None


def _out(row: HeartbeatRoutine) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "title": row.title,
        "role_code": row.role_code,
        "instructions": row.instructions,
        "daily_time": row.daily_time,
        "timezone": row.timezone,
        "is_enabled": row.is_enabled,
        "last_fired_on": row.last_fired_on,
    }


@router.get("/heartbeats")
async def list_heartbeats(user: CurrentUser = Depends(require_user)) -> list[dict[str, Any]]:
    async with database_session() as db:
        rows = (
            await db.scalars(
                select(HeartbeatRoutine)
                .where(HeartbeatRoutine.user_id == user.id)
                .order_by(HeartbeatRoutine.daily_time, HeartbeatRoutine.created_at)
            )
        ).all()
        return [_out(row) for row in rows]


@router.post("/heartbeats", status_code=201)
async def create_heartbeat(body: HeartbeatCreate, user: CurrentUser = Depends(require_user)) -> dict[str, Any]:
    async with database_session() as db:
        roster = await workspace_roles(db, user.id)
        enabled = {role.code for role, config in roster if config is None or config.is_enabled}
        if body.role_code not in enabled:
            raise HTTPException(status_code=404, detail="工作區中找不到這個角色")
        row = HeartbeatRoutine(user_id=user.id, **body.model_dump())
        db.add(row)
        await db.flush()
        await db.refresh(row)
        return _out(row)


@router.patch("/heartbeats/{routine_id}")
async def update_heartbeat(
    routine_id: UUID, body: HeartbeatPatch, user: CurrentUser = Depends(require_user)
) -> dict[str, Any]:
    async with database_session() as db:
        row = await _owned(db, routine_id, user.id)
        for field, value in body.model_dump(exclude_none=True).items():
            setattr(row, field, value)
        await db.flush()
        return _out(row)


@router.delete("/heartbeats/{routine_id}", status_code=204)
async def delete_heartbeat(routine_id: UUID, user: CurrentUser = Depends(require_user)) -> None:
    async with database_session() as db:
        await db.delete(await _owned(db, routine_id, user.id))


async def _owned(db: Any, routine_id: UUID, user_id: UUID) -> HeartbeatRoutine:
    row = await db.get(HeartbeatRoutine, routine_id)
    if row is None or row.user_id != user_id:
        raise HTTPException(status_code=404, detail="找不到排程")
    assert isinstance(row, HeartbeatRoutine)
    return row
