"""Parameterized CLI skills: anti-injection rendering, sandbox gating, file sync, and approval.

Public seams under test:
- UnifiedToolBus.dispatch("execute_skill_cli")
- ServerDockerSandboxRunner (the Docker process boundary is a recorded fake)
- the chat stream and HITL decision endpoint
"""

import asyncio
import json
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import httpx
import pytest
from sqlalchemy import delete, select

from app.api.deps import get_llm
from app.db.models import (
    AgentRole,
    AgentRoleSkill,
    CliExecutionLog,
    LocalWorkspaceMount,
    SecurityAuditLog,
    SkillRegistry,
)
from app.db.seed_runner import SeedRunner
from app.db.session import database_session, get_session_factory
from app.llm.embedding_client import EmbeddingClient
from app.main import app
from app.orchestrator.runtime import drain_background
from app.orchestrator.state import (
    DAGTaskNode,
    OrchestratorPlanOutput,
    SubAgentExecutionOutput,
    SubAgentToolCall,
)
from app.tool_bus.bus import UnifiedToolBus
from app.tool_bus.sandbox_runner import ServerDockerSandboxRunner, set_sandbox_runner
from app.tool_bus.ws_rpc_manager import ws_rpc_manager

TEST_SKILLS = ("TEST_CLI_ECHO", "TEST_CLI_COMMIT_ECHO", "TEST_CLI_BROKEN")


class FakeSandbox:
    """Stands in for the Docker boundary and records what the executor asked for."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.result: dict[str, Any] = {"exit_code": 0, "stdout": "ok", "stderr": ""}

    async def run_ephemeral_command(
        self,
        *,
        image: str,
        command: str,
        injected_files: dict[str, bytes],
        timeout: float,
    ) -> dict[str, Any]:
        self.calls.append(
            {"image": image, "command": command, "injected_files": dict(injected_files), "timeout": timeout}
        )
        return dict(self.result)


class BrowserSocket:
    def __init__(self, content: str = '{"openapi": "3.1.0"}') -> None:
        self.sent: list[dict[str, Any]] = []
        self.content = content

    async def accept(self) -> None:
        return None

    async def send_json(self, data: dict[str, Any]) -> None:
        self.sent.append(data)
        ws_rpc_manager.resolve_rpc_response(
            str(data["id"]),
            {"encoding": "utf-8", "content": self.content, "size": len(self.content)},
        )


@pytest.fixture
async def sandbox() -> AsyncIterator[FakeSandbox]:
    fake = FakeSandbox()
    set_sandbox_runner(fake)  # type: ignore[arg-type]
    yield fake
    set_sandbox_runner(None)


@pytest.fixture
async def client(sandbox: FakeSandbox) -> AsyncIterator[httpx.AsyncClient]:
    del sandbox
    async with get_session_factory()() as session:
        await SeedRunner(session, EmbeddingClient()).run()
    async with database_session() as db:
        fin = await db.scalar(select(AgentRole).where(AgentRole.code == "FIN"))
        assert fin is not None
        for code, tier, template, schema in (
            ("TEST_CLI_ECHO", "READ", "echo {{message}}", {"message": {"type": "string"}}),
            ("TEST_CLI_COMMIT_ECHO", "COMMIT", "echo {{message}}", {"message": {"type": "string"}}),
            ("TEST_CLI_BROKEN", "READ", "echo {{a}} {{b}}", {"a": {"type": "string"}}),
        ):
            skill = SkillRegistry(
                code=code,
                name=code,
                trigger_description="測試用 CLI 技能",
                sop_markdown="測試",
                execution_mode="SERVER_SANDBOX_CLI",
                cli_config={"action_tier": tier, "command_template": template, "allowed_args_schema": schema},
            )
            db.add(skill)
            await db.flush()
            db.add(AgentRoleSkill(role_id=fin.id, skill_id=skill.id))
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http:
        yield http
    await drain_background()
    await ws_rpc_manager.aclose()
    app.dependency_overrides.pop(get_llm, None)
    async with database_session() as db:
        await db.execute(delete(CliExecutionLog).where(CliExecutionLog.skill_code.in_(TEST_SKILLS)))
        await db.execute(delete(SkillRegistry).where(SkillRegistry.code.in_(TEST_SKILLS)))


async def _user(client: httpx.AsyncClient) -> tuple[str, dict[str, str]]:
    login = await client.post(
        "/api/v1/users/dev-login",
        json={"email": f"cli-{uuid4().hex}@hub.local", "display_name": "終端使用者", "department": "RD"},
    )
    user_id = str(login.json()["id"])
    headers = {"X-User-Id": user_id}
    enabled = await client.put(
        "/api/v1/users/me/tool-preferences",
        headers=headers,
        json={"code": "execute_skill_cli", "is_enabled": True},
    )
    assert enabled.status_code == 204
    return user_id, headers


async def _run_cli(user_id: str, skill: str, cli_args: dict[str, Any], session_id: str | None = None) -> dict[str, Any]:
    results = await UnifiedToolBus().dispatch(
        role_code="FIN",
        user_id=UUID(user_id),
        session_id=UUID(session_id or str(uuid4())),
        calls=[("execute_skill_cli", {"skill_code": skill, "cli_args": cli_args})],
    )
    assert results[0].ok, results[0].error
    return results[0].output


async def _audit_events(user_id: str) -> list[SecurityAuditLog]:
    async with database_session() as db:
        rows = (
            await db.scalars(
                select(SecurityAuditLog)
                .where(SecurityAuditLog.actor_user_id == UUID(user_id))
                .order_by(SecurityAuditLog.created_at)
            )
        ).all()
        return list(rows)


async def test_undeclared_argument_is_blocked_and_audited(client: httpx.AsyncClient, sandbox: FakeSandbox) -> None:
    user_id, _headers = await _user(client)
    out = await _run_cli(
        user_id,
        "SKILL_FIN_PYTHON_IRR_CALCULATOR",
        {"cashflows": "-100,110", "rate": "0.1", "shell": "1"},
    )
    assert out["blocked"] is True
    assert out["exit_code"] == -1
    assert sandbox.calls == []
    events = await _audit_events(user_id)
    assert [row.event_code for row in events] == ["CLI_INJECTION_BLOCKED"]
    assert events[0].resource == "SKILL_FIN_PYTHON_IRR_CALCULATOR"


async def test_command_injection_in_a_declared_argument_is_blocked(
    client: httpx.AsyncClient,
    sandbox: FakeSandbox,
) -> None:
    user_id, _headers = await _user(client)
    out = await _run_cli(user_id, "SKILL_FIN_PYTHON_IRR_CALCULATOR", {"cashflows": "-100,110; rm -rf /", "rate": "0.1"})
    assert out["blocked"] is True
    assert sandbox.calls == []
    assert [row.event_code for row in await _audit_events(user_id)] == ["CLI_INJECTION_BLOCKED"]


async def test_dangerous_token_is_blocked_even_when_quoted(client: httpx.AsyncClient, sandbox: FakeSandbox) -> None:
    user_id, _headers = await _user(client)
    out = await _run_cli(user_id, "TEST_CLI_ECHO", {"message": "x; rm -rf /"})
    assert out["blocked"] is True
    assert "rm -rf /" in out["stderr"]
    assert sandbox.calls == []
    events = await _audit_events(user_id)
    assert [row.event_code for row in events] == ["CLI_INJECTION_BLOCKED"]
    assert "rm -rf /" in events[0].detail


async def test_unfilled_placeholder_is_blocked(client: httpx.AsyncClient, sandbox: FakeSandbox) -> None:
    user_id, _headers = await _user(client)
    out = await _run_cli(user_id, "TEST_CLI_BROKEN", {"a": "one"})
    assert out["blocked"] is True
    assert "{{b}}" in out["stderr"] or "佔位符" in out["stderr"]
    assert sandbox.calls == []


async def test_read_skill_runs_with_every_argument_quoted_and_is_logged(
    client: httpx.AsyncClient,
    sandbox: FakeSandbox,
) -> None:
    user_id, _headers = await _user(client)
    sandbox.result = {"exit_code": 0, "stdout": "NPV=9.09", "stderr": ""}
    spaced = await _run_cli(user_id, "TEST_CLI_ECHO", {"message": "hello world; ls"})
    assert spaced["command"] == "echo 'hello world; ls'"
    assert sandbox.calls[0]["command"] == "echo 'hello world; ls'"

    out = await _run_cli(user_id, "SKILL_FIN_PYTHON_IRR_CALCULATOR", {"cashflows": "-100,110", "rate": "0.1"})
    assert out["command"] == "python3 /opt/skill-scripts/fin_calculator.py --cashflows -100,110 --rate 0.1"
    assert out["execution_target"] == "SERVER_SANDBOX_CLI"
    assert out["exit_code"] == 0
    assert out["stdout"] == "NPV=9.09"
    assert isinstance(out["duration_ms"], int)
    assert sandbox.calls[1]["image"] == "enterprise-sandbox:py312-node22"

    async with database_session() as db:
        row = await db.scalar(
            select(CliExecutionLog).where(
                CliExecutionLog.user_id == UUID(user_id),
                CliExecutionLog.skill_code == "SKILL_FIN_PYTHON_IRR_CALCULATOR",
            )
        )
        assert row is not None
        assert row.rendered_command == out["command"]
        assert row.exit_code == 0
        assert row.executing_role_code == "FIN"
        assert row.stdout_preview == "NPV=9.09"


async def test_a_skill_not_bound_to_the_role_does_not_run(client: httpx.AsyncClient, sandbox: FakeSandbox) -> None:
    user_id, _headers = await _user(client)
    results = await UnifiedToolBus().dispatch(
        role_code="PM",
        user_id=UUID(user_id),
        session_id=uuid4(),
        calls=[("execute_skill_cli", {"skill_code": "TEST_CLI_ECHO", "cli_args": {"message": "hi"}})],
    )
    assert results[0].output["blocked"] is True
    assert sandbox.calls == []


async def test_sync_local_files_reads_the_browser_file_into_the_sandbox(
    client: httpx.AsyncClient,
    sandbox: FakeSandbox,
) -> None:
    user_id, _headers = await _user(client)
    async with database_session() as db:
        db.add(LocalWorkspaceMount(user_id=UUID(user_id), mount_alias="規格", browser_handle_key="local_mount_specs"))
    session_id = str(uuid4())
    socket = BrowserSocket('{"openapi": "3.1.0"}')
    await ws_rpc_manager.register_connection(user_id, session_id, socket)
    async with database_session() as db:
        validator = await db.scalar(select(SkillRegistry).where(SkillRegistry.code == "SKILL_SA_OPENAPI_CLI_VALIDATOR"))
        assert validator is not None
        sa = await db.scalar(select(AgentRole).where(AgentRole.code == "SA"))
        assert sa is not None

    results = await UnifiedToolBus().dispatch(
        role_code="SA",
        user_id=UUID(user_id),
        session_id=UUID(session_id),
        calls=[
            (
                "execute_skill_cli",
                {"skill_code": "SKILL_SA_OPENAPI_CLI_VALIDATOR", "cli_args": {"target_file": "specs/api.json"}},
            )
        ],
    )
    assert results[0].ok, results[0].error
    assert socket.sent[0]["method"] == "CLIENT_FS_READ"
    assert socket.sent[0]["params"]["file_path"] == "specs/api.json"
    assert sandbox.calls[0]["injected_files"] == {"specs/api.json": b'{"openapi": "3.1.0"}'}
    assert sandbox.calls[0]["command"] == "python3 /opt/skill-scripts/validate_openapi.py --file specs/api.json"


async def test_sync_reports_an_offline_browser_without_running_anything(
    client: httpx.AsyncClient,
    sandbox: FakeSandbox,
) -> None:
    user_id, _headers = await _user(client)
    async with database_session() as db:
        db.add(LocalWorkspaceMount(user_id=UUID(user_id), mount_alias="規格", browser_handle_key="local_mount_specs"))
    results = await UnifiedToolBus().dispatch(
        role_code="SA",
        user_id=UUID(user_id),
        session_id=uuid4(),
        calls=[
            (
                "execute_skill_cli",
                {"skill_code": "SKILL_SA_OPENAPI_CLI_VALIDATOR", "cli_args": {"target_file": "specs/api.json"}},
            )
        ],
    )
    out = results[0].output
    assert out["exit_code"] == -1
    assert "BROWSER_OFFLINE" in out["stderr"]
    assert sandbox.calls == []


@pytest.mark.parametrize(("path", "event_code"), [(".env", "SENSITIVE_FILE"), ("../notes.json", "PATH_TRAVERSAL")])
async def test_sync_refuses_sensitive_and_escaping_paths(
    client: httpx.AsyncClient,
    sandbox: FakeSandbox,
    path: str,
    event_code: str,
) -> None:
    user_id, _headers = await _user(client)
    async with database_session() as db:
        db.add(LocalWorkspaceMount(user_id=UUID(user_id), mount_alias="規格", browser_handle_key="local_mount_specs"))
    session_id = str(uuid4())
    socket = BrowserSocket()
    await ws_rpc_manager.register_connection(user_id, session_id, socket)
    results = await UnifiedToolBus().dispatch(
        role_code="SA",
        user_id=UUID(user_id),
        session_id=UUID(session_id),
        calls=[("execute_skill_cli", {"skill_code": "SKILL_SA_OPENAPI_CLI_VALIDATOR", "cli_args": {"target_file": path}})],
    )
    assert results[0].output["blocked"] is True
    assert socket.sent == []
    assert sandbox.calls == []
    assert event_code in [row.event_code for row in await _audit_events(user_id)]


class _CliModel:
    """Scripted external model: one FIN step that calls a CLI skill."""

    def __init__(self, skill_code: str, message: str) -> None:
        self.skill_code = skill_code
        self.message = message

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
                reasoning="需要執行命令列技能",
                goal_statement="執行 CLI 技能",
                dag_steps=[
                    DAGTaskNode(
                        step_id=1,
                        target_role_code="FIN",
                        task_title="執行 CLI",
                        detailed_instructions="執行指定技能",
                    )
                ],
            )
        if "已直接執行" in text or "使用者已核准" in text:
            return SubAgentExecutionOutput(
                execution_status="COMPLETED",
                thought_process="CLI 已完成",
                tool_calls=[],
                artifact_title="CLI 結果",
                artifact_type="FINANCIAL_MODEL",
                summary_200_words="摘" * 200,
                full_markdown_content="# 結果\n",
                handoff_notes_for_next_role="完成",
            )
        return SubAgentExecutionOutput(
            execution_status="NEED_TOOL_CALL",
            thought_process="呼叫技能",
            tool_calls=[
                SubAgentToolCall(
                    tool_name="execute_skill_cli",
                    arguments={"skill_code": self.skill_code, "cli_args": {"message": self.message}},
                )
            ],
        )


def _events(body: str) -> list[tuple[str, dict[str, Any]]]:
    parsed: list[tuple[str, dict[str, Any]]] = []
    for block in body.split("\n\n"):
        name, data = "message", ""
        for line in block.splitlines():
            if line.startswith("event:"):
                name = line.split(":", 1)[1].strip()
            elif line.startswith("data:"):
                data += line.split(":", 1)[1].strip()
        if data:
            parsed.append((name, json.loads(data)))
    return parsed


async def test_read_cli_runs_without_pausing_and_streams_cli_output(
    client: httpx.AsyncClient,
    sandbox: FakeSandbox,
) -> None:
    app.dependency_overrides[get_llm] = lambda: _CliModel("TEST_CLI_ECHO", "你好")
    sandbox.result = {"exit_code": 0, "stdout": "\x1b[32m你好\x1b[0m", "stderr": ""}
    _user_id, headers = await _user(client)
    session_id = (await client.post("/api/v1/chat/sessions", headers=headers)).json()["id"]
    response = await client.post(
        f"/api/v1/chat/sessions/{session_id}/stream",
        headers=headers,
        json={"message": "請執行終端機技能"},
    )
    events = _events(response.text)
    names = [name for name, _payload in events]
    assert "hitl_required" not in names
    cli = next(payload for name, payload in events if name == "cli_output")
    assert cli["execution_target"] == "SERVER_SANDBOX_CLI"
    assert cli["command"] == "echo '你好'"
    assert cli["exit_code"] == 0
    assert cli["stdout"] == "\x1b[32m你好\x1b[0m"
    assert cli["role_code"] == "FIN"
    assert cli["skill_code"] == "TEST_CLI_ECHO"
    assert isinstance(cli["duration_ms"], int)
    assert names.index("cli_output") < names.index("artifact_created")
    state = (await client.get(f"/api/v1/chat/sessions/{session_id}/state", headers=headers)).json()
    assert "cli_output" in [message["event_type"] for message in state["messages"]]


async def test_commit_cli_previews_the_rendered_command_and_runs_only_after_approval(
    client: httpx.AsyncClient,
    sandbox: FakeSandbox,
) -> None:
    app.dependency_overrides[get_llm] = lambda: _CliModel("TEST_CLI_COMMIT_ECHO", "hello world")
    _user_id, headers = await _user(client)
    session_id = (await client.post("/api/v1/chat/sessions", headers=headers)).json()["id"]
    response = await client.post(
        f"/api/v1/chat/sessions/{session_id}/stream",
        headers=headers,
        json={"message": "請執行需要審批的技能"},
    )
    events = _events(response.text)
    hitl = next(payload for name, payload in events if name == "hitl_required")
    assert hitl["tool_name"] == "execute_skill_cli"
    assert hitl["execution_target"] == "SERVER_SANDBOX_CLI"
    assert hitl["proposed_payload"]["rendered_command"] == "echo 'hello world'"
    assert "echo 'hello world'" in hitl["preview_title"]
    assert sandbox.calls == []
    state = (await client.get(f"/api/v1/chat/sessions/{session_id}/state", headers=headers)).json()
    assert state["hold_reason"] == "WAITING_HITL"

    decided = await client.post(
        f"/api/v1/hitl/{hitl['hitl_request_id']}/decide",
        headers=headers,
        json={"status": "APPROVED"},
    )
    assert decided.status_code == 200, decided.text
    assert [call["command"] for call in sandbox.calls] == ["echo 'hello world'"]
    assert decided.json()["cli_output"]["command"] == "echo 'hello world'"
    assert decided.json()["cli_output"]["exit_code"] == 0


async def test_rejected_commit_cli_never_reaches_the_sandbox(client: httpx.AsyncClient, sandbox: FakeSandbox) -> None:
    app.dependency_overrides[get_llm] = lambda: _CliModel("TEST_CLI_COMMIT_ECHO", "hello")
    _user_id, headers = await _user(client)
    session_id = (await client.post("/api/v1/chat/sessions", headers=headers)).json()["id"]
    response = await client.post(
        f"/api/v1/chat/sessions/{session_id}/stream",
        headers=headers,
        json={"message": "請執行需要審批的技能"},
    )
    hitl = next(payload for name, payload in _events(response.text) if name == "hitl_required")
    decided = await client.post(
        f"/api/v1/hitl/{hitl['hitl_request_id']}/decide",
        headers=headers,
        json={"status": "REJECTED", "rejection_reason": "不要執行"},
    )
    assert decided.status_code == 200
    assert sandbox.calls == []


class FakeDocker:
    def __init__(self, delay: float = 0.0, hang_on_run: bool = False) -> None:
        self.argvs: list[list[str]] = []
        self.delay = delay
        self.hang_on_run = hang_on_run
        self.active = 0
        self.peak = 0
        self.workspace_files: dict[str, bytes] = {}
        self.workspace_dir: Path | None = None

    async def __call__(self, argv: list[str]) -> tuple[int, bytes, bytes]:
        self.argvs.append(list(argv))
        if argv[:2] == ["docker", "kill"]:
            return 0, b"", b""
        mount = next(part for part in argv if part.endswith(":/workspace:rw"))
        host = Path(mount.rsplit(":/workspace:rw", 1)[0])
        self.workspace_dir = host
        self.workspace_files = {
            str(path.relative_to(host)).replace("\\", "/"): path.read_bytes()
            for path in host.rglob("*")
            if path.is_file()
        }
        self.active += 1
        self.peak = max(self.peak, self.active)
        try:
            if self.hang_on_run:
                await asyncio.sleep(30)
            await asyncio.sleep(self.delay)
        finally:
            self.active -= 1
        return 0, b"out", b"err"


async def test_container_is_networkless_readonly_limited_and_removed() -> None:
    docker = FakeDocker()
    runner = ServerDockerSandboxRunner(max_concurrency=2, docker=docker, scripts_dir="/scripts")
    result = await runner.run_ephemeral_command(
        image="enterprise-sandbox:py312-node22",
        command="python3 /opt/skill-scripts/validate_openapi.py --file specs/api.json",
        injected_files={"specs/api.json": b"{}"},
        timeout=5,
    )
    assert result == {"exit_code": 0, "stdout": "out", "stderr": "err"}
    argv = docker.argvs[0]
    assert argv[:2] == ["docker", "run"]
    assert "--rm" in argv
    assert argv[argv.index("--network") + 1] == "none"
    assert argv[argv.index("--memory") + 1] == "512m"
    assert argv[argv.index("--pids-limit") + 1] == "64"
    assert "--read-only" in argv
    assert argv[argv.index("--cap-drop") + 1] == "ALL"
    assert argv[argv.index("--workdir") + 1] == "/workspace"
    assert "/scripts:/opt/skill-scripts:ro" in argv
    assert argv[-4:] == [
        "enterprise-sandbox:py312-node22",
        "sh",
        "-c",
        "python3 /opt/skill-scripts/validate_openapi.py --file specs/api.json",
    ]
    assert docker.workspace_files == {"specs/api.json": b"{}"}
    assert docker.workspace_dir is not None
    assert not docker.workspace_dir.exists()


async def test_only_the_configured_number_of_containers_run_at_once() -> None:
    docker = FakeDocker(delay=0.05)
    runner = ServerDockerSandboxRunner(max_concurrency=2, docker=docker, scripts_dir="/scripts")
    await asyncio.gather(
        *(
            runner.run_ephemeral_command(image="img", command="true", injected_files={}, timeout=5)
            for _ in range(6)
        )
    )
    assert docker.peak == 2
    assert len([argv for argv in docker.argvs if argv[1] == "run"]) == 6


async def test_a_timed_out_container_is_killed_by_name() -> None:
    docker = FakeDocker(hang_on_run=True)
    runner = ServerDockerSandboxRunner(max_concurrency=1, docker=docker, scripts_dir="/scripts")
    result = await runner.run_ephemeral_command(image="img", command="sleep 99", injected_files={}, timeout=0.05)
    assert result["exit_code"] == 124
    assert "逾時" in result["stderr"]
    run_argv = docker.argvs[0]
    name = run_argv[run_argv.index("--name") + 1]
    assert ["docker", "kill", name] in docker.argvs
    assert docker.workspace_dir is not None
    assert not docker.workspace_dir.exists()


@pytest.mark.parametrize("path", ["../escape.txt", "/etc/passwd", "a/../../b"])
async def test_injected_files_cannot_escape_the_workspace(path: str) -> None:
    runner = ServerDockerSandboxRunner(max_concurrency=1, docker=FakeDocker(), scripts_dir="/scripts")
    with pytest.raises(ValueError, match="工作區"):
        await runner.run_ephemeral_command(image="img", command="true", injected_files={path: b"x"}, timeout=5)
