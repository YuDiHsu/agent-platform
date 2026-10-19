"""Database-mounted remote MCP and webhook adapters. Implements: ADR-0002."""

from typing import Any

from app.tool_bus.adapter import BaseToolAdapter, ToolContext, ToolSpec
from app.tool_bus.http_pool import get_http_client


class RemoteMCPToolAdapter(BaseToolAdapter):
    namespace = "remote_mcp"

    def __init__(self, url: str) -> None:
        self._url = url

    def list_tools(self) -> list[ToolSpec]:
        return []

    async def health_check(self) -> bool:
        response = await get_http_client().post(self._url, json={"jsonrpc": "2.0", "method": "ping", "id": 1})
        return response.status_code < 500

    async def execute(self, tool_name: str, arguments: dict[str, Any], context: ToolContext) -> dict[str, Any]:
        response = await get_http_client().post(
            self._url,
            json={"jsonrpc": "2.0", "method": "tools/call", "params": {"name": tool_name, "arguments": arguments}, "id": 1},
        )
        response.raise_for_status()
        body = response.json()
        return body if isinstance(body, dict) else {"result": body}


class HttpWebhookToolAdapter(BaseToolAdapter):
    namespace = "http_webhook"

    def __init__(self, url: str) -> None:
        self._url = url

    def list_tools(self) -> list[ToolSpec]:
        return []

    async def health_check(self) -> bool:
        response = await get_http_client().get(self._url)
        return response.status_code < 500

    async def execute(self, tool_name: str, arguments: dict[str, Any], context: ToolContext) -> dict[str, Any]:
        response = await get_http_client().post(self._url, json={"tool": tool_name, "arguments": arguments})
        response.raise_for_status()
        body = response.json()
        return body if isinstance(body, dict) else {"result": body}
