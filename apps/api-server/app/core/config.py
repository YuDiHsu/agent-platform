"""Runtime settings. Implements: REQ-001, REQ-008, REQ-012, ADR-0001."""

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[4]
_ENV_FILE = REPO_ROOT / ".env"


class Settings(BaseSettings):
    """Environment-driven platform settings.

    Embedding model and dimension are read from the environment so SQLAlchemy
    models and Alembic never hard-code a vector width. See ADR-0001.
    """

    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE) if _ENV_FILE.exists() else None,
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    DATABASE_URL: str = "postgresql+asyncpg://eamp:eamp@localhost:5432/eamp"
    DATABASE_NULL_POOL: bool = False
    REDIS_URL: str = "redis://localhost:6379/0"
    SGLANG_BASE_URL: str = "http://localhost:30000/v1"
    SGLANG_API_KEY: str = "local"
    EMBEDDING_BASE_URL: str = "http://localhost:8081/v1"
    EMBEDDING_MODEL_NAME: str = "BAAI/bge-m3"
    EMBEDDING_DIMENSION: int = Field(default=1024, ge=1)
    EMBEDDING_API_KEY: str = "local"
    SEED_ON_STARTUP: bool = True
    CORS_ORIGINS: str = "http://localhost:3000"

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]

    @property
    def sync_database_url(self) -> str:
        """psycopg URL for Alembic. Alembic runs migrations on a sync engine."""
        url = self.DATABASE_URL
        for prefix in ("postgresql+psycopg_async://", "postgresql+asyncpg://", "postgresql://"):
            if url.startswith(prefix):
                return "postgresql+psycopg://" + url[len(prefix) :]
        return url


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
