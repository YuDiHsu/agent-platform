"""Browser local folder bridge: reverse RPC, office parsing, and confirmed writes.

Public seams:
- WebSocketReverseRPCManager.call_browser_tool
- UnifiedToolBus workspace_read_file / workspace_write_file
- POST /api/v1/mounts/register and bootstrap local_workspace_mounts
- WS /api/v1/ws/client-tools/{session_id}
"""

import asyncio
import base64
import inspect
import zipfile
from collections.abc import AsyncIterator
from io import BytesIO
from uuid import UUID, uuid4

import httpx
import pytest
from openpyxl import Workbook
from sqlalchemy import select

from app.api.deps import get_llm
from app.db.models import AgentMemory, LocalWorkspaceMount, SecurityAuditLog, User
from app.db.seed_runner import SeedRunner
from app.db.session import database_session, database_session_depth, get_session_factory
from app.llm.embedding_client import EmbeddingClient
from app.main import app
from app.orchestrator.runtime import drain_background
from app.orchestrator.state import (
    DAGTaskNode,
    OrchestratorPlanOutput,
    SubAgentExecutionOutput,
    SubAgentToolCall,
)
from fakeredis import FakeAsyncRedis, FakeServer

from app.tool_bus.bus import UnifiedToolBus
from app.tool_bus.ws_rpc_manager import WebSocketReverseRPCManager, ws_rpc_manager


class FakeSocket:
    def __init__(self, result: dict[str, object] | None = None) -> None:
        self.sent: list[dict[str, object]] = []
        self.result = result or {"encoding": "utf-8", "content": "plain", "size": 5}
        self.depths: list[int] = []

    async def accept(self) -> None:
        return None

    async def send_json(self, data: dict[str, object]) -> None:
        self.depths.append(database_session_depth())
        self.sent.append(data)
        if data.get("method") == "CLIENT_FS_READ":
            ws_rpc_manager.resolve_rpc_response(str(data["id"]), self.result)
        elif data.get("method") == "CLIENT_FS_WRITE":
            ws_rpc_manager.resolve_rpc_response(str(data["id"]), {"written": True})


class _QuietModel:
    async def generate_structured(
        self,
        system_prompt: str,
        messages: list[dict[str, object]],
        response_model: type[object],
        model_name: str = "gemma-4-27b-it",
        temperature: float = 0.15,
    ) -> object:
        del system_prompt, model_name, temperature
        text = "\n".join(str(message.get("content", "")) for message in messages)
        if response_model is OrchestratorPlanOutput:
            return OrchestratorPlanOutput(
                intent_mode="DELEGATE_DAG",
                reasoning="要寫入本機規格",
                goal_statement="確認後才寫硬碟",
                dag_steps=[
                    DAGTaskNode(
                        step_id=1,
                        target_role_code="PM",
                        task_title="寫入規格",
                        detailed_instructions="寫入 api_spec.md",
                    )
                ],
            )
        if "使用者已核准" in text:
            return SubAgentExecutionOutput(
                execution_status="COMPLETED",
                thought_process="使用者已確認寫入",
                tool_calls=[],
                artifact_title="本機規格",
                artifact_type="REQUIREMENT_SPEC",
                summary_200_words="摘" * 200,
                full_markdown_content="# 規格\n",
                handoff_notes_for_next_role="已寫入",
            )
        return SubAgentExecutionOutput(
            execution_status="NEED_TOOL_CALL",
            thought_process="先請使用者確認差異",
            tool_calls=[
                SubAgentToolCall(
                    tool_name="workspace_write_file",
                    arguments={"path": "api_spec.md", "content": "# API\n\n新規格"},
                )
            ],
        )


@pytest.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    async with get_session_factory()() as session:
        await SeedRunner(session, EmbeddingClient()).run()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http:
        yield http
    await drain_background()
    await ws_rpc_manager.aclose()


@pytest.fixture(autouse=True)
async def _close_rpc_workers() -> AsyncIterator[None]:
    yield
    await ws_rpc_manager.aclose()


async def _user(email: str) -> str:
    async with database_session() as db:
        row = User(email=email, display_name="本機使用者", department="RD")
        db.add(row)
        await db.flush()
        await db.refresh(row)
        return str(row.id)


async def _mount(user_id: str, handle: str = "local_mount_contract") -> None:
    async with database_session() as db:
        db.add(
            LocalWorkspaceMount(
                user_id=UUID(user_id),
                mount_alias="合約",
                browser_handle_key=handle,
            )
        )


def _docx(text: str) -> bytes:
    document = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f'<w:body><w:p><w:r><w:t xml:space="preserve">{text}</w:t></w:r></w:p></w:body>'
        "</w:document>"
    )
    content_types = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/word/document.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
        "</Types>"
    )
    rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
        'Target="word/document.xml"/>'
        "</Relationships>"
    )
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("[Content_Types].xml", content_types)
        archive.writestr("_rels/.rels", rels)
        archive.writestr("word/document.xml", document)
    return buffer.getvalue()


def _xlsx(cell: str) -> bytes:
    book = Workbook()
    sheet = book.active
    assert sheet is not None
    sheet["A1"] = cell
    buffer = BytesIO()
    book.save(buffer)
    return buffer.getvalue()


def _pdf(text: str) -> bytes:
    stream = f"BT /F1 12 Tf 72 100 Td ({text}) Tj ET".encode("ascii")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 144] /Contents 4 0 R "
        b"/Resources << /Font << /F1 5 0 R >> >> >>",
        f"<< /Length {len(stream)} >>\nstream\n".encode("ascii") + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    output = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for index, body in enumerate(objects, start=1):
        offsets.append(len(output))
        output += f"{index} 0 obj\n".encode("ascii") + body + b"\nendobj\n"
    xref = len(output)
    output += f"xref\n0 {len(objects) + 1}\n".encode("ascii")
    output += b"0000000000 65535 f \n"
    for offset in offsets[1:]:
        output += f"{offset:010d} 00000 n \n".encode("ascii")
    output += (
        f"trailer << /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF".encode("ascii")
    )
    return bytes(output)


async def _enable(client: httpx.AsyncClient, headers: dict[str, str], code: str) -> None:
    response = await client.put(
        "/api/v1/users/me/tool-preferences",
        headers=headers,
        json={"code": code, "is_enabled": True},
    )
    assert response.status_code == 204


async def _read(user_id: str, session_id: str, path: str, payload: dict[str, object]) -> dict[str, object]:
    socket = FakeSocket(payload)
    await ws_rpc_manager.register_connection(user_id, session_id, socket)
    results = await UnifiedToolBus().dispatch(
        role_code="PM",
        user_id=UUID(user_id),
        session_id=UUID(session_id),
        calls=[("workspace_read_file", {"path": path})],
    )
    assert socket.depths == [0]
    assert results[0].ok, results[0].error
    return results[0].output


async def test_reverse_rpc_default_timeout_is_thirty_seconds() -> None:
    default = inspect.signature(WebSocketReverseRPCManager.call_browser_tool).parameters["timeout"].default
    assert default == 30.0


async def test_offline_browser_returns_browser_offline_without_waiting() -> None:
    user_id = str(uuid4())
    result = await ws_rpc_manager.call_browser_tool(
        requester_user_id=user_id,
        mount_owner_user_id=user_id,
        session_id=str(uuid4()),
        method="CLIENT_FS_READ",
        params={"file_path": "notes.md"},
        timeout=30,
    )
    assert result["status"] == "BROWSER_OFFLINE"
    assert "瀏覽器" in str(result["error"])


async def test_browser_timeout_returns_timeout_status() -> None:
    user_id = str(uuid4())
    session_id = str(uuid4())

    class Silent(FakeSocket):
        async def send_json(self, data: dict[str, object]) -> None:
            self.sent.append(data)

    await ws_rpc_manager.register_connection(user_id, session_id, Silent())
    result = await ws_rpc_manager.call_browser_tool(
        requester_user_id=user_id,
        mount_owner_user_id=user_id,
        session_id=session_id,
        method="CLIENT_FS_READ",
        params={"file_path": "notes.md"},
        timeout=0.05,
    )
    assert result == {"status": "TIMEOUT", "error": "瀏覽器本機檔案操作逾時 (0.05s)"}


async def test_cross_worker_pubsub_delivers_the_read_to_the_socket_owner() -> None:
    user_id = str(uuid4())
    session_id = str(uuid4())
    holder_id = f"holder-{uuid4().hex}"
    caller_id = f"caller-{uuid4().hex}"
    server = FakeServer()

    def redis_factory() -> FakeAsyncRedis:
        return FakeAsyncRedis(server=server, decode_responses=True)

    holder = WebSocketReverseRPCManager(worker_id=holder_id, redis_factory=redis_factory)
    caller = WebSocketReverseRPCManager(worker_id=caller_id, redis_factory=redis_factory)
    socket = FakeSocket({"encoding": "utf-8", "content": "合約正文", "size": 4})

    async def answer() -> None:
        for _ in range(100):
            if socket.sent:
                message = socket.sent[0]
                await holder.handle_client_message(
                    user_id,
                    session_id,
                    {"jsonrpc": "2.0", "id": message["id"], "result": {"encoding": "utf-8", "content": "合約正文"}},
                )
                return
            await asyncio.sleep(0.02)
        raise AssertionError("holding worker never received the read")

    try:
        await holder.register_connection(user_id, session_id, socket)
        waiter = asyncio.create_task(answer())
        result = await caller.call_browser_tool(
            requester_user_id=user_id,
            mount_owner_user_id=user_id,
            session_id=session_id,
            method="CLIENT_FS_READ",
            params={"browser_handle_key": "local_mount_contract", "file_path": "notes.md"},
            timeout=3,
        )
        await waiter
    finally:
        await holder.aclose()
        await caller.aclose()

    assert result["status"] == "SUCCESS"
    assert result["data"]["content"] == "合約正文"
    assert socket.sent[0]["method"] == "CLIENT_FS_READ"


async def test_cross_user_mount_is_audited_and_rejected() -> None:
    owner = await _user(f"owner-{uuid4().hex}@hub.local")
    intruder = await _user(f"intruder-{uuid4().hex}@hub.local")
    with pytest.raises(PermissionError, match="ERR_LOCAL_MOUNT_MUST_BE_PRIVATE"):
        await ws_rpc_manager.call_browser_tool(
            requester_user_id=intruder,
            mount_owner_user_id=owner,
            session_id=str(uuid4()),
            method="CLIENT_FS_READ",
            params={"file_path": "secret.md"},
        )
    async with database_session() as db:
        row = await db.scalar(select(SecurityAuditLog).where(SecurityAuditLog.actor_user_id == UUID(intruder)))
        assert row is not None
        assert row.event_code == "ERR_LOCAL_MOUNT_MUST_BE_PRIVATE"
        assert row.target_user_id == UUID(owner)


@pytest.mark.parametrize(
    ("path", "event_code"),
    [
        ("../secret.md", "PATH_TRAVERSAL"),
        ("notes/../../.env", "PATH_TRAVERSAL"),
        (".env", "SENSITIVE_FILE"),
        ("config/.env.local", "SENSITIVE_FILE"),
        ("keys/id_rsa", "SENSITIVE_FILE"),
        ("cert.pem", "SENSITIVE_FILE"),
        ("cert.pfx", "SENSITIVE_FILE"),
        (".git/config", "SENSITIVE_FILE"),
        ("node_modules/leftpad/index.js", "SENSITIVE_FILE"),
    ],
)
async def test_server_rejects_traversal_and_sensitive_paths(path: str, event_code: str) -> None:
    user_id = await _user(f"path-{uuid4().hex}@hub.local")
    session_id = str(uuid4())
    socket = FakeSocket()
    await ws_rpc_manager.register_connection(user_id, session_id, socket)
    with pytest.raises(PermissionError, match="Security Violation"):
        await ws_rpc_manager.call_browser_tool(
            requester_user_id=user_id,
            mount_owner_user_id=user_id,
            session_id=session_id,
            method="CLIENT_FS_READ",
            params={"file_path": path},
        )
    assert socket.sent == []
    async with database_session() as db:
        row = await db.scalar(
            select(SecurityAuditLog).where(
                SecurityAuditLog.actor_user_id == UUID(user_id),
                SecurityAuditLog.resource == path,
            )
        )
        assert row is not None
        assert row.event_code == event_code


async def test_office_files_become_markdown_and_long_docx_is_chunked(client: httpx.AsyncClient) -> None:
    login = await client.post(
        "/api/v1/users/dev-login",
        json={"email": f"docs-{uuid4().hex}@hub.local", "display_name": "文件", "department": "RD"},
    )
    user_id = login.json()["id"]
    headers = {"X-User-Id": user_id}
    await _enable(client, headers, "workspace_read_file")
    await _mount(user_id)
    session_id = str(uuid4())

    docx = await _read(
        user_id,
        session_id,
        "合約.docx",
        {"encoding": "base64", "content": base64.b64encode(_docx("合約罰則")).decode("ascii"), "size": 12},
    )
    assert "合約罰則" in str(docx["markdown"])
    assert docx["chunked"] is False

    sheet = await _read(
        user_id,
        session_id,
        "營收.xlsx",
        {"encoding": "base64", "content": base64.b64encode(_xlsx("營收")).decode("ascii"), "size": 20},
    )
    assert "營收" in str(sheet["markdown"])

    pdf = await _read(
        user_id,
        session_id,
        "memo.pdf",
        {"encoding": "base64", "content": base64.b64encode(_pdf("HelloPDF")).decode("ascii"), "size": 40},
    )
    assert "HelloPDF" in str(pdf["markdown"])

    long_text = "甲" * 12_004
    long_doc = await _read(
        user_id,
        session_id,
        "長文件.docx",
        {"encoding": "base64", "content": base64.b64encode(_docx(long_text)).decode("ascii"), "size": len(long_text)},
    )
    assert long_doc["chunked"] is True
    assert str(long_doc["markdown"]).count("甲") >= 12_004
    async with database_session() as db:
        rows = (
            await db.scalars(
                select(AgentMemory)
                .where(
                    AgentMemory.owner_user_id == UUID(user_id),
                    AgentMemory.memory_scope == "EPHEMERAL_LOCAL_FILE",
                )
                .order_by(AgentMemory.source_reference)
            )
        ).all()
        chunks = [row.content for row in rows]
    assert len(chunks) >= 2
    assert "".join(chunks) == long_doc["markdown"]
    assert all(len(chunk) <= 12_000 for chunk in chunks)


async def test_write_waits_for_hitl_and_only_then_asks_the_browser(client: httpx.AsyncClient) -> None:
    model = _QuietModel()
    app.dependency_overrides[get_llm] = lambda: model
    try:
        login = await client.post(
            "/api/v1/users/dev-login",
            json={"email": f"write-{uuid4().hex}@hub.local", "display_name": "寫入", "department": "RD"},
        )
        user_id = login.json()["id"]
        headers = {"X-User-Id": user_id}
        await _enable(client, headers, "workspace_write_file")
        await _mount(user_id)
        opened = await client.post("/api/v1/chat/sessions", headers=headers)
        session_id = opened.json()["id"]
        socket = FakeSocket()
        await ws_rpc_manager.register_connection(user_id, session_id, socket)

        streamed = await client.post(
            f"/api/v1/chat/sessions/{session_id}/stream",
            headers=headers,
            json={"message": "請寫入本機規格"},
        )
        assert streamed.status_code == 200
        state = await client.get(f"/api/v1/chat/sessions/{session_id}/state", headers=headers)
        body = state.json()
        assert body["hold_reason"] == "WAITING_HITL"
        pending = body["pending_hitl"]
        assert pending[0]["tool_name"] == "workspace_write_file"
        assert pending[0]["execution_target"] == "BROWSER_WS_RPC"
        assert pending[0]["proposed_payload"]["content"] == "# API\n\n新規格"
        assert socket.sent == []

        decided = await client.post(
            f"/api/v1/hitl/{pending[0]['hitl_request_id']}/decide",
            headers=headers,
            json={"status": "APPROVED"},
        )
        assert decided.status_code == 200, decided.text
        assert socket.sent[0]["method"] == "CLIENT_FS_WRITE"
        params = socket.sent[0]["params"]
        assert isinstance(params, dict)
        assert params["file_path"] == "api_spec.md"
        assert params["content"] == "# API\n\n新規格"
        assert socket.depths == [0]
    finally:
        app.dependency_overrides.pop(get_llm, None)
        await drain_background()


async def test_bootstrap_returns_only_the_callers_local_mounts(client: httpx.AsyncClient) -> None:
    first = await client.post(
        "/api/v1/users/dev-login",
        json={"email": f"mount-a-{uuid4().hex}@hub.local", "display_name": "甲", "department": "RD"},
    )
    second = await client.post(
        "/api/v1/users/dev-login",
        json={"email": f"mount-b-{uuid4().hex}@hub.local", "display_name": "乙", "department": "RD"},
    )
    headers = {"X-User-Id": first.json()["id"]}
    created = await client.post(
        "/api/v1/mounts/register",
        headers=headers,
        json={
            "mount_alias": "合約資料夾",
            "browser_handle_key": "local_mount_alpha",
            "file_tree": [{"path": "api_spec.md", "size": 12}],
        },
    )
    assert created.status_code == 201
    boot = await client.get("/api/v1/users/me/bootstrap", headers=headers)
    mounts = boot.json()["local_workspace_mounts"]
    assert mounts[0]["browser_handle_key"] == "local_mount_alpha"
    assert mounts[0]["mount_alias"] == "合約資料夾"
    other = await client.get(
        "/api/v1/users/me/bootstrap",
        headers={"X-User-Id": second.json()["id"]},
    )
    assert other.json()["local_workspace_mounts"] == []

    denied = await client.post(
        "/api/v1/mounts/register",
        headers=headers,
        json={
            "mount_alias": "壞掉",
            "browser_handle_key": "local_mount_bad",
            "file_tree": [{"path": "../.env", "size": 1}],
        },
    )
    assert denied.status_code == 400
    assert "Security Violation" in denied.json()["detail"]
