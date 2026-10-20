"""Background ticket worker, heartbeat routines, and offline-mount notices.

Public seams:
- claim_background_ticket / run_next_background_ticket
- POST/GET/PATCH /api/v1/heartbeats and fire_due_heartbeats
- GET /api/v1/users/me/bootstrap notifications
"""

import asyncio
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from uuid import UUID, uuid4

import httpx
import pytest
from sqlalchemy import select, update

from app.core.crypto_vault import save_connector_token
from app.db.models import ChatSession, HeartbeatRoutine, TaskTicket, ToolRegistry, User, UserToolPreference
from app.db.seed_runner import SeedRunner
from app.db.session import database_session, get_session_factory
from app.llm.embedding_client import EmbeddingClient
from app.main import app
from app.orchestrator.state import SubAgentExecutionOutput, SubAgentToolCall
from app.tool_bus.http_pool import get_http_client, set_http_client
from app.workers.heartbeat_cron import fire_due_heartbeats
from app.workers.ticket_worker import claim_background_ticket, run_next_background_ticket


class _ScriptedModel:
    """Ask for one tool, then deliver once the tool result comes back."""

    def __init__(self, tool_name: str, arguments: dict[str, object]) -> None:
        self.tool_name = tool_name
        self.arguments = arguments

    async def generate_structured(
        self,
        system_prompt: str,
        messages: list[dict[str, object]],
        response_model: type[object],
        model_name: str = "gemma-4-27b-it",
        temperature: float = 0.15,
    ) -> object:
        del system_prompt, response_model, model_name, temperature
        text = "\n".join(str(message.get("content", "")) for message in messages)
        if "已直接執行" in text:
            return SubAgentExecutionOutput(
                execution_status="COMPLETED",
                thought_process="已整理信件",
                tool_calls=[],
                artifact_title="晨間摘要",
                artifact_type="EMAIL_DRAFT",
                summary_200_words="今日共有三封未讀信件需要處理。",
                full_markdown_content="# 晨間摘要\n\n- 三封未讀",
                handoff_notes_for_next_role="無",
            )
        return SubAgentExecutionOutput(
            execution_status="NEED_TOOL_CALL",
            thought_process="先讀取資料",
            tool_calls=[SubAgentToolCall(tool_name=self.tool_name, arguments=self.arguments)],
        )


@pytest.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    previous = get_http_client()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as http:
        yield http
    set_http_client(previous)


@pytest.fixture
async def seeded() -> None:
    async with get_session_factory()() as session:
        await SeedRunner(session, EmbeddingClient()).run()
    async with database_session() as db:
        await db.execute(
            update(TaskTicket)
            .where(TaskTicket.execution_lane == "BACKGROUND", TaskTicket.status == "PENDING")
            .values(status="FAILED", error_log="上一個測試留下的背景工單")
        )
        await db.execute(update(HeartbeatRoutine).values(is_enabled=False))


async def _user() -> UUID:
    async with database_session() as db:
        user = User(email=f"bg-{uuid4().hex}@example.com", display_name="背景", department="RD")
        db.add(user)
        await db.flush()
        await db.refresh(user)
        return user.id


async def _session_with_tickets(user_id: UUID, lanes: list[str]) -> list[UUID]:
    async with database_session() as db:
        chat = ChatSession(user_id=user_id, title="背景工作")
        db.add(chat)
        await db.flush()
        ids: list[UUID] = []
        for index, lane in enumerate(lanes):
            ticket = TaskTicket(
                session_id=chat.id,
                requester_user_id=user_id,
                assigned_role_code="PM",
                title=f"工單 {index}",
                input_instructions="整理信件",
                execution_lane=lane,
            )
            db.add(ticket)
            await db.flush()
            ids.append(ticket.id)
        return ids


async def test_concurrent_workers_claim_each_background_ticket_once(seeded: None) -> None:
    user_id = await _user()
    background = await _session_with_tickets(user_id, ["BACKGROUND", "BACKGROUND", "BACKGROUND"])
    interactive = await _session_with_tickets(user_id, ["INTERACTIVE"])

    claims = await asyncio.gather(*(claim_background_ticket(f"worker-{n}") for n in range(5)))

    claimed = [claim for claim in claims if claim is not None]
    assert sorted(str(claim.ticket_id) for claim in claimed) == sorted(str(item) for item in background)
    async with database_session() as db:
        rows = (await db.scalars(select(TaskTicket).where(TaskTicket.id.in_(background + interactive)))).all()
    by_id = {row.id: row for row in rows}
    for claim in claimed:
        row = by_id[claim.ticket_id]
        assert row.status == "IN_PROGRESS"
        assert row.locked_by_worker == claim.worker_id
        assert row.locked_at is not None
    assert by_id[interactive[0]].status == "PENDING"
    assert by_id[interactive[0]].locked_by_worker is None


def _headers(user_id: UUID) -> dict[str, str]:
    return {"X-User-Id": str(user_id)}


async def test_heartbeat_routine_is_created_listed_and_validated(seeded: None, client: httpx.AsyncClient) -> None:
    user_id = await _user()
    created = await client.post(
        "/api/v1/heartbeats",
        headers=_headers(user_id),
        json={"title": "晨間摘要", "role_code": "SA", "instructions": "分類未讀信件", "daily_time": "08:30"},
    )
    assert created.status_code == 201
    listed = await client.get("/api/v1/heartbeats", headers=_headers(user_id))
    assert [(item["title"], item["daily_time"], item["timezone"], item["is_enabled"]) for item in listed.json()] == [
        ("晨間摘要", "08:30", "Asia/Taipei", True)
    ]
    bad_time = await client.post(
        "/api/v1/heartbeats",
        headers=_headers(user_id),
        json={"title": "錯誤", "role_code": "SA", "instructions": "x", "daily_time": "25:00"},
    )
    assert bad_time.status_code == 422
    bad_role = await client.post(
        "/api/v1/heartbeats",
        headers=_headers(user_id),
        json={"title": "錯誤", "role_code": "NOPE", "instructions": "x", "daily_time": "08:30"},
    )
    assert bad_role.status_code == 404
    other = await client.get("/api/v1/heartbeats", headers=_headers(await _user()))
    assert other.json() == []


async def _routine(client: httpx.AsyncClient, user_id: UUID, daily_time: str = "08:30", role_code: str = "SA") -> str:
    response = await client.post(
        "/api/v1/heartbeats",
        headers=_headers(user_id),
        json={"title": "晨間摘要", "role_code": role_code, "instructions": "分類未讀信件", "daily_time": daily_time},
    )
    assert response.status_code == 201
    return str(response.json()["id"])


async def _background_tickets(user_id: UUID) -> list[TaskTicket]:
    async with database_session() as db:
        return list(
            (
                await db.scalars(
                    select(TaskTicket).where(
                        TaskTicket.requester_user_id == user_id,
                        TaskTicket.execution_lane == "BACKGROUND",
                    )
                )
            ).all()
        )


async def test_due_routine_fires_once_per_day_and_disabled_routine_never_fires(
    seeded: None, client: httpx.AsyncClient
) -> None:
    user_id = await _user()
    routine_id = await _routine(client, user_id)
    paused_id = await _routine(client, user_id, "08:00")
    patched = await client.patch(
        f"/api/v1/heartbeats/{paused_id}", headers=_headers(user_id), json={"is_enabled": False}
    )
    assert patched.status_code == 200

    # 08:29 and 08:30 in Asia/Taipei (UTC+8).
    await fire_due_heartbeats(datetime(2026, 10, 20, 0, 29, tzinfo=UTC))
    assert await _background_tickets(user_id) == []
    await fire_due_heartbeats(datetime(2026, 10, 20, 0, 30, tzinfo=UTC))
    await fire_due_heartbeats(datetime(2026, 10, 20, 0, 45, tzinfo=UTC))
    tickets = await _background_tickets(user_id)
    assert [(ticket.assigned_role_code, ticket.status, ticket.input_instructions) for ticket in tickets] == [
        ("SA", "PENDING", "分類未讀信件")
    ]
    await fire_due_heartbeats(datetime(2026, 10, 21, 0, 31, tzinfo=UTC))
    assert len(await _background_tickets(user_id)) == 2
    listed = await client.get("/api/v1/heartbeats", headers=_headers(user_id))
    fired = {item["id"]: item["last_fired_on"] for item in listed.json()}
    assert fired == {routine_id: "2026-10-21", paused_id: None}


async def _enable_tool(user_id: UUID, code: str) -> None:
    async with database_session() as db:
        tool = await db.scalar(select(ToolRegistry).where(ToolRegistry.code == code))
        assert tool is not None
        db.add(UserToolPreference(user_id=user_id, tool_id=tool.id, is_enabled=True))


async def test_worker_runs_server_connector_with_obo_token_while_browser_is_closed(
    seeded: None, client: httpx.AsyncClient
) -> None:
    user_id = await _user()
    await _enable_tool(user_id, "o365_search_messages")
    async with database_session() as db:
        await save_connector_token(
            db, owner_id=user_id, provider="MICROSOFT_365", access_token="obo-token-a", refresh_token=None, scopes=[]
        )
    seen: list[str | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.headers.get("Authorization"))
        return httpx.Response(200, json={"messages": 3})

    set_http_client(httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    await _routine(client, user_id)
    await fire_due_heartbeats(datetime(2026, 10, 20, 0, 30, tzinfo=UTC))

    result = await run_next_background_ticket(
        _ScriptedModel("o365_search_messages", {"query": "is:unread"}), worker_id="worker-a"
    )

    assert result is not None
    assert result.outcome == "completed"
    assert seen == ["Bearer obo-token-a"]
    [ticket] = await _background_tickets(user_id)
    assert ticket.status == "COMPLETED"
    assert ticket.locked_by_worker is None
    bootstrap = await client.get("/api/v1/users/me/bootstrap", headers=_headers(user_id))
    notices = bootstrap.json()["notifications"]
    assert [(item["kind"], item["session_id"]) for item in notices] == [("HEARTBEAT_COMPLETED", str(ticket.session_id))]
    assert await run_next_background_ticket(_ScriptedModel("o365_search_messages", {}), worker_id="worker-a") is None


async def test_offline_local_mount_hibernates_the_ticket_and_notifies_the_user(
    seeded: None, client: httpx.AsyncClient
) -> None:
    user_id = await _user()
    await _routine(client, user_id, role_code="PM")
    await fire_due_heartbeats(datetime(2026, 10, 20, 0, 30, tzinfo=UTC))

    result = await run_next_background_ticket(
        _ScriptedModel("workspace_read_file", {"path": "訪談紀錄.docx"}), worker_id="worker-a"
    )

    assert result is not None
    assert result.outcome == "waiting_browser"
    [ticket] = await _background_tickets(user_id)
    assert ticket.status == "WAITING_BROWSER"
    assert ticket.locked_by_worker is None
    bootstrap = await client.get("/api/v1/users/me/bootstrap", headers=_headers(user_id))
    [notice] = bootstrap.json()["notifications"]
    assert (notice["kind"], notice["session_id"]) == ("LOCAL_MOUNT_OFFLINE", str(ticket.session_id))
    assert "本機" in notice["title"]
    read = await client.post(f"/api/v1/users/me/notifications/{notice['id']}/read", headers=_headers(user_id))
    assert read.status_code == 204
    again = await client.get("/api/v1/users/me/bootstrap", headers=_headers(user_id))
    assert again.json()["notifications"] == []
