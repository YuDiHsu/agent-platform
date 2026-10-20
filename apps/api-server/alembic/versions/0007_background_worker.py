"""Background worker lane, heartbeat routines, notifications, and daemon pairings. Implements: REQ-005, REQ-011."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

from app.db.models import Base

revision: str = "0007_background_worker"
down_revision: str | None = "0006_user_agent_workspace"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLES = ("heartbeat_routines", "user_notifications", "local_daemon_pairings")


def upgrade() -> None:
    bind = op.get_bind()
    ticket_columns = {column["name"] for column in inspect(bind).get_columns("tasks_tickets")}
    if "execution_lane" not in ticket_columns:
        op.add_column(
            "tasks_tickets",
            sa.Column("execution_lane", sa.String(length=20), server_default=sa.text("'INTERACTIVE'"), nullable=False),
        )
        op.create_index(
            "ix_tasks_tickets_background_pending",
            "tasks_tickets",
            ["created_at"],
            postgresql_where=sa.text("execution_lane = 'BACKGROUND' AND status = 'PENDING'"),
        )
    existing = set(inspect(bind).get_table_names())
    missing = [Base.metadata.tables[name] for name in _TABLES if name not in existing]
    if missing:
        Base.metadata.create_all(bind=bind, tables=missing)


def downgrade() -> None:
    for name in reversed(_TABLES):
        op.drop_table(name)
    op.drop_index("ix_tasks_tickets_background_pending", table_name="tasks_tickets")
    op.drop_column("tasks_tickets", "execution_lane")
