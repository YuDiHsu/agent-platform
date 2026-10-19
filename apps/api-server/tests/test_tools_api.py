"""Tool catalog and persisted personal switches. Implements: ADR-0002, ADR-0004."""

from collections.abc import AsyncIterator

import httpx
import pytest

from app.db.seed_runner import SeedRunner
from app.db.session import get_session_factory
from app.llm.embedding_client import EmbeddingClient
from app.main import app


@pytest.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    async with get_session_factory()() as session:
        await SeedRunner(session, EmbeddingClient()).run()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http:
        yield http


async def _login(client: httpx.AsyncClient, email: str) -> dict[str, str]:
    response = await client.post(
        "/api/v1/users/dev-login",
        json={"email": email, "display_name": "工具使用者", "department": "RD"},
    )
    assert response.status_code == 200
    return {"X-User-Id": response.json()["id"]}


async def test_disabled_tool_stays_off_after_another_login(client: httpx.AsyncClient) -> None:
    headers = await _login(client, "tools-user@example.com")
    listed = (await client.get("/api/v1/tools", headers=headers)).json()
    codes = {row["code"] for row in listed}
    assert "o365_search_messages" in codes
    assert "TOOL_HIDDEN_GUARDRAIL" not in codes
    assert all(row["is_enabled"] is False for row in listed)

    hidden = await client.put(
        "/api/v1/users/me/tool-preferences",
        headers=headers,
        json={"code": "TOOL_HIDDEN_GUARDRAIL", "is_enabled": False},
    )
    assert hidden.status_code == 404

    saved = await client.put(
        "/api/v1/users/me/tool-preferences",
        headers=headers,
        json={"code": "o365_search_messages", "is_enabled": True},
    )
    assert saved.status_code == 204

    again = await _login(client, "tools-user@example.com")
    restored = (await client.get("/api/v1/tools", headers=again)).json()
    mail = next(row for row in restored if row["code"] == "o365_search_messages")
    assert mail["is_enabled"] is True
    turned_off = await client.put(
        "/api/v1/users/me/tool-preferences",
        headers=again,
        json={"code": "o365_search_messages", "is_enabled": False},
    )
    assert turned_off.status_code == 204
    after_logout = await _login(client, "tools-user@example.com")
    persisted = (await client.get("/api/v1/tools", headers=after_logout)).json()
    mail = next(row for row in persisted if row["code"] == "o365_search_messages")
    assert mail["is_enabled"] is False
    bootstrap = await client.get("/api/v1/users/me/bootstrap", headers=after_logout)
    preferences = {row["code"]: row["is_enabled"] for row in bootstrap.json()["tool_preferences"]}
    assert preferences["o365_search_messages"] is False
