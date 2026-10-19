"""Dynamic tool and role retrieval. Implements: REQ-009, TC-M2-03, ADR-0002."""

from uuid import uuid4

from sqlalchemy import delete, select

from app.core.config import settings
from app.db.models import AgentRole, AgentRoleTool, ToolRegistry, User, UserToolPreference
from app.db.seed_runner import SeedRunner
from app.db.session import get_session_factory
from app.llm.embedding_client import EmbeddingClient
from app.orchestrator.tool_rag import TOP_K, ToolRetriever, compile_role_turn


def _toward_query(rank: int) -> list[float]:
    vector = [0.0] * settings.EMBEDDING_DIMENSION
    vector[2] = 1 - rank * 0.12
    vector[3] = 0.15 + rank * 0.05
    return vector


def _axis(index: int) -> list[float]:
    vector = [0.0] * settings.EMBEDDING_DIMENSION
    vector[index] = 1.0
    return vector


async def test_turn_keeps_hidden_tools_and_caps_the_authorized_set_at_five() -> None:
    codes = [f"TEST_NEAR_{index}" for index in range(6)]
    extra = ["TEST_HIDDEN", "TEST_ROLE_ONLY", "TEST_DISABLED", "TEST_OTHER_USER_OFF"]
    async with get_session_factory()() as session:
        await SeedRunner(session, EmbeddingClient()).run()
        user = User(email=f"rag-{uuid4().hex}@example.com", display_name="檢索者", department="RD")
        other = User(email=f"rag-{uuid4().hex}@example.com", display_name="另一人", department="RD")
        session.add_all([user, other])
        await session.flush()
        sa = await session.scalar(select(AgentRole).where(AgentRole.code == "SA"))
        fin = await session.scalar(select(AgentRole).where(AgentRole.code == "FIN"))
        assert sa is not None and fin is not None
        made: list[ToolRegistry] = []
        for index, code in enumerate(codes):
            tool = ToolRegistry(
                code=code,
                namespace="test",
                name=code,
                description=code,
                input_json_schema={"type": "object"},
                action_tier="READ",
                scope_type="COMMON_DEFAULT",
                is_visible_to_user=True,
                routing_embedding=_toward_query(index),
                is_active=True,
            )
            session.add(tool)
            made.append(tool)
        hidden = ToolRegistry(
            code="TEST_HIDDEN",
            namespace="test",
            name="隱藏工具",
            description="HIDDEN-TOOL-GUARD-19",
            input_json_schema={"type": "object"},
            scope_type="COMMON_DEFAULT",
            is_visible_to_user=False,
            routing_embedding=_axis(8),
            is_active=True,
        )
        role_only = ToolRegistry(
            code="TEST_ROLE_ONLY",
            namespace="test",
            name="財務專用",
            description="TEST_ROLE_ONLY",
            input_json_schema={"type": "object"},
            scope_type="ROLE_SCOPED",
            is_visible_to_user=True,
            routing_embedding=_axis(2),
            is_active=True,
        )
        disabled = ToolRegistry(
            code="TEST_DISABLED",
            namespace="test",
            name="已關閉",
            description="TEST_DISABLED",
            input_json_schema={"type": "object"},
            scope_type="COMMON_DEFAULT",
            is_visible_to_user=True,
            routing_embedding=_axis(2),
            is_active=True,
        )
        shared = ToolRegistry(
            code="TEST_OTHER_USER_OFF",
            namespace="test",
            name="他人關閉",
            description="TEST_OTHER_USER_OFF",
            input_json_schema={"type": "object"},
            scope_type="COMMON_DEFAULT",
            is_visible_to_user=True,
            routing_embedding=_toward_query(0),
            is_active=True,
        )
        session.add_all([hidden, role_only, disabled, shared])
        await session.flush()
        session.add(AgentRoleTool(role_id=fin.id, tool_id=role_only.id))
        session.add(UserToolPreference(user_id=user.id, tool_id=disabled.id, is_enabled=False))
        session.add(UserToolPreference(user_id=other.id, tool_id=shared.id, is_enabled=False))
        private = AgentRole(
            code=f"PRIVATE_{uuid4().hex[:8]}",
            name="別人的私人角色",
            department="RD",
            visibility_scope="PRIVATE",
            approval_status="APPROVED",
            system_prompt="私人",
            routing_description="私人",
            routing_embedding=_axis(2),
            output_json_schema={"type": "object"},
            creator_user_id=other.id,
            is_active=True,
        )
        near = AgentRole(
            code=f"NEAR_{uuid4().hex[:8]}",
            name="最接近的角色",
            department="GLOBAL",
            visibility_scope="GLOBAL",
            approval_status="APPROVED",
            system_prompt="接近",
            routing_description="接近",
            routing_embedding=_axis(2),
            output_json_schema={"type": "object"},
            is_active=True,
        )
        other_dept = AgentRole(
            code=f"DEPT_{uuid4().hex[:8]}",
            name="其他部門角色",
            department="FINANCE",
            visibility_scope="DEPARTMENT",
            approval_status="APPROVED",
            system_prompt="部門",
            routing_description="部門",
            routing_embedding=_axis(2),
            output_json_schema={"type": "object"},
            is_active=True,
        )
        session.add_all([private, near, other_dept])
        await session.commit()
        try:
            selected = await ToolRetriever().tools_for_turn(
                session,
                role_id=sa.id,
                user_id=user.id,
                query_embedding=_axis(2),
            )
            prompt = await compile_role_turn(
                session,
                role=sa,
                user_id=user.id,
                user_department=user.department,
                query_embedding=_axis(2),
            )
            roles = await ToolRetriever().roles_for_turn(
                session,
                user_id=user.id,
                user_department="RD",
                query_embedding=_axis(2),
            )
        finally:
            await session.execute(delete(ToolRegistry).where(ToolRegistry.code.in_([*codes, *extra])))
            await session.execute(
                delete(AgentRole).where(AgentRole.code.in_([private.code, near.code, other_dept.code]))
            )
            await session.execute(delete(User).where(User.id.in_([user.id, other.id])))
            await session.commit()

    assert len(selected) == TOP_K
    picked = [tool.code for tool in selected]
    assert "TEST_HIDDEN" in picked
    assert "TOOL_HIDDEN_GUARDRAIL" in picked
    assert "TEST_NEAR_0" in picked
    assert "TEST_NEAR_5" not in picked
    assert "TEST_ROLE_ONLY" not in picked
    assert "TEST_DISABLED" not in picked
    assert "TEST_OTHER_USER_OFF" in picked
    assert "HIDDEN-TOOL-GUARD-19" in prompt
    assert "【本回合工具 Top-5】" in prompt
    assert "TEST_NEAR_5" not in prompt.split("【本回合工具 Top-5】", maxsplit=1)[1]
    assert roles[0].code == near.code
    assert private.code not in {role.code for role in roles}
    assert other_dept.code not in {role.code for role in roles}
    assert len(roles) <= TOP_K
