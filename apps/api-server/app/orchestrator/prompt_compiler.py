"""Onion prompt compiler. Implements: REQ-013, REQ-014, ADR-0002, ADR-0004."""

from dataclasses import dataclass
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AgentRole, AgentRoleRule, AgentRoleSkill, RuleRegistry, SkillRegistry

LAYER_JOIN = "\n\n---\n\n"
CATALOG_LINE_LIMIT = 59


@dataclass(frozen=True)
class ToolSchema:
    name: str
    description: str
    parameters: dict[str, Any]


@dataclass(frozen=True)
class PromptSegment:
    """One onion layer fragment.

    `body` is what the model sees. `preview_body` replaces it in the user-facing
    inspector when hidden lines must be removed from an otherwise visible layer.
    """

    layer: int
    heading: str
    body: str
    visible_to_user: bool
    preview_body: str | None = None

    def render(self, *, preview: bool) -> str:
        if preview and not self.visible_to_user:
            return ""
        text = self.preview_body if preview and self.preview_body is not None else self.body
        if not text:
            return ""
        return f"{self.heading}\n{text}" if self.heading else text


@dataclass(frozen=True)
class CompiledPrompt:
    segments: tuple[PromptSegment, ...]

    @property
    def system_prompt(self) -> str:
        return _join(self.segments, preview=False)

    @property
    def preview_prompt(self) -> str:
        return _join(self.segments, preview=True)

    @property
    def prefix_through_layer_4(self) -> str:
        return _join(tuple(segment for segment in self.segments if segment.layer <= 4), preview=False)


def _join(segments: tuple[PromptSegment, ...], *, preview: bool) -> str:
    parts = [segment.render(preview=preview) for segment in segments]
    return LAYER_JOIN.join(part for part in parts if part)


def stage_one_manifest(code: str, name: str, trigger: str) -> str:
    """Keep one standby skill under 60 tokens by staying under 60 characters."""
    summary = " ".join(trigger.split())
    prefix = f"{code} {name}: "
    room = CATALOG_LINE_LIMIT - len(prefix)
    if room <= 0:
        return prefix[:CATALOG_LINE_LIMIT]
    return prefix + summary[:room]


def _active(column: Any) -> Any:
    return or_(column.is_(True), column.is_(None))


class PromptCompiler:
    async def compile_for_role(
        self,
        db: AsyncSession,
        role: AgentRole,
        user_department: str,
        activated_skill_codes: list[str] | None = None,
        tool_schemas: list[ToolSchema] | None = None,
    ) -> CompiledPrompt:
        activated = set(activated_skill_codes or [])
        segments: list[PromptSegment] = []
        segments.extend(await self._shared_rules(db, user_department))
        segments.append(
            PromptSegment(
                layer=2,
                heading=f"【角色核心職責 {role.code}】",
                body=role.system_prompt.strip(),
                visible_to_user=True,
            )
        )
        segments.extend(await self._exclusive_rules(db, role))
        segments.extend(await self._skills(db, role, activated))
        tool_segment = self._tools(tool_schemas or [])
        if tool_segment is not None:
            segments.append(tool_segment)
        return CompiledPrompt(segments=tuple(segments))

    async def _shared_rules(self, db: AsyncSession, user_department: str) -> list[PromptSegment]:
        global_rules = (
            await db.scalars(
                select(RuleRegistry)
                .where(_active(RuleRegistry.is_active), RuleRegistry.scope_type == "GLOBAL_MANDATORY")
                .order_by(RuleRegistry.priority.asc(), RuleRegistry.code.asc())
            )
        ).all()
        department_rules = (
            await db.scalars(
                select(RuleRegistry)
                .where(
                    _active(RuleRegistry.is_active),
                    RuleRegistry.scope_type == "DEPARTMENT_SHARED",
                    RuleRegistry.department == user_department,
                )
                .order_by(RuleRegistry.priority.asc(), RuleRegistry.code.asc())
            )
        ).all()
        return [_rule_segment(rule, layer=1) for rule in (*global_rules, *department_rules)]

    async def _exclusive_rules(self, db: AsyncSession, role: AgentRole) -> list[PromptSegment]:
        rules = (
            await db.scalars(
                select(RuleRegistry)
                .join(AgentRoleRule, AgentRoleRule.rule_id == RuleRegistry.id)
                .where(
                    AgentRoleRule.role_id == role.id,
                    _active(RuleRegistry.is_active),
                    RuleRegistry.scope_type == "ROLE_EXCLUSIVE",
                )
                .order_by(RuleRegistry.priority.asc(), RuleRegistry.code.asc())
            )
        ).all()
        return [_rule_segment(rule, layer=3) for rule in rules]

    async def _skills(self, db: AsyncSession, role: AgentRole, activated: set[str]) -> list[PromptSegment]:
        rows = (
            await db.execute(
                select(SkillRegistry, AgentRoleSkill.auto_activate)
                .join(AgentRoleSkill, AgentRoleSkill.skill_id == SkillRegistry.id)
                .where(AgentRoleSkill.role_id == role.id, _active(SkillRegistry.is_active))
                .order_by(SkillRegistry.code.asc())
            )
        ).all()
        if not rows:
            return []
        all_lines = [
            stage_one_manifest(skill.code, skill.name, skill.trigger_description) for skill, _auto in rows
        ]
        visible_lines = [
            stage_one_manifest(skill.code, skill.name, skill.trigger_description)
            for skill, _auto in rows
            if skill.is_visible_to_user
        ]
        segments = [
            PromptSegment(
                layer=4,
                heading="【第一階段技能清單】",
                body="\n".join(all_lines),
                visible_to_user=True,
                preview_body="\n".join(visible_lines),
            )
        ]
        for skill, auto_activate in rows:
            if auto_activate or skill.code in activated:
                segments.append(_sop_segment(skill))
        return segments

    def _tools(self, tools: list[ToolSchema]) -> PromptSegment | None:
        chosen = tools[:5]
        if not chosen:
            return None
        lines = [f"{tool.name}: {tool.description}\n{tool.parameters}" for tool in chosen]
        return PromptSegment(
            layer=6,
            heading="【本回合工具 Top-5】",
            body="\n".join(lines),
            visible_to_user=True,
        )


def _rule_segment(rule: RuleRegistry, *, layer: int) -> PromptSegment:
    return PromptSegment(
        layer=layer,
        heading=f"【規範 {rule.code}】",
        body=rule.rule_content_markdown.strip(),
        visible_to_user=bool(rule.is_visible_to_user),
    )


def _sop_segment(skill: SkillRegistry) -> PromptSegment:
    cli = ""
    template = (skill.cli_config or {}).get("command_template")
    if skill.execution_mode in {"SERVER_SANDBOX_CLI", "LOCAL_DAEMON_CLI"} and template:
        cli = f"\nCLI：呼叫 execute_skill_cli，skill_code={skill.code}，命令範本 {template}"
    return PromptSegment(
        layer=5,
        heading=f"【技能 SOP {skill.code}】",
        body=f"{skill.sop_markdown.strip()}{cli}",
        visible_to_user=bool(skill.is_visible_to_user),
    )
