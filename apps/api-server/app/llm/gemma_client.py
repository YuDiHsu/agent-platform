"""SGLang JSON Schema constrained decoding. Implements: REQ-008."""

from typing import Any, TypeVar

from openai import AsyncOpenAI
from pydantic import BaseModel

from app.core.config import settings

T = TypeVar("T", bound=BaseModel)


class GemmaSGLangClient:
    """Local Gemma 4 client that forces strict JSON Schema decoding."""

    def __init__(self, client: AsyncOpenAI | None = None) -> None:
        self.client = client or AsyncOpenAI(
            base_url=settings.SGLANG_BASE_URL,
            api_key=settings.SGLANG_API_KEY,
        )

    async def generate_structured(
        self,
        system_prompt: str,
        messages: list[dict[str, Any]],
        response_model: type[T],
        model_name: str = "gemma-4-27b-it",
        temperature: float = 0.15,
    ) -> T:
        schema = response_model.model_json_schema()
        response = await self.client.chat.completions.create(  # type: ignore[call-overload]
            model=model_name,
            messages=[{"role": "system", "content": system_prompt}, *messages],
            temperature=temperature,
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": response_model.__name__,
                    "schema": schema,
                    "strict": True,
                },
            },
        )
        raw_json = response.choices[0].message.content or "{}"
        return response_model.model_validate_json(raw_json)
