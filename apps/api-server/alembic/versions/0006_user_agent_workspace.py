"""Personal agent workspace tables. Implements: ADR-0003."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

from app.db.models import Base

revision: str = "0006_user_agent_workspace"
down_revision: str | None = "0005_security_audit_logs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = set(inspector.get_table_names())
    if "user_agent_configs" not in tables:
        Base.metadata.create_all(bind=bind, tables=[Base.metadata.tables["user_agent_configs"]])
    memory_columns = {column["name"] for column in inspect(bind).get_columns("agent_memories")}
    if "role_code" not in memory_columns:
        op.add_column("agent_memories", sa.Column("role_code", sa.String(length=64), nullable=True))


def downgrade() -> None:
    op.drop_column("agent_memories", "role_code")
    op.drop_table("user_agent_configs")
