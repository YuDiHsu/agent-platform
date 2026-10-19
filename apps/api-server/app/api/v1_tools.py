"""Tool catalog and personal enablement. Implements: REQ-009, REQ-017, ADR-0002."""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, require_user
from app.db.models import ToolRegistry, UserToolPreference
from app.db.session import database_session

router = APIRouter()
HIDDEN_LOCKED = "底層資產不可關閉"


class PreferenceWrite(BaseModel):
    code: str
    is_enabled: bool


def _visible(tool: ToolRegistry, user: CurrentUser) -> bool:
    return user.is_admin or bool(tool.is_visible_to_user)


@router.get("/tools")
async def list_tools(user: CurrentUser = Depends(require_user)) -> list[dict[str, Any]]:
    async with database_session() as db:
        tools = (await db.scalars(select(ToolRegistry).order_by(ToolRegistry.namespace, ToolRegistry.code))).all()
        prefs = {
            row.tool_id: row.is_enabled
            for row in (
                await db.scalars(select(UserToolPreference).where(UserToolPreference.user_id == user.id))
            ).all()
        }
        return [
            {
                "code": tool.code,
                "namespace": tool.namespace,
                "name": tool.name,
                "description": tool.description,
                "action_tier": tool.action_tier,
                "scope_type": tool.scope_type,
                "is_visible_to_user": tool.is_visible_to_user,
                "is_enabled": prefs.get(tool.id, False),
            }
            for tool in tools
            if _visible(tool, user)
        ]


@router.put("/users/me/tool-preferences", status_code=204)
async def set_tool_preference(body: PreferenceWrite, user: CurrentUser = Depends(require_user)) -> None:
    async with database_session() as db:
        tool = await _tool(db, body.code, user)
        if not tool.is_visible_to_user and not user.is_admin:
            raise HTTPException(status_code=403, detail=HIDDEN_LOCKED)
        await db.execute(
            insert(UserToolPreference)
            .values(user_id=user.id, tool_id=tool.id, is_enabled=body.is_enabled)
            .on_conflict_do_update(
                index_elements=["user_id", "tool_id"],
                set_={"is_enabled": body.is_enabled},
            )
        )


async def _tool(db: AsyncSession, code: str, user: CurrentUser) -> ToolRegistry:
    tool = await db.scalar(select(ToolRegistry).where(ToolRegistry.code == code))
    if tool is None or not _visible(tool, user):
        raise HTTPException(status_code=404, detail="找不到工具")
    return tool
