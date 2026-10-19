"""Browser WebSocket for reverse RPC. Implements: REQ-004, ADR-0002."""

from uuid import UUID

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from app.db.models import ChatSession, User
from app.db.session import database_session
from app.tool_bus.ws_rpc_manager import ws_rpc_manager

router = APIRouter()


@router.websocket("/ws/client-tools/{session_id}")
async def client_tools_socket(
    websocket: WebSocket,
    session_id: UUID,
    user_id: UUID = Query(...),
) -> None:
    async with database_session() as db:
        chat = await db.get(ChatSession, session_id)
        user = await db.get(User, user_id)
        owned = chat is not None and user is not None and chat.user_id == user_id
    if not owned:
        await websocket.accept()
        await websocket.close(code=1008)
        return
    await ws_rpc_manager.register_connection(str(user_id), str(session_id), websocket)
    try:
        while True:
            message = await websocket.receive_json()
            if isinstance(message, dict):
                await ws_rpc_manager.handle_client_message(str(user_id), str(session_id), message)
    except WebSocketDisconnect:
        await ws_rpc_manager.unregister_connection(str(user_id), str(session_id))
