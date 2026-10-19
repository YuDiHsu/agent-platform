"""Tool registry, role bindings, and per-user enablement.

Implements: ADR-0002, ADR-0004.

Fresh databases created before this revision do not include these tables,
because 0001 only creates the original 13. Upgrades create them from the
live models, including the HNSW cosine index.
"""

from collections.abc import Sequence

from alembic import op
from sqlalchemy import inspect

from app.db.models import Base

revision: str = "0004_tools_registry"
down_revision: str | None = "0003_rule_skill_visibility"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TOOL_TABLES = ("tools_registry", "agent_role_tools", "user_tool_preferences")


def upgrade() -> None:
    bind = op.get_bind()
    existing = set(inspect(bind).get_table_names())
    missing = [Base.metadata.tables[name] for name in TOOL_TABLES if name not in existing]
    if missing:
        Base.metadata.create_all(bind=bind, tables=missing)


def downgrade() -> None:
    for name in reversed(TOOL_TABLES):
        op.drop_table(name)
