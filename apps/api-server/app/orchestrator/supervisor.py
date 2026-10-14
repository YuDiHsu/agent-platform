"""Topological DAG runner with hop limit and checkpoint hibernation.

Implements: REQ-002, REQ-008, REQ-010, ADR-0002, ADR-0003.
"""

import asyncio
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import func, select, text

from app.db.models import AgentRole, ChatMessage, ChatSession, TaskTicket, User
from app.db.session import database_session
from app.llm.gemma_client import GemmaSGLangClient
from app.orchestrator.artifact_manager import compose_instructions
from app.orchestrator.dag import MAX_HOPS, ancestor_labels, execution_waves
from app.orchestrator.role_runner import RoleRunner, StepOutcome
from app.orchestrator.state import (
    ArtifactPointer,
    DAGTaskNode,
    OrchestratorPlanOutput,
    build_checkpoint,
)

logger = logging.getLogger(__name__)

QUOTA_MESSAGE = "Token 額度已用盡，對話已暫停於 PAUSED_QUOTA_EXCEEDED。"
CONCURRENT_MESSAGE = "同時執行中的工單已達個人上限，工作區已休眠。"
CIRCUIT_MESSAGE = "已達 max_hops=8，後續步驟標記為 CIRCUIT_BROKEN。"
INVALID_PLAN_MESSAGE = "任務圖含有循環依賴或無效步驟，已中止。"
UNKNOWN_ROLE_MESSAGE = "任務圖含有未知角色，已中止。"
FAILED_MESSAGE = "角色執行失敗，工作區已停止。"
HITL_MESSAGE = "已暫停等待人工審批。"
BROWSER_MESSAGE = "已暫停等待瀏覽器重新連線。"


@dataclass
class SseEvent:
    event: str
    data: dict[str, Any]


class ChatTurn:
    """One user message, detached from the browser's HTTP connection."""

    def __init__(
        self,
        llm: GemmaSGLangClient,
        *,
        user_id: UUID,
        session_id: UUID,
        message: str,
    ) -> None:
        self._llm = llm
        self._runner = RoleRunner(llm)
        self._user_id = user_id
        self._session_id = session_id
        self._message = message
        self._worker_id = f"chat-{uuid4().hex[:8]}"
        self._hop = 0
        self._hop_lock = asyncio.Lock()
        self._slots = asyncio.Semaphore(1)
        self._max_concurrent = 1
        self._goal = ""
        self._pointers: dict[int, ArtifactPointer] = {}
        self._snapshot: list[dict[str, Any]] = []
        self._queue: asyncio.Queue[SseEvent | None] = asyncio.Queue()

    async def run(self) -> None:
        try:
            await self._run()
        except Exception:
            logger.exception("chat turn failed for session %s", self._session_id)
            await self._mark_session("FAILED", None)
            await self._emit(
                "final_response",
                role_code="ORCH",
                content=FAILED_MESSAGE,
                payload={"text": FAILED_MESSAGE, "session_status": "FAILED"},
            )
        finally:
            self._queue.put_nowait(None)

    def events(self) -> asyncio.Queue[SseEvent | None]:
        return self._queue

    async def _run(self) -> None:
        await self._remember_user_message()
        if await self._pause_for_token_quota():
            return
        await self._load_quota()
        plan = await self._llm.generate_structured(
            system_prompt=(
                "你是主代理 ORCH。能直接回答就用 DIRECT_ANSWER；"
                "跨角色工作就用 DELEGATE_DAG，且 depends_on_steps 必須無環。"
            ),
            messages=[{"role": "user", "content": self._message}],
            response_model=OrchestratorPlanOutput,
        )
        if plan.intent_mode == "DIRECT_ANSWER" or not plan.dag_steps:
            await self._finish_direct(plan)
            return
        waves = execution_waves(plan.dag_steps)
        if waves is None:
            await self._finish_invalid(INVALID_PLAN_MESSAGE)
            return
        known_roles = await self._role_codes()
        if any(step.target_role_code not in known_roles for step in plan.dag_steps):
            await self._finish_invalid(UNKNOWN_ROLE_MESSAGE)
            return
        self._goal = plan.goal_statement
        await self._create_tickets(plan)
        await self._emit(
            "orchestrator_plan",
            role_code="ORCH",
            content=plan.reasoning,
            payload={
                "intent_mode": plan.intent_mode,
                "reasoning": plan.reasoning,
                "goal_statement": plan.goal_statement,
                "dag_steps": [
                    {
                        "step_id": node["step_id"],
                        "target_role_code": node["target_role_code"],
                        "task_title": node["task_title"],
                        "status": "PENDING",
                        "depends_on_steps": node["depends_on_steps"],
                    }
                    for node in self._snapshot
                ],
            },
        )
        for wave in waves:
            outcomes = await asyncio.gather(*(self._guarded(node) for node in self._nodes_for(wave)))
            await self._sync_snapshot()
            if any(item.kind == "blocked" for item in outcomes):
                await self._hibernate(CONCURRENT_MESSAGE, "CONCURRENT_TICKET_QUOTA", None, None)
                return
            hibernated = next((item for item in outcomes if item.kind == "hibernated"), None)
            if hibernated is not None:
                message = BROWSER_MESSAGE if hibernated.wait_status == "WAITING_BROWSER" else HITL_MESSAGE
                waiting = next(
                    (
                        node
                        for node in self._snapshot
                        if node["status"] in {"WAITING_HITL", "WAITING_BROWSER"}
                    ),
                    None,
                )
                await self._hibernate(
                    message,
                    hibernated.wait_status or "WAITING_HITL",
                    hibernated.hitl,
                    None if waiting is None else int(waiting["step_id"]),
                )
                return
            if any(item.kind == "circuit" for item in outcomes):
                await self._break_circuit()
                return
            if any(item.kind == "failed" for item in outcomes):
                await self._mark_session("FAILED", None)
                await self._emit(
                    "final_response",
                    role_code="ORCH",
                    content=FAILED_MESSAGE,
                    payload={"text": FAILED_MESSAGE, "session_status": "FAILED"},
                )
                return
        titles = [self._pointers[step_id].title for step_id in sorted(self._pointers)]
        synthesis = "已完成：" + "、".join(titles)
        await self._mark_session("COMPLETED", None)
        await self._emit(
            "final_response",
            role_code="ORCH",
            content=synthesis,
            payload={"text": synthesis, "session_status": "COMPLETED"},
        )

    def _nodes_for(self, wave: list[DAGTaskNode]) -> list[dict[str, Any]]:
        wanted = {step.step_id for step in wave}
        return [node for node in self._snapshot if node["step_id"] in wanted]

    async def _guarded(self, node: dict[str, Any]) -> StepOutcome:
        async with self._slots:
            async with self._hop_lock:
                blocked = await self._other_sessions_are_full()
                if blocked:
                    return StepOutcome(kind="blocked")
                if self._hop >= MAX_HOPS:
                    await self._mark_ticket_circuit(UUID(str(node["ticket_id"])))
                    return StepOutcome(kind="circuit")
                self._hop += 1
                hop = self._hop
                pointers = [
                    self._pointers[dependency]
                    for dependency in node["depends_on_steps"]
                    if dependency in self._pointers
                ]
                ancestry = list(node["goal_ancestry"])
                instructions = compose_instructions(
                    detailed=str(node["detailed_instructions"]),
                    goal_ancestry=ancestry,
                    pointers=pointers,
                )
                await self._claim(UUID(str(node["ticket_id"])), hop, instructions, pointers)
            await self._emit(
                "role_switched",
                role_code=str(node["target_role_code"]),
                content=f"{node['target_role_code']} 開始執行：{node['task_title']}",
                payload={
                    "active_role": node["target_role_code"],
                    "step_id": node["step_id"],
                    "task_title": node["task_title"],
                },
            )
            outcome = await self._runner.infer_and_finish(
                chat_session_id=self._session_id,
                ticket_id=UUID(str(node["ticket_id"])),
                role_code=str(node["target_role_code"]),
                user_id=self._user_id,
                original_query=self._message,
                instructions=instructions,
            )
        if outcome.kind == "completed" and outcome.pointer is not None:
            self._pointers[int(node["step_id"])] = outcome.pointer
            payload = outcome.pointer.model_dump()
            payload["step_id"] = node["step_id"]
            payload["content_body"] = outcome.content_body or ""
            payload["created_at"] = outcome.created_at or ""
            await self._emit(
                "artifact_created",
                role_code=str(node["target_role_code"]),
                content=outcome.pointer.summary_200_words,
                payload=payload,
            )
        return outcome

    async def _claim(
        self,
        ticket_id: UUID,
        hop: int,
        instructions: str,
        pointers: list[ArtifactPointer],
    ) -> None:
        async with database_session() as db:
            ticket = await db.get(TaskTicket, ticket_id)
            if ticket is None:
                return
            ticket.status = "IN_PROGRESS"
            ticket.hop_count = hop
            ticket.locked_by_worker = self._worker_id
            ticket.locked_at = datetime.now(UTC)
            ticket.input_instructions = instructions
            ticket.input_artifact_ids = [pointer.artifact_id for pointer in pointers]

    async def _other_sessions_are_full(self) -> bool:
        async with database_session() as db:
            await db.execute(
                text("SELECT pg_advisory_xact_lock(:key)"),
                {"key": self._user_id.int % (2**31)},
            )
            running = await db.scalar(
                select(func.count())
                .select_from(TaskTicket)
                .where(
                    TaskTicket.requester_user_id == self._user_id,
                    TaskTicket.status == "IN_PROGRESS",
                    TaskTicket.session_id != self._session_id,
                )
            )
            return int(running or 0) >= self._max_concurrent

    async def _pause_for_token_quota(self) -> bool:
        async with database_session() as db:
            user = await db.get(User, self._user_id)
            if user is None:
                return False
            if user.token_quota_limit is None or user.tokens_consumed_total < user.token_quota_limit:
                return False
            ticket = TaskTicket(
                session_id=self._session_id,
                requester_user_id=self._user_id,
                assigned_role_code="ORCH",
                title="額度暫停",
                status="PAUSED_QUOTA_EXCEEDED",
                hop_count=0,
                max_hops=MAX_HOPS,
                goal_ancestry=[self._message],
                input_instructions=self._message,
                locked_by_worker=None,
            )
            db.add(ticket)
            await db.flush()
            chat = await db.get(ChatSession, self._session_id)
            if chat is not None:
                chat.status = "HIBERNATING"
                chat.hold_reason = "PAUSED_QUOTA_EXCEEDED"
                chat.checkpoint = build_checkpoint(
                    original_user_query=self._message,
                    goal_statement=self._message,
                    dag_plan=[],
                    completed_step_ids=[],
                    artifact_pointers=[],
                    hop_count=0,
                    wait_status="PAUSED_QUOTA_EXCEEDED",
                    active_ticket_id=str(ticket.id),
                )
                chat.updated_at = datetime.now(UTC)
        await self._emit(
            "checkpoint_hibernated",
            role_code="ORCH",
            content=QUOTA_MESSAGE,
            payload={"text": QUOTA_MESSAGE, "status": "PAUSED_QUOTA_EXCEEDED", "step_id": None, "hitl": None},
        )
        return True

    async def _load_quota(self) -> None:
        async with database_session() as db:
            user = await db.get(User, self._user_id)
            limit = 4 if user is None else user.max_concurrent_tickets
        self._max_concurrent = max(1, limit)
        self._slots = asyncio.Semaphore(self._max_concurrent)

    async def _role_codes(self) -> set[str]:
        async with database_session() as db:
            codes = (await db.scalars(select(AgentRole.code))).all()
        return set(codes)

    async def _create_tickets(self, plan: OrchestratorPlanOutput) -> None:
        by_id = {step.step_id: step for step in plan.dag_steps}
        async with database_session() as db:
            chat = await db.get(ChatSession, self._session_id)
            if chat is None:
                return
            if chat.title == "新的協作":
                chat.title = self._message[:40]
            chat.goal_statement = plan.goal_statement
            chat.status = "ACTIVE"
            snapshot: list[dict[str, Any]] = []
            for step in plan.dag_steps:
                ancestry = [plan.goal_statement, *ancestor_labels(step.step_id, by_id)]
                ticket = TaskTicket(
                    session_id=self._session_id,
                    requester_user_id=self._user_id,
                    assigned_role_code=step.target_role_code,
                    title=step.task_title,
                    status="PENDING",
                    hop_count=0,
                    max_hops=MAX_HOPS,
                    goal_ancestry=ancestry,
                    input_instructions=step.detailed_instructions,
                )
                db.add(ticket)
                await db.flush()
                snapshot.append(
                    {
                        "step_id": step.step_id,
                        "ticket_id": str(ticket.id),
                        "target_role_code": step.target_role_code,
                        "task_title": step.task_title,
                        "detailed_instructions": step.detailed_instructions,
                        "depends_on_steps": list(step.depends_on_steps),
                        "goal_ancestry": ancestry,
                        "status": "PENDING",
                    }
                )
            chat.dag_snapshot = snapshot
            chat.updated_at = datetime.now(UTC)
            self._snapshot = snapshot

    async def _finish_direct(self, plan: OrchestratorPlanOutput) -> None:
        text_out = plan.direct_response_to_user or plan.reasoning
        async with database_session() as db:
            chat = await db.get(ChatSession, self._session_id)
            if chat is not None:
                chat.goal_statement = plan.goal_statement
                chat.status = "COMPLETED"
                chat.checkpoint = None
                chat.hold_reason = None
                if chat.title == "新的協作":
                    chat.title = self._message[:40]
                chat.updated_at = datetime.now(UTC)
        await self._emit(
            "orchestrator_plan",
            role_code="ORCH",
            content=plan.reasoning,
            payload={
                "intent_mode": "DIRECT_ANSWER",
                "reasoning": plan.reasoning,
                "goal_statement": plan.goal_statement,
                "dag_steps": [],
            },
        )
        await self._emit(
            "final_response",
            role_code="ORCH",
            content=text_out,
            payload={"text": text_out, "session_status": "COMPLETED"},
        )

    async def _finish_invalid(self, message: str) -> None:
        await self._mark_session("FAILED", None)
        await self._emit(
            "final_response",
            role_code="ORCH",
            content=message,
            payload={"text": message, "session_status": "FAILED"},
        )

    async def _hibernate(
        self,
        message: str,
        reason: str,
        hitl: dict[str, Any] | None,
        step_id: int | None,
    ) -> None:
        active = hitl["ticket_id"] if hitl is not None else None
        checkpoint = build_checkpoint(
            original_user_query=self._message,
            goal_statement=self._goal or self._message,
            dag_plan=self._snapshot,
            completed_step_ids=sorted(self._pointers),
            artifact_pointers=[self._pointers[step_id] for step_id in sorted(self._pointers)],
            hop_count=self._hop,
            wait_status=reason,
            active_ticket_id=str(active) if active is not None else None,
        )
        async with database_session() as db:
            chat = await db.get(ChatSession, self._session_id)
            if chat is not None:
                chat.status = "HIBERNATING"
                chat.hold_reason = reason
                chat.checkpoint = checkpoint
                chat.updated_at = datetime.now(UTC)
            tickets = (
                await db.scalars(select(TaskTicket).where(TaskTicket.session_id == self._session_id))
            ).all()
            by_id = {str(ticket.id): ticket.status for ticket in tickets}
            if chat is not None:
                chat.dag_snapshot = [{**node, "status": by_id.get(str(node["ticket_id"]), node["status"])} for node in self._snapshot]
        await self._emit(
            "checkpoint_hibernated",
            role_code="ORCH",
            content=message,
            payload={"text": message, "status": reason, "hitl": hitl, "step_id": step_id},
        )

    async def _break_circuit(self) -> None:
        async with database_session() as db:
            tickets = (
                await db.scalars(select(TaskTicket).where(TaskTicket.session_id == self._session_id))
            ).all()
            for ticket in tickets:
                if ticket.status in {"PENDING", "IN_PROGRESS"}:
                    ticket.status = "CIRCUIT_BROKEN"
                    ticket.error_log = "超過 max_hops=8"
                    ticket.locked_by_worker = None
                    ticket.locked_at = None
                    if ticket.hop_count == 0:
                        ticket.hop_count = MAX_HOPS + 1
            chat = await db.get(ChatSession, self._session_id)
            if chat is not None:
                chat.status = "CIRCUIT_BROKEN"
                chat.hold_reason = "CIRCUIT_BROKEN"
                chat.checkpoint = None
                by_id = {str(ticket.id): ticket.status for ticket in tickets}
                chat.dag_snapshot = [
                    {**node, "status": by_id.get(str(node["ticket_id"]), "CIRCUIT_BROKEN")} for node in self._snapshot
                ]
                chat.updated_at = datetime.now(UTC)
        await self._emit(
            "final_response",
            role_code="ORCH",
            content=CIRCUIT_MESSAGE,
            payload={"text": CIRCUIT_MESSAGE, "session_status": "CIRCUIT_BROKEN"},
        )

    async def _mark_ticket_circuit(self, ticket_id: UUID) -> None:
        async with database_session() as db:
            ticket = await db.get(TaskTicket, ticket_id)
            if ticket is None:
                return
            ticket.status = "CIRCUIT_BROKEN"
            ticket.hop_count = MAX_HOPS + 1
            ticket.error_log = "超過 max_hops=8"
            ticket.locked_by_worker = None
            ticket.locked_at = None

    async def _sync_snapshot(self) -> None:
        async with database_session() as db:
            chat = await db.get(ChatSession, self._session_id)
            if chat is None:
                return
            tickets = (
                await db.scalars(select(TaskTicket).where(TaskTicket.session_id == self._session_id))
            ).all()
            by_id = {str(ticket.id): ticket.status for ticket in tickets}
            chat.dag_snapshot = [
                {**node, "status": by_id.get(str(node["ticket_id"]), node["status"])} for node in self._snapshot
            ]
            self._snapshot = list(chat.dag_snapshot)
            chat.updated_at = datetime.now(UTC)

    async def _mark_session(self, status: str, hold_reason: str | None) -> None:
        async with database_session() as db:
            chat = await db.get(ChatSession, self._session_id)
            if chat is None:
                return
            chat.status = status
            chat.hold_reason = hold_reason
            if status in {"COMPLETED", "FAILED", "CIRCUIT_BROKEN"}:
                chat.checkpoint = None
            chat.updated_at = datetime.now(UTC)

    async def _remember_user_message(self) -> None:
        async with database_session() as db:
            db.add(
                ChatMessage(
                    session_id=self._session_id,
                    role_code="USER",
                    event_type="user_message",
                    content=self._message,
                    payload={},
                )
            )
            chat = await db.get(ChatSession, self._session_id)
            if chat is not None:
                chat.updated_at = datetime.now(UTC)

    async def _emit(self, event: str, *, role_code: str, content: str, payload: dict[str, Any]) -> None:
        stored = dict(payload)
        stored.pop("content_body", None)
        async with database_session() as db:
            db.add(
                ChatMessage(
                    session_id=self._session_id,
                    role_code=role_code,
                    event_type=event,
                    content=content,
                    payload=stored,
                )
            )
            chat = await db.get(ChatSession, self._session_id)
            if chat is not None and event == "role_switched":
                chat.active_role_code = str(payload.get("active_role"))
                chat.updated_at = datetime.now(UTC)
            elif chat is not None:
                chat.updated_at = datetime.now(UTC)
        self._queue.put_nowait(SseEvent(event, payload))
        await asyncio.sleep(0)
