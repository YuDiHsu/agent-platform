"""HITL decisions and checkpoint resume. Implements: REQ-007, REQ-012, TC-M2-02."""

from datetime import UTC, datetime
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.api.deps import CurrentUser, get_llm, require_user
from app.db.models import ChatSession, HitlApprovalRequest
from app.db.session import database_session
from app.llm.gemma_client import GemmaSGLangClient
from app.orchestrator.supervisor import ChatTurn

router = APIRouter()


class HitlDecision(BaseModel):
    status: Literal["APPROVED", "MODIFIED", "REJECTED"]
    user_modified_payload: dict[str, Any] | None = None
    rejection_reason: str | None = Field(default=None, max_length=500)


@router.post("/hitl/{request_id}/decide")
async def decide_hitl(
    request_id: UUID,
    body: HitlDecision,
    user: CurrentUser = Depends(require_user),
    llm: GemmaSGLangClient = Depends(get_llm),
) -> dict[str, Any]:
    async with database_session() as db:
        row = await db.get(HitlApprovalRequest, request_id)
        if row is None or row.user_id != user.id:
            raise HTTPException(status_code=403, detail="只能決定自己的審批單")
        if row.status != "PENDING":
            raise HTTPException(status_code=409, detail="這張審批單已經決定過")
        if body.status == "MODIFIED" and not body.user_modified_payload:
            raise HTTPException(status_code=422, detail="修改後放行需要新的參數")
        chat = await db.get(ChatSession, row.session_id)
        query = ""
        if chat is not None and chat.checkpoint:
            query = str(chat.checkpoint.get("original_user_query", ""))
        payload = body.user_modified_payload if body.status == "MODIFIED" else dict(row.proposed_payload)
        if body.status == "REJECTED":
            reason = body.rejection_reason or "使用者拒絕這次操作"
            instruction = (
                f"target_role_code: {row.executing_role_code}\n"
                f"使用者拒絕了工具 {row.tool_name}。原因：{reason}。"
                "請取消這次呼叫並收尾，不要再呼叫工具。"
            )
            executed: dict[str, Any] | None = None
        else:
            instruction = (
                f"target_role_code: {row.executing_role_code}\n"
                f"使用者已核准工具 {row.tool_name}，請使用這些參數完成交付、不要再呼叫工具：{payload}"
            )
            executed = payload
            if body.status == "MODIFIED":
                row.user_modified_payload = body.user_modified_payload
        row.status = body.status
        row.decided_at = datetime.now(UTC)
        ticket_id = row.ticket_id
        session_id = row.session_id

    outcome = await ChatTurn(llm, user_id=user.id, session_id=session_id, message=query).resume_after_decision(
        ticket_id=ticket_id,
        instructions=instruction,
    )
    return {
        "status": body.status,
        "executed_payload": executed,
        "ticket_status": "COMPLETED" if outcome.kind == "completed" else outcome.kind,
    }
