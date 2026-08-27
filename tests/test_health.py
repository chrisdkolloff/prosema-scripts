"""Tests for the unauthenticated /health probe."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

import app.jobs as jobs_mod
from app.db import engine
from app.health import WORKER_STALE_SECONDS, build_health
from app.jobs import (
    STALE_JOB_TIMEOUT_SECONDS,
    _JobHeartbeat,
    _sweep_stale_jobs,
    touch_worker_last_seen,
    worker_last_seen_at,
)
from app.main import app
from app.models import Job


def test_health_is_public_no_auth_redirect():
    client = TestClient(app)
    response = client.get("/health", follow_redirects=False)
    assert response.status_code in {200, 503}
    assert response.headers.get("location") is None
    assert response.headers["content-type"].startswith("application/json")
    body = response.json()
    assert set(body) == {
        "status",
        "database",
        "worker_last_seen_seconds",
        "alembic_revision",
        "alembic_head",
    }


def test_build_health_ok_when_db_and_worker_fresh():
    fixed_now = datetime(2026, 8, 27, 12, 0, 4, 200_000, tzinfo=UTC)
    fresh = datetime(2026, 8, 27, 12, 0, 0, tzinfo=UTC)
    with (
        patch("app.health._check_database", return_value="ok"),
        patch("app.health.worker_last_seen_at", return_value=fresh),
        patch("app.health._alembic_revision", return_value="011_job_leases"),
        patch("app.health._alembic_head", return_value="011_job_leases"),
        patch("app.health.datetime") as mock_datetime,
    ):
        mock_datetime.now.return_value = fixed_now
        status_code, body = build_health()
    assert status_code == 200
    assert body == {
        "status": "ok",
        "database": "ok",
        "worker_last_seen_seconds": 4.2,
        "alembic_revision": "011_job_leases",
        "alembic_head": "011_job_leases",
    }


def test_build_health_degraded_when_database_errors():
    fresh = datetime.now(UTC)
    with (
        patch("app.health._check_database", return_value="error"),
        patch("app.health.worker_last_seen_at", return_value=fresh),
        patch("app.health._alembic_revision", return_value="unknown"),
        patch("app.health._alembic_head", return_value="011_job_leases"),
    ):
        status_code, body = build_health()
    assert status_code == 503
    assert body["status"] == "degraded"
    assert body["database"] == "error"


def test_build_health_degraded_when_worker_stale():
    stale = datetime.now(UTC) - timedelta(seconds=WORKER_STALE_SECONDS + 10)
    with (
        patch("app.health._check_database", return_value="ok"),
        patch("app.health.worker_last_seen_at", return_value=stale),
        patch("app.health._alembic_revision", return_value="011_job_leases"),
        patch("app.health._alembic_head", return_value="011_job_leases"),
    ):
        status_code, body = build_health()
    assert status_code == 503
    assert body["status"] == "degraded"
    assert body["database"] == "ok"
    assert isinstance(body["worker_last_seen_seconds"], float)
    assert body["worker_last_seen_seconds"] >= WORKER_STALE_SECONDS


def test_build_health_degraded_when_worker_never_seen():
    with (
        patch("app.health._check_database", return_value="ok"),
        patch("app.health.worker_last_seen_at", return_value=None),
        patch("app.health._alembic_revision", return_value="011_job_leases"),
        patch("app.health._alembic_head", return_value="011_job_leases"),
    ):
        status_code, body = build_health()
    assert status_code == 503
    assert body["status"] == "degraded"
    assert body["worker_last_seen_seconds"] == "error"


def test_alembic_mismatch_does_not_degrade_status():
    fresh = datetime.now(UTC)
    with (
        patch("app.health._check_database", return_value="ok"),
        patch("app.health.worker_last_seen_at", return_value=fresh),
        patch("app.health._alembic_revision", return_value="010_sales_article_number_always"),
        patch("app.health._alembic_head", return_value="011_job_leases"),
    ):
        status_code, body = build_health()
    assert status_code == 200
    assert body["status"] == "ok"
    assert body["alembic_revision"] != body["alembic_head"]


def _health_with_real_worker_clock():
    """build_health using the real worker_last_seen_at; DB/alembic patched."""
    with (
        patch("app.health._check_database", return_value="ok"),
        patch("app.health._alembic_revision", return_value="011_job_leases"),
        patch("app.health._alembic_head", return_value="011_job_leases"),
    ):
        return build_health()


def test_health_ok_when_worker_ticking_no_job():
    touch_worker_last_seen()
    status_code, body = _health_with_real_worker_clock()
    assert status_code == 200
    assert body["status"] == "ok"
    assert isinstance(body["worker_last_seen_seconds"], float)
    assert body["worker_last_seen_seconds"] < WORKER_STALE_SECONDS


def test_health_degraded_when_worker_last_seen_120s_ago():
    jobs_mod._worker_last_seen = datetime.now(UTC) - timedelta(seconds=120)
    status_code, body = _health_with_real_worker_clock()
    assert status_code == 503
    assert body["status"] == "degraded"
    assert isinstance(body["worker_last_seen_seconds"], float)
    assert body["worker_last_seen_seconds"] >= 120


def test_health_stays_ok_when_only_job_heartbeat_ticks():
    """Long job: worker loop blocked; only the per-job heartbeat refreshes liveness."""
    job_id = uuid.uuid4()
    heartbeat = _JobHeartbeat(job_id)

    # Simulate >90s of blocked worker-loop by ageing the stamp, then ticking.
    for _ in range(4):
        jobs_mod._worker_last_seen = datetime.now(UTC) - timedelta(seconds=100)
        aged = worker_last_seen_at()
        assert aged is not None
        assert (datetime.now(UTC) - aged).total_seconds() >= 90

        with patch.object(jobs_mod, "SessionLocal") as mock_sessions:
            # Avoid DB I/O; tick must still refresh process liveness.
            session = mock_sessions.return_value.__enter__.return_value
            session.execute.return_value = None
            heartbeat.tick()

        status_code, body = _health_with_real_worker_clock()
        assert status_code == 200, body
        assert body["status"] == "ok"
        assert body["worker_last_seen_seconds"] < WORKER_STALE_SECONDS


@pytest.fixture
def db_session():
    connection = engine.connect()
    trans = connection.begin()
    session = Session(
        bind=connection,
        join_transaction_mode="create_savepoint",
        expire_on_commit=False,
    )
    try:
        yield session
    finally:
        session.close()
        trans.rollback()
        connection.close()


def test_wedged_job_healthy_process_health_ok_sweep_selects(db_session):
    """Process liveness fresh, job lease stale → /health 200 and sweep requeues."""
    assert STALE_JOB_TIMEOUT_SECONDS == 300
    now = datetime.now(UTC)
    job = Job(
        id=uuid.uuid4(),
        job_type="noop",
        payload={},
        status="running",
        created_by_oid="oid-health",
        created_by_name="Health Test",
        started_at=now - timedelta(seconds=400),
        heartbeat_at=now - timedelta(seconds=400),
        attempts=1,
        worker_id="test-worker",
    )
    db_session.add(job)
    db_session.commit()

    touch_worker_last_seen()
    status_code, body = _health_with_real_worker_clock()
    assert status_code == 200
    assert body["status"] == "ok"

    _sweep_stale_jobs(db_session)
    db_session.refresh(job)
    assert job.status == "queued"
    assert job.heartbeat_at is None
    assert job.worker_id is None
