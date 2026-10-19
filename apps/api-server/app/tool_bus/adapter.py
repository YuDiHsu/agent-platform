"""Pluggable tool adapters. Implements: ADR-0002, REQ-006."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, ClassVar


@dataclass(frozen=True)
class ToolSpec:
    code: str
    name: str
    description: str
    action_tier: str
    input_json_schema: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ToolContext:
    user_id: str
    session_id: str
    role_code: str
    access_token: str | None
    timeout_seconds: float


@dataclass(frozen=True)
class ToolResult:
    tool_name: str
    ok: bool
    output: dict[str, Any]
    error: str | None = None


class BaseToolAdapter(ABC):
    namespace: ClassVar[str]
    provider: ClassVar[str] = ""

    @abstractmethod
    def list_tools(self) -> list[ToolSpec]:
        """Tools this adapter contributes to the registry."""

    @abstractmethod
    async def health_check(self) -> bool:
        """Return whether the remote dependency answers."""

    @abstractmethod
    async def execute(self, tool_name: str, arguments: dict[str, Any], context: ToolContext) -> dict[str, Any]:
        """Run one tool. The caller has already released the database session."""


_REGISTRY: list[type[BaseToolAdapter]] = []


def register_tool_adapter(adapter: type[BaseToolAdapter]) -> type[BaseToolAdapter]:
    if adapter not in _REGISTRY:
        _REGISTRY.append(adapter)
    return adapter


def registered_adapters() -> list[type[BaseToolAdapter]]:
    return list(_REGISTRY)
