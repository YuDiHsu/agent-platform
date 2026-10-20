# /// script
# requires-python = ">=3.12"
# dependencies = ["websockets>=14"]
# ///
"""Local MCP Daemon: serve one folder on this computer to the platform over a reverse-RPC WebSocket.

Implements: REQ-005, ADR-0002. Run with
    uv run packages/local-mcp-daemon/daemon.py --server ws://host/api/v1/ws/local-daemon --token <配對權杖> --root <資料夾>
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import json
import re
import shlex
import subprocess
from pathlib import Path, PurePosixPath
from typing import Any

_SENSITIVE_FILE = re.compile(
    r"(^|/)\.env($|\.)|\.pem$|\.pfx$|(^|/)id_rsa($|\.)|(^|/)\.git(/|$)|(^|/)node_modules(/|$)",
    re.IGNORECASE,
)
_FORBIDDEN_COMMANDS = {"shutdown", "reboot", "mkfs", "format", "dd", "diskpart", "chown", "sudo", "su"}
_FORBIDDEN_FRAGMENTS = ("rm -rf", "chmod 777", ":(){", "init 0")
_MAX_READ_BYTES = 10 * 1024 * 1024
_DEFAULT_CLI_TIMEOUT = 60.0
_OUTPUT_LIMIT = 64 * 1024
_POLICY_VIOLATION = 1008


class LocalDaemon:
    """Answer CLIENT_FS_* and DAEMON_EXEC_CLI requests strictly inside ``root``."""

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    async def handle(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        if method == "CLIENT_FS_LIST":
            return self._list(str(params.get("file_path") or ""))
        if method == "CLIENT_FS_READ":
            return self._read(str(params.get("file_path") or ""))
        if method == "CLIENT_FS_WRITE":
            return self._write(str(params.get("file_path") or ""), str(params.get("content", "")))
        if method == "DAEMON_EXEC_CLI":
            timeout = float(params.get("timeout") or _DEFAULT_CLI_TIMEOUT)
            return await asyncio.to_thread(self._run, str(params.get("command", "")), timeout)
        raise ValueError(f"不支援的方法: {method}")

    def _resolve(self, relative: str) -> Path:
        _reject_path(relative)
        normalized = relative.replace("\\", "/").strip()
        target = (self.root / normalized).resolve()
        if not target.is_relative_to(self.root):
            raise PermissionError(f"禁止存取資料夾外的路徑 ({relative})")
        return target

    def _list(self, relative: str) -> dict[str, Any]:
        folder = self._resolve(relative)
        entries = []
        for child in sorted(folder.iterdir(), key=lambda item: item.name):
            name = f"{relative.strip('/')}/{child.name}".lstrip("/")
            if _SENSITIVE_FILE.search(name):
                continue
            entries.append({"name": child.name, "kind": "dir" if child.is_dir() else "file"})
        return {"entries": entries}

    def _read(self, relative: str) -> dict[str, Any]:
        target = self._resolve(relative)
        size = target.stat().st_size
        if size > _MAX_READ_BYTES:
            raise ValueError(f"檔案超過 {_MAX_READ_BYTES // (1024 * 1024)} MB 上限")
        raw = target.read_bytes()
        try:
            return {"encoding": "utf-8", "content": raw.decode("utf-8"), "size": size}
        except UnicodeDecodeError:
            return {"encoding": "base64", "content": base64.b64encode(raw).decode("ascii"), "size": size}

    def _write(self, relative: str, content: str) -> dict[str, Any]:
        target = self._resolve(relative)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return {"written": True, "path": relative, "size": len(content.encode("utf-8"))}

    def _run(self, command: str, timeout: float) -> dict[str, Any]:
        args = shlex.split(command)
        if not args:
            return {"exit_code": -1, "stdout": "", "stderr": "沒有指令"}
        _reject_command(command, args)
        try:
            done = subprocess.run(args, cwd=self.root, capture_output=True, timeout=timeout, check=False)
        except subprocess.TimeoutExpired:
            return {"exit_code": -1, "stdout": "", "stderr": f"指令逾時 ({timeout}s)"}
        except OSError as exc:
            return {"exit_code": -1, "stdout": "", "stderr": f"無法執行指令: {exc}"}
        return {
            "exit_code": done.returncode,
            "stdout": done.stdout.decode("utf-8", "replace")[:_OUTPUT_LIMIT],
            "stderr": done.stderr.decode("utf-8", "replace")[:_OUTPUT_LIMIT],
        }


def _reject_path(relative: str) -> None:
    normalized = relative.replace("\\", "/").strip()
    pure = PurePosixPath(normalized)
    if pure.is_absolute() or re.match(r"^[A-Za-z]:", normalized) or ".." in pure.parts:
        raise PermissionError(f"禁止存取資料夾外的路徑 ({relative})")
    if _SENSITIVE_FILE.search(normalized):
        raise PermissionError(f"禁止存取敏感檔案 ({relative})")


def _reject_command(command: str, args: list[str]) -> None:
    """Refuse dangerous programs, and any argument that names a path outside the root or a sensitive file."""

    program = PurePosixPath(args[0].replace("\\", "/")).name.lower().removesuffix(".exe")
    lowered = command.lower()
    if program in _FORBIDDEN_COMMANDS or any(fragment in lowered for fragment in _FORBIDDEN_FRAGMENTS):
        raise PermissionError(f"偵測到禁止執行的危險指令 ({args[0]})")
    for arg in args[1:]:
        value = arg.split("=", 1)[1] if arg.startswith("-") and "=" in arg else arg
        if value.startswith("-"):
            continue
        _reject_path(value)


async def serve(server: str, token: str, daemon: LocalDaemon) -> None:
    import websockets

    delay = 1.0
    running: set[asyncio.Task[None]] = set()
    while True:
        try:
            async with websockets.connect(server, additional_headers={"Authorization": f"Bearer {token}"}) as socket:
                print(f"已連線 {server}，服務資料夾 {daemon.root}")
                delay = 1.0
                async for raw in socket:
                    task = asyncio.create_task(_answer(socket, daemon, raw))
                    running.add(task)
                    task.add_done_callback(running.discard)
        except websockets.ConnectionClosed as exc:
            if exc.rcvd is not None and exc.rcvd.code == _POLICY_VIOLATION:
                print("配對權杖無效或已撤銷，請在平台重新產生配對權杖")
                return
            print(f"連線中斷（{exc}），{delay:.0f} 秒後重試")
        except OSError as exc:
            print(f"連線中斷（{exc}），{delay:.0f} 秒後重試")
        await asyncio.sleep(delay)
        delay = min(delay * 2, 60.0)


async def _answer(socket: Any, daemon: LocalDaemon, raw: str | bytes) -> None:
    message = json.loads(raw)
    rpc_id = message.get("id")
    try:
        result = await daemon.handle(str(message.get("method", "")), dict(message.get("params") or {}))
        reply: dict[str, Any] = {"jsonrpc": "2.0", "id": rpc_id, "result": result}
    except Exception as exc:  # noqa: BLE001 - every failure goes back to the caller as an RPC error
        reply = {"jsonrpc": "2.0", "id": rpc_id, "error": {"message": str(exc)}}
    await socket.send(json.dumps(reply, ensure_ascii=False))


def main() -> None:
    parser = argparse.ArgumentParser(description="Local MCP Daemon")
    parser.add_argument("--server", required=True, help="ws(s)://.../api/v1/ws/local-daemon")
    parser.add_argument("--token", required=True, help="平台「本機 Daemon」頁面產生的配對權杖")
    parser.add_argument("--root", required=True, type=Path, help="開放給平台的本機資料夾")
    args = parser.parse_args()
    if not args.root.is_dir():
        parser.error(f"找不到資料夾: {args.root}")
    asyncio.run(serve(args.server, args.token, LocalDaemon(args.root)))


if __name__ == "__main__":
    main()
