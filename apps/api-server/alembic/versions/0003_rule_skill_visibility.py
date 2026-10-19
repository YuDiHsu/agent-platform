"""Visibility and approval columns for rules and skills.

Implements: ADR-0004.

Fresh databases receive the columns from the live models in 0001. This
revision adds them when upgrading a database stamped at 0002.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "0003_rule_skill_visibility"
down_revision: str | None = "0002_chat_workspace"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _add_visibility(table: str) -> None:
    bind = op.get_bind()
    columns = {column["name"] for column in inspect(bind).get_columns(table)}
    if "is_visible_to_user" not in columns:
        op.add_column(
            table,
            sa.Column("is_visible_to_user", sa.Boolean(), nullable=False, server_default=sa.true()),
        )
    if "approval_status" not in columns:
        op.add_column(
            table,
            sa.Column("approval_status", sa.String(length=20), nullable=False, server_default="APPROVED"),
        )


def upgrade() -> None:
    _add_visibility("rules_registry")
    _add_visibility("skills_registry")


def downgrade() -> None:
    op.drop_column("skills_registry", "approval_status")
    op.drop_column("skills_registry", "is_visible_to_user")
    op.drop_column("rules_registry", "approval_status")
    op.drop_column("rules_registry", "is_visible_to_user")
