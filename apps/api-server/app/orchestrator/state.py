"""Structured contracts for the orchestrator and role turns.

Implements: REQ-002, REQ-008.
"""

from typing import Any, Literal

from pydantic import BaseModel, Field


class ArtifactPointer(BaseModel):
    """Claim-check passed between roles. The full body stays in shared_artifacts."""

    artifact_id: str
    producer_role: str
    title: str
    artifact_type: str
    summary_200_words: str


class DAGTaskNode(BaseModel):
    step_id: int = Field(..., description="1-based step ID")
    target_role_code: str = Field(..., description="Target role code from candidate pool")
    task_title: str = Field(..., description="Concise ticket title")
    detailed_instructions: str = Field(..., description="Expected deliverable instructions")
    depends_on_steps: list[int] = Field(default_factory=list)
    required_mount_or_connectors: list[str] = Field(default_factory=list)


class OrchestratorPlanOutput(BaseModel):
    intent_mode: Literal["DIRECT_ANSWER", "DELEGATE_DAG"]
    reasoning: str
    goal_statement: str
    direct_response_to_user: str | None = None
    dag_steps: list[DAGTaskNode] = Field(default_factory=list)


class SubAgentToolCall(BaseModel):
    tool_name: str = Field(..., description="MCP tool name, 'activate_skill', or 'execute_skill_cli'")
    arguments: dict[str, Any] = Field(default_factory=dict)


class SubAgentExecutionOutput(BaseModel):
    execution_status: Literal["COMPLETED", "NEED_TOOL_CALL", "REQUEST_CLARIFICATION"]
    thought_process: str
    tool_calls: list[SubAgentToolCall] = Field(default_factory=list)
    artifact_title: str | None = None
    artifact_type: (
        Literal[
            "STRATEGY_MEMO",
            "PROJECT_PLAN_WBS",
            "FINANCIAL_MODEL",
            "REQUIREMENT_SPEC",
            "ARCH_DIAGRAM",
            "CODE_DIFF",
            "EMAIL_DRAFT",
        ]
        | None
    ) = None
    summary_200_words: str | None = None
    full_markdown_content: str | None = None
    handoff_notes_for_next_role: str | None = None


def build_checkpoint(
    *,
    original_user_query: str,
    goal_statement: str,
    dag_plan: list[dict[str, Any]],
    completed_step_ids: list[int],
    artifact_pointers: list[ArtifactPointer],
    hop_count: int,
    wait_status: str,
    active_ticket_id: str | None,
) -> dict[str, Any]:
    """Hibernation document. Pointers only — never the artifact body."""

    return {
        "original_user_query": original_user_query,
        "goal_statement": goal_statement,
        "dag_plan": dag_plan,
        "completed_step_ids": completed_step_ids,
        "artifact_pointers": [pointer.model_dump() for pointer in artifact_pointers],
        "hop_count": hop_count,
        "max_hops": 8,
        "wait_status": wait_status,
        "active_ticket_id": active_ticket_id,
    }
