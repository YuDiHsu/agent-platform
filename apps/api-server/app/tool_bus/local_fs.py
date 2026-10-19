"""Browser-backed local folder tools. Implements: REQ-004, REQ-012, TC-M3-02."""

import base64
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import select

from app.db.models import LocalWorkspaceMount
from app.db.session import database_session
from app.tool_bus.adapter import BaseToolAdapter, ToolContext, ToolSpec, register_tool_adapter
from app.tool_bus.doc_parser import OFFICE_EXTENSIONS, markdown_from_office_bytes, remember_oversized_markdown
from app.tool_bus.ws_rpc_manager import ws_rpc_manager

_OFFLINE = {
    "status": "BROWSER_OFFLINE",
    "error": "使用者的瀏覽器分頁未連線，請開啟平台網頁以授權存取本機資料夾。",
}
_RPC_TIMEOUT_SECONDS = 30.0


def _schema(properties: dict[str, Any]) -> dict[str, Any]:
    return {"type": "object", "properties": properties}


@register_tool_adapter
class LocalFsAdapter(BaseToolAdapter):
    namespace = "local_fs"

    def list_tools(self) -> list[ToolSpec]:
        return [
            ToolSpec(
                "workspace_list_files",
                "列出本機檔案",
                "列出使用者已授權本機資料夾中的檔案。",
                "READ",
                _schema({"mount_id": {"type": "string"}, "path": {"type": "string"}}),
            ),
            ToolSpec(
                "workspace_read_file",
                "讀取本機檔案",
                "讀取使用者已授權本機資料夾中的檔案。Office 檔會轉成 Markdown。",
                "READ",
                _schema({"mount_id": {"type": "string"}, "path": {"type": "string"}}),
            ),
            ToolSpec(
                "workspace_write_file",
                "寫入本機檔案",
                "在使用者確認紅綠差異後，寫入已授權的本機資料夾。",
                "COMMIT",
                _schema(
                    {
                        "mount_id": {"type": "string"},
                        "path": {"type": "string"},
                        "content": {"type": "string"},
                    }
                ),
            ),
        ]

    async def health_check(self) -> bool:
        return True

    async def execute(self, tool_name: str, arguments: dict[str, Any], context: ToolContext) -> dict[str, Any]:
        owner_id, handle_key = await mount_owner_and_handle(context.user_id, arguments.get("mount_id"))
        if not handle_key:
            return dict(_OFFLINE)
        path = str(arguments.get("path") or arguments.get("file_path") or "")
        if tool_name == "workspace_list_files":
            return await ws_rpc_manager.call_browser_tool(
                requester_user_id=context.user_id,
                mount_owner_user_id=owner_id,
                session_id=context.session_id,
                method="CLIENT_FS_LIST",
                params={"browser_handle_key": handle_key, "file_path": path},
                timeout=_RPC_TIMEOUT_SECONDS,
            )
        if tool_name == "workspace_read_file":
            return await self._read(context, owner_id, handle_key, path)
        if tool_name == "workspace_write_file":
            return await ws_rpc_manager.call_browser_tool(
                requester_user_id=context.user_id,
                mount_owner_user_id=owner_id,
                session_id=context.session_id,
                method="CLIENT_FS_WRITE",
                params={
                    "browser_handle_key": handle_key,
                    "file_path": path,
                    "content": str(arguments.get("content", "")),
                },
                timeout=_RPC_TIMEOUT_SECONDS,
            )
        raise ValueError(f"不支援的本機檔案工具: {tool_name}")

    async def _read(self, context: ToolContext, owner_id: str, handle_key: str, path: str) -> dict[str, Any]:
        rpc = await ws_rpc_manager.call_browser_tool(
            requester_user_id=context.user_id,
            mount_owner_user_id=owner_id,
            session_id=context.session_id,
            method="CLIENT_FS_READ",
            params={"browser_handle_key": handle_key, "file_path": path},
            timeout=_RPC_TIMEOUT_SECONDS,
        )
        if rpc.get("status") != "SUCCESS":
            return rpc
        data = rpc.get("data")
        payload = data if isinstance(data, dict) else {}
        suffix = Path(path).suffix.lower()
        if payload.get("encoding") == "base64" and suffix in OFFICE_EXTENSIONS:
            raw = base64.b64decode(str(payload.get("content", "")))
            markdown = markdown_from_office_bytes(raw, suffix)
        else:
            markdown = str(payload.get("content", ""))
        chunked = False
        if suffix in OFFICE_EXTENSIONS:
            chunked = await remember_oversized_markdown(
                owner_user_id=context.user_id,
                session_id=context.session_id,
                source_reference=path,
                markdown=markdown,
            )
        return {"status": "SUCCESS", "path": path, "markdown": markdown, "chunked": chunked}


async def mount_owner_and_handle(user_id: str, mount_id: object) -> tuple[str, str]:
    async with database_session() as db:
        if mount_id:
            mount = await db.get(LocalWorkspaceMount, UUID(str(mount_id)))
        else:
            mount = await db.scalar(
                select(LocalWorkspaceMount)
                .where(LocalWorkspaceMount.user_id == UUID(user_id))
                .order_by(LocalWorkspaceMount.last_synced_at.desc())
            )
        if mount is None or not mount.browser_handle_key:
            return "", ""
        return str(mount.user_id), mount.browser_handle_key
