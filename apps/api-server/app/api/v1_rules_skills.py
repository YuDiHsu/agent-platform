"""Rule and skill catalog, bindings, and the Studio prompt preview.

Implements: REQ-013, REQ-014, ADR-0004.
"""

from collections.abc import AsyncIterator
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, require_user
from app.db.models import (
    AgentRole,
    AgentRoleRule,
    AgentRoleSkill,
    ChatSession,
    RuleRegistry,
    SkillRegistry,
)
from app.db.session import database_session
from app.llm.embedding_client import EmbeddingClient
from app.llm.gemma_client import GemmaSGLangClient
from app.orchestrator.prompt_compiler import PromptCompiler, ToolSchema
from app.orchestrator.state import SubAgentExecutionOutput

router = APIRouter()
HIDDEN_LOCKED = "底層資產不可關閉"


class RuleWrite(BaseModel):
    code: str = Field(min_length=3, max_length=64)
    name: str = Field(min_length=1, max_length=120)
    scope_type: Literal["GLOBAL_MANDATORY", "DEPARTMENT_SHARED", "ROLE_EXCLUSIVE"]
    department: str | None = None
    priority: int = 100
    rule_content_markdown: str = Field(min_length=1)
    glob_trigger: str | None = None
    is_visible_to_user: bool = True


class RulePatch(BaseModel):
    name: str | None = None
    rule_content_markdown: str | None = None
    priority: int | None = None
    is_active: bool | None = None


class SkillWrite(BaseModel):
    code: str = Field(min_length=3, max_length=64)
    name: str = Field(min_length=1, max_length=120)
    trigger_description: str = Field(min_length=1, max_length=300)
    sop_markdown: str = Field(min_length=1)
    execution_mode: Literal["PROMPT_ONLY", "SERVER_SANDBOX_CLI", "LOCAL_DAEMON_CLI", "MCP_TOOL_COMBO"] = "PROMPT_ONLY"
    cli_config: dict[str, Any] | None = None
    is_visible_to_user: bool = True


class SkillPatch(BaseModel):
    name: str | None = None
    trigger_description: str | None = Field(default=None, max_length=300)
    sop_markdown: str | None = None
    is_active: bool | None = None


class TryRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)


def _approval_for(user: CurrentUser, scope: str) -> str:
    if user.is_admin or scope == "ROLE_EXCLUSIVE":
        return "APPROVED"
    return "PENDING_REVIEW"


def _reject_hidden_create(user: CurrentUser, visible: bool) -> None:
    if not visible and not user.is_admin:
        raise HTTPException(status_code=403, detail=HIDDEN_LOCKED)


@router.get("/rules")
async def list_rules(user: CurrentUser = Depends(require_user)) -> list[dict[str, Any]]:
    async with database_session() as db:
        rows = (await db.scalars(select(RuleRegistry).order_by(RuleRegistry.priority, RuleRegistry.code))).all()
        return [_rule_out(row) for row in rows if user.is_admin or row.is_visible_to_user]


@router.post("/rules", status_code=201)
async def create_rule(body: RuleWrite, user: CurrentUser = Depends(require_user)) -> dict[str, str]:
    _reject_hidden_create(user, body.is_visible_to_user)
    async with database_session() as db:
        if await db.scalar(select(RuleRegistry).where(RuleRegistry.code == body.code)):
            raise HTTPException(status_code=409, detail="規範代碼已存在")
        db.add(
            RuleRegistry(
                code=body.code,
                name=body.name,
                scope_type=body.scope_type,
                department=body.department,
                creator_user_id=user.id,
                priority=body.priority,
                rule_content_markdown=body.rule_content_markdown,
                glob_trigger=body.glob_trigger,
                is_visible_to_user=body.is_visible_to_user,
                approval_status=_approval_for(user, body.scope_type),
                is_active=True,
            )
        )
        return {"code": body.code}


@router.patch("/rules/{code}")
async def update_rule(code: str, body: RulePatch, user: CurrentUser = Depends(require_user)) -> dict[str, str]:
    async with database_session() as db:
        rule = await _visible_rule(db, code, user)
        if body.name is not None:
            rule.name = body.name
        if body.rule_content_markdown is not None:
            rule.rule_content_markdown = body.rule_content_markdown
        if body.priority is not None:
            rule.priority = body.priority
        if body.is_active is not None:
            if not rule.is_visible_to_user and not user.is_admin:
                raise HTTPException(status_code=403, detail=HIDDEN_LOCKED)
            rule.is_active = body.is_active
        return {"code": rule.code}


@router.delete("/roles/{role_code}/rules/{rule_code}", status_code=204)
async def unbind_rule(role_code: str, rule_code: str, user: CurrentUser = Depends(require_user)) -> None:
    async with database_session() as db:
        role = await _role(db, role_code)
        rule = await _visible_rule(db, rule_code, user)
        if not rule.is_visible_to_user and not user.is_admin:
            raise HTTPException(status_code=403, detail=HIDDEN_LOCKED)
        await db.execute(
            delete(AgentRoleRule).where(AgentRoleRule.role_id == role.id, AgentRoleRule.rule_id == rule.id)
        )


@router.put("/roles/{role_code}/rules/{rule_code}", status_code=204)
async def bind_rule(role_code: str, rule_code: str, user: CurrentUser = Depends(require_user)) -> None:
    async with database_session() as db:
        role = await _role(db, role_code)
        rule = await _visible_rule(db, rule_code, user)
        await db.execute(
            insert(AgentRoleRule)
            .values(role_id=role.id, rule_id=rule.id, is_mandatory=True, bound_by_user_id=user.id)
            .on_conflict_do_nothing(index_elements=["role_id", "rule_id"])
        )


@router.get("/skills")
async def list_skills(user: CurrentUser = Depends(require_user)) -> list[dict[str, Any]]:
    async with database_session() as db:
        rows = (await db.scalars(select(SkillRegistry).order_by(SkillRegistry.code))).all()
        return [_skill_out(row) for row in rows if user.is_admin or row.is_visible_to_user]


@router.post("/skills", status_code=201)
async def create_skill(body: SkillWrite, user: CurrentUser = Depends(require_user)) -> dict[str, str]:
    _reject_hidden_create(user, body.is_visible_to_user)
    embedding = await EmbeddingClient().embed_text(body.trigger_description)
    async with database_session() as db:
        if await db.scalar(select(SkillRegistry).where(SkillRegistry.code == body.code)):
            raise HTTPException(status_code=409, detail="技能代碼已存在")
        db.add(
            SkillRegistry(
                code=body.code,
                name=body.name,
                visibility_scope="PRIVATE",
                creator_user_id=user.id,
                trigger_description=body.trigger_description,
                trigger_embedding=embedding,
                sop_markdown=body.sop_markdown,
                execution_mode=body.execution_mode,
                cli_config=body.cli_config,
                is_visible_to_user=body.is_visible_to_user,
                approval_status="APPROVED",
                is_active=True,
            )
        )
        return {"code": body.code}


@router.patch("/skills/{code}")
async def update_skill(code: str, body: SkillPatch, user: CurrentUser = Depends(require_user)) -> dict[str, str]:
    async with database_session() as db:
        skill = await _visible_skill(db, code, user)
        if not skill.is_visible_to_user and not user.is_admin:
            raise HTTPException(status_code=403, detail=HIDDEN_LOCKED)
        if body.name is not None:
            skill.name = body.name
        if body.sop_markdown is not None:
            skill.sop_markdown = body.sop_markdown
        if body.trigger_description is not None:
            skill.trigger_description = body.trigger_description
            skill.trigger_embedding = await EmbeddingClient().embed_text(body.trigger_description)
        if body.is_active is not None:
            skill.is_active = body.is_active
        return {"code": skill.code}


@router.put("/roles/{role_code}/skills/{skill_code}", status_code=204)
async def bind_skill(role_code: str, skill_code: str, user: CurrentUser = Depends(require_user)) -> None:
    async with database_session() as db:
        role = await _role(db, role_code)
        skill = await _visible_skill(db, skill_code, user)
        await db.execute(
            insert(AgentRoleSkill)
            .values(role_id=role.id, skill_id=skill.id, auto_activate=False, bound_by_user_id=user.id)
            .on_conflict_do_nothing(index_elements=["role_id", "skill_id"])
        )


@router.delete("/roles/{role_code}/skills/{skill_code}", status_code=204)
async def unbind_skill(role_code: str, skill_code: str, user: CurrentUser = Depends(require_user)) -> None:
    async with database_session() as db:
        role = await _role(db, role_code)
        skill = await _visible_skill(db, skill_code, user)
        if not skill.is_visible_to_user and not user.is_admin:
            raise HTTPException(status_code=403, detail=HIDDEN_LOCKED)
        await db.execute(
            delete(AgentRoleSkill).where(AgentRoleSkill.role_id == role.id, AgentRoleSkill.skill_id == skill.id)
        )


@router.get("/studio/roles/{role_code}/prompt")
async def preview_prompt(role_code: str, user: CurrentUser = Depends(require_user)) -> dict[str, Any]:
    async with database_session() as db:
        role = await _role(db, role_code)
        chat = await db.scalar(
            select(ChatSession).where(ChatSession.user_id == user.id).order_by(ChatSession.updated_at.desc())
        )
        activated = _activated(chat, role_code)
        compiled = await PromptCompiler().compile_for_role(db, role, user.department, activated)
        if user.is_admin:
            text = compiled.system_prompt
        else:
            text = compiled.preview_prompt
        return {
            "role_code": role.code,
            "layers": [
                {
                    "layer": segment.layer,
                    "heading": segment.heading,
                    "body": segment.preview_body if segment.preview_body is not None and not user.is_admin else segment.body,
                }
                for segment in compiled.segments
                if user.is_admin or segment.visible_to_user
            ],
            "prompt": text,
        }


@router.post("/chat/sessions/{session_id}/roles/{role_code}/skills/{skill_code}/activate")
async def activate_skill(
    session_id: UUID,
    role_code: str,
    skill_code: str,
    user: CurrentUser = Depends(require_user),
) -> StreamingResponse:
    async with database_session() as db:
        chat = await db.get(ChatSession, session_id)
        if chat is None or chat.user_id != user.id:
            raise HTTPException(status_code=404, detail="找不到對話")
        skill = await db.scalar(select(SkillRegistry).where(SkillRegistry.code == skill_code))
        if skill is None or (not skill.is_visible_to_user and not user.is_admin):
            raise HTTPException(status_code=404, detail="找不到技能")
        checkpoint = dict(chat.checkpoint or {})
        by_role = dict(checkpoint.get("activated_skills", {}))
        codes = list(by_role.get(role_code, []))
        if skill_code not in codes:
            codes.append(skill_code)
        by_role[role_code] = codes
        checkpoint["activated_skills"] = by_role
        chat.checkpoint = checkpoint
        name = skill.name

    payload = {"role_code": role_code, "skill_code": skill_code, "name": name}

    async def events() -> AsyncIterator[str]:
        import json

        yield f"event: skill_activated\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"

    return StreamingResponse(events(), media_type="text/event-stream")


@router.post("/studio/roles/{role_code}/try")
async def try_prompt(
    role_code: str,
    body: TryRequest,
    user: CurrentUser = Depends(require_user),
) -> dict[str, Any]:
    async with database_session() as db:
        role = await _role(db, role_code)
        compiled = await PromptCompiler().compile_for_role(
            db,
            role,
            user.department,
            tool_schemas=[
                ToolSchema(name="activate_skill", description="載入技能 SOP", parameters={"skill_code": "string"})
            ],
        )
        prompt = compiled.system_prompt if user.is_admin else compiled.preview_prompt
    try:
        output = await GemmaSGLangClient().generate_structured(
            system_prompt=compiled.system_prompt,
            messages=[{"role": "user", "content": body.message}],
            response_model=SubAgentExecutionOutput,
        )
        model_output: dict[str, Any] | None = output.model_dump()
        inference_error = None
    except Exception as exc:
        model_output = None
        inference_error = str(exc)
    return {"prompt": prompt, "model_output": model_output, "inference_error": inference_error}


def _rule_out(rule: RuleRegistry) -> dict[str, Any]:
    return {
        "code": rule.code,
        "name": rule.name,
        "scope_type": rule.scope_type,
        "department": rule.department,
        "priority": rule.priority,
        "rule_content_markdown": rule.rule_content_markdown,
        "is_visible_to_user": rule.is_visible_to_user,
        "approval_status": rule.approval_status,
    }


def _skill_out(skill: SkillRegistry) -> dict[str, Any]:
    return {
        "code": skill.code,
        "name": skill.name,
        "trigger_description": skill.trigger_description,
        "sop_markdown": skill.sop_markdown,
        "execution_mode": skill.execution_mode,
        "cli_config": skill.cli_config,
        "is_visible_to_user": skill.is_visible_to_user,
        "approval_status": skill.approval_status,
    }


async def _role(db: AsyncSession, code: str) -> AgentRole:
    role = await db.scalar(select(AgentRole).where(AgentRole.code == code))
    if role is None:
        raise HTTPException(status_code=404, detail="找不到角色")
    return role


async def _visible_rule(db: AsyncSession, code: str, user: CurrentUser) -> RuleRegistry:
    rule = await db.scalar(select(RuleRegistry).where(RuleRegistry.code == code))
    if rule is None or (not rule.is_visible_to_user and not user.is_admin):
        raise HTTPException(status_code=404, detail="找不到規範")
    return rule


async def _visible_skill(db: AsyncSession, code: str, user: CurrentUser) -> SkillRegistry:
    skill = await db.scalar(select(SkillRegistry).where(SkillRegistry.code == code))
    if skill is None or (not skill.is_visible_to_user and not user.is_admin):
        raise HTTPException(status_code=404, detail="找不到技能")
    return skill


def _activated(chat: ChatSession | None, role_code: str) -> list[str]:
    if chat is None or not chat.checkpoint:
        return []
    raw = chat.checkpoint.get("activated_skills", {})
    values = raw.get(role_code, [])
    return [str(item) for item in values]
