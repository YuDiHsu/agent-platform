"""Embedding client returns unit vectors of the configured width. Implements: ADR-0001."""

import json

import httpx
import pytest
from openai import AsyncOpenAI

from app.llm.embedding_client import EmbeddingClient, EmbeddingDimensionError


def _embedding_response(vectors: list[tuple[int, list[float]]], model: str) -> dict[str, object]:
    return {
        "object": "list",
        "data": [
            {"object": "embedding", "index": index, "embedding": vector} for index, vector in vectors
        ],
        "model": model,
        "usage": {"prompt_tokens": 1, "total_tokens": 1},
    }


@pytest.mark.asyncio
async def test_single_text_is_l2_normalized_to_configured_width(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.llm.embedding_client.settings.EMBEDDING_DIMENSION", 2)
    seen: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        seen.append(body)
        return httpx.Response(200, json=_embedding_response([(0, [3.0, 4.0])], str(body["model"])))

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        client = EmbeddingClient(
            client=AsyncOpenAI(
                base_url="http://embedding.test/v1",
                api_key="local",
                http_client=http_client,
                max_retries=0,
            )
        )
        vector = await client.embed_text("角色路由")

    assert seen[0]["model"] == "BAAI/bge-m3"
    assert seen[0]["input"] == ["角色路由"]
    assert vector == pytest.approx([0.6, 0.8])


@pytest.mark.asyncio
async def test_batch_preserves_input_order_after_normalization(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.llm.embedding_client.settings.EMBEDDING_DIMENSION", 2)

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        return httpx.Response(
            200,
            json=_embedding_response([(1, [0.0, 5.0]), (0, [3.0, 4.0])], str(body["model"])),
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        client = EmbeddingClient(
            client=AsyncOpenAI(
                base_url="http://embedding.test/v1",
                api_key="local",
                http_client=http_client,
                max_retries=0,
            )
        )
        first, second = await client.embed_texts(["alpha", "beta"])

    assert first == pytest.approx([0.6, 0.8])
    assert second == pytest.approx([0.0, 1.0])


@pytest.mark.asyncio
async def test_wrong_width_is_rejected() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        return httpx.Response(200, json=_embedding_response([(0, [3.0, 4.0])], str(body["model"])))

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        client = EmbeddingClient(
            client=AsyncOpenAI(
                base_url="http://embedding.test/v1",
                api_key="local",
                http_client=http_client,
                max_retries=0,
            )
        )
        with pytest.raises(EmbeddingDimensionError):
            await client.embed_text("too short")
