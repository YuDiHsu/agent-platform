"""FastAPI entrypoint. Implements: REQ-001, REQ-008, REQ-012."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.health import router as health_router
from app.api.v1_chat import router as chat_router
from app.api.v1_rules_skills import router as rules_router
from app.api.v1_tools import router as tools_router
from app.core.config import settings
from app.db.migrate import run_migrations
from app.db.seed_runner import SeedRunner
from app.db.session import get_session_factory
from app.llm.embedding_client import EmbeddingClient


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    run_migrations()
    if settings.SEED_ON_STARTUP:
        async with get_session_factory()() as session:
            await SeedRunner(session, EmbeddingClient()).run()
    yield


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
app.include_router(rules_router, prefix="/api/v1")
app.include_router(tools_router, prefix="/api/v1")
