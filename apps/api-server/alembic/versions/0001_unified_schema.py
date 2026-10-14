"""Initial unified schema. Implements: REQ-001, REQ-008, REQ-012, ADR-0001.

Vector columns use settings.EMBEDDING_DIMENSION via the SQLAlchemy metadata.
"""

from collections.abc import Sequence

from alembic import op
from sqlalchemy import text

from app.db.models import Base

revision: str = "0001_unified_schema"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Later revisions add tables to Base.metadata. This migration must keep creating
# only the original 13 tables so an existing 0001 database stays upgradeable.
ORIGINAL_TABLES = (
    "users",
    "local_workspace_mounts",
    "agent_roles",
    "rules_registry",
    "agent_role_rules",
    "skills_registry",
    "agent_role_skills",
    "shared_artifacts",
    "tasks_tickets",
    "hitl_approval_requests",
    "cli_execution_logs",
    "user_connector_tokens",
    "agent_memories",
)


def _enable_uuid_generator() -> None:
    """Prefer uuid-ossp. Fall back when the server image does not ship that contrib module."""
    bind = op.get_bind()
    available = bind.execute(
        text("SELECT 1 FROM pg_available_extensions WHERE name = 'uuid-ossp'")
    ).scalar()
    if available:
        op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')
        return
    op.execute(
        text(
            "CREATE OR REPLACE FUNCTION uuid_generate_v4() RETURNS uuid "
            "LANGUAGE sql VOLATILE AS $$ SELECT gen_random_uuid() $$"
        )
    )


def _original_tables() -> list[object]:
    return [Base.metadata.tables[name] for name in ORIGINAL_TABLES]


def upgrade() -> None:
    _enable_uuid_generator()
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    Base.metadata.create_all(bind=op.get_bind(), tables=_original_tables())


def downgrade() -> None:
    Base.metadata.drop_all(bind=op.get_bind(), tables=_original_tables())
