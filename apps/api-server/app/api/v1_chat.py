"""Chat workspace HTTP and SSE contract. Implements: REQ-002, REQ-010, ADR-0002, ADR-0003."""

import json
from collections import defaultdict
from collections.abc import AsyncIterator
from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, get_llm, require_user
from app.db.models import (
    AgentRole,
    AgentRoleRule,
    AgentRoleSkill,
    ChatMessage,
    ChatSession,
    HitlApprovalRequest,
    LocalWorkspaceMount,
    SharedArtifact,
    SkillRegistry,
    TaskTicket,
    ToolRegistry,
    User,
    UserNotification,
    UserToolPreference,
)
from app.db.session import database_session
from app.llm.gemma_client import GemmaSGLangClient
from app.orchestrator.runtime import spawn
from app.orchestrator.supervisor import ChatTurn
from app.workers.notifications import unread_notifications
from app.workspace.roster import display_name, workspace_roles

router = APIRouter()


class DevLoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    display_name: str = Field(min_length=1, max_length=100)
    department: str = Field(min_length=1, max_length=100)


class UserOut(BaseModel):
    id: str
    email: str
    display_name: str
    department: str
    max_concurrent_tickets: int
    token_quota_limit: int | None
    tokens_consumed_total: int


class SessionCreated(BaseModel):
    id: str
    title: str
    status: str


class StreamRequest(BaseModel):
    message: str = Field(min_length=1, max_length=8000)


def _iso(value: datetime | None) -> str:
    return value.isoformat() if value is not None else ""


def _user_out(user: CurrentUser) -> UserOut:
    return UserOut(
        id=str(user.id),
        email=user.email,
        display_name=user.display_name,
        department=user.department,
        max_concurrent_tickets=user.max_concurrent_tickets,
        token_quota_limit=user.token_quota_limit,
        tokens_consumed_total=user.tokens_consumed_total,
    )


@router.post("/users/dev-login", response_model=UserOut)
async def dev_login(body: DevLoginRequest) -> UserOut:
    """Local sign-in until the enterprise IdP is connected."""

    async with database_session() as db:
        user = await db.scalar(select(User).where(User.email == body.email))
        if user is None:
            user = User(email=body.email, display_name=body.display_name, department=body.department)
            db.add(user)
            await db.flush()
            await db.refresh(user)
        return UserOut(
            id=str(user.id),
            email=user.email,
            display_name=user.display_name,
            department=user.department,
            max_concurrent_tickets=user.max_concurrent_tickets,
            token_quota_limit=user.token_quota_limit,
            tokens_consumed_total=user.tokens_consumed_total,
        )


@router.post("/chat/sessions", response_model=SessionCreated, status_code=201)
async def create_session(user: CurrentUser = Depends(require_user)) -> SessionCreated:
    async with database_session() as db:
        chat = ChatSession(user_id=user.id, title="新的協作", status="ACTIVE")
        db.add(chat)
        await db.flush()
        await db.refresh(chat)
        return SessionCreated(id=str(chat.id), title=chat.title, status=chat.status)


@router.post("/chat/sessions/{session_id}/stream")
async def stream_message(
    session_id: UUID,
    body: StreamRequest,
    user: CurrentUser = Depends(require_user),
    llm: GemmaSGLangClient = Depends(get_llm),
) -> StreamingResponse:
    await _require_owned(session_id, user.id)
    turn = ChatTurn(llm, user_id=user.id, session_id=session_id, message=body.message)
    queue = turn.events()
    spawn(turn.run())

    async def events() -> AsyncIterator[str]:
        while True:
            item = await queue.get()
            if item is None:
                break
            payload = json.dumps(item.data, ensure_ascii=False)
            yield f"event: {item.event}\ndata: {payload}\n\n"

    return StreamingResponse(events(), media_type="text/event-stream")


@router.get("/users/me/bootstrap")
async def bootstrap(user: CurrentUser = Depends(require_user)) -> dict[str, Any]:
    async with database_session() as db:
        sessions = (
            await db.scalars(
                select(ChatSession)
                .where(ChatSession.user_id == user.id)
                .order_by(ChatSession.updated_at.desc())
            )
        ).all()
        pending = (
            await db.scalars(
                select(HitlApprovalRequest).where(
                    HitlApprovalRequest.user_id == user.id,
                    HitlApprovalRequest.status == "PENDING",
                )
            )
        ).all()
        mounts = (
            await db.scalars(select(LocalWorkspaceMount).where(LocalWorkspaceMount.user_id == user.id))
        ).all()
        roster = await workspace_roles(db, user.id)
        role_by_id = {role.id: role for role, _config in roster}
        preferences = (
            await db.execute(
                select(ToolRegistry.code, UserToolPreference.is_enabled)
                .join(UserToolPreference, UserToolPreference.tool_id == ToolRegistry.id)
                .where(UserToolPreference.user_id == user.id)
            )
        ).all()
        return {
            "user": _user_out(user).model_dump(),
            "sessions": [
                {
                    "id": str(chat.id),
                    "title": chat.title,
                    "status": chat.status,
                    "active_role_code": chat.active_role_code,
                    "hold_reason": chat.hold_reason,
                    "updated_at": _iso(chat.updated_at),
                }
                for chat in sessions
            ],
            "pending_hitl": [_hitl_out(row) for row in pending],
            "mounts": [
                {
                    "mount_id": str(mount.id),
                    "alias": mount.mount_alias,
                    "handle_key": mount.browser_handle_key,
                }
                for mount in mounts
            ],
            "local_workspace_mounts": [
                {
                    "id": str(mount.id),
                    "mount_alias": mount.mount_alias,
                    "browser_handle_key": mount.browser_handle_key,
                    "provider_type": mount.provider_type,
                    "permission_mode": mount.permission_mode,
                }
                for mount in mounts
            ],
            "agents": [
                {
                    "code": role.code,
                    "name": display_name(role, config),
                    "reports_to_code": None
                    if role.reports_to_id is None or role.reports_to_id not in role_by_id
                    else role_by_id[role.reports_to_id].code,
                    "is_enabled": True if config is None else config.is_enabled,
                }
                for role, config in roster
            ],
            "tool_preferences": [
                {"code": code, "is_enabled": enabled} for code, enabled in preferences
            ],
            "notifications": await unread_notifications(db, user.id),
        }


@router.post("/users/me/notifications/{notification_id}/read", status_code=204)
async def read_notification(notification_id: UUID, user: CurrentUser = Depends(require_user)) -> None:
    async with database_session() as db:
        row = await db.get(UserNotification, notification_id)
        if row is None or row.user_id != user.id:
            raise HTTPException(status_code=404, detail="找不到通知")
        row.is_read = True


@router.get("/chat/sessions/{session_id}/state")
async def session_state(session_id: UUID, user: CurrentUser = Depends(require_user)) -> dict[str, Any]:
    async with database_session() as db:
        chat = await _owned_in_session(db, session_id, user.id)
        messages = (
            await db.scalars(
                select(ChatMessage)
                .where(ChatMessage.session_id == session_id)
                .order_by(ChatMessage.created_at, ChatMessage.id)
            )
        ).all()
        tickets = (
            await db.scalars(select(TaskTicket).where(TaskTicket.session_id == session_id))
        ).all()
        artifacts = (
            await db.scalars(
                select(SharedArtifact)
                .where(SharedArtifact.session_id == session_id)
                .order_by(SharedArtifact.created_at)
            )
        ).all()
        pending = (
            await db.scalars(
                select(HitlApprovalRequest).where(
                    HitlApprovalRequest.session_id == session_id,
                    HitlApprovalRequest.status == "PENDING",
                )
            )
        ).all()
        ticket_status = {str(ticket.id): ticket.status for ticket in tickets}
        dag_steps = [
            {
                "step_id": node["step_id"],
                "target_role_code": node["target_role_code"],
                "task_title": node["task_title"],
                "status": ticket_status.get(str(node["ticket_id"]), node["status"]),
                "depends_on_steps": node["depends_on_steps"],
            }
            for node in chat.dag_snapshot
        ]
        return {
            "session_id": str(chat.id),
            "title": chat.title,
            "status": chat.status,
            "active_role_code": chat.active_role_code,
            "goal_statement": chat.goal_statement,
            "hold_reason": chat.hold_reason,
            "hibernated": chat.checkpoint is not None,
            "checkpoint": chat.checkpoint,
            "messages": [
                {
                    "id": str(message.id),
                    "role_code": message.role_code,
                    "event_type": message.event_type,
                    "content": message.content,
                    "payload": message.payload,
                    "created_at": _iso(message.created_at),
                }
                for message in messages
            ],
            "dag_steps": dag_steps,
            "artifacts": [
                {
                    "artifact_id": str(artifact.id),
                    "producer_role": artifact.producer_role_code,
                    "title": artifact.title,
                    "artifact_type": artifact.artifact_type,
                    "summary_200_words": artifact.summary_200_words,
                    "content_body": artifact.content_body,
                    "created_at": _iso(artifact.created_at),
                }
                for artifact in artifacts
            ],
            "tickets": [
                {
                    "id": str(ticket.id),
                    "title": ticket.title,
                    "assigned_role_code": ticket.assigned_role_code,
                    "status": ticket.status,
                    "hop_count": ticket.hop_count,
                    "max_hops": ticket.max_hops,
                    "goal_ancestry": ticket.goal_ancestry,
                    "input_instructions": ticket.input_instructions,
                    "locked_by_worker": ticket.locked_by_worker,
                    "tokens_consumed": ticket.tokens_consumed,
                    "token_budget": ticket.token_budget,
                }
                for ticket in tickets
            ],
            "pending_hitl": [_hitl_out(row) for row in pending],
        }


@router.get("/org/roles")
async def org_roles(user: CurrentUser = Depends(require_user)) -> list[dict[str, Any]]:
    async with database_session() as db:
        roles = (await db.scalars(select(AgentRole).where(AgentRole.is_active.is_not(False)))).all()
        role_by_id = {role.id: role for role in roles}
        rule_rows = (
            await db.execute(select(AgentRoleRule.role_id, func.count()).group_by(AgentRoleRule.role_id))
        ).all()
        rule_counts = {role_id: int(count) for role_id, count in rule_rows}
        skill_rows = (
            await db.execute(
                select(AgentRoleSkill.role_id, SkillRegistry.code, SkillRegistry.name).join(
                    SkillRegistry, SkillRegistry.id == AgentRoleSkill.skill_id
                )
            )
        ).all()
        skills: dict[UUID, list[dict[str, str]]] = defaultdict(list)
        for role_id, code, name in skill_rows:
            skills[role_id].append({"code": str(code), "name": str(name)})
        tickets = (
            await db.scalars(
                select(TaskTicket)
                .where(TaskTicket.requester_user_id == user.id)
                .order_by(TaskTicket.created_at.desc())
            )
        ).all()
        by_role: dict[str, list[TaskTicket]] = defaultdict(list)
        for ticket in tickets:
            by_role[ticket.assigned_role_code].append(ticket)
        payload: list[dict[str, Any]] = []
        for role in roles:
            history = by_role.get(role.code, [])
            payload.append(
                {
                    "id": str(role.id),
                    "code": role.code,
                    "name": role.name,
                    "department": role.department,
                    "visibility_scope": role.visibility_scope,
                    "reports_to_code": None
                    if role.reports_to_id is None or role.reports_to_id not in role_by_id
                    else role_by_id[role.reports_to_id].code,
                    "rule_count": rule_counts.get(role.id, 0),
                    "skill_count": len(skills.get(role.id, [])),
                    "skills": skills.get(role.id, []),
                    "active_ticket_status": None if not history else history[0].status,
                    "tickets": [
                        {
                            "id": str(ticket.id),
                            "title": ticket.title,
                            "status": ticket.status,
                            "tokens_consumed": ticket.tokens_consumed,
                            "token_budget": ticket.token_budget,
                            "created_at": _iso(ticket.created_at),
                            "session_id": str(ticket.session_id),
                        }
                        for ticket in history[:20]
                    ],
                }
            )
        return payload


def _hitl_out(row: HitlApprovalRequest) -> dict[str, Any]:
    return {
        "hitl_request_id": str(row.id),
        "ticket_id": str(row.ticket_id),
        "executing_role_code": row.executing_role_code,
        "tool_name": row.tool_name,
        "execution_target": row.execution_target,
        "preview_title": row.preview_title,
        "proposed_payload": row.proposed_payload,
        "status": row.status,
    }


async def _require_owned(session_id: UUID, user_id: UUID) -> None:
    async with database_session() as db:
        await _owned_in_session(db, session_id, user_id)


async def _owned_in_session(db: AsyncSession, session_id: UUID, user_id: UUID) -> ChatSession:
    chat = await db.get(ChatSession, session_id)
    if chat is None or chat.user_id != user_id:
        raise HTTPException(status_code=404, detail="找不到對話工作階段")
    return chat
