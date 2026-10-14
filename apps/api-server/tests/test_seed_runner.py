"""TC-M1-01: builtin seed is complete and idempotent. Implements: ADR-0001."""

import math

import pytest

from app.db.catalog import binding_map, read_builtin_catalog
from app.db.seed_runner import SeedRunner
from app.db.session import get_session_factory
from app.llm.embedding_client import EmbeddingClient

ALL_ROLES = frozenset({"ORCH", "CEO", "PM", "FIN", "SA", "ARCH", "SE"})


def _unit(vector: list[float]) -> float:
    return math.sqrt(sum(component * component for component in vector))


async def test_seed_loads_roles_rules_skills_and_can_run_twice() -> None:
    factory = get_session_factory()
    async with factory() as session:
        first = await SeedRunner(session, EmbeddingClient()).run()
        catalog = await read_builtin_catalog(session)
        role_ids = {role.code: role.id for role in catalog.roles}

    async with factory() as session:
        second = await SeedRunner(session, EmbeddingClient()).run()
        catalog = await read_builtin_catalog(session)

    assert first.roles == 7
    assert first.rules == 5
    assert first.skills == 4
    assert second.roles == 7
    assert second.rules == 5
    assert second.skills == 4
    assert {role.code: role.id for role in catalog.roles} == role_ids

    roles = {role.code: role for role in catalog.roles}
    assert set(roles) == set(ALL_ROLES)
    assert roles["ORCH"].reports_to_code is None
    assert roles["CEO"].reports_to_code == "ORCH"
    assert roles["PM"].reports_to_code == "CEO"
    assert roles["FIN"].reports_to_code == "CEO"
    assert roles["SA"].reports_to_code == "PM"
    assert roles["ARCH"].reports_to_code == "PM"
    assert roles["SE"].reports_to_code == "ARCH"
    for role in catalog.roles:
        assert len(role.embedding) == 32
        assert _unit(role.embedding) == pytest.approx(1.0)

    rules = {rule.code: rule for rule in catalog.rules}
    assert sum(1 for rule in rules.values() if rule.scope_type == "GLOBAL_MANDATORY") == 2
    assert sum(1 for rule in rules.values() if rule.scope_type == "ROLE_EXCLUSIVE") == 3
    assert rules["RULE_GLOBAL_ZH_TW"].priority == 10
    assert rules["RULE_GLOBAL_ZERO_TRUST_DLP"].priority == 20

    rule_bindings = binding_map(catalog.rule_bindings, by_right=True)
    assert rule_bindings["RULE_GLOBAL_ZH_TW"] == ALL_ROLES
    assert rule_bindings["RULE_GLOBAL_ZERO_TRUST_DLP"] == ALL_ROLES
    assert rule_bindings["RULE_SA_OPENAPI_AND_ERD"] == frozenset({"SA"})
    assert rule_bindings["RULE_FIN_TWD_THREE_SCENARIOS"] == frozenset({"FIN"})
    assert rule_bindings["RULE_SE_PYTHON_TS_STRICT"] == frozenset({"SE"})

    skills = {skill.code: skill for skill in catalog.skills}
    assert set(skills) == {
        "SKILL_COMMON_MEETING_ACTION_ITEMS",
        "SKILL_SA_OPENAPI_CLI_VALIDATOR",
        "SKILL_FIN_PYTHON_IRR_CALCULATOR",
        "SKILL_SE_PYTEST_AND_GIT_DIAGNOSTICS",
    }
    assert skills["SKILL_SA_OPENAPI_CLI_VALIDATOR"].execution_mode == "SERVER_SANDBOX_CLI"
    assert skills["SKILL_SE_PYTEST_AND_GIT_DIAGNOSTICS"].execution_mode == "LOCAL_DAEMON_CLI"
    assert skills["SKILL_COMMON_MEETING_ACTION_ITEMS"].execution_mode == "PROMPT_ONLY"
    for skill in catalog.skills:
        assert len(skill.embedding) == 32
        assert _unit(skill.embedding) == pytest.approx(1.0)

    skill_bindings = binding_map(catalog.skill_bindings, by_right=True)
    assert skill_bindings["SKILL_COMMON_MEETING_ACTION_ITEMS"] == frozenset({"PM", "SA", "ARCH", "CEO"})
    assert skill_bindings["SKILL_SA_OPENAPI_CLI_VALIDATOR"] == frozenset({"SA", "ARCH"})
    assert skill_bindings["SKILL_FIN_PYTHON_IRR_CALCULATOR"] == frozenset({"FIN"})
    assert skill_bindings["SKILL_SE_PYTEST_AND_GIT_DIAGNOSTICS"] == frozenset({"SE"})
