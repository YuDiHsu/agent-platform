"""Onion compiler isolation, hidden assets, and progressive skills. Implements: REQ-013, REQ-014, ADR-0004."""

from sqlalchemy import select

from app.db.models import AgentRole, RuleRegistry
from app.db.seed_runner import SeedRunner
from app.db.session import get_session_factory
from app.llm.embedding_client import EmbeddingClient
from app.orchestrator.prompt_compiler import PromptCompiler, ToolSchema, stage_one_manifest


async def test_sa_prompt_keeps_company_rules_and_drops_other_roles() -> None:
    async with get_session_factory()() as session:
        await SeedRunner(session, EmbeddingClient()).run()
        session.add(
            RuleRegistry(
                code="RULE_RD_SHARED",
                name="研發部門共通",
                scope_type="DEPARTMENT_SHARED",
                department="RD",
                priority=30,
                rule_content_markdown="RD-DEPT-ONLY-44",
                is_visible_to_user=True,
                approval_status="APPROVED",
                is_active=True,
            )
        )
        await session.commit()
        role = await session.scalar(select(AgentRole).where(AgentRole.code == "SA"))
        assert role is not None
        compiled = await PromptCompiler().compile_for_role(session, role, "RD")
        prompt = compiled.system_prompt
        preview = compiled.preview_prompt
        await session.execute(RuleRegistry.__table__.delete().where(RuleRegistry.code == "RULE_RD_SHARED"))
        await session.commit()

    assert "RULE_GLOBAL_ZH_TW" in prompt
    assert "RULE_SA_OPENAPI_AND_ERD" in prompt
    assert "HIDDEN-RADIX-77" in prompt
    assert "RULE_FIN_TWD_THREE_SCENARIOS" not in prompt
    assert "RULE_SE_PYTHON_TS_STRICT" not in prompt
    assert "RD-DEPT-ONLY-44" in prompt
    assert prompt.index("HIDDEN-RADIX-77") < prompt.index("【角色核心職責 SA】")
    assert prompt.index("【角色核心職責 SA】") < prompt.index("RULE_SA_OPENAPI_AND_ERD")
    assert "HIDDEN-RADIX-77" not in preview
    assert "HIDDEN-SKILL-SOP-88" not in preview


async def test_same_department_shares_layers_until_the_tool_tail() -> None:
    async with get_session_factory()() as session:
        await SeedRunner(session, EmbeddingClient()).run()
        role = await session.scalar(select(AgentRole).where(AgentRole.code == "SA"))
        assert role is not None
        compiler = PromptCompiler()
        read_tool = [ToolSchema(name="workspace_read_file", description="讀檔", parameters={"type": "object"})]
        many_tools = [
            ToolSchema(name="o365_search_messages", description="搜信", parameters={"type": "object"}),
            ToolSchema(name="tool_two", description="二", parameters={}),
            ToolSchema(name="tool_three", description="三", parameters={}),
            ToolSchema(name="tool_four", description="四", parameters={}),
            ToolSchema(name="tool_five", description="五", parameters={}),
            ToolSchema(name="tool_six", description="六不該出現", parameters={}),
        ]
        first = await compiler.compile_for_role(session, role, "RD", tool_schemas=read_tool)
        second = await compiler.compile_for_role(session, role, "RD", tool_schemas=many_tools)

    assert first.prefix_through_layer_4 == second.prefix_through_layer_4
    assert first.prefix_through_layer_4.startswith("【規範 RULE_HIDDEN_RADIX_PREFIX】")
    assert "【本回合工具 Top-5】" not in first.prefix_through_layer_4
    assert "【本回合工具 Top-5】" in first.system_prompt
    assert "workspace_read_file" in first.system_prompt.split("【本回合工具 Top-5】", maxsplit=1)[1]
    assert "tool_six" not in second.system_prompt
    assert "tool_five" in second.system_prompt


async def test_standby_skill_stays_short_until_activation() -> None:
    long_trigger = "很長的觸發說明" * 20
    from app.db.models import SkillRegistry

    async with get_session_factory()() as session:
        await SeedRunner(session, EmbeddingClient()).run()
        stored = await session.scalar(
            select(SkillRegistry).where(SkillRegistry.code == "SKILL_FIN_PYTHON_IRR_CALCULATOR")
        )
        assert stored is not None
        stored.trigger_description = long_trigger[:300]
        await session.commit()
        role = await session.scalar(select(AgentRole).where(AgentRole.code == "FIN"))
        assert role is not None
        waiting = await PromptCompiler().compile_for_role(session, role, "FINANCE")
        active = await PromptCompiler().compile_for_role(
            session,
            role,
            "FINANCE",
            activated_skill_codes=["SKILL_FIN_PYTHON_IRR_CALCULATOR"],
        )

    catalog = waiting.prefix_through_layer_4
    assert "fin_calculator.py" not in catalog
    for line in catalog.splitlines():
        if line.startswith("SKILL_"):
            assert len(line) < 60
    assert long_trigger[:80] not in catalog
    assert "fin_calculator.py" in active.system_prompt
    assert active.prefix_through_layer_4 == waiting.prefix_through_layer_4
    assert len(stage_one_manifest("SKILL_X", "名稱", long_trigger)) < 60
