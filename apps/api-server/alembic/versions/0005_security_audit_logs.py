"""Security audit log for local-mount and path denials.

Implements: REQ-012, ADR-0004.
"""

from collections.abc import Sequence

from alembic import op
from sqlalchemy import inspect

from app.db.models import Base

revision: str = "0005_security_audit_logs"
down_revision: str | None = "0004_tools_registry"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    existing = set(inspect(bind).get_table_names())
    table = Base.metadata.tables["security_audit_logs"]
    if table.name not in existing:
        Base.metadata.create_all(bind=bind, tables=[table])


def downgrade() -> None:
    op.drop_table("security_audit_logs")
