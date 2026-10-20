"""FastAPI entrypoint. Implements: REQ-001, REQ-008, REQ-012."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.health import router as health_router
from app.api.v1_agents import router as agents_router
from app.api.v1_chat import router as chat_router
from app.api.v1_daemon import router as daemon_router
from app.api.v1_heartbeats import router as heartbeats_router
from app.api.v1_hitl import router as hitl_router
from app.api.v1_rules_skills import router as rules_router
from app.api.v1_mounts import router as mounts_router
from app.api.v1_tools import router as tools_router
from app.api.ws_client_tools import router as ws_router
from app.api.ws_local_daemon import router as daemon_ws_router
from app.core.config import settings
from app.db.migrate import run_migrations
from app.db.seed_runner import SeedRunner
from app.db.session import get_session_factory
from app.llm.embedding_client import EmbeddingClient
from app.tool_bus.http_pool import get_http_client, set_http_client
from app.tool_bus.ws_rpc_manager import ws_rpc_manager


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    get_http_client()
    run_migrations()
    if settings.SEED_ON_STARTUP:
        async with get_session_factory()() as session:
            await SeedRunner(session, EmbeddingClient()).run()
    await ws_rpc_manager.start()
    yield
    await ws_rpc_manager.aclose()
    await get_http_client().aclose()
    set_http_client(None)


app = FastAPI(title="Enterprise Multi-Agent Platform", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(health_router)
app.include_router(chat_router, prefix="/api/v1")
app.include_router(agents_router, prefix="/api/v1")
app.include_router(hitl_router, prefix="/api/v1")
app.include_router(heartbeats_router, prefix="/api/v1")
app.include_router(rules_router, prefix="/api/v1")
app.include_router(tools_router, prefix="/api/v1")
app.include_router(mounts_router, prefix="/api/v1")
app.include_router(ws_router, prefix="/api/v1")
app.include_router(daemon_router, prefix="/api/v1")
app.include_router(daemon_ws_router, prefix="/api/v1")
