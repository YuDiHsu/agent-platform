"""Unified tool bus: authorization, parallelism, timeout, cache, and remote mounts."""

import asyncio
import time
from uuid import UUID, uuid4

import httpx
from sqlalchemy import select

from app.core.config import settings
from app.db.models import AgentRole, ToolRegistry, User, UserToolPreference
from app.db.seed_runner import SeedRunner
from app.db.session import database_session_depth, get_session_factory
from app.llm.embedding_client import EmbeddingClient
from app.main import app
from app.tool_bus.adapter import BaseToolAdapter, ToolContext, ToolSpec
from app.tool_bus.bus import CircuitBreaker, UnifiedToolBus
from app.tool_bus.http_pool import set_http_client


class _SlowAdapter(BaseToolAdapter):
    namespace = "slow"

    def list_tools(self) -> list[ToolSpec]:
        return []

    async def health_check(self) -> bool:
        return True

    calls = 0

    async def execute(self, tool_name: str, arguments: dict[str, object], context: ToolContext) -> dict[str, object]:
        type(self).calls += 1
        await asyncio.sleep(0.3)
        return {"tool": tool_name}


async def _ready() -> tuple[User, str]:
    async with get_session_factory()() as session:
        await SeedRunner(session, EmbeddingClient()).run()
        user = User(email=f"bus-{uuid4().hex}@example.com", display_name="匯流排", department="RD")
        session.add(user)
        await session.flush()
        role = await session.scalar(select(AgentRole).where(AgentRole.code == "SA"))
        assert role is not None
        tool = await session.scalar(select(ToolRegistry).where(ToolRegistry.code == "o365_search_messages"))
        assert tool is not None
        session.add(UserToolPreference(user_id=user.id, tool_id=tool.id, is_enabled=True))
        await session.commit()
        return user, role.code


def _bus(breaker: CircuitBreaker | None = None) -> UnifiedToolBus:
    bus = UnifiedToolBus(breaker=breaker or CircuitBreaker())
    bus._builtins["slow"] = _SlowAdapter()
    return bus


async def test_disabled_or_unbound_tool_is_refused_before_any_call() -> None:
    user, role_code = await _ready()
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        assert database_session_depth() == 0
        calls.append(request.url.path)
        return httpx.Response(200, json={"ok": True})

    set_http_client(httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    async with get_session_factory()() as session:
        tool = await session.scalar(select(ToolRegistry).where(ToolRegistry.code == "o365_search_messages"))
        assert tool is not None
        preference = await session.scalar(
            select(UserToolPreference).where(
                UserToolPreference.user_id == user.id,
                UserToolPreference.tool_id == tool.id,
            )
        )
        assert preference is not None
        preference.is_enabled = False
        await session.commit()
    refused = await _bus().dispatch(
        role_code=role_code,
        user_id=user.id,
        session_id=uuid4(),
        calls=[("o365_search_messages", {"query": "週報"})],
    )
    assert refused[0].ok is False
    assert calls == []


async def test_read_calls_run_in_parallel_and_repeat_hits_the_cache() -> None:
    user, role_code = await _ready()
    async with get_session_factory()() as session:
        for code in ("slow_one", "slow_two"):
            tool = ToolRegistry(
                code=code,
                namespace="slow",
                name=code,
                description=code,
                input_json_schema={"type": "object"},
                action_tier="READ",
                scope_type="COMMON_DEFAULT",
                is_visible_to_user=True,
                timeout_seconds=2,
                routing_embedding=[0.0] * settings.EMBEDDING_DIMENSION,
                is_active=True,
            )
            session.add(tool)
            await session.flush()
            session.add(UserToolPreference(user_id=user.id, tool_id=tool.id, is_enabled=True))
        await session.commit()
    _SlowAdapter.calls = 0
    bus = _bus()
    started = time.monotonic()
    first = await bus.dispatch(
        role_code=role_code,
        user_id=user.id,
        session_id=uuid4(),
        calls=[("slow_one", {"n": 1}), ("slow_two", {"n": 1})],
    )
    elapsed = time.monotonic() - started
    assert all(item.ok for item in first)
    assert elapsed < 0.6
    session_id = uuid4()
    await bus.dispatch(role_code=role_code, user_id=user.id, session_id=session_id, calls=[("slow_one", {"n": 1})])
    cached_started = time.monotonic()
    cached = await bus.dispatch(
        role_code=role_code,
        user_id=user.id,
        session_id=session_id,
        calls=[("slow_one", {"n": 1})],
    )
    assert cached[0].ok is True
    assert _SlowAdapter.calls == 3


async def test_timeout_opens_the_circuit_breaker() -> None:
    user, role_code = await _ready()
    async with get_session_factory()() as session:
        tool = ToolRegistry(
            code="slow_timeout",
            namespace="slow",
            name="逾時",
            description="逾時",
            input_json_schema={"type": "object"},
            action_tier="DRAFT",
            scope_type="COMMON_DEFAULT",
            is_visible_to_user=True,
            timeout_seconds=1,
            routing_embedding=[0.0] * settings.EMBEDDING_DIMENSION,
            is_active=True,
        )
        session.add(tool)
        await session.flush()
        session.add(UserToolPreference(user_id=user.id, tool_id=tool.id, is_enabled=True))
        tool.timeout_seconds = 1
        await session.commit()
    breaker = CircuitBreaker()
    bus = _bus(breaker)
    bus._builtins["slow"] = _SlowAdapter()

    class _TinyTimeout(BaseToolAdapter):
        namespace = "slow"

        def list_tools(self) -> list[ToolSpec]:
            return []

        async def health_check(self) -> bool:
            return True

        async def execute(self, tool_name: str, arguments: dict[str, object], context: ToolContext) -> dict[str, object]:
            await asyncio.sleep(1.1)
            return {"ok": True}

    bus._builtins["slow"] = _TinyTimeout()
    results = []
    for _ in range(3):
        results.append(
            (
                await bus.dispatch(
                    role_code=role_code,
                    user_id=user.id,
                    session_id=uuid4(),
                    calls=[("slow_timeout", {})],
                )
            )[0]
        )
    assert [item.error for item in results] == ["逾時", "逾時", "逾時"]
    opened = (
        await bus.dispatch(
            role_code=role_code,
            user_id=user.id,
            session_id=uuid4(),
            calls=[("slow_timeout", {})],
        )
    )[0]
    assert opened.error == "斷路器已開啟"


async def test_admin_can_mount_a_webhook_and_the_bus_calls_it() -> None:
    seen: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        assert database_session_depth() == 0
        seen.append({"path": request.url.path, "body": request.content.decode()})
        return httpx.Response(200, json={"delivered": True})

    set_http_client(httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    async with get_session_factory()() as session:
        await SeedRunner(session, EmbeddingClient()).run()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        login = await client.post(
            "/api/v1/users/dev-login",
            json={"email": f"mount-{uuid4().hex}@example.com", "display_name": "管理員", "department": "RD"},
        )
        user_id = login.json()["id"]
        async with get_session_factory()() as session:
            account = await session.get(User, UUID(user_id))
            assert account is not None
            account.is_admin = True
            await session.commit()
        headers = {"X-User-Id": user_id}
        created = await client.post(
            "/api/v1/tools/remote",
            headers=headers,
            json={
                "code": "webhook_ping",
                "name": "Webhook",
                "namespace": "hooks",
                "adapter_type": "HTTP_WEBHOOK",
                "url": "http://hooks.test/run",
                "action_tier": "READ",
            },
        )
        assert created.status_code == 201
        await client.put(
            "/api/v1/users/me/tool-preferences",
            headers=headers,
            json={"code": "webhook_ping", "is_enabled": True},
        )
    result = await UnifiedToolBus(breaker=CircuitBreaker()).dispatch(
        role_code="SA",
        user_id=UUID(user_id),
        session_id=uuid4(),
        calls=[("webhook_ping", {"hello": "world"})],
    )
    assert result[0].ok is True
    assert result[0].output["delivered"] is True
    assert "hello" in seen[0]["body"]
