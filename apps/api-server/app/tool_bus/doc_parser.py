"""In-memory office conversion and ephemeral chunking. Implements: REQ-004, TC-M3-02."""

from datetime import UTC, datetime, timedelta
from io import BytesIO
from uuid import UUID

from markitdown import MarkItDown, StreamInfo

from app.db.models import AgentMemory
from app.db.session import database_session
from app.llm.embedding_client import EmbeddingClient

TOKEN_LIMIT = 3000
CHARS_PER_TOKEN = 4
CHUNK_CHARS = TOKEN_LIMIT * CHARS_PER_TOKEN
OFFICE_EXTENSIONS = {".docx", ".xlsx", ".pdf"}


def markdown_from_office_bytes(data: bytes, extension: str) -> str:
    """Convert one office document entirely in memory. Nothing is written to disk."""

    suffix = extension if extension.startswith(".") else f".{extension}"
    converted = MarkItDown(enable_plugins=False).convert(
        BytesIO(data),
        stream_info=StreamInfo(extension=suffix),
    )
    text = getattr(converted, "markdown", None)
    if not isinstance(text, str):
        fallback = getattr(converted, "text_content", "")
        text = fallback if isinstance(fallback, str) else ""
    return text


async def remember_oversized_markdown(
    *,
    owner_user_id: str,
    session_id: str,
    source_reference: str,
    markdown: str,
) -> bool:
    """Store EPHEMERAL_LOCAL_FILE slices when the markdown exceeds 3,000 tokens."""

    if len(markdown) <= CHUNK_CHARS:
        return False
    chunks = [markdown[index : index + CHUNK_CHARS] for index in range(0, len(markdown), CHUNK_CHARS)]
    vectors = await EmbeddingClient().embed_texts(chunks)
    expires_at = datetime.now(UTC) + timedelta(hours=24)
    async with database_session() as db:
        for index, (chunk, vector) in enumerate(zip(chunks, vectors, strict=True)):
            db.add(
                AgentMemory(
                    memory_scope="EPHEMERAL_LOCAL_FILE",
                    owner_user_id=UUID(owner_user_id),
                    session_id=UUID(session_id),
                    source_reference=f"{source_reference}#{index}",
                    content=chunk,
                    embedding=vector,
                    expires_at=expires_at,
                )
            )
    return True
