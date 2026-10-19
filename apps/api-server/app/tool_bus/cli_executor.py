"""Parameterized, injection-safe CLI skills for two targets. Implements: REQ-015, REQ-016, TC-M5-03, TC-M5-04."""

import base64
import shlex
import time
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from jsonschema import ValidationError
from jsonschema import validate as validate_json_schema
from sqlalchemy import select

from app.core.config import settings
from app.db.models import AgentRole, AgentRoleSkill, CliExecutionLog, SkillRegistry
from app.db.session import database_session
from app.tool_bus.audit import record_security_audit
from app.tool_bus.local_fs import mount_owner_and_handle
from app.tool_bus.sandbox_runner import SandboxRunner
from app.tool_bus.ws_rpc_manager import ws_rpc_manager

CLI_TOOL_NAME = "execute_skill_cli"
SANDBOX_TARGET = "SERVER_SANDBOX_CLI"
DAEMON_TARGET = "LOCAL_DAEMON_CLI"
CLI_MODES = {SANDBOX_TARGET, DAEMON_TARGET}
TIERS = {"READ", "DRAFT", "COMMIT"}
INJECTION_EVENT = "CLI_INJECTION_BLOCKED"
NOT_AUTHORIZED_EVENT = "CLI_SKILL_NOT_AUTHORIZED"

FORBIDDEN_CLI_TOKENS = (
    "rm -rf /",
    "mkfs",
    "shutdown",
    "reboot",
    "init 0",
    "dd if=",
    ":(){ :|:& };:",
    "chmod 777",
    "chown root",
    "/etc/shadow",
    "/etc/passwd",
)

_STDOUT_LIMIT = 8000
_STDERR_LIMIT = 4000


class CliRejected(Exception):
    """The call may not run. The reason is safe to show to the model and the user."""


@dataclass(frozen=True)
class PreparedCli:
    skill_code: str
    execution_mode: str
    tier: str
    rendered_command: str
    cli_config: dict[str, Any]
    cli_args: dict[str, Any]


def skill_tier(skill: SkillRegistry) -> str:
    tier = (skill.cli_config or {}).get("action_tier")
    return str(tier) if tier in TIERS else "COMMIT"


def render_safe_command(skill: SkillRegistry, cli_args: dict[str, Any]) -> str:
    """Validate against the declared schema, quote every value, and refuse dangerous commands."""

    config = skill.cli_config or {}
    properties = config.get("allowed_args_schema", {})
    try:
        validate_json_schema(
            instance=cli_args,
            schema={
                "type": "object",
                "properties": properties,
                "required": list(properties),
                "additionalProperties": False,
            },
        )
    except ValidationError as exc:
        raise ValueError(f"CLI 參數未通過 Schema 驗證: {exc.message}") from exc

    rendered = str(config.get("command_template", ""))
    for key, value in cli_args.items():
        rendered = rendered.replace(f"{{{{{key}}}}}", shlex.quote(str(value)))
    if "{{" in rendered or "}}" in rendered:
        raise ValueError("CLI 指令範本尚有未替換的參數佔位符")
    lowered = rendered.lower()
    for token in FORBIDDEN_CLI_TOKENS:
        if token in lowered:
            raise PermissionError(f"偵測到禁止執行的危險指令片段 ({token})")
    return rendered


def cli_event(role_code: str, output: dict[str, Any]) -> dict[str, Any] | None:
    """The cli_output payload for one finished execution, or None when nothing ran."""

    if output.get("blocked") or "id" not in output or not output.get("command"):
        return None
    return {
        "id": output["id"],
        "role_code": role_code,
        "skill_code": output.get("skill_code", ""),
        "execution_target": output["execution_target"],
        "command": output["command"],
        "exit_code": output["exit_code"],
        "stdout": output.get("stdout", ""),
        "stderr": output.get("stderr", ""),
        "duration_ms": output.get("duration_ms", 0),
    }


class SkillCLIExecutor:
    def __init__(self, sandbox: SandboxRunner) -> None:
        self._sandbox = sandbox

    async def prepare(
        self,
        *,
        user_id: UUID,
        role_code: str,
        skill_code: str,
        cli_args: dict[str, Any],
    ) -> PreparedCli:
        """Load the skill, confirm the role owns it, and render the command. No external I/O."""

        async with database_session() as db:
            skill = await db.scalar(
                select(SkillRegistry)
                .join(AgentRoleSkill, AgentRoleSkill.skill_id == SkillRegistry.id)
                .join(AgentRole, AgentRole.id == AgentRoleSkill.role_id)
                .where(SkillRegistry.code == skill_code, AgentRole.code == role_code)
            )
            if skill is not None:
                db.expunge(skill)
        if skill is None or skill.is_active is False or skill.execution_mode not in CLI_MODES:
            await record_security_audit(
                actor_user_id=str(user_id),
                event_code=NOT_AUTHORIZED_EVENT,
                resource=skill_code,
                detail=f"角色 {role_code} 沒有可執行的 CLI 技能 {skill_code}",
            )
            raise CliRejected(f"技能 {skill_code} 不存在或未授權給 {role_code}")
        try:
            rendered = render_safe_command(skill, cli_args)
        except (ValueError, PermissionError) as exc:
            await record_security_audit(
                actor_user_id=str(user_id),
                event_code=INJECTION_EVENT,
                resource=skill_code,
                detail=str(exc),
            )
            raise CliRejected(str(exc)) from exc
        return PreparedCli(
            skill_code=skill.code,
            execution_mode=skill.execution_mode,
            tier=skill_tier(skill),
            rendered_command=rendered,
            cli_config=dict(skill.cli_config or {}),
            cli_args=dict(cli_args),
        )

    async def execute(
        self,
        *,
        session_id: UUID,
        user_id: UUID,
        role_code: str,
        skill_code: str,
        cli_args: dict[str, Any],
    ) -> dict[str, Any]:
        prepared = await self.prepare(user_id=user_id, role_code=role_code, skill_code=skill_code, cli_args=cli_args)
        timeout = float(prepared.cli_config.get("timeout_seconds", 30))
        started = time.monotonic()
        if prepared.execution_mode == SANDBOX_TARGET:
            result = await self._run_in_sandbox(prepared, session_id, user_id, timeout)
        else:
            result = await self._run_on_daemon(prepared, session_id, user_id, timeout)
        duration_ms = int((time.monotonic() - started) * 1000)
        output = {
            "skill_code": prepared.skill_code,
            "execution_target": prepared.execution_mode,
            "command": prepared.rendered_command,
            "exit_code": int(result["exit_code"]),
            "stdout": str(result["stdout"])[:_STDOUT_LIMIT],
            "stderr": str(result["stderr"])[:_STDERR_LIMIT],
            "duration_ms": duration_ms,
        }
        output["id"] = await self._log(session_id, user_id, role_code, output)
        return output

    async def _run_in_sandbox(
        self,
        prepared: PreparedCli,
        session_id: UUID,
        user_id: UUID,
        timeout: float,
    ) -> dict[str, Any]:
        files: dict[str, bytes] = {}
        target = prepared.cli_args.get("target_file")
        if prepared.cli_config.get("sync_local_files") and target:
            fetched = await self._read_browser_file(session_id, user_id, str(target))
            if isinstance(fetched, dict):
                return fetched
            files[str(target)] = fetched
        return await self._sandbox.run_ephemeral_command(
            image=str(prepared.cli_config.get("sandbox_image", settings.SANDBOX_IMAGE)),
            command=prepared.rendered_command,
            injected_files=files,
            timeout=timeout,
        )

    async def _read_browser_file(self, session_id: UUID, user_id: UUID, path: str) -> bytes | dict[str, Any]:
        owner_id, handle_key = await mount_owner_and_handle(str(user_id), None)
        if not handle_key:
            return _failed("尚未授權任何本機資料夾，無法同步檔案")
        try:
            rpc = await ws_rpc_manager.call_browser_tool(
                requester_user_id=str(user_id),
                mount_owner_user_id=owner_id,
                session_id=str(session_id),
                method="CLIENT_FS_READ",
                params={"browser_handle_key": handle_key, "file_path": path},
            )
        except PermissionError as exc:
            raise CliRejected(str(exc)) from exc
        if rpc.get("status") != "SUCCESS":
            return _failed(f"{rpc.get('status')}: {rpc.get('error', '無法讀取本機檔案')}")
        data = rpc.get("data")
        body = data if isinstance(data, dict) else {}
        content = str(body.get("content", ""))
        if body.get("encoding") == "base64":
            return base64.b64decode(content)
        return content.encode("utf-8")

    async def _run_on_daemon(
        self,
        prepared: PreparedCli,
        session_id: UUID,
        user_id: UUID,
        timeout: float,
    ) -> dict[str, Any]:
        rpc = await ws_rpc_manager.call_browser_tool(
            requester_user_id=str(user_id),
            mount_owner_user_id=str(user_id),
            session_id=str(session_id),
            method="DAEMON_EXEC_CLI",
            params={"command": prepared.rendered_command, "timeout": timeout},
            timeout=timeout + 5.0,
        )
        if rpc.get("status") != "SUCCESS":
            return _failed(f"{rpc.get('status')}: 本機 Local MCP Daemon 未啟動或沒有回應")
        data = rpc.get("data")
        body = data if isinstance(data, dict) else {}
        return {
            "exit_code": body.get("exit_code", 0),
            "stdout": body.get("stdout", ""),
            "stderr": body.get("stderr", ""),
        }

    async def _log(self, session_id: UUID, user_id: UUID, role_code: str, output: dict[str, Any]) -> str:
        async with database_session() as db:
            row = CliExecutionLog(
                session_id=session_id,
                user_id=user_id,
                executing_role_code=role_code,
                skill_code=str(output["skill_code"]),
                execution_target=str(output["execution_target"]),
                rendered_command=str(output["command"]),
                working_directory="/workspace" if output["execution_target"] == SANDBOX_TARGET else None,
                exit_code=int(output["exit_code"]),
                stdout_preview=str(output["stdout"]),
                stderr_preview=str(output["stderr"]),
                duration_ms=int(output["duration_ms"]),
            )
            db.add(row)
            await db.flush()
            return str(row.id)


def _failed(reason: str) -> dict[str, Any]:
    return {"exit_code": -1, "stdout": "", "stderr": reason}
