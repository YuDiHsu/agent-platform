"""In-app notices for background work. Implements: REQ-011, TC-M4-01."""

from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import UserNotification
from app.db.session import database_session


async def notify(*, user_id: UUID, kind: str, title: str, body: str, session_id: UUID | None = None) -> None:
    async with database_session() as db:
        db.add(UserNotification(user_id=user_id, session_id=session_id, kind=kind, title=title, body=body))


async def unread_notifications(db: AsyncSession, user_id: UUID) -> list[dict[str, Any]]:
    rows = (
        await db.scalars(
            select(UserNotification)
            .where(UserNotification.user_id == user_id, UserNotification.is_read.is_(False))
            .order_by(UserNotification.created_at.desc(), UserNotification.id)
        )
    ).all()
    return [
        {
            "id": str(row.id),
            "kind": row.kind,
            "title": row.title,
            "body": row.body,
            "session_id": None if row.session_id is None else str(row.session_id),
            "created_at": "" if row.created_at is None else row.created_at.isoformat(),
        }
        for row in rows
    ]
