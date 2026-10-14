"""Read back builtin roles, rules, and skills. Implements: REQ-001, TC-M1-01."""

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AgentRole, AgentRoleRule, AgentRoleSkill, RuleRegistry, SkillRegistry


def coerce_vector(value: object) -> list[float]:
    if isinstance(value, str):
        raw = value.strip().strip("[]")
        if not raw:
            return []
        return [float(part) for part in raw.split(",")]
    if isinstance(value, list | tuple):
        return [float(part) for part in value]
    return []


@dataclass(frozen=True)
class RoleView:
    id: uuid.UUID
    code: str
    reports_to_code: str | None
    embedding: list[float]


@dataclass(frozen=True)
class RuleView:
    code: str
    scope_type: str
    priority: int


@dataclass(frozen=True)
class SkillView:
    code: str
    execution_mode: str
    embedding: list[float]


@dataclass(frozen=True)
class BuiltinCatalog:
    roles: tuple[RoleView, ...]
    rules: tuple[RuleView, ...]
    skills: tuple[SkillView, ...]
    rule_bindings: tuple[tuple[str, str], ...]
    skill_bindings: tuple[tuple[str, str], ...]


async def read_builtin_catalog(session: AsyncSession) -> BuiltinCatalog:
    role_rows = (await session.scalars(select(AgentRole).order_by(AgentRole.code))).all()
    id_to_code = {role.id: role.code for role in role_rows}
    roles = tuple(
        RoleView(
            id=role.id,
            code=role.code,
            reports_to_code=None if role.reports_to_id is None else id_to_code.get(role.reports_to_id),
            embedding=coerce_vector(role.routing_embedding),
        )
        for role in role_rows
    )
    rule_rows = (await session.scalars(select(RuleRegistry).order_by(RuleRegistry.code))).all()
    rules = tuple(
        RuleView(code=rule.code, scope_type=rule.scope_type, priority=rule.priority) for rule in rule_rows
    )
    skill_rows = (await session.scalars(select(SkillRegistry).order_by(SkillRegistry.code))).all()
    skills = tuple(
        SkillView(
            code=skill.code,
            execution_mode=skill.execution_mode,
            embedding=coerce_vector(skill.trigger_embedding),
        )
        for skill in skill_rows
    )
    rule_id_to_code = {rule.id: rule.code for rule in rule_rows}
    skill_id_to_code = {skill.id: skill.code for skill in skill_rows}
    role_rule_rows = (await session.scalars(select(AgentRoleRule))).all()
    role_skill_rows = (await session.scalars(select(AgentRoleSkill))).all()
    rule_bindings = tuple(
        sorted(
            (id_to_code[row.role_id], rule_id_to_code[row.rule_id])
            for row in role_rule_rows
            if row.role_id in id_to_code and row.rule_id in rule_id_to_code
        )
    )
    skill_bindings = tuple(
        sorted(
            (id_to_code[row.role_id], skill_id_to_code[row.skill_id])
            for row in role_skill_rows
            if row.role_id in id_to_code and row.skill_id in skill_id_to_code
        )
    )
    return BuiltinCatalog(
        roles=roles,
        rules=rules,
        skills=skills,
        rule_bindings=rule_bindings,
        skill_bindings=skill_bindings,
    )


def binding_map(pairs: tuple[tuple[str, str], ...], *, by_right: bool) -> dict[str, frozenset[str]]:
    grouped: dict[str, set[str]] = {}
    for left, right in pairs:
        key = right if by_right else left
        value = left if by_right else right
        grouped.setdefault(key, set()).add(value)
    return {key: frozenset(values) for key, values in grouped.items()}
