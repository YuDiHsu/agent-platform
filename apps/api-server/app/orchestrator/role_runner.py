"""Run one claimed ticket, then either store a claim-check or hibernate.

Implements: REQ-002, REQ-008, ADR-0002, ADR-0003.
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import UUID

from app.db.models import ChatSession, HitlApprovalRequest, TaskTicket, User
from app.db.session import database_session
from app.llm.gemma_client import GemmaSGLangClient
from app.orchestrator.artifact_manager import store_artifact
from app.orchestrator.state import ArtifactPointer, SubAgentExecutionOutput

def _activated_skill(output: SubAgentExecutionOutput) -> str | None:
    if output.execution_status != "NEED_TOOL_CALL" or not output.tool_calls:
        return None
    call = output.tool_calls[0]
    if call.tool_name != "activate_skill":
        return None
    code = call.arguments.get("skill_code")
    return str(code) if code else None


BROWSER_WAIT_TOOLS = {"workspace_list_files", "workspace_read_file"}


@dataclass
class StepOutcome:
    kind: Literal["completed", "hibernated", "failed", "blocked", "circuit"]
    wait_status: str | None = None
    pointer: ArtifactPointer | None = None
    content_body: str | None = None
    created_at: str | None = None
    hitl: dict[str, Any] | None = None
    detail: str | None = None
    skill_activated: dict[str, str] | None = None


def wait_status_for(tool_name: str) -> str:
    if tool_name in BROWSER_WAIT_TOOLS:
        return "WAITING_BROWSER"
    return "WAITING_HITL"


def execution_target_for(tool_name: str) -> str:
    if tool_name.startswith("workspace_"):
        return "BROWSER_WS_RPC"
    if tool_name == "execute_skill_cli":
        return "SERVER_SANDBOX_CLI"
    return "SERVER_MCP"


class RoleRunner:
    def __init__(self, llm: GemmaSGLangClient) -> None:
        self._llm = llm

    async def infer_and_finish(
        self,
        *,
        chat_session_id: UUID,
        ticket_id: UUID,
        role_code: str,
        user_id: UUID,
        original_query: str,
        instructions: str,
    ) -> StepOutcome:
        """Call the model only after the database session has been closed."""

        prompt = await self._system_prompt(
            role_code=role_code,
            user_id=user_id,
            session_id=chat_session_id,
            query=original_query,
        )
        activated: dict[str, str] | None = None
        try:
            output = await self._llm.generate_structured(
                system_prompt=prompt,
                messages=[
                    {
                        "role": "user",
                        "content": f"target_role_code: {role_code}\n使用者原話：{original_query}\n{instructions}",
                    }
                ],
                response_model=SubAgentExecutionOutput,
            )
            if _activated_skill(output) is not None:
                skill_code = _activated_skill(output)
                assert skill_code is not None
                await self._remember_skill(chat_session_id, role_code, skill_code)
                activated = {"role_code": role_code, "skill_code": skill_code}
                prompt = await self._system_prompt(
                    role_code=role_code,
                    user_id=user_id,
                    session_id=chat_session_id,
                    query=original_query,
                )
                output = await self._llm.generate_structured(
                    system_prompt=prompt,
                    messages=[
                        {
                            "role": "user",
                            "content": f"target_role_code: {role_code}\n已啟用技能 {skill_code}。使用者原話：{original_query}\n{instructions}",
                        }
                    ],
                    response_model=SubAgentExecutionOutput,
                )
            for _ in range(2):
                if output.execution_status != "NEED_TOOL_CALL" or not output.tool_calls:
                    break
                runnable: list[tuple[str, dict[str, Any]]] = []
                for call in output.tool_calls:
                    if call.tool_name in BROWSER_WAIT_TOOLS:
                        break
                    tier = await self._action_tier(call.tool_name)
                    if tier == "COMMIT":
                        break
                    runnable.append((call.tool_name, dict(call.arguments)))
                if not runnable:
                    break
                from app.tool_bus.bus import UnifiedToolBus

                results = await UnifiedToolBus().dispatch(
                    role_code=role_code,
                    user_id=user_id,
                    session_id=chat_session_id,
                    calls=runnable,
                )
                summary = "；".join(
                    f"{item.tool_name} {'已直接執行' if item.ok else '執行失敗'} {item.output or item.error}"
                    for item in results
                )
                output = await self._llm.generate_structured(
                    system_prompt=prompt,
                    messages=[
                        {
                            "role": "user",
                            "content": (
                                f"target_role_code: {role_code}\n"
                                f"{summary}。請完成交付，不要再呼叫工具。"
                            ),
                        }
                    ],
                    response_model=SubAgentExecutionOutput,
                )
        except Exception as exc:
            await self._fail(ticket_id, str(exc))
            return StepOutcome(kind="failed", detail=str(exc))
        async with database_session() as db:
            ticket = await db.get(TaskTicket, ticket_id)
            if ticket is None:
                return StepOutcome(kind="failed", detail="工單不存在")
            ticket.locked_by_worker = None
            ticket.locked_at = None
            if output.execution_status == "COMPLETED":
                outcome = await self._complete(
                    db,
                    ticket,
                    chat_session_id=chat_session_id,
                    role_code=role_code,
                    output=output,
                )
            elif output.execution_status == "NEED_TOOL_CALL":
                outcome = await self._wait(
                    db,
                    ticket,
                    chat_session_id=chat_session_id,
                    user_id=user_id,
                    role_code=role_code,
                    output=output,
                )
            else:
                ticket.status = "FAILED"
                ticket.error_log = output.thought_process
                outcome = StepOutcome(kind="failed", detail=output.thought_process)
            outcome.skill_activated = activated
            return outcome

    async def _complete(
        self,
        db: Any,
        ticket: TaskTicket,
        *,
        chat_session_id: UUID,
        role_code: str,
        output: SubAgentExecutionOutput,
    ) -> StepOutcome:
        if (
            not output.artifact_title
            or not output.artifact_type
            or output.summary_200_words is None
            or output.full_markdown_content is None
        ):
            ticket.status = "FAILED"
            ticket.error_log = "完成狀態缺少交付物"
            return StepOutcome(kind="failed", detail="完成狀態缺少交付物")
        pointer, created_at = await store_artifact(
            db,
            session_id=chat_session_id,
            producer_role_code=role_code,
            artifact_type=output.artifact_type,
            title=output.artifact_title,
            summary=output.summary_200_words,
            content_body=output.full_markdown_content,
            handoff_notes=output.handoff_notes_for_next_role,
        )
        ticket.status = "COMPLETED"
        ticket.output_artifact_id = UUID(pointer.artifact_id)
        ticket.completed_at = datetime.now(UTC)
        return StepOutcome(
            kind="completed",
            pointer=pointer,
            content_body=output.full_markdown_content,
            created_at=created_at,
        )

    async def _wait(
        self,
        db: Any,
        ticket: TaskTicket,
        *,
        chat_session_id: UUID,
        user_id: UUID,
        role_code: str,
        output: SubAgentExecutionOutput,
    ) -> StepOutcome:
        if not output.tool_calls:
            ticket.status = "FAILED"
            ticket.error_log = "需要工具但未提供工具名稱"
            return StepOutcome(kind="failed", detail="需要工具但未提供工具名稱")
        call = output.tool_calls[0]
        status = wait_status_for(call.tool_name)
        ticket.status = status
        hitl: dict[str, Any] | None = None
        if status == "WAITING_HITL":
            preview = f"{role_code} 請求執行 {call.tool_name}"
            tier = await self._tier_in(db, call.tool_name)
            if tier != "COMMIT":
                ticket.status = "FAILED"
                ticket.error_log = f"{call.tool_name} 是 {tier}，不進入審批"
                return StepOutcome(kind="failed", detail=ticket.error_log)
            row = HitlApprovalRequest(
                ticket_id=ticket.id,
                session_id=chat_session_id,
                user_id=user_id,
                executing_role_code=role_code,
                tool_name=call.tool_name,
                execution_target=execution_target_for(call.tool_name),
                action_tier=tier,
                preview_title=preview,
                proposed_payload=call.arguments,
                status="PENDING",
            )
            db.add(row)
            await db.flush()
            await db.refresh(row)
            hitl = {
                "hitl_request_id": str(row.id),
                "ticket_id": str(ticket.id),
                "executing_role_code": role_code,
                "tool_name": call.tool_name,
                "execution_target": row.execution_target,
                "preview_title": preview,
                "proposed_payload": call.arguments,
                "status": "PENDING",
            }
        return StepOutcome(kind="hibernated", wait_status=status, hitl=hitl, detail=call.tool_name)

    async def _action_tier(self, tool_name: str) -> str:
        async with database_session() as db:
            return await self._tier_in(db, tool_name)

    async def _tier_in(self, db: Any, tool_name: str) -> str:
        from sqlalchemy import select

        from app.db.models import ToolRegistry

        tool = await db.scalar(select(ToolRegistry).where(ToolRegistry.code == tool_name))
        if tool is None or tool.action_tier not in {"READ", "DRAFT", "COMMIT"}:
            return "COMMIT"
        return str(tool.action_tier)

    async def _system_prompt(self, *, role_code: str, user_id: UUID, session_id: UUID, query: str) -> str:
        from sqlalchemy import select

        from app.db.models import AgentRole
        from app.llm.embedding_client import EmbeddingClient
        from app.orchestrator.tool_rag import compile_role_turn

        query_embedding = await EmbeddingClient().embed_text(query)
        async with database_session() as db:
            role = await db.scalar(select(AgentRole).where(AgentRole.code == role_code))
            user = await db.get(User, user_id)
            if role is None or user is None:
                return "你是企業角色代理。只根據產出物指標工作，不要在回覆中複寫上游全文。"
            chat = await db.get(ChatSession, session_id)
            activated: list[str] = []
            if chat is not None and chat.checkpoint:
                raw = chat.checkpoint.get("activated_skills", {}).get(role_code, [])
                activated = [str(item) for item in raw]
            return await compile_role_turn(
                db,
                role=role,
                user_id=user_id,
                user_department=user.department,
                query_embedding=query_embedding,
                activated_skill_codes=activated,
            )

    async def _remember_skill(self, session_id: UUID, role_code: str, skill_code: str) -> None:
        async with database_session() as db:
            chat = await db.get(ChatSession, session_id)
            if chat is None:
                return
            checkpoint = dict(chat.checkpoint or {})
            by_role = dict(checkpoint.get("activated_skills", {}))
            codes = list(by_role.get(role_code, []))
            if skill_code not in codes:
                codes.append(skill_code)
            by_role[role_code] = codes
            checkpoint["activated_skills"] = by_role
            chat.checkpoint = checkpoint

    async def _fail(self, ticket_id: UUID, detail: str) -> None:
        async with database_session() as db:
            ticket = await db.get(TaskTicket, ticket_id)
            if ticket is None:
                return
            ticket.status = "FAILED"
            ticket.error_log = detail
            ticket.locked_by_worker = None
            ticket.locked_at = None
