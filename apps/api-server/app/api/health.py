"""Health check for the walking skeleton. Implements: REQ-001, REQ-008, REQ-012."""

import logging
from typing import Literal

from fastapi import APIRouter, Response
from pydantic import BaseModel
from redis.asyncio import Redis
from sqlalchemy import func, select, text

from app.core.config import settings
from app.db.models import AgentRole, RuleRegistry, SkillRegistry
from app.db.session import get_session_factory

logger = logging.getLogger(__name__)

router = APIRouter()

EXPECTED_ROLES = 7
EXPECTED_RULES = 5
EXPECTED_SKILLS = 4


class SeedCounts(BaseModel):
    roles: int
    rules: int
    skills: int


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    postgres: Literal["ok", "error"]
    redis: Literal["ok", "error"]
    seed: SeedCounts | None


@router.get("/health", response_model=HealthResponse)
async def health(response: Response) -> HealthResponse:
    postgres: Literal["ok", "error"] = "error"
    redis_status: Literal["ok", "error"] = "error"
    seed: SeedCounts | None = None
    try:
        async with get_session_factory()() as session:
            await session.execute(text("SELECT 1"))
            postgres = "ok"
            roles = await session.scalar(select(func.count()).select_from(AgentRole))
            rules = await session.scalar(select(func.count()).select_from(RuleRegistry))
            skills = await session.scalar(select(func.count()).select_from(SkillRegistry))
            seed = SeedCounts(roles=int(roles or 0), rules=int(rules or 0), skills=int(skills or 0))
    except Exception:
        logger.exception("postgres health check failed")
    try:
        client = Redis.from_url(settings.REDIS_URL)
        try:
            await client.ping()
            redis_status = "ok"
        finally:
            await client.aclose()
    except Exception:
        logger.exception("redis health check failed")
    seeded = (
        seed is not None
        and seed.roles == EXPECTED_ROLES
        and seed.rules == EXPECTED_RULES
        and seed.skills == EXPECTED_SKILLS
    )
    status: Literal["ok", "degraded"] = "ok" if postgres == "ok" and redis_status == "ok" and seeded else "degraded"
    if status != "ok":
        response.status_code = 503
    return HealthResponse(status=status, postgres=postgres, redis=redis_status, seed=seed)
