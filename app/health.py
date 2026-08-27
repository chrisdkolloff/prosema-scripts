"""Unauthenticated liveness/readiness probe for Azure App Service."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import text

from app.db import SessionLocal
from app.jobs import worker_last_seen_at

logger = logging.getLogger(__name__)

WORKER_STALE_SECONDS = 90.0
_REPO_ROOT = Path(__file__).resolve().parents[1]


def _alembic_revision() -> str:
    try:
        with SessionLocal() as db:
            value = db.execute(text("SELECT version_num FROM alembic_version")).scalar()
        return str(value) if value else "unknown"
    except Exception:
        logger.exception("health: failed to read alembic_version")
        return "unknown"


def _alembic_head() -> str:
    try:
        cfg = Config(str(_REPO_ROOT / "alembic.ini"))
        script = ScriptDirectory.from_config(cfg)
        head = script.get_current_head()
        return str(head) if head else "unknown"
    except Exception:
        logger.exception("health: failed to read alembic head")
        return "unknown"


def _check_database() -> str:
    try:
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))
        return "ok"
    except Exception:
        logger.exception("health: database check failed")
        return "error"


def _worker_last_seen_seconds() -> float | str:
    seen = worker_last_seen_at()
    if seen is None:
        return "error"
    age = (datetime.now(UTC) - seen).total_seconds()
    return round(age, 1)


def build_health() -> tuple[int, dict[str, Any]]:
    """Return (HTTP status, JSON body). Never raises."""
    database = _check_database()
    worker_age = _worker_last_seen_seconds()
    alembic_revision = _alembic_revision()
    alembic_head = _alembic_head()

    worker_ok = isinstance(worker_age, (int, float)) and worker_age < WORKER_STALE_SECONDS
    healthy = database == "ok" and worker_ok

    body: dict[str, Any] = {
        "status": "ok" if healthy else "degraded",
        "database": database,
        "worker_last_seen_seconds": worker_age,
        "alembic_revision": alembic_revision,
        "alembic_head": alembic_head,
    }
    return (200 if healthy else 503, body)
