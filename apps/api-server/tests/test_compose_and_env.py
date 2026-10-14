"""Compose file and env template parse into the platform settings."""

from pathlib import Path

import yaml

from app.core.config import Settings

REPO_ROOT = Path(__file__).resolve().parents[3]


def _parse_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        key, value = stripped.split("=", 1)
        values[key] = value
    return values


def test_env_example_selects_bge_m3_and_its_dimension() -> None:
    loaded = Settings(**_parse_env(REPO_ROOT / ".env.example"))
    assert loaded.EMBEDDING_MODEL_NAME == "BAAI/bge-m3"
    assert loaded.EMBEDDING_DIMENSION == 1024
    assert loaded.EMBEDDING_BASE_URL == "http://localhost:8081/v1"
    assert loaded.SGLANG_BASE_URL == "http://localhost:30000/v1"
    assert loaded.DATABASE_URL.startswith("postgresql+asyncpg://")
    assert loaded.REDIS_URL == "redis://redis:6379/0"


def test_compose_file_starts_pgvector_postgres_and_redis() -> None:
    document = yaml.safe_load((REPO_ROOT / "docker-compose.yml").read_text(encoding="utf-8"))
    services = document["services"]
    assert services["postgres"]["image"] == "pgvector/pgvector:pg16"
    assert services["redis"]["image"] == "redis:7-alpine"
    assert services["api"]["env_file"] == [".env"]
    assert "8000:8000" in services["api"]["ports"]
    assert "3000:3000" in services["web"]["ports"]
    init_sql = (REPO_ROOT / "infra" / "postgres" / "init.sql").read_text(encoding="utf-8")
    assert 'CREATE EXTENSION IF NOT EXISTS "uuid-ossp"' in init_sql
    assert "CREATE EXTENSION IF NOT EXISTS vector" in init_sql
