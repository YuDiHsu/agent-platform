"""Chat sessions, messages, and per-user execution quotas.

Implements: REQ-002, REQ-018, ADR-0002, ADR-0003.

Fresh databases already receive the new user columns from the users table in
0001, because that revision builds the live users model. This revision still
adds those columns when upgrading a database stamped at the original 0001.
Chat tables are created here and are excluded from 0001.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql

revision: str = "0002_chat_workspace"
down_revision: str | None = "0001_unified_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = set(inspector.get_table_names())
    user_columns = {column["name"] for column in inspector.get_columns("users")}
    if "max_concurrent_tickets" not in user_columns:
        op.add_column(
            "users",
            sa.Column("max_concurrent_tickets", sa.Integer(), server_default=sa.text("4"), nullable=False),
        )
    if "token_quota_limit" not in user_columns:
        op.add_column("users", sa.Column("token_quota_limit", sa.Integer(), nullable=True))
    if "tokens_consumed_total" not in user_columns:
        op.add_column(
            "users",
            sa.Column("tokens_consumed_total", sa.Integer(), server_default=sa.text("0"), nullable=False),
        )
    if "chat_sessions" not in tables:
        op.create_table(
            "chat_sessions",
            sa.Column(
                "id",
                postgresql.UUID(as_uuid=True),
                primary_key=True,
                server_default=sa.text("uuid_generate_v4()"),
            ),
            sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("title", sa.String(length=255), nullable=False),
            sa.Column("status", sa.String(length=32), nullable=False, server_default=sa.text("'ACTIVE'")),
            sa.Column("active_role_code", sa.String(length=64), nullable=True),
            sa.Column("goal_statement", sa.Text(), nullable=True),
            sa.Column(
                "dag_snapshot",
                postgresql.JSONB(),
                nullable=False,
                server_default=sa.text("'[]'::jsonb"),
            ),
            sa.Column("checkpoint", postgresql.JSONB(), nullable=True),
            sa.Column("hold_reason", sa.String(length=40), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        )
        op.create_index("ix_chat_sessions_user_id", "chat_sessions", ["user_id"])
    if "chat_messages" not in tables:
        op.create_table(
            "chat_messages",
            sa.Column(
                "id",
                postgresql.UUID(as_uuid=True),
                primary_key=True,
                server_default=sa.text("uuid_generate_v4()"),
            ),
            sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("role_code", sa.String(length=64), nullable=False),
            sa.Column("event_type", sa.String(length=40), nullable=False),
            sa.Column("content", sa.Text(), nullable=False),
            sa.Column(
                "payload",
                postgresql.JSONB(),
                nullable=False,
                server_default=sa.text("'{}'::jsonb"),
            ),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
            sa.ForeignKeyConstraint(["session_id"], ["chat_sessions.id"], ondelete="CASCADE"),
        )
        op.create_index("ix_chat_messages_session_id", "chat_messages", ["session_id"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = set(inspector.get_table_names())
    if "chat_messages" in tables:
        op.drop_index("ix_chat_messages_session_id", table_name="chat_messages")
        op.drop_table("chat_messages")
    if "chat_sessions" in tables:
        op.drop_index("ix_chat_sessions_user_id", table_name="chat_sessions")
        op.drop_table("chat_sessions")
    user_columns = {column["name"] for column in inspector.get_columns("users")}
    if "tokens_consumed_total" in user_columns:
        op.drop_column("users", "tokens_consumed_total")
    if "token_quota_limit" in user_columns:
        op.drop_column("users", "token_quota_limit")
    if "max_concurrent_tickets" in user_columns:
        op.drop_column("users", "max_concurrent_tickets")
