"""Personal agent workspace, preset reset, and memory cleanup. Implements: ADR-0003, REQ-003, REQ-012."""

from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from app.api.deps import CurrentUser, get_llm, require_user
from app.db.models import (
    AgentMemory,
    AgentRole,
    ChatSession,
    CliExecutionLog,
    HitlApprovalRequest,
    LocalWorkspaceMount,
    SharedArtifact,
    TaskTicket,
    UserAgentConfig,
)
from app.db.session import database_session
from app.llm.embedding_client import EmbeddingClient
from app.llm.gemma_client import GemmaSGLangClient
from app.workspace.roster import PRESET_CODES, display_name, display_prompt, workspace_roles

router = APIRouter()

PRIVATE_MOUNT_ERROR = "ERR_LOCAL_MOUNT_MUST_BE_PRIVATE: 綁定本機資料夾的 Agent 只能是個人私有"
PERSONAL_SCOPES = ("USER_PRIVATE", "EPHEMERAL_LOCAL_FILE")
SHARED_SCOPES = ("DEPARTMENT_SHARED", "ORG_GLOBAL")


class GenerateSpecRequest(BaseModel):
    description: str = Field(min_length=1, max_length=500)


class GeneratedAgentSpec(BaseModel):
    name: str
    code: str
    system_prompt: str
    routing_description: str
    recommended_rule_codes: list[str] = Field(default_factory=list)
    recommended_skill_codes: list[str] = Field(default_factory=list)
    recommended_tool_codes: list[str] = Field(default_factory=list)


class AgentWrite(BaseModel):
    code: str = Field(min_length=2, max_length=64)
    name: str = Field(min_length=1, max_length=120)
    department: str = Field(min_length=1, max_length=100)
    system_prompt: str = Field(min_length=1)
    routing_description: str = Field(min_length=1)
    visibility_scope: Literal["PRIVATE", "DEPARTMENT", "GLOBAL"] = "PRIVATE"
    reports_to_code: str | None = None
    bound_local_mount_id: UUID | None = None
    allowed_tool_namespaces: list[str] = Field(default_factory=list)


class AgentPatch(BaseModel):
    is_enabled: bool | None = None
    name: str | None = Field(default=None, max_length=120)
    system_prompt: str | None = None


class PresetReset(BaseModel):
    code: str | None = None


def _agent_out(role: AgentRole, config: UserAgentConfig | None) -> dict[str, Any]:
    enabled = True if config is None else config.is_enabled
    return {
        "code": role.code,
        "name": display_name(role, config),
        "is_preset": role.code in PRESET_CODES and role.creator_user_id is None,
        "is_enabled": enabled,
        "visibility_scope": role.visibility_scope,
        "approval_status": role.approval_status,
        "department": role.department,
        "bound_local_mount_id": None if role.bound_local_mount_id is None else str(role.bound_local_mount_id),
        "system_prompt": display_prompt(role, config),
        "routing_description": role.routing_description,
    }


async def _role_for_user(db: AsyncSession, user_id: UUID, code: str) -> tuple[AgentRole, UserAgentConfig | None]:
    match = [item for item in await workspace_roles(db, user_id) if item[0].code == code]
    if not match:
        raise HTTPException(status_code=404, detail="工作區裡沒有這個 Agent")
    return match[0]


async def _config(db: AsyncSession, user_id: UUID, role_id: UUID) -> UserAgentConfig:
    row = await db.scalar(
        select(UserAgentConfig).where(
            UserAgentConfig.user_id == user_id,
            UserAgentConfig.role_id == role_id,
        )
    )
    if row is not None:
        return row
    created = UserAgentConfig(user_id=user_id, role_id=role_id, is_enabled=True, is_removed=False)
    db.add(created)
    await db.flush()
    return created


@router.get("/agents")
async def list_agents(user: CurrentUser = Depends(require_user)) -> list[dict[str, Any]]:
    async with database_session() as db:
        rows = await workspace_roles(db, user.id)
        return [_agent_out(role, config) for role, config in rows]


@router.post("/agents/generate-spec")
async def generate_spec(
    body: GenerateSpecRequest,
    user: CurrentUser = Depends(require_user),
    llm: GemmaSGLangClient = Depends(get_llm),
) -> GeneratedAgentSpec:
    del user
    return await llm.generate_structured(
        system_prompt=(
            "你是 Agent 規格產生器。依使用者的一句話，產出繁體中文角色名稱、系統提示詞與路由描述，"
            "並推薦既有的 rule、skill、tool 代碼。code 使用大寫英數與底線。"
        ),
        messages=[{"role": "user", "content": body.description}],
        response_model=GeneratedAgentSpec,
    )


@router.post("/agents", status_code=201)
async def create_agent(body: AgentWrite, user: CurrentUser = Depends(require_user)) -> dict[str, Any]:
    if body.bound_local_mount_id is not None and body.visibility_scope != "PRIVATE":
        raise HTTPException(status_code=400, detail=PRIVATE_MOUNT_ERROR)
    approval = "APPROVED"
    if body.visibility_scope in {"DEPARTMENT", "GLOBAL"} and not user.is_admin:
        approval = "PENDING_REVIEW"
    embedding = await EmbeddingClient().embed_text(body.routing_description)
    async with database_session() as db:
        if await db.scalar(select(AgentRole).where(AgentRole.code == body.code)):
            raise HTTPException(status_code=409, detail="Agent 代碼已存在")
        if body.bound_local_mount_id is not None:
            mount = await db.get(LocalWorkspaceMount, body.bound_local_mount_id)
            if mount is None or mount.user_id != user.id:
                raise HTTPException(status_code=404, detail="找不到你的本機掛載")
        reports_to_id = None
        if body.reports_to_code:
            parent = await db.scalar(select(AgentRole).where(AgentRole.code == body.reports_to_code))
            if parent is None:
                raise HTTPException(status_code=404, detail="找不到上層 Agent")
            reports_to_id = parent.id
        template = await db.scalar(select(AgentRole).where(AgentRole.code == "PM"))
        schema = {} if template is None else dict(template.output_json_schema)
        role = AgentRole(
            code=body.code,
            name=body.name,
            department=body.department,
            reports_to_id=reports_to_id,
            creator_user_id=user.id,
            visibility_scope=body.visibility_scope,
            approval_status=approval,
            system_prompt=body.system_prompt,
            routing_description=body.routing_description,
            routing_embedding=embedding,
            output_json_schema=schema,
            allowed_tool_namespaces=list(body.allowed_tool_namespaces),
            bound_local_mount_id=body.bound_local_mount_id,
            is_active=True,
        )
        db.add(role)
        try:
            await db.flush()
        except IntegrityError as exc:
            raise HTTPException(status_code=400, detail=PRIVATE_MOUNT_ERROR) from exc
        db.add(UserAgentConfig(user_id=user.id, role_id=role.id, is_enabled=True, is_removed=False))
        await db.flush()
        return _agent_out(role, None)


@router.patch("/agents/{code}")
async def update_agent(code: str, body: AgentPatch, user: CurrentUser = Depends(require_user)) -> dict[str, Any]:
    async with database_session() as db:
        role, config = await _role_for_user(db, user.id, code)
        stored = config or await _config(db, user.id, role.id)
        if body.is_enabled is not None:
            stored.is_enabled = body.is_enabled
        preset = role.code in PRESET_CODES and role.creator_user_id is None
        if body.name is not None:
            if preset:
                stored.name_override = body.name
            else:
                role.name = body.name
        if body.system_prompt is not None:
            if preset:
                stored.system_prompt_override = body.system_prompt
            else:
                role.system_prompt = body.system_prompt
        await db.flush()
        return _agent_out(role, stored)


@router.delete("/agents/{code}", status_code=204)
async def delete_agent(code: str, user: CurrentUser = Depends(require_user)) -> None:
    async with database_session() as db:
        role, config = await _role_for_user(db, user.id, code)
        preset = role.code in PRESET_CODES and role.creator_user_id is None
        if preset:
            stored = config or await _config(db, user.id, role.id)
            stored.is_removed = True
            stored.is_enabled = False
            return
        if role.creator_user_id != user.id:
            raise HTTPException(status_code=404, detail="工作區裡沒有這個 Agent")
        role.is_active = False


@router.post("/agents/presets/reset")
async def reset_presets(body: PresetReset, user: CurrentUser = Depends(require_user)) -> dict[str, Any]:
    codes = PRESET_CODES if body.code is None else (body.code,)
    unknown = [code for code in codes if code not in PRESET_CODES]
    if unknown:
        raise HTTPException(status_code=404, detail="沒有這個預設 Agent")
    async with database_session() as db:
        roles = (await db.scalars(select(AgentRole).where(AgentRole.code.in_(codes)))).all()
        restored: list[str] = []
        for role in roles:
            if role.creator_user_id is not None:
                continue
            stored = await _config(db, user.id, role.id)
            stored.is_enabled = True
            stored.is_removed = False
            stored.name_override = None
            stored.system_prompt_override = None
            restored.append(role.code)
        return {"restored": restored}


@router.delete("/memories")
async def clear_memories(
    user: CurrentUser = Depends(require_user),
    role_code: str | None = Query(default=None),
    memory_scope: str | None = Query(default=None),
) -> dict[str, int]:
    if memory_scope in SHARED_SCOPES:
        raise HTTPException(status_code=403, detail="一般使用者不能刪除部門或全公司記憶")
    async with database_session() as db:
        filters = [
            AgentMemory.owner_user_id == user.id,
            AgentMemory.memory_scope.in_(PERSONAL_SCOPES),
        ]
        if role_code is not None:
            filters.append(AgentMemory.role_code == role_code)
        before = await db.scalar(select(func.count()).select_from(AgentMemory).where(*filters))
        await db.execute(delete(AgentMemory).where(*filters))
        return {"deleted": int(before or 0)}


@router.delete("/chat/sessions/{session_id}", status_code=204)
async def delete_session(session_id: UUID, user: CurrentUser = Depends(require_user)) -> None:
    async with database_session() as db:
        chat = await db.get(ChatSession, session_id)
        if chat is None or chat.user_id != user.id:
            raise HTTPException(status_code=404, detail="找不到對話工作階段")
        await db.execute(delete(CliExecutionLog).where(CliExecutionLog.session_id == session_id))
        await db.execute(delete(HitlApprovalRequest).where(HitlApprovalRequest.session_id == session_id))
        await db.execute(
            delete(TaskTicket).where(
                TaskTicket.session_id == session_id,
                TaskTicket.parent_ticket_id.is_not(None),
            )
        )
        await db.execute(delete(TaskTicket).where(TaskTicket.session_id == session_id))
        await db.execute(delete(SharedArtifact).where(SharedArtifact.session_id == session_id))
        await db.execute(
            delete(AgentMemory).where(
                AgentMemory.owner_user_id == user.id,
                AgentMemory.session_id == session_id,
                AgentMemory.memory_scope.in_(PERSONAL_SCOPES),
            )
        )
        await db.delete(chat)
