"""Rootless Docker sandbox for CLI skills. Implements: REQ-015, ADR-0002."""

import asyncio
import contextlib
import shutil
import tempfile
from collections.abc import Awaitable, Callable
from pathlib import Path, PurePosixPath
from typing import Any, Protocol
from uuid import uuid4

from app.core.config import settings

DockerCall = Callable[[list[str]], Awaitable[tuple[int, bytes, bytes]]]

TIMEOUT_EXIT_CODE = 124


class SandboxRunner(Protocol):
    async def run_ephemeral_command(
        self,
        *,
        image: str,
        command: str,
        injected_files: dict[str, bytes],
        timeout: float,
    ) -> dict[str, Any]: ...


async def _docker_cli(argv: list[str]) -> tuple[int, bytes, bytes]:
    process = await asyncio.create_subprocess_exec(
        *argv,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await process.communicate()
    except asyncio.CancelledError:
        with contextlib.suppress(ProcessLookupError):
            process.kill()
        raise
    return int(process.returncode or 0), stdout, stderr


class ServerDockerSandboxRunner:
    """One short-lived container per command, with at most `max_concurrency` alive at once."""

    def __init__(
        self,
        max_concurrency: int | None = None,
        docker: DockerCall | None = None,
        scripts_dir: str | None = None,
    ) -> None:
        self._gate = asyncio.Semaphore(max_concurrency or settings.SANDBOX_MAX_CONCURRENCY)
        self._docker = docker or _docker_cli
        self._scripts_dir = scripts_dir or settings.SANDBOX_SCRIPTS_DIR

    async def run_ephemeral_command(
        self,
        *,
        image: str,
        command: str,
        injected_files: dict[str, bytes],
        timeout: float,
    ) -> dict[str, Any]:
        safe_files = {_workspace_path(name): data for name, data in injected_files.items()}
        async with self._gate:
            workspace = Path(tempfile.mkdtemp(prefix="sandbox-"))
            name = f"sandbox-{uuid4().hex[:12]}"
            try:
                for relative, data in safe_files.items():
                    target = workspace / relative
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(data)
                argv = self._run_argv(name, image, command, workspace)
                try:
                    code, stdout, stderr = await asyncio.wait_for(self._docker(argv), timeout)
                except TimeoutError:
                    with contextlib.suppress(Exception):
                        await self._docker(["docker", "kill", name])
                    return {
                        "exit_code": TIMEOUT_EXIT_CODE,
                        "stdout": "",
                        "stderr": f"沙盒指令逾時 ({timeout}s)，容器已銷毀",
                    }
                return {
                    "exit_code": code,
                    "stdout": stdout.decode("utf-8", errors="replace"),
                    "stderr": stderr.decode("utf-8", errors="replace"),
                }
            finally:
                shutil.rmtree(workspace, ignore_errors=True)

    def _run_argv(self, name: str, image: str, command: str, workspace: Path) -> list[str]:
        return [
            "docker",
            "run",
            "--rm",
            "--name",
            name,
            "--network",
            "none",
            "--memory",
            "512m",
            "--pids-limit",
            "64",
            "--read-only",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges",
            "--tmpfs",
            "/tmp:rw,size=64m",
            "--workdir",
            "/workspace",
            "-v",
            f"{workspace}:/workspace:rw",
            "-v",
            f"{self._scripts_dir}:/opt/skill-scripts:ro",
            image,
            "sh",
            "-c",
            command,
        ]


def _workspace_path(name: str) -> str:
    path = PurePosixPath(name.replace("\\", "/"))
    if path.is_absolute() or ".." in path.parts or not path.parts:
        raise ValueError(f"注入檔案路徑必須留在沙盒工作區內: {name}")
    return str(path)


_runner: SandboxRunner | None = None


def get_sandbox_runner() -> SandboxRunner:
    global _runner
    if _runner is None:
        _runner = ServerDockerSandboxRunner()
    return _runner


def set_sandbox_runner(runner: SandboxRunner | None) -> None:
    global _runner
    _runner = runner
