"""OpenAI-compatible embedding client. Implements: ADR-0001, REQ-009."""

import math

from openai import AsyncOpenAI

from app.core.config import settings


class EmbeddingDimensionError(ValueError):
    """The embedding provider returned a vector that cannot be stored."""


class EmbeddingClient:
    """Turns text into L2-normalized vectors of `settings.EMBEDDING_DIMENSION`."""

    def __init__(self, client: AsyncOpenAI | None = None) -> None:
        self._client = client or AsyncOpenAI(
            base_url=settings.EMBEDDING_BASE_URL,
            api_key=settings.EMBEDDING_API_KEY,
        )

    async def embed_text(self, text: str) -> list[float]:
        vectors = await self.embed_texts([text])
        return vectors[0]

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        response = await self._client.embeddings.create(
            model=settings.EMBEDDING_MODEL_NAME,
            input=texts,
        )
        ordered = sorted(response.data, key=lambda item: item.index)
        if len(ordered) != len(texts):
            raise EmbeddingDimensionError(
                f"expected {len(texts)} embeddings, received {len(ordered)}"
            )
        return [self._normalize(list(item.embedding)) for item in ordered]

    def _normalize(self, vector: list[float]) -> list[float]:
        expected = settings.EMBEDDING_DIMENSION
        if len(vector) != expected:
            raise EmbeddingDimensionError(
                f"expected {expected} dimensions, received {len(vector)}"
            )
        norm = math.sqrt(sum(component * component for component in vector))
        if norm == 0.0:
            raise EmbeddingDimensionError("embedding provider returned a zero vector")
        return [component / norm for component in vector]
