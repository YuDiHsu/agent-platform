"""Request dependencies for the chat workspace. Implements: ADR-0003."""

from dataclasses import dataclass
from uuid import UUID

from fastapi import Header, HTTPException

from app.db.models import User
from app.db.session import database_session
from app.llm.gemma_client import GemmaSGLangClient


@dataclass(frozen=True)
class CurrentUser:
    id: UUID
    email: str
    display_name: str
    department: str
    max_concurrent_tickets: int
    token_quota_limit: int | None
    tokens_consumed_total: int
    is_admin: bool


def get_llm() -> GemmaSGLangClient:
    return GemmaSGLangClient()


async def require_user(x_user_id: UUID = Header(...)) -> CurrentUser:
    async with database_session() as db:
        user = await db.get(User, x_user_id)
        if user is None:
            raise HTTPException(status_code=401, detail="需要登入")
        return CurrentUser(
            id=user.id,
            email=user.email,
            display_name=user.display_name,
            department=user.department,
            max_concurrent_tickets=user.max_concurrent_tickets,
            token_quota_limit=user.token_quota_limit,
            tokens_consumed_total=user.tokens_consumed_total,
            is_admin=bool(user.is_admin),
        )
