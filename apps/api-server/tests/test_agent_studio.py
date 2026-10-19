"""Personal agent workspace, preset reset, and private-mount publication. Implements: ADR-0003, TC-M3-01."""

from collections.abc import AsyncIterator
from uuid import UUID, uuid4

import httpx
import pytest
from sqlalchemy import delete, select

from app.api.deps import get_llm
from app.core.config import settings
from app.db.models import AgentMemory, AgentRole
from app.db.seed_runner import SeedRunner
from app.db.session import database_session, get_session_factory
from app.llm.embedding_client import EmbeddingClient
from app.main import app
from app.orchestrator.state import SubAgentExecutionOutput


class _SpecModel:
    async def generate_structured(
        self,
        system_prompt: str,
        messages: list[dict[str, object]],
        response_model: type[object],
        model_name: str = "gemma-4-27b-it",
        temperature: float = 0.15,
    ) -> object:
        del system_prompt, messages, model_name, temperature
        if response_model is SubAgentExecutionOutput:
            raise AssertionError("規格產生不該走到角色輸出")
        return response_model.model_validate(
            {
                "name": "法務助理",
                "code": "LEGAL_ASSISTANT",
                "system_prompt": "你是法務助理，一律使用繁體中文指出合約罰則。",
                "routing_description": "檢查本機採購合約並標出違約罰則",
                "recommended_rule_codes": ["RULE_GLOBAL_ZH_TW"],
                "recommended_skill_codes": [],
                "recommended_tool_codes": ["workspace_read_file"],
            }
        )


@pytest.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    async with get_session_factory()() as session:
        await SeedRunner(session, EmbeddingClient()).run()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http:
        yield http
    async with database_session() as db:
        await db.execute(delete(AgentRole).where(AgentRole.creator_user_id.is_not(None)))
    app.dependency_overrides.pop(get_llm, None)


async def _login(client: httpx.AsyncClient, email: str) -> dict[str, str]:
    response = await client.post(
        "/api/v1/users/dev-login",
        json={"email": email, "display_name": "工作區使用者", "department": "RD"},
    )
    assert response.status_code == 200
    return {"X-User-Id": response.json()["id"]}


def _by_code(rows: list[dict[str, object]]) -> dict[str, dict[str, object]]:
    return {str(row["code"]): row for row in rows}


async def test_disabling_or_removing_a_preset_stays_inside_one_workspace(client: httpx.AsyncClient) -> None:
    alice = await _login(client, f"alice-{uuid4().hex}@hub.local")
    bella = await _login(client, f"bella-{uuid4().hex}@hub.local")

    disabled = await client.patch("/api/v1/agents/PM", headers=alice, json={"is_enabled": False, "name": "我的專案經理"})
    assert disabled.status_code == 200
    assert disabled.json()["name"] == "我的專案經理"
    assert disabled.json()["is_enabled"] is False

    alice_rows = _by_code((await client.get("/api/v1/agents", headers=alice)).json())
    bella_rows = _by_code((await client.get("/api/v1/agents", headers=bella)).json())
    assert alice_rows["PM"]["is_enabled"] is False
    assert bella_rows["PM"]["is_enabled"] is True
    assert bella_rows["PM"]["name"] != "我的專案經理"

    removed = await client.delete("/api/v1/agents/PM", headers=alice)
    assert removed.status_code == 204
    assert "PM" not in _by_code((await client.get("/api/v1/agents", headers=alice)).json())
    assert "PM" in _by_code((await client.get("/api/v1/agents", headers=bella)).json())

    restored = await client.post("/api/v1/agents/presets/reset", headers=alice, json={"code": "PM"})
    assert restored.status_code == 200
    assert restored.json()["restored"] == ["PM"]
    again = _by_code((await client.get("/api/v1/agents", headers=alice)).json())
    assert again["PM"]["is_enabled"] is True
    assert again["PM"]["name"] == bella_rows["PM"]["name"]


async def test_generate_spec_creates_a_private_agent_with_an_embedding(client: httpx.AsyncClient) -> None:
    app.dependency_overrides[get_llm] = lambda: _SpecModel()
    headers = await _login(client, f"spec-{uuid4().hex}@hub.local")
    generated = await client.post(
        "/api/v1/agents/generate-spec",
        headers=headers,
        json={"description": "幫我建立一個檢查本機採購合約資料夾並標出違約罰則的法務助理"},
    )
    assert generated.status_code == 200
    spec = generated.json()
    assert spec["name"] == "法務助理"
    assert spec["system_prompt"] == "你是法務助理，一律使用繁體中文指出合約罰則。"
    assert spec["recommended_tool_codes"] == ["workspace_read_file"]

    created = await client.post(
        "/api/v1/agents",
        headers=headers,
        json={
            "code": spec["code"],
            "name": spec["name"],
            "department": "RD",
            "system_prompt": spec["system_prompt"],
            "routing_description": spec["routing_description"],
            "visibility_scope": "PRIVATE",
            "allowed_tool_namespaces": ["local_fs"],
        },
    )
    assert created.status_code == 201
    assert created.json()["approval_status"] == "APPROVED"
    assert created.json()["visibility_scope"] == "PRIVATE"
    async with database_session() as db:
        role = await db.scalar(select(AgentRole).where(AgentRole.code == "LEGAL_ASSISTANT"))
        assert role is not None
        assert role.routing_embedding is not None
        assert len(list(role.routing_embedding)) == settings.EMBEDDING_DIMENSION


async def test_a_local_mount_cannot_be_published_and_department_waits_for_review(
    client: httpx.AsyncClient,
) -> None:
    headers = await _login(client, f"publish-{uuid4().hex}@hub.local")
    mount = await client.post(
        "/api/v1/mounts/register",
        headers=headers,
        json={"mount_alias": "合約", "browser_handle_key": "local_mount_legal", "file_tree": []},
    )
    assert mount.status_code == 201
    rejected = await client.post(
        "/api/v1/agents",
        headers=headers,
        json={
            "code": "LEGAL_PUBLIC",
            "name": "公開法務",
            "department": "RD",
            "system_prompt": "你是法務助理。",
            "routing_description": "公開合約審查",
            "visibility_scope": "GLOBAL",
            "bound_local_mount_id": mount.json()["id"],
        },
    )
    assert rejected.status_code == 400
    assert "ERR_LOCAL_MOUNT_MUST_BE_PRIVATE" in rejected.json()["detail"]

    pending = await client.post(
        "/api/v1/agents",
        headers=headers,
        json={
            "code": "LEGAL_DEPT",
            "name": "部門法務",
            "department": "RD",
            "system_prompt": "你是部門法務助理。",
            "routing_description": "部門合約審查",
            "visibility_scope": "DEPARTMENT",
        },
    )
    assert pending.status_code == 201
    assert pending.json()["approval_status"] == "PENDING_REVIEW"


async def _memory(
    *,
    owner_id: str,
    scope: str,
    role_code: str | None,
    session_id: str | None,
    content: str,
) -> None:
    vector = [0.0] * settings.EMBEDDING_DIMENSION
    vector[0] = 1.0
    async with database_session() as db:
        db.add(
            AgentMemory(
                memory_scope=scope,
                owner_user_id=UUID(owner_id),
                role_code=role_code,
                session_id=UUID(session_id) if session_id else None,
                content=content,
                embedding=vector,
            )
        )


async def _contents(owner_id: str) -> set[str]:
    async with database_session() as db:
        rows = (await db.scalars(select(AgentMemory).where(AgentMemory.owner_user_id == owner_id))).all()
        return {row.content for row in rows}


async def test_memory_cleanup_has_three_scopes_and_spares_shared_memory(client: httpx.AsyncClient) -> None:
    headers = await _login(client, f"memory-{uuid4().hex}@hub.local")
    owner = headers["X-User-Id"]
    opened = await client.post("/api/v1/chat/sessions", headers=headers)
    session_id = opened.json()["id"]
    await _memory(owner_id=owner, scope="USER_PRIVATE", role_code="PM", session_id=None, content="PM 私人筆記")
    await _memory(owner_id=owner, scope="USER_PRIVATE", role_code="SA", session_id=None, content="SA 私人筆記")
    await _memory(owner_id=owner, scope="EPHEMERAL_LOCAL_FILE", role_code="PM", session_id=session_id, content="PM 暫時切片")
    await _memory(owner_id=owner, scope="DEPARTMENT_SHARED", role_code="PM", session_id=None, content="部門共享")
    await _memory(owner_id=owner, scope="ORG_GLOBAL", role_code="PM", session_id=None, content="全公司記憶")

    by_role = await client.delete("/api/v1/memories", headers=headers, params={"role_code": "PM"})
    assert by_role.status_code == 200
    assert by_role.json()["deleted"] == 2
    assert await _contents(owner) == {"SA 私人筆記", "部門共享", "全公司記憶"}

    await _memory(owner_id=owner, scope="EPHEMERAL_LOCAL_FILE", role_code=None, session_id=session_id, content="對話暫時切片")
    deleted = await client.delete(f"/api/v1/chat/sessions/{session_id}", headers=headers)
    assert deleted.status_code == 204
    missing = await client.get(f"/api/v1/chat/sessions/{session_id}/state", headers=headers)
    assert missing.status_code == 404
    assert "對話暫時切片" not in await _contents(owner)

    stranger = await _login(client, f"stranger-{uuid4().hex}@hub.local")
    foreign = await client.delete(f"/api/v1/chat/sessions/{session_id}", headers=stranger)
    assert foreign.status_code == 404

    forbidden = await client.delete("/api/v1/memories", headers=headers, params={"memory_scope": "ORG_GLOBAL"})
    assert forbidden.status_code == 403
    cleared = await client.delete("/api/v1/memories", headers=headers)
    assert cleared.status_code == 200
    assert await _contents(owner) == {"部門共享", "全公司記憶"}
