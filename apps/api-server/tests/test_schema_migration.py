"""Migration creates the 13-table schema, private-mount check, and HNSW indexes."""

import uuid

import psycopg
import pytest
from sqlalchemy import text

from app.core.config import settings
from app.db.session import get_session_factory

EXPECTED_TABLES = {
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
}
HNSW_INDEXES = {
    "idx_agent_roles_embedding",
    "idx_skills_trigger_vec",
    "idx_agent_memories_vec",
}


async def test_migration_creates_tables_extensions_and_hnsw_indexes() -> None:
    factory = get_session_factory()
    async with factory() as session:
        table_names = set(
            (
                await session.scalars(
                    text(
                        "SELECT table_name FROM information_schema.tables "
                        "WHERE table_schema = 'public' AND table_type = 'BASE TABLE'"
                    )
                )
            ).all()
        )
        extensions = set((await session.scalars(text("SELECT extname FROM pg_extension"))).all())
        constraint = await session.scalar(
            text("SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conname = 'chk_local_mount_private'")
        )
        index_rows = (
            await session.execute(
                text("SELECT indexname, indexdef FROM pg_indexes WHERE schemaname = 'public'")
            )
        ).all()
        vector_types = (
            await session.execute(
                text(
                    """
                    SELECT c.relname, a.attname, format_type(a.atttypid, a.atttypmod)
                    FROM pg_attribute a
                    JOIN pg_class c ON c.oid = a.attrelid
                    JOIN pg_namespace n ON n.oid = c.relnamespace
                    WHERE n.nspname = 'public'
                      AND a.attname IN ('routing_embedding', 'trigger_embedding', 'embedding')
                      AND NOT a.attisdropped
                    """
                )
            )
        ).all()

    assert EXPECTED_TABLES <= table_names
    assert "vector" in extensions
    uuid_ready = "uuid-ossp" in extensions
    if not uuid_ready:
        generated = await session.scalar(text("SELECT uuid_generate_v4()"))
        uuid_ready = generated is not None
    assert uuid_ready
    assert constraint is not None
    assert "bound_local_mount_id IS NULL" in constraint
    assert "visibility_scope = 'PRIVATE'" in constraint
    index_defs = {name: definition for name, definition in index_rows}
    for index_name in HNSW_INDEXES:
        definition = index_defs[index_name].lower()
        assert "hnsw" in definition
        assert "vector_cosine_ops" in definition
        assert {row[2] for row in vector_types} == {"vector(32)"}
        await session.commit()


def _sync_dsn() -> str:
    return settings.sync_database_url.replace("postgresql+psycopg://", "postgresql://", 1)


def test_global_role_cannot_bind_a_local_mount() -> None:
    dsn = _sync_dsn()
    with psycopg.connect(dsn, prepare_threshold=None, autocommit=True) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO users (email, display_name, department) VALUES (%s, %s, %s) RETURNING id",
                (f"mount-{uuid.uuid4().hex}@example.com", "掛載擁有者", "RD"),
            )
            user_row = cursor.fetchone()
            assert user_row is not None
            cursor.execute(
                "INSERT INTO local_workspace_mounts (user_id, mount_alias) VALUES (%s, %s) RETURNING id",
                (user_row[0], "規格書"),
            )
            mount_row = cursor.fetchone()
            assert mount_row is not None
            with pytest.raises(psycopg.Error):
                cursor.execute(
                    """
                    INSERT INTO agent_roles (
                        code, name, department, visibility_scope, approval_status,
                        system_prompt, routing_description, output_json_schema, bound_local_mount_id
                    ) VALUES (%s, %s, %s, 'GLOBAL', 'APPROVED', %s, %s, %s::jsonb, %s)
                    """,
                    (
                        f"CUSTOM_GLOBAL_{uuid.uuid4().hex[:8]}",
                        "不可公開掛載",
                        "RD",
                        "系統提示",
                        "路由說明",
                        '{"type": "object"}',
                        mount_row[0],
                    ),
                )
    with psycopg.connect(dsn, prepare_threshold=None, autocommit=True) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT COUNT(*) FROM agent_roles WHERE visibility_scope = 'GLOBAL' AND bound_local_mount_id IS NOT NULL"
            )
            blocked = cursor.fetchone()
            assert blocked is not None
            assert blocked[0] == 0
            cursor.execute(
                "INSERT INTO users (email, display_name, department) VALUES (%s, %s, %s) RETURNING id",
                (f"private-{uuid.uuid4().hex}@example.com", "私人擁有者", "RD"),
            )
            private_user = cursor.fetchone()
            assert private_user is not None
            cursor.execute(
                "INSERT INTO local_workspace_mounts (user_id, mount_alias) VALUES (%s, %s) RETURNING id",
                (private_user[0], "私人規格"),
            )
            private_mount = cursor.fetchone()
            assert private_mount is not None
            cursor.execute(
                """
                INSERT INTO agent_roles (
                    code, name, department, visibility_scope, approval_status,
                    system_prompt, routing_description, output_json_schema, bound_local_mount_id
                ) VALUES (%s, %s, %s, 'PRIVATE', 'APPROVED', %s, %s, %s::jsonb, %s)
                """,
                (
                    f"CUSTOM_PRIVATE_{uuid.uuid4().hex[:8]}",
                    "私人掛載",
                    "RD",
                    "系統提示",
                    "路由說明",
                    '{"type": "object"}',
                    private_mount[0],
                ),
            )
            cursor.execute("DELETE FROM agent_roles WHERE code LIKE 'CUSTOM_%'")
            cursor.execute("DELETE FROM local_workspace_mounts")
            cursor.execute("DELETE FROM users WHERE email LIKE '%@example.com'")
