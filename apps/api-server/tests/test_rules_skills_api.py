"""Hidden rules stay out of the user catalog and cannot be unbound. Implements: ADR-0004, REQ-014."""

import httpx
import pytest
from sqlalchemy import select

from app.db.models import User
from app.db.seed_runner import SeedRunner
from app.db.session import get_session_factory
from app.llm.embedding_client import EmbeddingClient
from app.main import app


@pytest.fixture
async def client() -> httpx.AsyncClient:
    async with get_session_factory()() as session:
        await SeedRunner(session, EmbeddingClient()).run()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http:
        yield http


async def _login(client: httpx.AsyncClient, email: str, *, admin: bool = False) -> dict[str, str]:
    response = await client.post(
        "/api/v1/users/dev-login",
        json={"email": email, "display_name": "測試者", "department": "RD"},
    )
    assert response.status_code == 200
    user_id = response.json()["id"]
    if admin:
        async with get_session_factory()() as session:
            user = await session.scalar(select(User).where(User.id == user_id))
            assert user is not None
            user.is_admin = True
            await session.commit()
    return {"X-User-Id": user_id}


async def test_user_catalog_hides_system_rules_and_blocks_unbinding(client: httpx.AsyncClient) -> None:
    headers = await _login(client, "studio-user@example.com")
    rules = (await client.get("/api/v1/rules", headers=headers)).json()
    codes = {row["code"] for row in rules}
    assert "RULE_GLOBAL_ZH_TW" in codes
    assert "RULE_HIDDEN_RADIX_PREFIX" not in codes
    skills = (await client.get("/api/v1/skills", headers=headers)).json()
    assert "SKILL_HIDDEN_GUARDRAIL" not in {row["code"] for row in skills}

    hidden = await client.delete("/api/v1/roles/SA/rules/RULE_HIDDEN_RADIX_PREFIX", headers=headers)
    assert hidden.status_code == 404

    preview = await client.get("/api/v1/studio/roles/SA/prompt", headers=headers)
    assert preview.status_code == 200
    body = preview.json()["prompt"]
    assert "RULE_SA_OPENAPI_AND_ERD" in body
    assert "HIDDEN-RADIX-77" not in body
    assert "RULE_FIN_TWD_THREE_SCENARIOS" not in body


async def test_admin_can_see_hidden_rule_and_activation_emits_sse(client: httpx.AsyncClient) -> None:
    headers = await _login(client, "studio-admin@example.com", admin=True)
    rules = (await client.get("/api/v1/rules", headers=headers)).json()
    assert "RULE_HIDDEN_RADIX_PREFIX" in {row["code"] for row in rules}

    created = await client.post(
        "/api/v1/chat/sessions",
        headers=headers,
    )
    session_id = created.json()["id"]
    response = await client.post(
        f"/api/v1/chat/sessions/{session_id}/roles/SA/skills/SKILL_SA_OPENAPI_CLI_VALIDATOR/activate",
        headers=headers,
    )
    assert response.status_code == 200
    assert "event: skill_activated" in response.text
    assert "SKILL_SA_OPENAPI_CLI_VALIDATOR" in response.text

    preview = await client.get("/api/v1/studio/roles/SA/prompt", headers=headers)
    assert "validate_openapi.py" in preview.json()["prompt"]
