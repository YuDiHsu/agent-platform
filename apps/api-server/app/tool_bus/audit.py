"""Persist security denials. Implements: REQ-012, ADR-0004."""

from uuid import UUID

from app.db.models import SecurityAuditLog
from app.db.session import database_session


async def record_security_audit(
    *,
    actor_user_id: str,
    event_code: str,
    resource: str,
    detail: str,
    target_user_id: str | None = None,
) -> None:
    """Write one audit row and commit it before the caller waits on anything else."""

    async with database_session() as db:
        db.add(
            SecurityAuditLog(
                actor_user_id=_uuid_or_none(actor_user_id),
                target_user_id=_uuid_or_none(target_user_id) if target_user_id else None,
                event_code=event_code,
                resource=resource,
                detail=detail,
            )
        )


def _uuid_or_none(value: str) -> UUID | None:
    try:
        return UUID(value)
    except ValueError:
        return None
