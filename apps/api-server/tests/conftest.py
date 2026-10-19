"""Test infrastructure: in-process Postgres (pgvector) and Redis, plus a fake embedding server."""

import asyncio
import json
import os
import shutil
import socket
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

if sys.platform == "win32":
    # psycopg's async driver cannot run on the Proactor event loop.
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

os.environ["EMBEDDING_DIMENSION"] = "32"
os.environ["TOKEN_VAULT_KEY"] = "MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY="
os.environ["EMBEDDING_MODEL_NAME"] = "BAAI/bge-m3"
os.environ["EMBEDDING_API_KEY"] = "local"
os.environ["SGLANG_BASE_URL"] = "http://sglang.test/v1"
os.environ["SGLANG_API_KEY"] = "local"
os.environ["DATABASE_NULL_POOL"] = "true"
os.environ["SEED_ON_STARTUP"] = "true"
os.environ["CORS_ORIGINS"] = "http://localhost:3000"

def _ensure_node_on_path() -> None:
    if shutil.which("node"):
        return
    candidate = Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "nodejs"
    if (candidate / "node.exe").exists():
        os.environ["PATH"] = str(candidate) + os.pathsep + os.environ.get("PATH", "")


_ensure_node_on_path()


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


class _EmbeddingHandler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length", "0"))
        body = json.loads(self.rfile.read(length))
        inputs = body["input"]
        if isinstance(inputs, str):
            inputs = [inputs]
        dimension = int(os.environ["EMBEDDING_DIMENSION"])
        data = []
        for index, text in enumerate(inputs):
            vector = [0.0] * dimension
            vector[0] = 3.0
            vector[1] = float((len(str(text)) % 5) + 1)
            data.append({"object": "embedding", "index": index, "embedding": vector})
        payload = json.dumps(
            {
                "object": "list",
                "data": data,
                "model": body["model"],
                "usage": {"prompt_tokens": 1, "total_tokens": 1},
            }
        ).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, format: str, *args: object) -> None:
        return


def _start_embedding_server() -> ThreadingHTTPServer:
    server = ThreadingHTTPServer(("127.0.0.1", 0), _EmbeddingHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


def _start_redis(port: int) -> object:
    from fakeredis import TcpFakeServer

    server = TcpFakeServer(("127.0.0.1", port))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


_embedding_server = _start_embedding_server()
_embedding_port = int(_embedding_server.server_address[1])
os.environ["EMBEDDING_BASE_URL"] = f"http://127.0.0.1:{_embedding_port}/v1"

_redis_port = _free_port()
_redis_server = _start_redis(_redis_port)
os.environ["REDIS_URL"] = f"redis://127.0.0.1:{_redis_port}/0"

_PGLITE_HOME = Path(__file__).resolve().parent / ".pglite-home"
_PGLITE_HOME.mkdir(exist_ok=True)
_PGLITE_PACKAGES = {
    "@electric-sql/pglite": "0.5.9",
    "@electric-sql/pglite-pgvector": "0.0.10",
    "@electric-sql/pglite-socket": "0.2.12",
}
_PACKAGE_JSON = _PGLITE_HOME / "package.json"
_expected_package = {
    "name": "pglite-test-db",
    "private": True,
    "dependencies": _PGLITE_PACKAGES,
}
if not _PACKAGE_JSON.exists() or json.loads(_PACKAGE_JSON.read_text(encoding="utf-8")) != _expected_package:
    _PACKAGE_JSON.write_text(json.dumps(_expected_package), encoding="utf-8")
if not (_PGLITE_HOME / "node_modules" / "@electric-sql" / "pglite-pgvector").exists():
    npm = shutil.which("npm.cmd") or shutil.which("npm")
    if npm is None:
        raise RuntimeError("npm is required to start the embedded Postgres used by tests")
    subprocess.run([npm, "install"], cwd=_PGLITE_HOME, check=True)


def _start_pglite(port: int) -> subprocess.Popen[str]:
    source = Path(__file__).resolve().parent / "pglite_server.mjs"
    target = _PGLITE_HOME / "pglite_server.mjs"
    target.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    env = os.environ.copy()
    env["PGLITE_PORT"] = str(port)
    process = subprocess.Popen(
        ["node", str(target)],
        cwd=_PGLITE_HOME,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    ready = threading.Event()
    logs: list[str] = []

    def _read_output() -> None:
        if process.stdout is None:
            return
        for line in process.stdout:
            logs.append(line)
            if "READY" in line:
                ready.set()

    threading.Thread(target=_read_output, daemon=True).start()
    if not ready.wait(60):
        process.kill()
        raise RuntimeError("embedded Postgres failed to start:\n" + "".join(logs))
    return process


_pg_port = _free_port()
_pglite = _start_pglite(_pg_port)
os.environ["DATABASE_URL"] = (
    "postgresql+psycopg_async://"
    f"postgres:postgres@127.0.0.1:{_pg_port}/postgres?sslmode=disable"
)

from app.db.migrate import run_migrations

run_migrations()

import httpx
from app.tool_bus.http_pool import set_http_client


def _connector_ok(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, json={"ok": True, "path": request.url.path})


set_http_client(httpx.AsyncClient(transport=httpx.MockTransport(_connector_ok)))


@pytest.fixture(autouse=True)
async def release_database_connections():
    yield
    from app.db.session import get_engine

    await get_engine().dispose()


def pytest_sessionfinish(session: object, exitstatus: int) -> None:
    _embedding_server.shutdown()
    _pglite.terminate()
    shutdown = getattr(_redis_server, "shutdown", None)
    if callable(shutdown):
        shutdown()
