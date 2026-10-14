"""Async database session. Implements: REQ-012."""

from collections.abc import AsyncIterator
from typing import Any

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import settings

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        connect_args: dict[str, Any]
        if settings.DATABASE_URL.startswith("postgresql+asyncpg"):
            connect_args = {"ssl": False, "statement_cache_size": 0}
        else:
            connect_args = {"prepare_threshold": None}
        if settings.DATABASE_NULL_POOL:
            _engine = create_async_engine(
                settings.DATABASE_URL,
                pool_pre_ping=True,
                poolclass=NullPool,
                connect_args=connect_args,
            )
        else:
            _engine = create_async_engine(
                settings.DATABASE_URL,
                pool_pre_ping=True,
                connect_args=connect_args,
            )
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(get_engine(), expire_on_commit=False)
    return _session_factory


async def get_session() -> AsyncIterator[AsyncSession]:
    async with get_session_factory()() as session:
        yield session


def reset_engine() -> None:
    """Drop the cached engine so tests can point at a new database URL."""
    global _engine, _session_factory
    _engine = None
    _session_factory = None
