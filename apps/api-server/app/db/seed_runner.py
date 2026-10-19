"""Idempotent builtin role, rule, and skill loader. Implements: REQ-001, TC-M1-01, ADR-0001."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import REPO_ROOT
from app.db.catalog import read_builtin_catalog
from app.db.models import AgentRole, AgentRoleRule, AgentRoleSkill, RuleRegistry, SkillRegistry
from app.llm.embedding_client import EmbeddingClient

ROLES_PATH = REPO_ROOT / "packages" / "builtin-roles" / "seed_roles.yaml"
RULES_PATH = REPO_ROOT / "packages" / "builtin-skills-rules" / "seed_rules.yaml"
SKILLS_PATH = REPO_ROOT / "packages" / "builtin-skills-rules" / "seed_skills.yaml"


@dataclass(frozen=True)
class SeedSummary:
    roles: int
    rules: int
    skills: int
    rule_bindings: int
    skill_bindings: int


def _load_yaml(path: Path) -> dict[str, Any]:
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise ValueError(f"{path} must contain a mapping")
    return loaded


def _clean(value: str) -> str:
    return value.strip()


class SeedRunner:
    def __init__(self, session: AsyncSession, embedder: EmbeddingClient) -> None:
        self._session = session
        self._embedder = embedder

    async def run(
        self,
        roles_path: Path = ROLES_PATH,
        rules_path: Path = RULES_PATH,
        skills_path: Path = SKILLS_PATH,
    ) -> SeedSummary:
        role_docs = list(_load_yaml(roles_path)["roles"])
        rule_docs = list(_load_yaml(rules_path)["rules"])
        skill_docs = list(_load_yaml(skills_path)["skills"])

        role_vectors = await self._embedder.embed_texts(
            [_clean(str(doc["routing_description"])) for doc in role_docs]
        )
        skill_vectors = await self._embedder.embed_texts(
            [_clean(str(doc["trigger_description"])) for doc in skill_docs]
        )

        code_to_role: dict[str, AgentRole] = {}
        for doc, vector in zip(role_docs, role_vectors, strict=True):
            code_to_role[str(doc["code"])] = await self._upsert_role(doc, vector)
        await self._session.flush()
        for doc in role_docs:
            parent_code = doc.get("reports_to_code")
            role = code_to_role[str(doc["code"])]
            role.reports_to_id = None if parent_code is None else code_to_role[str(parent_code)].id

        code_to_rule: dict[str, RuleRegistry] = {}
        for doc in rule_docs:
            code_to_rule[str(doc["code"])] = await self._upsert_rule(doc)
        await self._session.flush()

        code_to_skill: dict[str, SkillRegistry] = {}
        for doc, vector in zip(skill_docs, skill_vectors, strict=True):
            code_to_skill[str(doc["code"])] = await self._upsert_skill(doc, vector)
        await self._session.flush()

        for doc in rule_docs:
            rule = code_to_rule[str(doc["code"])]
            for role_code in doc["bound_role_codes"]:
                role = code_to_role[str(role_code)]
                await self._session.execute(
                    insert(AgentRoleRule)
                    .values(role_id=role.id, rule_id=rule.id, is_mandatory=True)
                    .on_conflict_do_nothing(index_elements=["role_id", "rule_id"])
                )
        for doc in skill_docs:
            skill = code_to_skill[str(doc["code"])]
            for role_code in doc["bound_role_codes"]:
                role = code_to_role[str(role_code)]
                await self._session.execute(
                    insert(AgentRoleSkill)
                    .values(role_id=role.id, skill_id=skill.id, auto_activate=False)
                    .on_conflict_do_nothing(index_elements=["role_id", "skill_id"])
                )
        await self._session.commit()
        catalog = await read_builtin_catalog(self._session)
        return SeedSummary(
            roles=len(catalog.roles),
            rules=len(catalog.rules),
            skills=len(catalog.skills),
            rule_bindings=len(catalog.rule_bindings),
            skill_bindings=len(catalog.skill_bindings),
        )

    async def _upsert_role(self, doc: dict[str, Any], embedding: list[float]) -> AgentRole:
        code = str(doc["code"])
        existing = await self._session.scalar(select(AgentRole).where(AgentRole.code == code))
        fields = {
            "name": str(doc["name"]),
            "department": str(doc["department"]),
            "visibility_scope": str(doc["visibility_scope"]),
            "approval_status": str(doc["approval_status"]),
            "system_prompt": str(doc["system_prompt"]),
            "routing_description": _clean(str(doc["routing_description"])),
            "routing_embedding": embedding,
            "output_json_schema": doc["output_json_schema"],
            "allowed_tool_namespaces": list(doc["allowed_tool_namespaces"]),
            "model_params": dict(doc["model_params"]),
            "is_active": True,
        }
        if existing is None:
            role = AgentRole(code=code, **fields)
            self._session.add(role)
            return role
        for key, value in fields.items():
            setattr(existing, key, value)
        return existing

    async def _upsert_rule(self, doc: dict[str, Any]) -> RuleRegistry:
        code = str(doc["code"])
        existing = await self._session.scalar(select(RuleRegistry).where(RuleRegistry.code == code))
        fields = {
            "name": str(doc["name"]),
            "scope_type": str(doc["scope_type"]),
            "department": doc.get("department"),
            "priority": int(doc["priority"]),
            "rule_content_markdown": str(doc["rule_content_markdown"]).strip(),
            "glob_trigger": doc.get("glob_trigger"),
            "is_visible_to_user": bool(doc.get("is_visible_to_user", True)),
            "approval_status": str(doc.get("approval_status", "APPROVED")),
            "is_active": True,
        }
        if existing is None:
            rule = RuleRegistry(code=code, **fields)
            self._session.add(rule)
            return rule
        for key, value in fields.items():
            setattr(existing, key, value)
        return existing

    async def _upsert_skill(self, doc: dict[str, Any], embedding: list[float]) -> SkillRegistry:
        code = str(doc["code"])
        existing = await self._session.scalar(select(SkillRegistry).where(SkillRegistry.code == code))
        fields = {
            "name": str(doc["name"]),
            "visibility_scope": str(doc.get("visibility_scope", "GLOBAL")),
            "department": doc.get("department"),
            "trigger_description": _clean(str(doc["trigger_description"])),
            "trigger_embedding": embedding,
            "sop_markdown": str(doc["sop_markdown"]).strip(),
            "execution_mode": str(doc["execution_mode"]),
            "cli_config": doc.get("cli_config"),
            "required_tool_namespaces": list(doc.get("required_tool_namespaces", [])),
            "is_visible_to_user": bool(doc.get("is_visible_to_user", True)),
            "approval_status": str(doc.get("approval_status", "APPROVED")),
            "is_active": True,
        }
        if existing is None:
            skill = SkillRegistry(code=code, **fields)
            self._session.add(skill)
            return skill
        for key, value in fields.items():
            setattr(existing, key, value)
        return existing
