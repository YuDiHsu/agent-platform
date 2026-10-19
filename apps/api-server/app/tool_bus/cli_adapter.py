"""Expose CLI skills as one tool on the unified bus. Implements: REQ-015, REQ-016, ADR-0002."""

from typing import Any
from uuid import UUID

from app.tool_bus.adapter import BaseToolAdapter, ToolContext, ToolSpec, register_tool_adapter
from app.tool_bus.cli_executor import CLI_TOOL_NAME, CliRejected, SkillCLIExecutor
from app.tool_bus.sandbox_runner import get_sandbox_runner


@register_tool_adapter
class SkillCliAdapter(BaseToolAdapter):
    namespace = "skill_cli"

    def list_tools(self) -> list[ToolSpec]:
        return [
            ToolSpec(
                CLI_TOOL_NAME,
                "執行 CLI 技能",
                "執行已啟用技能的參數化命令列。READ 技能直接執行，COMMIT 技能先審批。",
                "READ",
                {
                    "type": "object",
                    "properties": {"skill_code": {"type": "string"}, "cli_args": {"type": "object"}},
                    "required": ["skill_code", "cli_args"],
                },
            )
        ]

    async def health_check(self) -> bool:
        return True

    async def execute(self, tool_name: str, arguments: dict[str, Any], context: ToolContext) -> dict[str, Any]:
        if tool_name != CLI_TOOL_NAME:
            raise ValueError(f"不支援的 CLI 工具: {tool_name}")
        skill_code = str(arguments.get("skill_code", ""))
        cli_args = arguments.get("cli_args")
        executor = SkillCLIExecutor(get_sandbox_runner())
        try:
            if not isinstance(cli_args, dict):
                raise CliRejected("cli_args 必須是物件")
            return await executor.execute(
                session_id=UUID(context.session_id),
                user_id=UUID(context.user_id),
                role_code=context.role_code,
                skill_code=skill_code,
                cli_args=cli_args,
            )
        except CliRejected as exc:
            return {
                "blocked": True,
                "skill_code": skill_code,
                "execution_target": "",
                "command": "",
                "exit_code": -1,
                "stdout": "",
                "stderr": str(exc),
                "duration_ms": 0,
            }
