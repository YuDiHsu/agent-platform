"""Pair a Local MCP Daemon with the current user. Implements: REQ-005, ADR-0002."""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.api.deps import CurrentUser, require_user
from app.core.pairing_token import new_pairing_token, token_digest
from app.db.models import LocalDaemonPairing, LocalWorkspaceMount
from app.db.session import database_session
from app.tool_bus.local_fs import DAEMON_PROVIDER
from app.tool_bus.ws_rpc_manager import DAEMON_HANDLE_PREFIX, ws_rpc_manager

router = APIRouter()


class PairingCreate(BaseModel):
    label: str = Field(min_length=1, max_length=100)


def _out(row: LocalDaemonPairing) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "label": row.label,
        "mount_id": str(row.mount_id) if row.mount_id else None,
        "last_connected_at": row.last_connected_at.isoformat() if row.last_connected_at else None,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def _socket_url(request: Request) -> str:
    base = str(request.base_url).rstrip("/")
    scheme = "wss" if base.startswith("https") else "ws"
    return f"{scheme}{base[base.index(':'):]}/api/v1/ws/local-daemon"


@router.get("/daemon/pairings")
async def list_pairings(user: CurrentUser = Depends(require_user)) -> list[dict[str, Any]]:
    async with database_session() as db:
        rows = (
            await db.scalars(
                select(LocalDaemonPairing)
                .where(LocalDaemonPairing.user_id == user.id, LocalDaemonPairing.revoked_at.is_(None))
                .order_by(LocalDaemonPairing.created_at)
            )
        ).all()
        return [_out(row) for row in rows]


@router.post("/daemon/pairings", status_code=201)
async def create_pairing(
    body: PairingCreate, request: Request, user: CurrentUser = Depends(require_user)
) -> dict[str, Any]:
    token = new_pairing_token()
    async with database_session() as db:
        mount = LocalWorkspaceMount(user_id=user.id, mount_alias=body.label, provider_type=DAEMON_PROVIDER)
        db.add(mount)
        await db.flush()
        row = LocalDaemonPairing(user_id=user.id, mount_id=mount.id, label=body.label, token_sha256=token_digest(token))
        db.add(row)
        await db.flush()
        mount.browser_handle_key = f"{DAEMON_HANDLE_PREFIX}{row.id}"
        await db.refresh(row)
        command = (
            "uv run packages/local-mcp-daemon/daemon.py "
            f"--server {_socket_url(request)} --token {token} --root <本機資料夾>"
        )
        return {**_out(row), "token": token, "command": command}


@router.delete("/daemon/pairings/{pairing_id}", status_code=204)
async def revoke_pairing(pairing_id: UUID, user: CurrentUser = Depends(require_user)) -> None:
    async with database_session() as db:
        row = await db.get(LocalDaemonPairing, pairing_id)
        if row is None or row.user_id != user.id or row.revoked_at is not None:
            raise HTTPException(status_code=404, detail="找不到配對")
        row.revoked_at = datetime.now(UTC)
        if row.mount_id is not None:
            mount = await db.get(LocalWorkspaceMount, row.mount_id)
            row.mount_id = None
            if mount is not None:
                await db.delete(mount)
    await ws_rpc_manager.close_daemon(str(user.id), str(pairing_id))
