"""Local MCP Daemon: pairing, reverse-RPC routing, and the daemon's own request handler.

Public seams:
- POST/GET/DELETE /api/v1/daemon/pairings and authenticate_daemon
- WebSocketReverseRPCManager.register_daemon / call_browser_tool
- packages/local-mcp-daemon/daemon.py LocalDaemon.handle
"""

import asyncio
import hashlib
import importlib.util
import sys
from collections.abc import AsyncIterator
from pathlib import Path
from types import ModuleType
from uuid import UUID, uuid4

import httpx
import pytest
from fakeredis import FakeAsyncRedis, FakeServer
from sqlalchemy import select

from app.api.ws_local_daemon import authenticate_daemon
from app.db.models import LocalDaemonPairing, LocalWorkspaceMount, ToolRegistry, User, UserToolPreference
from app.db.seed_runner import SeedRunner
from app.db.session import database_session, get_session_factory
from app.llm.embedding_client import EmbeddingClient
from app.main import app
from app.tool_bus.bus import UnifiedToolBus
from app.tool_bus.ws_rpc_manager import WebSocketReverseRPCManager, ws_rpc_manager

_DAEMON_FILE = Path(__file__).resolve().parents[3] / "packages" / "local-mcp-daemon" / "daemon.py"


def _load_daemon() -> ModuleType:
    spec = importlib.util.spec_from_file_location("local_mcp_daemon", _DAEMON_FILE)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["local_mcp_daemon"] = module
    spec.loader.exec_module(module)
    return module


class AnsweringSocket:
    def __init__(self, manager: WebSocketReverseRPCManager, result: dict[str, object]) -> None:
        self.manager = manager
        self.result = result
        self.sent: list[dict[str, object]] = []
        self.closed_with: int | None = None

    async def accept(self) -> None:
        return None

    async def close(self, code: int = 1000) -> None:
        self.closed_with = code

    async def send_json(self, data: dict[str, object]) -> None:
        self.sent.append(data)
        if "id" in data:
            self.manager.resolve_rpc_response(str(data["id"]), self.result)


@pytest.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    async with get_session_factory()() as session:
        await SeedRunner(session, EmbeddingClient()).run()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as http:
        yield http


@pytest.fixture(autouse=True)
async def _close_rpc_workers() -> AsyncIterator[None]:
    yield
    await ws_rpc_manager.aclose()


async def _user() -> str:
    async with database_session() as db:
        row = User(email=f"daemon-{uuid4().hex}@example.com", display_name="本機", department="RD")
        db.add(row)
        await db.flush()
        await db.refresh(row)
        return str(row.id)


def _headers(user_id: str) -> dict[str, str]:
    return {"X-User-Id": user_id}


async def _pair(client: httpx.AsyncClient, user_id: str, label: str = "我的筆電") -> dict[str, str]:
    response = await client.post("/api/v1/daemon/pairings", headers=_headers(user_id), json={"label": label})
    assert response.status_code == 201
    body: dict[str, str] = response.json()
    return body


async def test_pairing_returns_the_token_once_and_stores_only_its_hash(client: httpx.AsyncClient) -> None:
    user_id = await _user()
    paired = await _pair(client, user_id)

    token = paired["token"]
    assert len(token) >= 32
    assert token in paired["command"]
    async with database_session() as db:
        row = await db.get(LocalDaemonPairing, UUID(paired["id"]))
        assert row is not None
        assert row.token_sha256 == hashlib.sha256(token.encode()).hexdigest()
        mount = await db.get(LocalWorkspaceMount, row.mount_id)
        assert mount is not None
        assert mount.provider_type == "LOCAL_MCP_DAEMON"
        assert mount.browser_handle_key == f"daemon:{row.id}"
    listed = await client.get("/api/v1/daemon/pairings", headers=_headers(user_id))
    assert [(item["label"], "token" in item) for item in listed.json()] == [("我的筆電", False)]
    other = await client.get("/api/v1/daemon/pairings", headers=_headers(await _user()))
    assert other.json() == []

    assert await authenticate_daemon(token) == (UUID(user_id), UUID(paired["id"]))
    assert await authenticate_daemon("not-a-token") is None
    revoked = await client.delete(f"/api/v1/daemon/pairings/{paired['id']}", headers=_headers(user_id))
    assert revoked.status_code == 204
    assert await authenticate_daemon(token) is None
    async with database_session() as db:
        left = await db.scalar(select(LocalWorkspaceMount).where(LocalWorkspaceMount.user_id == UUID(user_id)))
    assert left is None


async def test_daemon_mount_reads_reach_the_daemon_without_a_browser(client: httpx.AsyncClient) -> None:
    user_id = await _user()
    async with database_session() as db:
        tool = await db.scalar(select(ToolRegistry).where(ToolRegistry.code == "workspace_read_file"))
        assert tool is not None
        db.add(UserToolPreference(user_id=UUID(user_id), tool_id=tool.id, is_enabled=True))
    paired = await _pair(client, user_id)
    daemon = AnsweringSocket(ws_rpc_manager, {"encoding": "utf-8", "content": "會議紀錄", "size": 4})
    await ws_rpc_manager.register_daemon(user_id, paired["id"], daemon)

    results = await UnifiedToolBus().dispatch(
        role_code="PM",
        user_id=UUID(user_id),
        session_id=uuid4(),
        calls=[("workspace_read_file", {"path": "notes.md"})],
    )

    assert results[0].ok, results[0].error
    assert results[0].output["markdown"] == "會議紀錄"
    assert daemon.sent[0]["method"] == "CLIENT_FS_READ"
    assert daemon.sent[0]["params"]["browser_handle_key"] == f"daemon:{paired['id']}"  # type: ignore[index]


async def test_each_pairing_has_its_own_route_and_revoking_disconnects_it(client: httpx.AsyncClient) -> None:
    user_id = await _user()
    laptop = await _pair(client, user_id, "筆電")
    desktop = await _pair(client, user_id, "桌機")
    laptop_socket = AnsweringSocket(ws_rpc_manager, {"from": "筆電"})
    desktop_socket = AnsweringSocket(ws_rpc_manager, {"from": "桌機"})
    await ws_rpc_manager.register_daemon(user_id, laptop["id"], laptop_socket)
    await ws_rpc_manager.register_daemon(user_id, desktop["id"], desktop_socket)

    async def read(pairing_id: str) -> dict[str, object]:
        return await ws_rpc_manager.call_browser_tool(
            requester_user_id=user_id,
            mount_owner_user_id=user_id,
            session_id=str(uuid4()),
            method="CLIENT_FS_READ",
            params={"browser_handle_key": f"daemon:{pairing_id}", "file_path": "notes.md"},
            timeout=1,
        )

    assert await read(laptop["id"]) == {"status": "SUCCESS", "data": {"from": "筆電"}}
    assert await read(desktop["id"]) == {"status": "SUCCESS", "data": {"from": "桌機"}}

    revoked = await client.delete(f"/api/v1/daemon/pairings/{laptop['id']}", headers=_headers(user_id))
    assert revoked.status_code == 204
    assert laptop_socket.closed_with == 1008
    assert desktop_socket.closed_with is None
    assert (await read(laptop["id"]))["status"] == "BROWSER_OFFLINE"
    assert len(laptop_socket.sent) == 1


async def test_revoking_closes_a_daemon_held_by_another_worker() -> None:
    user_id = str(uuid4())
    pairing_id = str(uuid4())
    server = FakeServer()

    def redis_factory() -> FakeAsyncRedis:
        return FakeAsyncRedis(server=server, decode_responses=True)

    holder = WebSocketReverseRPCManager(worker_id=f"holder-{uuid4().hex}", redis_factory=redis_factory)
    revoker = WebSocketReverseRPCManager(worker_id=f"revoker-{uuid4().hex}", redis_factory=redis_factory)
    daemon = AnsweringSocket(holder, {})
    try:
        await holder.register_daemon(user_id, pairing_id, daemon)
        await revoker.start()
        await revoker.close_daemon(user_id, pairing_id)
        for _ in range(50):
            if daemon.closed_with is not None:
                break
            await asyncio.sleep(0.02)
    finally:
        await holder.aclose()
        await revoker.aclose()

    assert daemon.closed_with == 1008


async def test_cli_goes_only_to_the_daemon_and_never_to_another_users_daemon() -> None:
    owner = await _user()
    intruder = await _user()
    session_id = str(uuid4())
    pairing_id = str(uuid4())
    handle = {"browser_handle_key": f"daemon:{pairing_id}", "command": "git status"}
    browser = AnsweringSocket(ws_rpc_manager, {"exit_code": 0})
    await ws_rpc_manager.register_connection(owner, session_id, browser)

    offline = await ws_rpc_manager.call_browser_tool(
        requester_user_id=owner,
        mount_owner_user_id=owner,
        session_id=session_id,
        method="DAEMON_EXEC_CLI",
        params={"command": "git status"},
        timeout=1,
    )
    assert offline["status"] == "BROWSER_OFFLINE"
    assert "Daemon" in str(offline["error"])
    assert browser.sent == []

    daemon = AnsweringSocket(ws_rpc_manager, {"exit_code": 0, "stdout": "clean", "stderr": ""})
    await ws_rpc_manager.register_daemon(owner, pairing_id, daemon)
    ran = await ws_rpc_manager.call_browser_tool(
        requester_user_id=owner,
        mount_owner_user_id=owner,
        session_id=session_id,
        method="DAEMON_EXEC_CLI",
        params=handle,
        timeout=1,
    )
    assert ran == {"status": "SUCCESS", "data": {"exit_code": 0, "stdout": "clean", "stderr": ""}}

    intruder_call = await ws_rpc_manager.call_browser_tool(
        requester_user_id=intruder,
        mount_owner_user_id=intruder,
        session_id=session_id,
        method="DAEMON_EXEC_CLI",
        params=handle,
        timeout=1,
    )
    assert intruder_call["status"] == "BROWSER_OFFLINE"
    with pytest.raises(PermissionError, match="ERR_LOCAL_MOUNT_MUST_BE_PRIVATE"):
        await ws_rpc_manager.call_browser_tool(
            requester_user_id=intruder,
            mount_owner_user_id=owner,
            session_id=session_id,
            method="CLIENT_FS_READ",
            params={"browser_handle_key": f"daemon:{pairing_id}", "file_path": "notes.md"},
        )
    assert len(daemon.sent) == 1


async def test_a_daemon_on_another_worker_receives_the_forwarded_call() -> None:
    user_id = str(uuid4())
    pairing_id = str(uuid4())
    server = FakeServer()

    def redis_factory() -> FakeAsyncRedis:
        return FakeAsyncRedis(server=server, decode_responses=True)

    holder = WebSocketReverseRPCManager(worker_id=f"holder-{uuid4().hex}", redis_factory=redis_factory)
    caller = WebSocketReverseRPCManager(worker_id=f"caller-{uuid4().hex}", redis_factory=redis_factory)

    class Relaying(AnsweringSocket):
        async def send_json(self, data: dict[str, object]) -> None:
            self.sent.append(data)
            asyncio.get_running_loop().create_task(
                holder.handle_client_message(user_id, "daemon", {"id": data["id"], "result": self.result})
            )

    daemon = Relaying(holder, {"exit_code": 0, "stdout": "ok", "stderr": ""})
    try:
        await holder.register_daemon(user_id, pairing_id, daemon)
        result = await caller.call_browser_tool(
            requester_user_id=user_id,
            mount_owner_user_id=user_id,
            session_id=str(uuid4()),
            method="DAEMON_EXEC_CLI",
            params={"browser_handle_key": f"daemon:{pairing_id}", "command": "git status"},
            timeout=3,
        )
    finally:
        await holder.aclose()
        await caller.aclose()

    assert result["status"] == "SUCCESS"
    assert daemon.sent[0]["method"] == "DAEMON_EXEC_CLI"


async def test_daemon_handler_reads_lists_and_writes_inside_its_root(tmp_path: Path) -> None:
    module = _load_daemon()
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "spec.md").write_text("# 規格", encoding="utf-8")
    daemon = module.LocalDaemon(tmp_path)

    listed = await daemon.handle("CLIENT_FS_LIST", {"file_path": "docs"})
    assert listed["entries"] == [{"name": "spec.md", "kind": "file"}]
    read = await daemon.handle("CLIENT_FS_READ", {"file_path": "docs/spec.md"})
    assert read == {"encoding": "utf-8", "content": "# 規格", "size": len("# 規格".encode())}
    written = await daemon.handle("CLIENT_FS_WRITE", {"file_path": "docs/new.md", "content": "新內容"})
    assert written["written"] is True
    assert (tmp_path / "docs" / "new.md").read_text(encoding="utf-8") == "新內容"


def test_daemon_refuses_the_same_sensitive_files_as_the_server() -> None:
    from app.tool_bus import local_path_policy

    assert _load_daemon()._SENSITIVE_FILE.pattern == local_path_policy._SENSITIVE_FILE.pattern


@pytest.mark.parametrize("path", ["../outside.md", ".env", "repo/.git/config", "keys/id_rsa", "C:/Windows/win.ini"])
async def test_daemon_handler_refuses_escaping_and_sensitive_paths(tmp_path: Path, path: str) -> None:
    module = _load_daemon()
    daemon = module.LocalDaemon(tmp_path)
    with pytest.raises(PermissionError):
        await daemon.handle("CLIENT_FS_READ", {"file_path": path})


async def test_daemon_cli_runs_without_a_shell_in_the_root_and_times_out(tmp_path: Path) -> None:
    module = _load_daemon()
    daemon = module.LocalDaemon(tmp_path)
    python = sys.executable.replace("\\", "/")

    ran = await daemon.handle("DAEMON_EXEC_CLI", {"command": f'"{python}" -c "import os; print(os.getcwd())"'})
    assert ran["exit_code"] == 0
    assert Path(ran["stdout"].strip()).resolve() == tmp_path.resolve()

    piped = await daemon.handle("DAEMON_EXEC_CLI", {"command": f'"{python}" -c "print(1)" && echo pwned'})
    assert "pwned" not in piped["stdout"]

    slow = await daemon.handle(
        "DAEMON_EXEC_CLI", {"command": f'"{python}" -c "import time; time.sleep(5)"', "timeout": 0.5}
    )
    assert slow["exit_code"] == -1
    assert "逾時" in slow["stderr"]


@pytest.mark.parametrize(
    "command",
    [
        "cat ../outside.md",
        "type C:/Windows/win.ini",
        "git show --output=/etc/passwd",
        "cat .env",
        "git diff repo/.git/config",
        "shutdown -h now",
        "rm -rf /",
    ],
)
async def test_daemon_cli_refuses_blacklisted_commands_and_paths_outside_its_root(
    tmp_path: Path, command: str
) -> None:
    module = _load_daemon()
    daemon = module.LocalDaemon(tmp_path)
    with pytest.raises(PermissionError):
        await daemon.handle("DAEMON_EXEC_CLI", {"command": command})
