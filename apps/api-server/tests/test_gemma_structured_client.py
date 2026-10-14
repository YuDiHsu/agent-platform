"""TC-M1-03: strict JSON Schema decoding parses on every call."""

import json
from typing import Literal

import httpx
import pytest
from openai import AsyncOpenAI
from pydantic import BaseModel, ValidationError

from app.llm.gemma_client import GemmaSGLangClient


class ProbeAnswer(BaseModel):
    answer: Literal["pong"]
    seq: int


def _completion(content: str) -> dict[str, object]:
    return {
        "id": "chatcmpl-test",
        "object": "chat.completion",
        "created": 0,
        "model": "gemma-4-27b-it",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
    }


@pytest.mark.asyncio
async def test_fifty_strict_schema_calls_all_parse() -> None:
    seen: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        return httpx.Response(200, json=_completion('{"answer":"pong","seq":7}'))

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        gemma = GemmaSGLangClient(
            client=AsyncOpenAI(
                base_url="http://sglang.test/v1",
                api_key="local",
                http_client=http_client,
                max_retries=0,
            )
        )
        parsed = [
            await gemma.generate_structured(
                system_prompt="Reply with the probe object.",
                messages=[{"role": "user", "content": "ping"}],
                response_model=ProbeAnswer,
            )
            for _ in range(50)
        ]

    assert len(parsed) == 50
    assert all(item.answer == "pong" and item.seq == 7 for item in parsed)
    assert len(seen) == 50
    for body in seen:
        response_format = body["response_format"]
        assert isinstance(response_format, dict)
        assert response_format["type"] == "json_schema"
        json_schema = response_format["json_schema"]
        assert isinstance(json_schema, dict)
        assert json_schema["strict"] is True
        assert json_schema["name"] == "ProbeAnswer"


@pytest.mark.asyncio
async def test_invalid_model_json_is_rejected() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_completion('{"answer":"nope","seq":1}'))

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        gemma = GemmaSGLangClient(
            client=AsyncOpenAI(
                base_url="http://sglang.test/v1",
                api_key="local",
                http_client=http_client,
                max_retries=0,
            )
        )
        with pytest.raises(ValidationError):
            await gemma.generate_structured(
                system_prompt="Reply with the probe object.",
                messages=[{"role": "user", "content": "ping"}],
                response_model=ProbeAnswer,
            )
