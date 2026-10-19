"""Dynamic role and tool retrieval. Implements: REQ-009, ADR-0002, ADR-0004."""

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AgentRole, AgentRoleTool, ToolRegistry, UserToolPreference
from app.orchestrator.prompt_compiler import PromptCompiler, ToolSchema

TOP_K = 5


@dataclass(frozen=True)
class RetrievedTool:
    code: str
    name: str
    description: str
    input_json_schema: dict[str, Any]
    distance: float
    visible_to_user: bool


@dataclass(frozen=True)
class RetrievedRole:
    code: str
    name: str
    distance: float


class ToolRetriever:
    async def tools_for_turn(
        self,
        db: AsyncSession,
        *,
        role_id: UUID,
        user_id: UUID,
        query_embedding: list[float],
    ) -> list[RetrievedTool]:
        preference = (
            select(UserToolPreference.is_enabled)
            .where(
                UserToolPreference.user_id == user_id,
                UserToolPreference.tool_id == ToolRegistry.id,
            )
            .correlate(ToolRegistry)
            .scalar_subquery()
        )
        bound = select(AgentRoleTool.tool_id).where(AgentRoleTool.role_id == role_id)
        authorized = or_(
            ToolRegistry.scope_type == "COMMON_DEFAULT",
            ToolRegistry.id.in_(bound),
        )
        distance = ToolRegistry.routing_embedding.cosine_distance(query_embedding)
        rows = (
            await db.execute(
                select(ToolRegistry, distance.label("distance"))
                .where(
                    or_(ToolRegistry.is_active.is_(True), ToolRegistry.is_active.is_(None)),
                    ToolRegistry.routing_embedding.is_not(None),
                    or_(
                        ToolRegistry.is_visible_to_user.is_(False),
                        and_(ToolRegistry.is_visible_to_user.is_(True), authorized, preference.is_(True)),
                    ),
                )
                .order_by(distance.asc())
                .limit(TOP_K)
            )
        ).all()
        return [
            RetrievedTool(
                code=tool.code,
                name=tool.name,
                description=tool.description,
                input_json_schema=dict(tool.input_json_schema),
                distance=float(score),
                visible_to_user=bool(tool.is_visible_to_user),
            )
            for tool, score in rows
        ]

    async def roles_for_turn(
        self,
        db: AsyncSession,
        *,
        user_id: UUID,
        user_department: str,
        query_embedding: list[float],
    ) -> list[RetrievedRole]:
        distance = AgentRole.routing_embedding.cosine_distance(query_embedding)
        visible = or_(
            AgentRole.visibility_scope == "GLOBAL",
            and_(AgentRole.visibility_scope == "DEPARTMENT", AgentRole.department == user_department),
            and_(AgentRole.visibility_scope == "PRIVATE", AgentRole.creator_user_id == user_id),
        )
        rows = (
            await db.execute(
                select(AgentRole, distance.label("distance"))
                .where(
                    or_(AgentRole.is_active.is_(True), AgentRole.is_active.is_(None)),
                    AgentRole.approval_status == "APPROVED",
                    AgentRole.routing_embedding.is_not(None),
                    visible,
                )
                .order_by(distance.asc())
                .limit(TOP_K)
            )
        ).all()
        return [
            RetrievedRole(code=role.code, name=role.name, distance=float(score)) for role, score in rows
        ]


def tool_schemas(tools: list[RetrievedTool]) -> list[ToolSchema]:
    return [
        ToolSchema(name=tool.code, description=tool.description, parameters=tool.input_json_schema) for tool in tools
    ]


async def compile_role_turn(
    db: AsyncSession,
    *,
    role: AgentRole,
    user_id: UUID,
    user_department: str,
    query_embedding: list[float],
    activated_skill_codes: list[str] | None = None,
) -> str:
    tools = await ToolRetriever().tools_for_turn(
        db,
        role_id=role.id,
        user_id=user_id,
        query_embedding=query_embedding,
    )
    compiled = await PromptCompiler().compile_for_role(
        db,
        role,
        user_department,
        activated_skill_codes,
        tool_schemas(tools),
    )
    return compiled.system_prompt
