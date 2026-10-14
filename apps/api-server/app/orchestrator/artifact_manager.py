"""Store the full deliverable and return a 200-character claim-check.

Implements: REQ-008, ADR-0002.
"""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import SharedArtifact
from app.orchestrator.state import ArtifactPointer

SUMMARY_CHAR_LIMIT = 200


def clip_summary(summary: str | None, fallback: str) -> str:
    text = (summary or "").strip() or fallback.strip() or "交付物"
    return text[:SUMMARY_CHAR_LIMIT]


async def store_artifact(
    session: AsyncSession,
    *,
    session_id: UUID,
    producer_role_code: str,
    artifact_type: str,
    title: str,
    summary: str | None,
    content_body: str,
    handoff_notes: str | None,
) -> tuple[ArtifactPointer, str]:
    clipped = clip_summary(summary, title)
    row = SharedArtifact(
        session_id=session_id,
        producer_role_code=producer_role_code,
        artifact_type=artifact_type,
        title=title,
        summary_200_words=clipped,
        content_body=content_body,
        structured_metadata={"handoff_notes": handoff_notes} if handoff_notes else {},
    )
    session.add(row)
    await session.flush()
    await session.refresh(row)
    pointer = ArtifactPointer(
        artifact_id=str(row.id),
        producer_role=producer_role_code,
        title=title,
        artifact_type=artifact_type,
        summary_200_words=clipped,
    )
    created_at = row.created_at.isoformat() if row.created_at is not None else ""
    return pointer, created_at


def compose_instructions(
    *,
    detailed: str,
    goal_ancestry: list[str],
    pointers: list[ArtifactPointer],
) -> str:
    """Prompt text for the next role. Pointers only; the body is not interpolated."""

    lines = [
        "目標繼承：" + " > ".join(goal_ancestry),
        f"本步指示：{detailed}",
        "上游產出物指標：",
    ]
    if not pointers:
        lines.append("（無）")
    for pointer in pointers:
        lines.append(
            " - "
            f"artifact_id={pointer.artifact_id}"
            f"；標題={pointer.title}"
            f"；類別={pointer.artifact_type}"
            f"；摘要={pointer.summary_200_words}"
        )
    return "\n".join(lines)
