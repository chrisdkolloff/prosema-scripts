"""Tests for job enqueueing and the jobs table CHECK constraint."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.exc import IntegrityError

from app.db import SessionLocal
from app.jobs import enqueue
from app.models import Job


@pytest.fixture
def db_session():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


def test_enqueue_unknown_job_type_raises():
    with pytest.raises(ValueError, match="Unknown job type"):
        enqueue(
            db=None,  # type: ignore[arg-type]
            job_type="not-a-real-job",
            payload={},
            user={"oid": "oid-1", "name": "Test User"},
        )


def test_job_status_check_constraint_rejects_invalid_value(db_session):
    job = Job(
        id=uuid.uuid4(),
        job_type="noop",
        payload={},
        status="not-a-status",
        created_by_oid="oid-1",
        created_by_name="Test User",
    )
    db_session.add(job)
    with pytest.raises(IntegrityError):
        db_session.commit()
