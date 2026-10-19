"""Which agents a person can see, toggle, and restore. Implements: ADR-0003."""

from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AgentRole, UserAgentConfig

PRESET_CODES = ("ORCH", "CEO", "PM", "FIN", "SA", "ARCH", "SE")


async def load_configs(db: AsyncSession, user_id: UUID) -> dict[UUID, UserAgentConfig]:
    rows = (
        await db.scalars(select(UserAgentConfig).where(UserAgentConfig.user_id == user_id))
    ).all()
    return {row.role_id: row for row in rows}


def visible_to_owner(role: AgentRole, user_id: UUID, config: UserAgentConfig | None) -> bool:
    if config is not None and config.is_removed:
        return False
    if role.code in PRESET_CODES and role.creator_user_id is None:
        return True
    return role.creator_user_id == user_id and role.is_active is not False


async def workspace_roles(db: AsyncSession, user_id: UUID) -> list[tuple[AgentRole, UserAgentConfig | None]]:
    configs = await load_configs(db, user_id)
    roles = (
        await db.scalars(
            select(AgentRole).where(
                or_(AgentRole.is_active.is_(True), AgentRole.is_active.is_(None)),
            )
        )
    ).all()
    visible = [role for role in roles if visible_to_owner(role, user_id, configs.get(role.id))]
    visible.sort(key=lambda role: (role.code not in PRESET_CODES, role.code))
    return [(role, configs.get(role.id)) for role in visible]


def display_name(role: AgentRole, config: UserAgentConfig | None) -> str:
    if config is not None and config.name_override:
        return config.name_override
    return role.name


def display_prompt(role: AgentRole, config: UserAgentConfig | None) -> str:
    if config is not None and config.system_prompt_override:
        return config.system_prompt_override
    return role.system_prompt
