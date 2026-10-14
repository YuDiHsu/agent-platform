"""Chat workspace seam: persisted sessions, DAG delegation, and login hydration.

The public boundary is the FastAPI HTTP and SSE contract (spec seam A).
A scripted model stands in for the external Gemma server.
"""

import asyncio
import contextlib
import json
import re
from uuid import UUID, uuid4

import httpx
import pytest
from sqlalchemy import text, update

from app.api.deps import get_llm
from app.db.models import TaskTicket, User
from app.db.seed_runner import SeedRunner
from app.db.session import database_session_depth, get_session_factory
from app.llm.embedding_client import EmbeddingClient
from app.main import app
from app.orchestrator.runtime import drain_background
from app.orchestrator.state import (
    DAGTaskNode,
    OrchestratorPlanOutput,
    SubAgentExecutionOutput,
    SubAgentToolCall,
)

CHAT_SESSION_COLUMNS = {
    "id",
    "user_id",
    "title",
    "status",
    "active_role_code",
    "goal_statement",
    "dag_snapshot",
    "checkpoint",
    "hold_reason",
    "created_at",
    "updated_at",
}
CHAT_MESSAGE_COLUMNS = {
    "id",
    "session_id",
    "role_code",
    "event_type",
    "content",
    "payload",
    "created_at",
}
DELEGATE_REQUEST = "請先由系統分析師拆解需求，再平行請架構與財務估算，最後由專案經理彙整"
FINAL_SYNTHESIS = "已完成：SA 交付物、ARCH 交付物、FIN 交付物、PM 交付物"


def parse_sse(body: str) -> list[tuple[str, dict[str, object]]]:
    events: list[tuple[str, dict[str, object]]] = []
    for block in body.split("\n\n"):
        if not block.strip():
            continue
        event_name = "message"
        data = ""
        for line in block.splitlines():
            if line.startswith("event:"):
                event_name = line.split(":", 1)[1].strip()
            elif line.startswith("data:"):
                data += line.split(":", 1)[1].strip()
        if data:
            payload = json.loads(data)
            assert isinstance(payload, dict)
            events.append((event_name, payload))
    return events


def _role_from(prompt: str) -> str:
    match = re.search(r"target_role_code: (\w+)", prompt)
    assert match is not None
    return match.group(1)


class ScriptedGemma:
    """External model stand-in. Plans are fixed literals, not derived from the engine."""

    def __init__(self) -> None:
        self.mode = "delegate"
        self.prompts: list[str] = []
        self.role_calls = 0
        self.held_session = False
        self.parallel_ok = False
        self.pause_pm = False
        self.pm_entered = asyncio.Event()
        self.release_pm = asyncio.Event()
        self._entered: list[str] = []
        self._gate = asyncio.Event()

    async def generate_structured(
        self,
        system_prompt: str,
        messages: list[dict[str, object]],
        response_model: type[object],
        model_name: str = "gemma-4-27b-it",
        temperature: float = 0.15,
    ) -> object:
        del system_prompt, model_name, temperature
        if database_session_depth() != 0:
            self.held_session = True
            raise RuntimeError("database session held during inference")
        text_blob = "\n".join(str(message.get("content", "")) for message in messages)
        self.prompts.append(text_blob)
        if response_model.__name__ == "OrchestratorPlanOutput":
            return self._plan()
        self.role_calls += 1
        role = _role_from(text_blob)
        if self.mode == "delegate" and role in {"ARCH", "FIN"}:
            self._entered.append(role)
            if len(set(self._entered)) >= 2:
                self.parallel_ok = True
                self._gate.set()
            else:
                await asyncio.wait_for(self._gate.wait(), 2)
        if self.pause_pm and role == "PM":
            self.pm_entered.set()
            await self.release_pm.wait()
        return self._role_output(role)

    def _plan(self) -> OrchestratorPlanOutput:
        if self.mode == "direct":
            return OrchestratorPlanOutput(
                intent_mode="DIRECT_ANSWER",
                reasoning="這個問題不需要委派",
                goal_statement="直接說明",
                direct_response_to_user="企業採本地模型，不提供即時時鐘。",
            )
        if self.mode == "circuit":
            steps = [
                DAGTaskNode(
                    step_id=index,
                    target_role_code="SA",
                    task_title=f"步驟{index}",
                    detailed_instructions=f"執行步驟{index}",
                    depends_on_steps=[] if index == 1 else [index - 1],
                )
                for index in range(1, 10)
            ]
            return OrchestratorPlanOutput(
                intent_mode="DELEGATE_DAG",
                reasoning="長鏈委派",
                goal_statement="走完九步",
                dag_steps=steps,
            )
        if self.mode == "cycle":
            return OrchestratorPlanOutput(
                intent_mode="DELEGATE_DAG",
                reasoning="這張圖互相依賴",
                goal_statement="無效圖",
                dag_steps=[
                    DAGTaskNode(
                        step_id=1,
                        target_role_code="SA",
                        task_title="甲",
                        detailed_instructions="甲",
                        depends_on_steps=[2],
                    ),
                    DAGTaskNode(
                        step_id=2,
                        target_role_code="PM",
                        task_title="乙",
                        detailed_instructions="乙",
                        depends_on_steps=[1],
                    ),
                ],
            )
        if self.mode == "hitl":
            return OrchestratorPlanOutput(
                intent_mode="DELEGATE_DAG",
                reasoning="寄信前需要核准",
                goal_statement="核准後才寄信",
                dag_steps=[
                    DAGTaskNode(
                        step_id=1,
                        target_role_code="PM",
                        task_title="寄出進度信",
                        detailed_instructions="草擬信件",
                    )
                ],
            )
        if self.mode == "browser":
            return OrchestratorPlanOutput(
                intent_mode="DELEGATE_DAG",
                reasoning="需要讀取使用者電腦上的檔案",
                goal_statement="讀到訪談紀錄",
                dag_steps=[
                    DAGTaskNode(
                        step_id=1,
                        target_role_code="PM",
                        task_title="讀取本機檔案",
                        detailed_instructions="讀取訪談紀錄",
                    )
                ],
            )
        if self.mode == "handoff_then_wait":
            return OrchestratorPlanOutput(
                intent_mode="DELEGATE_DAG",
                reasoning="先寫規格，寄信前暫停",
                goal_statement="規格完成後等待核准",
                dag_steps=[
                    DAGTaskNode(
                        step_id=1,
                        target_role_code="SA",
                        task_title="需求規格",
                        detailed_instructions="拆解需求",
                    ),
                    DAGTaskNode(
                        step_id=2,
                        target_role_code="PM",
                        task_title="寄出進度信",
                        detailed_instructions="草擬信件",
                        depends_on_steps=[1],
                    ),
                ],
            )
        return OrchestratorPlanOutput(
            intent_mode="DELEGATE_DAG",
            reasoning="跨領域需求需要規格、架構與成本後由專案經理彙整",
            goal_statement="交出可執行的產品方案",
            dag_steps=[
                DAGTaskNode(
                    step_id=1,
                    target_role_code="SA",
                    task_title="需求規格",
                    detailed_instructions="拆解需求",
                ),
                DAGTaskNode(
                    step_id=2,
                    target_role_code="ARCH",
                    task_title="架構設計",
                    detailed_instructions="設計架構",
                    depends_on_steps=[1],
                ),
                DAGTaskNode(
                    step_id=3,
                    target_role_code="FIN",
                    task_title="成本試算",
                    detailed_instructions="試算成本",
                    depends_on_steps=[1],
                ),
                DAGTaskNode(
                    step_id=4,
                    target_role_code="PM",
                    task_title="彙整交付",
                    detailed_instructions="彙整成可執行方案",
                    depends_on_steps=[2, 3],
                ),
            ],
        )

    def _role_output(self, role: str) -> SubAgentExecutionOutput:
        if self.mode == "hitl" or (self.mode == "handoff_then_wait" and role == "PM"):
            return SubAgentExecutionOutput(
                execution_status="NEED_TOOL_CALL",
                thought_process="需要寄信，先等待核准",
                tool_calls=[
                    SubAgentToolCall(
                        tool_name="o365_send_mail",
                        arguments={"to": "dev-team@company.com", "subject": "進度"},
                    )
                ],
            )
        if self.mode == "browser":
            return SubAgentExecutionOutput(
                execution_status="NEED_TOOL_CALL",
                thought_process="瀏覽器目前離線",
                tool_calls=[
                    SubAgentToolCall(tool_name="workspace_read_file", arguments={"path": "訪談紀錄.docx"})
                ],
            )
        kinds = {
            "SA": "REQUIREMENT_SPEC",
            "ARCH": "ARCH_DIAGRAM",
            "FIN": "FINANCIAL_MODEL",
            "PM": "PROJECT_PLAN_WBS",
            "SE": "CODE_DIFF",
            "CEO": "STRATEGY_MEMO",
            "ORCH": "STRATEGY_MEMO",
        }
        return SubAgentExecutionOutput(
            execution_status="COMPLETED",
            thought_process=f"{role} 完成本職交付",
            tool_calls=[],
            artifact_title=f"{role} 交付物",
            artifact_type=kinds[role],  # type: ignore[arg-type]
            summary_200_words="摘" * 250,
            full_markdown_content=(
                f"# {role} 交付物\n\n"
                + ("詳細規格段落。" * 30)
                + "\n\nFULL-BODY-SENTINEL\n\n```mermaid\ngraph TD; A-->B;\n```\n"
            ),
            handoff_notes_for_next_role=f"{role} 交接備註",
        )


@pytest.fixture
async def client() -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http:
        yield http


@pytest.fixture
async def scripted() -> ScriptedGemma:
    model = ScriptedGemma()
    app.dependency_overrides[get_llm] = lambda: model
    yield model
    model.release_pm.set()
    model._gate.set()
    await drain_background()
    app.dependency_overrides.pop(get_llm, None)


@pytest.fixture(autouse=True)
async def seeded_catalog() -> None:
    async with get_session_factory()() as session:
        await SeedRunner(session, EmbeddingClient()).run()


async def test_chat_tables_and_per_user_quota_columns_exist() -> None:
    factory = get_session_factory()
    async with factory() as session:
        tables = set(
            (
                await session.scalars(
                    text(
                        "SELECT table_name FROM information_schema.tables "
                        "WHERE table_schema = 'public' AND table_type = 'BASE TABLE'"
                    )
                )
            ).all()
        )
        session_columns = set(
            (
                await session.scalars(
                    text(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_schema = 'public' AND table_name = 'chat_sessions'"
                    )
                )
            ).all()
        )
        message_columns = set(
            (
                await session.scalars(
                    text(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_schema = 'public' AND table_name = 'chat_messages'"
                    )
                )
            ).all()
        )
        user_columns = set(
            (
                await session.scalars(
                    text(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_schema = 'public' AND table_name = 'users'"
                    )
                )
            ).all()
        )

    assert "chat_sessions" in tables
    assert "chat_messages" in tables
    assert session_columns == CHAT_SESSION_COLUMNS
    assert message_columns == CHAT_MESSAGE_COLUMNS
    assert {"max_concurrent_tickets", "token_quota_limit", "tokens_consumed_total"} <= user_columns


async def test_new_user_gets_a_concurrent_ticket_quota_of_four() -> None:
    factory = get_session_factory()
    async with factory() as session:
        row = (
            await session.execute(
                text(
                    "INSERT INTO users (email, display_name, department) "
                    "VALUES (:email, '配額', 'RD') "
                    "RETURNING max_concurrent_tickets, token_quota_limit, tokens_consumed_total"
                ),
                {"email": f"quota-{uuid4().hex}@hub.local"},
            )
        ).one()
        await session.commit()
    assert row[0] == 4
    assert row[1] is None
    assert row[2] == 0


def _headers(user: dict[str, object]) -> dict[str, str]:
    return {"X-User-Id": str(user["id"])}


async def _login(client: httpx.AsyncClient) -> dict[str, object]:
    response = await client.post(
        "/api/v1/users/dev-login",
        json={
            "email": f"worker-{uuid4().hex}@hub.local",
            "display_name": "王小明",
            "department": "RD",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, dict)
    return body


async def _open_session(client: httpx.AsyncClient, user: dict[str, object]) -> str:
    response = await client.post("/api/v1/chat/sessions", headers=_headers(user))
    assert response.status_code == 201
    body = response.json()
    assert isinstance(body["id"], str)
    return body["id"]


async def _send(
    client: httpx.AsyncClient,
    user: dict[str, object],
    session_id: str,
    message: str,
) -> list[tuple[str, dict[str, object]]]:
    response = await client.post(
        f"/api/v1/chat/sessions/{session_id}/stream",
        headers=_headers(user),
        json={"message": message},
    )
    assert response.status_code == 200, response.text
    return parse_sse(response.text)


async def _state(client: httpx.AsyncClient, user: dict[str, object], session_id: str) -> dict[str, object]:
    response = await client.get(f"/api/v1/chat/sessions/{session_id}/state", headers=_headers(user))
    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, dict)
    return body


def _at(events: list[tuple[str, dict[str, object]]], event_name: str, field: str, value: str) -> int:
    for index, (name, payload) in enumerate(events):
        if name == event_name and payload.get(field) == value:
            return index
    raise AssertionError(f"missing {event_name} {field}={value}")


async def test_delegate_dag_runs_sa_then_parallel_arch_and_fin_then_pm(
    client: httpx.AsyncClient,
    scripted: ScriptedGemma,
) -> None:
    user = await _login(client)
    session_id = await _open_session(client, user)
    events = await _send(client, user, session_id, DELEGATE_REQUEST)
    body = await _state(client, user, session_id)

    sa_switch = _at(events, "role_switched", "active_role", "SA")
    arch_switch = _at(events, "role_switched", "active_role", "ARCH")
    fin_switch = _at(events, "role_switched", "active_role", "FIN")
    pm_switch = _at(events, "role_switched", "active_role", "PM")
    sa_art = _at(events, "artifact_created", "producer_role", "SA")
    arch_art = _at(events, "artifact_created", "producer_role", "ARCH")
    fin_art = _at(events, "artifact_created", "producer_role", "FIN")
    pm_art = _at(events, "artifact_created", "producer_role", "PM")
    assert events[0][0] == "orchestrator_plan"
    assert sa_switch < sa_art < arch_switch
    assert sa_art < fin_switch
    assert max(arch_art, fin_art) < pm_switch < pm_art
    assert events[-1][0] == "final_response"
    assert events[-1][1]["text"] == FINAL_SYNTHESIS
    assert scripted.parallel_ok is True
    assert scripted.held_session is False
    tickets = body["tickets"]
    assert isinstance(tickets, list)
    by_role = {str(ticket["assigned_role_code"]): ticket for ticket in tickets}
    assert {role: by_role[role]["hop_count"] for role in ("SA", "ARCH", "FIN", "PM")} == {
        "SA": 1,
        "ARCH": 2,
        "FIN": 3,
        "PM": 4,
    }
    assert by_role["PM"]["goal_ancestry"] == [
        "交出可執行的產品方案",
        "SA 需求規格",
        "ARCH 架構設計",
        "FIN 成本試算",
    ]
    assert all(int(ticket["hop_count"]) <= 8 for ticket in tickets)
    assert all(ticket["locked_by_worker"] is None for ticket in tickets)
    forwarded = "\n".join(scripted.prompts)
    assert "FULL-BODY-SENTINEL" not in forwarded
    assert "摘" * 201 not in forwarded


async def test_claim_check_keeps_the_full_body_out_of_the_checkpoint(
    client: httpx.AsyncClient,
    scripted: ScriptedGemma,
) -> None:
    scripted.mode = "handoff_then_wait"
    user = await _login(client)
    session_id = await _open_session(client, user)
    await _send(client, user, session_id, "請系統分析師寫規格後交給專案經理寄信")
    body = await _state(client, user, session_id)

    assert body["hold_reason"] == "WAITING_HITL"
    assert body["hibernated"] is True
    checkpoint = json.dumps(body["checkpoint"], ensure_ascii=False)
    assert "FULL-BODY-SENTINEL" not in checkpoint
    assert "content_body" not in checkpoint
    tickets = body["tickets"]
    assert isinstance(tickets, list)
    pm = next(ticket for ticket in tickets if ticket["assigned_role_code"] == "PM")
    assert pm["status"] == "WAITING_HITL"
    assert pm["locked_by_worker"] is None
    assert "FULL-BODY-SENTINEL" not in str(pm["input_instructions"])
    assert "摘" * 200 in str(pm["input_instructions"])
    assert "摘" * 201 not in str(pm["input_instructions"])
    artifacts = body["artifacts"]
    assert isinstance(artifacts, list)
    assert artifacts[0]["summary_200_words"] == "摘" * 200
    assert "FULL-BODY-SENTINEL" in str(artifacts[0]["content_body"])
    messages = body["messages"]
    assert isinstance(messages, list)
    stored = next(message for message in messages if message["event_type"] == "artifact_created")
    assert "content_body" not in stored["payload"]
    pending = body["pending_hitl"]
    assert isinstance(pending, list)
    assert pending[0]["tool_name"] == "o365_send_mail"
    assert pending[0]["proposed_payload"] == {"to": "dev-team@company.com", "subject": "進度"}


async def test_ninth_hop_is_circuit_broken(client: httpx.AsyncClient, scripted: ScriptedGemma) -> None:
    scripted.mode = "circuit"
    user = await _login(client)
    session_id = await _open_session(client, user)
    events = await _send(client, user, session_id, "請連續委派九個步驟")
    body = await _state(client, user, session_id)
    tickets = body["tickets"]
    assert isinstance(tickets, list)
    broken = next(ticket for ticket in tickets if ticket["title"] == "步驟9")
    assert body["status"] == "CIRCUIT_BROKEN"
    assert broken["status"] == "CIRCUIT_BROKEN"
    assert broken["hop_count"] == 9
    completed = {ticket["title"]: ticket["hop_count"] for ticket in tickets if ticket["status"] == "COMPLETED"}
    assert completed == {f"步驟{index}": index for index in range(1, 9)}
    assert scripted.role_calls == 8
    assert events[-1][1]["text"] == "已達 max_hops=8，後續步驟標記為 CIRCUIT_BROKEN。"


async def test_waiting_for_the_browser_hibernates_and_releases_the_worker(
    client: httpx.AsyncClient,
    scripted: ScriptedGemma,
) -> None:
    scripted.mode = "browser"
    user = await _login(client)
    session_id = await _open_session(client, user)
    await _send(client, user, session_id, "請讀取本機訪談紀錄")
    body = await _state(client, user, session_id)
    tickets = body["tickets"]
    assert isinstance(tickets, list)
    assert body["hold_reason"] == "WAITING_BROWSER"
    assert body["hibernated"] is True
    assert tickets[0]["status"] == "WAITING_BROWSER"
    assert tickets[0]["locked_by_worker"] is None
    assert body["pending_hitl"] == []


async def test_token_quota_pauses_before_any_model_call(
    client: httpx.AsyncClient,
    scripted: ScriptedGemma,
) -> None:
    user = await _login(client)
    async with get_session_factory()() as session:
        await session.execute(update(User).where(User.id == UUID(str(user["id"]))).values(token_quota_limit=0))
        await session.commit()
    session_id = await _open_session(client, user)
    events = await _send(client, user, session_id, "請專案經理整理週報")
    body = await _state(client, user, session_id)
    tickets = body["tickets"]
    assert isinstance(tickets, list)
    assert scripted.prompts == []
    assert body["hold_reason"] == "PAUSED_QUOTA_EXCEEDED"
    assert tickets[0]["status"] == "PAUSED_QUOTA_EXCEEDED"
    assert tickets[0]["locked_by_worker"] is None
    assert events[0][1]["text"] == "Token 額度已用盡，對話已暫停於 PAUSED_QUOTA_EXCEEDED。"


async def test_concurrent_ticket_quota_does_not_start_another_in_progress_ticket(
    client: httpx.AsyncClient,
    scripted: ScriptedGemma,
) -> None:
    user = await _login(client)
    async with get_session_factory()() as session:
        await session.execute(
            update(User).where(User.id == UUID(str(user["id"]))).values(max_concurrent_tickets=1)
        )
        session.add(
            TaskTicket(
                session_id=uuid4(),
                requester_user_id=UUID(str(user["id"])),
                assigned_role_code="PM",
                title="既有進行中工單",
                status="IN_PROGRESS",
                input_instructions="佔用配額",
                locked_by_worker="other-worker",
            )
        )
        await session.commit()
    session_id = await _open_session(client, user)
    events = await _send(client, user, session_id, DELEGATE_REQUEST)
    body = await _state(client, user, session_id)
    tickets = body["tickets"]
    assert isinstance(tickets, list)
    assert scripted.role_calls == 0
    assert body["hold_reason"] == "CONCURRENT_TICKET_QUOTA"
    assert {ticket["status"] for ticket in tickets} == {"PENDING"}
    assert events[-1][1]["text"] == "同時執行中的工單已達個人上限，工作區已休眠。"


async def test_bootstrap_restores_the_session_after_relogin(
    client: httpx.AsyncClient,
    scripted: ScriptedGemma,
) -> None:
    user = await _login(client)
    session_id = await _open_session(client, user)
    await _send(client, user, session_id, DELEGATE_REQUEST)
    boot = await client.get("/api/v1/users/me/bootstrap", headers=_headers(user))
    assert boot.status_code == 200
    payload = boot.json()
    assert session_id in [item["id"] for item in payload["sessions"]]
    body = await _state(client, user, session_id)
    messages = body["messages"]
    assert isinstance(messages, list)
    assert any(message["event_type"] == "user_message" and message["content"] == DELEGATE_REQUEST for message in messages)
    tickets = body["tickets"]
    assert isinstance(tickets, list)
    pm = next(ticket for ticket in tickets if ticket["assigned_role_code"] == "PM")
    assert pm["status"] == "COMPLETED"
    artifacts = body["artifacts"]
    assert isinstance(artifacts, list)
    assert any(artifact["producer_role"] == "PM" for artifact in artifacts)
    dag_steps = body["dag_steps"]
    assert isinstance(dag_steps, list)
    assert dag_steps[-1]["status"] == "COMPLETED"
    assert dag_steps[-1]["target_role_code"] == "PM"


async def test_direct_answer_skips_delegation(client: httpx.AsyncClient, scripted: ScriptedGemma) -> None:
    scripted.mode = "direct"
    user = await _login(client)
    session_id = await _open_session(client, user)
    events = await _send(client, user, session_id, "現在幾點")
    body = await _state(client, user, session_id)
    assert [name for name, _payload in events] == ["orchestrator_plan", "final_response"]
    assert events[-1][1]["text"] == "企業採本地模型，不提供即時時鐘。"
    assert body["tickets"] == []
    assert body["status"] == "COMPLETED"


async def test_cyclic_plan_is_rejected(client: httpx.AsyncClient, scripted: ScriptedGemma) -> None:
    scripted.mode = "cycle"
    user = await _login(client)
    session_id = await _open_session(client, user)
    events = await _send(client, user, session_id, "循環依賴")
    body = await _state(client, user, session_id)
    assert scripted.role_calls == 0
    assert events[-1][1]["text"] == "任務圖含有循環依賴或無效步驟，已中止。"
    assert body["status"] == "FAILED"


async def test_turn_continues_after_the_browser_disconnects(
    client: httpx.AsyncClient,
    scripted: ScriptedGemma,
) -> None:
    scripted.mode = "delegate"
    scripted.pause_pm = True
    user = await _login(client)
    session_id = await _open_session(client, user)

    async def consume() -> None:
        async with client.stream(
            "POST",
            f"/api/v1/chat/sessions/{session_id}/stream",
            headers=_headers(user),
            json={"message": DELEGATE_REQUEST},
        ) as response:
            async for _line in response.aiter_lines():
                if scripted.pm_entered.is_set():
                    return

    consumer = asyncio.create_task(consume())
    await asyncio.wait_for(scripted.pm_entered.wait(), 5)
    consumer.cancel()
    with contextlib.suppress(asyncio.CancelledError, Exception):
        await consumer
    scripted.release_pm.set()
    pm: dict[str, object] | None = None
    for _ in range(100):
        body = await _state(client, user, session_id)
        tickets = body["tickets"]
        assert isinstance(tickets, list)
        pm = next((ticket for ticket in tickets if ticket["assigned_role_code"] == "PM"), None)
        if pm is not None and pm["status"] == "COMPLETED":
            break
        await asyncio.sleep(0.05)
    else:
        raise AssertionError("background turn stopped when the browser disconnected")
    assert pm is not None
    assert pm["status"] == "COMPLETED"


async def test_another_user_cannot_read_the_session(
    client: httpx.AsyncClient,
    scripted: ScriptedGemma,
) -> None:
    scripted.mode = "direct"
    user = await _login(client)
    session_id = await _open_session(client, user)
    await _send(client, user, session_id, "現在幾點")
    other = await _login(client)
    response = await client.get(f"/api/v1/chat/sessions/{session_id}/state", headers=_headers(other))
    assert response.status_code == 404


async def test_org_chart_lists_role_history_tokens_and_skills(
    client: httpx.AsyncClient,
    scripted: ScriptedGemma,
) -> None:
    user = await _login(client)
    session_id = await _open_session(client, user)
    await _send(client, user, session_id, DELEGATE_REQUEST)
    response = await client.get("/api/v1/org/roles", headers=_headers(user))
    assert response.status_code == 200
    roles = {role["code"]: role for role in response.json()}
    assert roles["ORCH"]["reports_to_code"] is None
    assert roles["PM"]["reports_to_code"] == "CEO"
    assert roles["SA"]["reports_to_code"] == "PM"
    assert roles["PM"]["skill_count"] == len(roles["PM"]["skills"])
    assert roles["PM"]["skill_count"] > 0
    assert any(ticket["title"] == "彙整交付" for ticket in roles["PM"]["tickets"])
    assert roles["PM"]["tickets"][0]["token_budget"] == 16000
