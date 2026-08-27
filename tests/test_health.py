"""Tests for the unauthenticated /health probe."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.health import WORKER_STALE_SECONDS, build_health
from app.main import app


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
