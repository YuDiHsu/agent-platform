"""Local MCP Daemon WebSocket for reverse RPC. Implements: REQ-005, ADR-0002."""

from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy import select

from app.core.pairing_token import token_digest
from app.db.models import LocalDaemonPairing, LocalWorkspaceMount
from app.db.session import database_session
from app.tool_bus.ws_rpc_manager import ws_rpc_manager

router = APIRouter()


async def authenticate_daemon(token: str) -> tuple[UUID, UUID] | None:
    """Return (user, pairing) for a live token and mark the daemon mount as most recently synced."""

    async with database_session() as db:
        row = await db.scalar(
            select(LocalDaemonPairing).where(
                LocalDaemonPairing.token_sha256 == token_digest(token),
                LocalDaemonPairing.revoked_at.is_(None),
            )
        )
        if row is None:
            return None
        now = datetime.now(UTC)
        row.last_connected_at = now
        if row.mount_id is not None:
            mount = await db.get(LocalWorkspaceMount, row.mount_id)
            if mount is not None:
                mount.last_synced_at = now
        return row.user_id, row.id


@router.websocket("/ws/local-daemon")
async def local_daemon_socket(websocket: WebSocket) -> None:
    header = websocket.headers.get("authorization", "")
    token = header.removeprefix("Bearer ").strip() if header.startswith("Bearer ") else ""
    paired = await authenticate_daemon(token) if token else None
    if paired is None:
        await websocket.accept()
        await websocket.close(code=1008)
        return
    user_id, pairing_id = str(paired[0]), str(paired[1])
    await ws_rpc_manager.register_daemon(user_id, pairing_id, websocket)
    try:
        while True:
            message = await websocket.receive_json()
            if isinstance(message, dict):
                await ws_rpc_manager.handle_client_message(user_id, "daemon", message)
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        await ws_rpc_manager.unregister_daemon(user_id, pairing_id, websocket)
