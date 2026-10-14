"""Thirteen-table platform schema. Implements: REQ-001, REQ-008, REQ-012, ADR-0001."""

import uuid
from datetime import datetime
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.core.config import settings

EMBEDDING_DIM = settings.EMBEDDING_DIMENSION


class Base(DeclarativeBase):
    pass


def _uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        server_default=text("uuid_generate_v4()"),
    )


def _created_at() -> Mapped[datetime | None]:
    return mapped_column(DateTime(timezone=True), server_default=func.now())


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = _uuid_pk()
    email: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(Text, nullable=False)
    department: Mapped[str] = mapped_column(Text, nullable=False)
    job_title: Mapped[str | None] = mapped_column(Text)
    sso_subject_id: Mapped[str | None] = mapped_column(Text, unique=True)
    is_admin: Mapped[bool | None] = mapped_column(Boolean, server_default=text("false"))
    created_at: Mapped[datetime | None] = _created_at()


class LocalWorkspaceMount(Base):
    __tablename__ = "local_workspace_mounts"

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    mount_alias: Mapped[str] = mapped_column(Text, nullable=False)
    provider_type: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        server_default=text("'BROWSER_FS_API'"),
    )
    browser_handle_key: Mapped[str | None] = mapped_column(Text)
    permission_mode: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        server_default=text("'READ_WRITE_WITH_CONFIRM'"),
    )
    allowed_extensions: Mapped[list[Any]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text(
            """'[".md", ".txt", ".docx", ".xlsx", ".pdf", ".py", ".ts", ".json", ".sql", ".yaml", ".yml"]'::jsonb"""
        ),
    )
    cached_file_tree: Mapped[list[Any]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'[]'::jsonb"),
    )
    last_synced_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )


class AgentRole(Base):
    __tablename__ = "agent_roles"
    __table_args__ = (
        CheckConstraint(
            "bound_local_mount_id IS NULL OR visibility_scope = 'PRIVATE'",
            name="chk_local_mount_private",
        ),
        Index(
            "idx_agent_roles_embedding",
            "routing_embedding",
            postgresql_using="hnsw",
            postgresql_ops={"routing_embedding": "vector_cosine_ops"},
        ),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    code: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    department: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'GLOBAL'"))
    reports_to_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("agent_roles.id", ondelete="SET NULL"),
    )
    creator_user_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
    )
    visibility_scope: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        server_default=text("'PRIVATE'"),
    )
    approval_status: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        server_default=text("'APPROVED'"),
    )
    system_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    routing_description: Mapped[str] = mapped_column(Text, nullable=False)
    routing_embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIM))
    output_json_schema: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    allowed_tool_namespaces: Mapped[list[Any]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'[]'::jsonb"),
    )
    bound_local_mount_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("local_workspace_mounts.id", ondelete="SET NULL"),
    )
    model_params: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text(
            """'{"model": "gemma-4-27b-it", "temperature": 0.2, "max_tokens": 4096}'::jsonb"""
        ),
    )
    is_active: Mapped[bool | None] = mapped_column(Boolean, server_default=text("true"))
    created_at: Mapped[datetime | None] = _created_at()
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )


class RuleRegistry(Base):
    __tablename__ = "rules_registry"

    id: Mapped[uuid.UUID] = _uuid_pk()
    code: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    scope_type: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        server_default=text("'ROLE_EXCLUSIVE'"),
    )
    department: Mapped[str | None] = mapped_column(Text)
    creator_user_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
    )
    priority: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("100"))
    rule_content_markdown: Mapped[str] = mapped_column(Text, nullable=False)
    glob_trigger: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool | None] = mapped_column(Boolean, server_default=text("true"))
    created_at: Mapped[datetime | None] = _created_at()


class AgentRoleRule(Base):
    __tablename__ = "agent_role_rules"

    role_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("agent_roles.id", ondelete="CASCADE"),
        primary_key=True,
    )
    rule_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("rules_registry.id", ondelete="CASCADE"),
        primary_key=True,
    )
    is_mandatory: Mapped[bool | None] = mapped_column(Boolean, server_default=text("true"))
    bound_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
    )
    created_at: Mapped[datetime | None] = _created_at()


class SkillRegistry(Base):
    __tablename__ = "skills_registry"
    __table_args__ = (
        Index(
            "idx_skills_trigger_vec",
            "trigger_embedding",
            postgresql_using="hnsw",
            postgresql_ops={"trigger_embedding": "vector_cosine_ops"},
        ),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    code: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    visibility_scope: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        server_default=text("'GLOBAL'"),
    )
    department: Mapped[str | None] = mapped_column(Text)
    creator_user_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
    )
    trigger_description: Mapped[str] = mapped_column(Text, nullable=False)
    trigger_embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIM))
    sop_markdown: Mapped[str] = mapped_column(Text, nullable=False)
    execution_mode: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        server_default=text("'PROMPT_ONLY'"),
    )
    cli_config: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    required_tool_namespaces: Mapped[list[Any]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'[]'::jsonb"),
    )
    is_active: Mapped[bool | None] = mapped_column(Boolean, server_default=text("true"))
    created_at: Mapped[datetime | None] = _created_at()


class AgentRoleSkill(Base):
    __tablename__ = "agent_role_skills"

    role_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("agent_roles.id", ondelete="CASCADE"),
        primary_key=True,
    )
    skill_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("skills_registry.id", ondelete="CASCADE"),
        primary_key=True,
    )
    auto_activate: Mapped[bool | None] = mapped_column(Boolean, server_default=text("false"))
    bound_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
    )
    created_at: Mapped[datetime | None] = _created_at()


class SharedArtifact(Base):
    __tablename__ = "shared_artifacts"

    id: Mapped[uuid.UUID] = _uuid_pk()
    session_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    producer_role_code: Mapped[str] = mapped_column(Text, nullable=False)
    artifact_type: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    summary_200_words: Mapped[str] = mapped_column(Text, nullable=False)
    content_body: Mapped[str] = mapped_column(Text, nullable=False)
    structured_metadata: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB,
        server_default=text("'{}'::jsonb"),
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    created_at: Mapped[datetime | None] = _created_at()


class TaskTicket(Base):
    __tablename__ = "tasks_tickets"

    id: Mapped[uuid.UUID] = _uuid_pk()
    session_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    parent_ticket_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("tasks_tickets.id", ondelete="CASCADE"),
    )
    requester_user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=False,
    )
    assigned_role_code: Mapped[str] = mapped_column(
        Text,
        ForeignKey("agent_roles.code"),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'PENDING'"))
    hop_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    max_hops: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("8"))
    token_budget: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("16000"))
    tokens_consumed: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    locked_by_worker: Mapped[str | None] = mapped_column(Text)
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    goal_ancestry: Mapped[list[Any]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'[]'::jsonb"),
    )
    input_instructions: Mapped[str] = mapped_column(Text, nullable=False)
    input_artifact_ids: Mapped[list[Any]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'[]'::jsonb"),
    )
    output_artifact_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("shared_artifacts.id"),
    )
    error_log: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime | None] = _created_at()
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class HitlApprovalRequest(Base):
    __tablename__ = "hitl_approval_requests"

    id: Mapped[uuid.UUID] = _uuid_pk()
    ticket_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("tasks_tickets.id", ondelete="CASCADE"),
        nullable=False,
    )
    session_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=False,
    )
    executing_role_code: Mapped[str] = mapped_column(Text, nullable=False)
    tool_name: Mapped[str] = mapped_column(Text, nullable=False)
    execution_target: Mapped[str] = mapped_column(Text, nullable=False)
    action_tier: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'COMMIT'"))
    preview_title: Mapped[str] = mapped_column(Text, nullable=False)
    proposed_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'PENDING'"))
    user_modified_payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime | None] = _created_at()


class CliExecutionLog(Base):
    __tablename__ = "cli_execution_logs"

    id: Mapped[uuid.UUID] = _uuid_pk()
    session_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    ticket_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("tasks_tickets.id", ondelete="SET NULL"),
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=False,
    )
    executing_role_code: Mapped[str] = mapped_column(Text, nullable=False)
    skill_code: Mapped[str] = mapped_column(
        Text,
        ForeignKey("skills_registry.code"),
        nullable=False,
    )
    execution_target: Mapped[str] = mapped_column(Text, nullable=False)
    rendered_command: Mapped[str] = mapped_column(Text, nullable=False)
    working_directory: Mapped[str | None] = mapped_column(Text)
    exit_code: Mapped[int | None] = mapped_column(Integer)
    stdout_preview: Mapped[str | None] = mapped_column(Text)
    stderr_preview: Mapped[str | None] = mapped_column(Text)
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    hitl_request_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("hitl_approval_requests.id"),
    )
    executed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )


class UserConnectorToken(Base):
    __tablename__ = "user_connector_tokens"
    __table_args__ = (UniqueConstraint("user_id", "provider", name="uq_user_connector_tokens_user_provider"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    provider: Mapped[str] = mapped_column(Text, nullable=False)
    encrypted_access_token: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    encrypted_refresh_token: Mapped[bytes | None] = mapped_column(LargeBinary)
    scopes: Mapped[list[Any]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'[]'::jsonb"),
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )


class AgentMemory(Base):
    __tablename__ = "agent_memories"
    __table_args__ = (
        Index(
            "idx_agent_memories_vec",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    memory_scope: Mapped[str] = mapped_column(Text, nullable=False)
    owner_user_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
    )
    department: Mapped[str | None] = mapped_column(Text)
    session_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True))
    source_reference: Mapped[str | None] = mapped_column(Text)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list[float]] = mapped_column(Vector(EMBEDDING_DIM), nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime | None] = _created_at()
