"""Cross-worker browser reverse RPC. Implements: REQ-004, REQ-012, ADR-0002."""

from __future__ import annotations

import asyncio
import contextlib
import json
from collections.abc import Awaitable, Callable
from typing import Any, Protocol, cast
from uuid import uuid4

from redis.asyncio import Redis

from app.core.config import settings
from app.tool_bus.audit import record_security_audit
from app.tool_bus.local_path_policy import local_path_violation

_OWNERS = "ws-rpc:owners"
_OFFLINE = {
    "status": "BROWSER_OFFLINE",
    "error": "使用者的瀏覽器分頁未連線，請開啟平台網頁以授權存取本機資料夾。",
}
_DAEMON_OFFLINE = {
    "status": "BROWSER_OFFLINE",
    "error": "使用者的本機 Local MCP Daemon 未連線，請在電腦上啟動 Daemon。",
}
DAEMON_HANDLE_PREFIX = "daemon:"
_DAEMON_ONLY_METHODS = {"DAEMON_EXEC_CLI"}
_POLICY_VIOLATION = 1008


def _socket_field(user_id: str, session_id: str) -> str:
    return f"{user_id}:{session_id}"


def _daemon_field(user_id: str, pairing_id: str) -> str:
    return f"{DAEMON_HANDLE_PREFIX}{user_id}:{pairing_id}"


def _route(requester_user_id: str, session_id: str, method: str, params: dict[str, Any]) -> str | None:
    """The owners-hash field this call goes to; None when it needs a Daemon but names none."""

    handle = str(params.get("browser_handle_key") or "")
    if handle.startswith(DAEMON_HANDLE_PREFIX):
        return _daemon_field(requester_user_id, handle.removeprefix(DAEMON_HANDLE_PREFIX))
    if method in _DAEMON_ONLY_METHODS:
        return None
    return _socket_field(requester_user_id, session_id)


def _offline_for(field: str | None) -> dict[str, str]:
    return dict(_OFFLINE) if field and not field.startswith(DAEMON_HANDLE_PREFIX) else dict(_DAEMON_OFFLINE)


class BrowserSocket(Protocol):
    async def accept(self) -> None: ...

    async def send_json(self, data: Any) -> None: ...

    async def close(self, code: int = 1000) -> None: ...


class _Commands(Protocol):
    def hset(self, name: str, key: str, value: str) -> Awaitable[int]: ...

    def hget(self, name: str, key: str) -> Awaitable[str | None]: ...

    def hdel(self, name: str, key: str) -> Awaitable[int]: ...

    def publish(self, channel: str, message: str) -> Awaitable[int]: ...

    def pubsub(self) -> Any: ...

    def aclose(self) -> Awaitable[None]: ...


def _default_redis() -> _Commands:
    return cast(_Commands, Redis.from_url(settings.REDIS_URL, decode_responses=True))


class WebSocketReverseRPCManager:
    """Route CLIENT_FS_* calls to the worker holding the browser socket, and CLI or daemon mounts to the Daemon."""

    def __init__(
        self,
        worker_id: str | None = None,
        redis_factory: Callable[[], _Commands] | None = None,
    ) -> None:
        self.worker_id = worker_id or f"worker-{uuid4().hex}"
        self._redis_factory = redis_factory or _default_redis
        self._connections: dict[str, BrowserSocket] = {}
        self._pending: dict[str, asyncio.Future[Any]] = {}
        self._forwarded: dict[str, str] = {}
        self._commands: _Commands | None = None
        self._listener: asyncio.Task[None] | None = None
        self._ready = asyncio.Event()

    @property
    def inbox(self) -> str:
        return f"ws-rpc:inbox:{self.worker_id}"

    async def start(self) -> None:
        await self._ensure_listener()

    async def register_connection(self, user_id: str, session_id: str, websocket: BrowserSocket) -> None:
        await self._register(_socket_field(user_id, session_id), websocket)

    async def unregister_connection(self, user_id: str, session_id: str) -> None:
        await self._unregister(_socket_field(user_id, session_id))

    async def register_daemon(self, user_id: str, pairing_id: str, websocket: BrowserSocket) -> None:
        await self._register(_daemon_field(user_id, pairing_id), websocket)

    async def unregister_daemon(self, user_id: str, pairing_id: str, websocket: BrowserSocket) -> None:
        field = _daemon_field(user_id, pairing_id)
        if self._connections.get(field) is websocket:
            await self._unregister(field)

    async def close_daemon(self, user_id: str, pairing_id: str) -> None:
        """Disconnect a revoked pairing's Daemon on whichever worker holds it."""

        field = _daemon_field(user_id, pairing_id)
        if field in self._connections:
            await self._close_local(field)
            return
        owner = await self._commands_client().hget(_OWNERS, field)
        if owner and owner != self.worker_id:
            await self._publish(str(owner), {"kind": "close", "field": field})

    async def _close_local(self, field: str) -> None:
        socket = self._connections.get(field)
        await self._unregister(field)
        if socket is not None:
            with contextlib.suppress(Exception):
                await socket.close(code=_POLICY_VIOLATION)

    async def _register(self, field: str, websocket: BrowserSocket) -> None:
        await websocket.accept()
        self._connections[field] = websocket
        await self._ensure_listener()
        await self._commands_client().hset(_OWNERS, field, self.worker_id)

    async def _unregister(self, field: str) -> None:
        self._connections.pop(field, None)
        client = self._commands
        if client is None:
            return
        current = await client.hget(_OWNERS, field)
        if current == self.worker_id:
            await client.hdel(_OWNERS, field)

    async def call_browser_tool(
        self,
        requester_user_id: str,
        mount_owner_user_id: str,
        session_id: str,
        method: str,
        params: dict[str, Any],
        timeout: float = 30.0,
    ) -> dict[str, Any]:
        await self._reject_if_forbidden(
            requester_user_id=requester_user_id,
            mount_owner_user_id=mount_owner_user_id,
            session_id=session_id,
            method=method,
            params=params,
        )
        field = _route(requester_user_id, session_id, method, params)
        if field is None:
            return _offline_for(field)
        socket = self._connections.get(field)
        if socket is not None:
            return await self._wait_on(socket, method, params, timeout)

        await self._ensure_listener()
        owner = await self._commands_client().hget(_OWNERS, field)
        if not owner or owner == self.worker_id:
            return _offline_for(field)

        rpc_id = f"rpc_{uuid4().hex}"
        future: asyncio.Future[Any] = asyncio.get_running_loop().create_future()
        self._pending[rpc_id] = future
        await self._publish(
            str(owner),
            {
                "kind": "call",
                "rpc_id": rpc_id,
                "origin_worker": self.worker_id,
                "field": field,
                "method": method,
                "params": params,
            },
        )
        try:
            payload = await asyncio.wait_for(future, timeout)
        except TimeoutError:
            return _timeout(timeout)
        finally:
            self._pending.pop(rpc_id, None)
        return _wrap(payload)

    def resolve_rpc_response(self, rpc_id: str, payload: dict[str, Any]) -> None:
        future = self._pending.get(rpc_id)
        if future is not None and not future.done():
            future.set_result(payload)

    async def handle_client_message(self, user_id: str, session_id: str, message: dict[str, Any]) -> None:
        del user_id, session_id
        rpc_id = str(message.get("id", ""))
        if "error" in message:
            error = message["error"]
            text = error.get("message") if isinstance(error, dict) else str(error)
            payload: dict[str, Any] = {"status": "ERROR", "error": text}
        else:
            result = message.get("result", {})
            payload = result if isinstance(result, dict) else {"result": result}
        origin = self._forwarded.pop(rpc_id, None)
        if origin and origin != self.worker_id:
            await self._publish(origin, {"kind": "result", "rpc_id": rpc_id, "payload": payload})
            return
        self.resolve_rpc_response(rpc_id, payload)

    async def aclose(self) -> None:
        fields = list(self._connections)
        self._connections.clear()
        client = self._commands
        if client is not None:
            for field in fields:
                with contextlib.suppress(Exception):
                    current = await client.hget(_OWNERS, field)
                    if current == self.worker_id:
                        await client.hdel(_OWNERS, field)
        task = self._listener
        self._listener = None
        self._ready = asyncio.Event()
        if task is not None:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
        if client is not None:
            self._commands = None
            with contextlib.suppress(Exception):
                await client.aclose()
        self._pending.clear()
        self._forwarded.clear()

    async def _reject_if_forbidden(
        self,
        *,
        requester_user_id: str,
        mount_owner_user_id: str,
        session_id: str,
        method: str,
        params: dict[str, Any],
    ) -> None:
        if requester_user_id != mount_owner_user_id:
            await record_security_audit(
                actor_user_id=requester_user_id,
                target_user_id=mount_owner_user_id,
                event_code="ERR_LOCAL_MOUNT_MUST_BE_PRIVATE",
                resource=session_id,
                detail="禁止跨使用者存取本機掛載目錄",
            )
            raise PermissionError("ERR_LOCAL_MOUNT_MUST_BE_PRIVATE: 禁止跨使用者存取本機掛載目錄")
        file_path = str(params.get("file_path") or params.get("path") or "")
        violation = local_path_violation(file_path)
        if violation is None:
            return
        verb = "寫入" if method == "CLIENT_FS_WRITE" else "讀取"
        await record_security_audit(
            actor_user_id=requester_user_id,
            event_code=violation,
            resource=file_path,
            detail=f"禁止{verb}敏感或越權路徑",
        )
        raise PermissionError(f"Security Violation: 禁止{verb}敏感或越權路徑 ({file_path})")

    async def _wait_on(
        self,
        socket: BrowserSocket,
        method: str,
        params: dict[str, Any],
        timeout: float,
    ) -> dict[str, Any]:
        rpc_id = f"rpc_{uuid4().hex}"
        future: asyncio.Future[Any] = asyncio.get_running_loop().create_future()
        self._pending[rpc_id] = future
        await socket.send_json({"jsonrpc": "2.0", "id": rpc_id, "method": method, "params": params})
        try:
            payload = await asyncio.wait_for(future, timeout)
        except TimeoutError:
            return _timeout(timeout)
        finally:
            self._pending.pop(rpc_id, None)
        return _wrap(payload)

    async def _ensure_listener(self) -> None:
        if self._listener is not None and not self._listener.done():
            await asyncio.wait_for(self._ready.wait(), timeout=5)
            return
        self._ready = asyncio.Event()
        self._listener = asyncio.create_task(self._listen(), name=f"ws-rpc-{self.worker_id}")
        await asyncio.wait_for(self._ready.wait(), timeout=5)

    async def _listen(self) -> None:
        client: _Commands = self._redis_factory()
        pubsub = client.pubsub()
        try:
            await pubsub.subscribe(self.inbox)
            self._ready.set()
            async for message in pubsub.listen():
                if not isinstance(message, dict) or message.get("type") != "message":
                    continue
                data = message.get("data")
                if isinstance(data, str):
                    await self._on_bus_message(data)
        finally:
            self._ready.set()
            with contextlib.suppress(Exception):
                await pubsub.aclose()
            with contextlib.suppress(Exception):
                await client.aclose()

    async def _on_bus_message(self, raw: str) -> None:
        try:
            body = json.loads(raw)
        except json.JSONDecodeError:
            return
        if not isinstance(body, dict):
            return
        if body.get("kind") == "call":
            await self._deliver(body)
            return
        if body.get("kind") == "close":
            await self._close_local(str(body.get("field", "")))
            return
        if body.get("kind") == "result":
            payload = body.get("payload")
            self.resolve_rpc_response(str(body.get("rpc_id", "")), payload if isinstance(payload, dict) else {})

    async def _deliver(self, body: dict[str, Any]) -> None:
        field = str(body.get("field", ""))
        origin = str(body.get("origin_worker", ""))
        rpc_id = str(body.get("rpc_id", ""))
        socket = self._connections.get(field)
        if socket is None:
            await self._publish(origin, {"kind": "result", "rpc_id": rpc_id, "payload": _offline_for(field)})
            return
        self._forwarded[rpc_id] = origin
        params = body.get("params")
        await socket.send_json(
            {
                "jsonrpc": "2.0",
                "id": rpc_id,
                "method": body.get("method"),
                "params": params if isinstance(params, dict) else {},
            }
        )

    def _commands_client(self) -> _Commands:
        if self._commands is None:
            self._commands = self._redis_factory()
        return self._commands

    async def _publish(self, worker_id: str, body: dict[str, Any]) -> None:
        await self._commands_client().publish(
            f"ws-rpc:inbox:{worker_id}",
            json.dumps(body, ensure_ascii=False),
        )


def _timeout(timeout: float) -> dict[str, str]:
    return {"status": "TIMEOUT", "error": f"瀏覽器本機檔案操作逾時 ({timeout}s)"}


def _wrap(payload: Any) -> dict[str, Any]:
    if isinstance(payload, dict) and payload.get("status") in {"BROWSER_OFFLINE", "TIMEOUT", "ERROR"}:
        return payload
    return {"status": "SUCCESS", "data": payload}


ws_rpc_manager = WebSocketReverseRPCManager()
