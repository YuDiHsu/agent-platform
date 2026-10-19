"""Walking-skeleton health check includes postgres, redis, and the builtin seed."""

import httpx
import pytest

from app.db.seed_runner import SeedRunner
from app.db.session import get_session_factory
from app.llm.embedding_client import EmbeddingClient
from app.main import app


@pytest.mark.asyncio
async def test_health_reports_infrastructure_and_seed() -> None:
    async with get_session_factory()() as session:
        await SeedRunner(session, EmbeddingClient()).run()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "postgres": "ok",
        "redis": "ok",
        "seed": {"roles": 7, "rules": 6, "skills": 5},
    }
