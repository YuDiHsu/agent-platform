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


def test_compose_runs_a_celery_worker_and_a_single_beat() -> None:
    services = yaml.safe_load((REPO_ROOT / "docker-compose.yml").read_text(encoding="utf-8"))["services"]
    for name, role in (("worker", "worker"), ("beat", "beat")):
        service = services[name]
        assert service["command"][:4] == ["celery", "-A", "app.workers.celery_app", role]
        assert service["env_file"] == [".env"]
        assert service["environment"]["REDIS_URL"] == "redis://redis:6379/0"
        assert service["depends_on"]["api"]["condition"] == "service_healthy"
    assert "replicas" not in services["beat"].get("deploy", {})


def test_celery_beat_schedules_heartbeats_and_ticket_sweeps() -> None:
    from app.workers.celery_app import celery_app

    schedule = celery_app.conf.beat_schedule
    assert schedule["fire-due-heartbeats"] == {"task": "eamp.fire_due_heartbeats", "schedule": 60.0}
    assert schedule["sweep-background-tickets"] == {"task": "eamp.sweep_background_tickets", "schedule": 15.0}
    assert {"eamp.fire_due_heartbeats", "eamp.sweep_background_tickets"} <= set(celery_app.tasks)
    assert celery_app.conf.task_acks_late is True
    assert celery_app.conf.worker_prefetch_multiplier == 1
