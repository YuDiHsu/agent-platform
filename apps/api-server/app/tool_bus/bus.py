"""Unified tool bus. Implements: ADR-0002, REQ-006, TC-M2-01."""

import asyncio
import hashlib
import json
import time
from dataclasses import dataclass
from typing import Any
from uuid import UUID

import httpx
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.crypto_vault import read_connector_token
from app.db.models import AgentRole, AgentRoleTool, ToolRegistry, UserToolPreference
from app.db.session import database_session
from app.tool_bus import connectors as _connectors
from app.tool_bus.adapter import BaseToolAdapter, ToolContext, ToolResult, registered_adapters
from app.tool_bus.remote import HttpWebhookToolAdapter, RemoteMCPToolAdapter

_ = _connectors

_CACHE_TTL_SECONDS = 60
_BREAKER_THRESHOLD = 3
_BREAKER_COOLDOWN_SECONDS = 30.0


@dataclass(frozen=True)
class _Plan:
    tool_name: str
    arguments: dict[str, Any]
    allowed: bool
    tier: str
    namespace: str
    timeout_seconds: float
    adapter: BaseToolAdapter | None
    access_token: str | None
    error: str | None = None


class CircuitBreaker:
    def __init__(self) -> None:
        self._failures: dict[str, int] = {}
        self._open_until: dict[str, float] = {}

    def allow(self, namespace: str) -> bool:
        return time.monotonic() >= self._open_until.get(namespace, 0.0)

    def record_success(self, namespace: str) -> None:
        self._failures[namespace] = 0
        self._open_until.pop(namespace, None)

    def record_failure(self, namespace: str) -> None:
        count = self._failures.get(namespace, 0) + 1
        self._failures[namespace] = count
        if count >= _BREAKER_THRESHOLD:
            self._open_until[namespace] = time.monotonic() + _BREAKER_COOLDOWN_SECONDS


class UnifiedToolBus:
    def __init__(self, breaker: CircuitBreaker | None = None) -> None:
        self._breaker = breaker or _breaker
        self._builtins = {adapter.namespace: adapter() for adapter in registered_adapters()}

    async def dispatch(
        self,
        *,
        role_code: str,
        user_id: UUID,
        session_id: UUID,
        calls: list[tuple[str, dict[str, Any]]],
    ) -> list[ToolResult]:
        async with database_session() as db:
            plans = [await self._plan(db, role_code=role_code, user_id=user_id, call=call) for call in calls]
        return list(await asyncio.gather(*(self._run(plan, session_id=session_id, role_code=role_code, user_id=user_id) for plan in plans)))

    async def refusal(
        self,
        *,
        role_code: str,
        user_id: UUID,
        call: tuple[str, dict[str, Any]],
    ) -> str | None:
        """Return why this call must not run. None means the role and the user both allow it."""

        async with database_session() as db:
            plan = await self._plan(db, role_code=role_code, user_id=user_id, call=call)
        if plan.allowed:
            return None
        return plan.error or "工具未授權或已關閉"

    async def _plan(
        self,
        db: AsyncSession,
        *,
        role_code: str,
        user_id: UUID,
        call: tuple[str, dict[str, Any]],
    ) -> _Plan:
        tool_name, arguments = call
        role = await db.scalar(select(AgentRole).where(AgentRole.code == role_code))
        tool = await db.scalar(select(ToolRegistry).where(ToolRegistry.code == tool_name))
        if role is None or tool is None or not tool.is_active:
            return _Plan(tool_name, arguments, False, "COMMIT", "", 10, None, None, "找不到工具或角色")
        allowed = await self._allowed(db, role_id=role.id, user_id=user_id, tool=tool)
        token = await self._token(db, user_id=user_id, namespace=tool.namespace)
        adapter = self._adapter_for(tool)
        if not allowed:
            return _Plan(tool_name, arguments, False, tool.action_tier, tool.namespace, float(tool.timeout_seconds), adapter, token, "工具未授權或已關閉")
        return _Plan(tool_name, arguments, True, tool.action_tier, tool.namespace, float(tool.timeout_seconds), adapter, token)

    async def _allowed(self, db: AsyncSession, *, role_id: UUID, user_id: UUID, tool: ToolRegistry) -> bool:
        if not tool.is_visible_to_user:
            return True
        if tool.scope_type != "COMMON_DEFAULT":
            bound = await db.scalar(
                select(AgentRoleTool.tool_id).where(
                    AgentRoleTool.role_id == role_id,
                    AgentRoleTool.tool_id == tool.id,
                )
            )
            if bound is None:
                return False
        enabled = await db.scalar(
            select(UserToolPreference.is_enabled).where(
                UserToolPreference.user_id == user_id,
                UserToolPreference.tool_id == tool.id,
            )
        )
        return bool(enabled)

    async def _token(self, db: AsyncSession, *, user_id: UUID, namespace: str) -> str | None:
        provider = _provider_for(namespace)
        if provider is None:
            return None
        try:
            secrets = await read_connector_token(db, actor_id=user_id, owner_id=user_id, provider=provider)
        except Exception:
            return None
        return secrets.access_token

    def _adapter_for(self, tool: ToolRegistry) -> BaseToolAdapter | None:
        if tool.adapter_type == "REMOTE_MCP":
            url = str((tool.endpoint_config or {}).get("url", ""))
            return RemoteMCPToolAdapter(url) if url else None
        if tool.adapter_type == "HTTP_WEBHOOK":
            url = str((tool.endpoint_config or {}).get("url", ""))
            return HttpWebhookToolAdapter(url) if url else None
        return self._builtins.get(_namespace_key(tool.namespace))

    async def _run(self, plan: _Plan, *, session_id: UUID, role_code: str, user_id: UUID) -> ToolResult:
        if not plan.allowed or plan.adapter is None:
            return ToolResult(plan.tool_name, False, {}, plan.error or "無法執行")
        if not self._breaker.allow(plan.namespace):
            return ToolResult(plan.tool_name, False, {}, "斷路器已開啟")
        if plan.tier == "READ":
            cached = await _cache_get(session_id, plan.tool_name, plan.arguments)
            if cached is not None:
                return ToolResult(plan.tool_name, True, cached)
        context = ToolContext(
            user_id=str(user_id),
            session_id=str(session_id),
            role_code=role_code,
            access_token=plan.access_token,
            timeout_seconds=plan.timeout_seconds,
        )
        try:
            output = await asyncio.wait_for(
                plan.adapter.execute(plan.tool_name, plan.arguments, context),
                timeout=plan.timeout_seconds,
            )
        except (TimeoutError, httpx.HTTPError) as exc:
            self._breaker.record_failure(plan.namespace)
            reason = "逾時" if isinstance(exc, TimeoutError) else "連接器呼叫失敗"
            return ToolResult(plan.tool_name, False, {}, reason)
        self._breaker.record_success(plan.namespace)
        if plan.tier == "READ":
            await _cache_set(session_id, plan.tool_name, plan.arguments, output)
        return ToolResult(plan.tool_name, True, output)


_breaker = CircuitBreaker()


def _namespace_key(namespace: str) -> str:
    if namespace.startswith("o365") or namespace == "onedrive":
        return "o365"
    if namespace.startswith("teams"):
        return "teams"
    if namespace.startswith("slack"):
        return "slack"
    if namespace in {"mail", "imap", "smtp"}:
        return "mail"
    return namespace


def _provider_for(namespace: str) -> str | None:
    key = _namespace_key(namespace)
    if key in {"o365", "teams"}:
        return "MICROSOFT_365"
    if key == "slack":
        return "SLACK"
    if key == "mail":
        return "GENERIC_IMAP"
    return None


def _cache_key(session_id: UUID, tool_name: str, arguments: dict[str, Any]) -> str:
    digest = hashlib.sha256(json.dumps(arguments, sort_keys=True, default=str).encode()).hexdigest()
    return f"tool-cache:{session_id}:{tool_name}:{digest}"


async def _cache_get(session_id: UUID, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any] | None:
    try:
        client = Redis.from_url(settings.REDIS_URL)
        raw = await client.get(_cache_key(session_id, tool_name, arguments))
        await client.aclose()
    except Exception:
        return None
    if raw is None:
        return None
    loaded = json.loads(raw)
    return loaded if isinstance(loaded, dict) else None


async def _cache_set(session_id: UUID, tool_name: str, arguments: dict[str, Any], output: dict[str, Any]) -> None:
    try:
        client = Redis.from_url(settings.REDIS_URL)
        await client.set(_cache_key(session_id, tool_name, arguments), json.dumps(output), ex=_CACHE_TTL_SECONDS)
        await client.aclose()
    except Exception:
        return
