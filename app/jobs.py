"""Job enqueueing, handler registry, and in-process worker loop.

This design assumes a single App Service instance. ``FOR UPDATE SKIP LOCKED``
is what makes claiming safe if that ever stops being true: concurrent workers
will not pick up the same queued row.
"""

from __future__ import annotations

import inspect
import logging
import threading
import time
import traceback
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models import ArticleSnapshot, Job
from app.weclapp import job_error_message

logger = logging.getLogger(__name__)

JobHandler = Callable[[Session, dict], dict]
HANDLERS: dict[str, JobHandler] = {}

TERMINAL_STATUSES = frozenset({"succeeded", "failed"})

JOB_TYPE_LABELS = {
    "noop": "Testlauf",
    "weclapp_article_snapshot": "Artikel-Abfrage",
    "weclapp_supply_source_export": "Bezugsquellen-Abfrage",
}


def job_handler(name: str) -> Callable[[JobHandler], JobHandler]:
    def decorator(fn: JobHandler) -> JobHandler:
        HANDLERS[name] = fn
        return fn

    return decorator


@job_handler("noop")
def handle_noop(_db: Session, _payload: dict) -> dict:
    time.sleep(3)
    return {"message": "Testlauf erfolgreich"}


@job_handler("weclapp_article_snapshot")
def handle_weclapp_article_snapshot(
    db: Session,
    payload: dict,
    oid: str,
) -> dict:
    import uuid as uuid_mod

    from app.snapshots import fail_snapshot, pull_snapshot_rows

    snapshot_id = uuid_mod.UUID(str(payload["snapshot_id"]))
    snapshot = db.get(ArticleSnapshot, snapshot_id)
    if snapshot is None:
        raise ValueError("Snapshot nicht gefunden")
    try:
        return pull_snapshot_rows(db, snapshot, oid=oid)
    except Exception as exc:
        db.rollback()
        snapshot = db.get(ArticleSnapshot, snapshot_id)
        if snapshot is not None:
            message = job_error_message(exc) or "Abfrage fehlgeschlagen"
            fail_snapshot(db, snapshot, message)
        raise


@job_handler("weclapp_supply_source_export")
def handle_weclapp_supply_source_export(
    db: Session,
    payload: dict,
    oid: str,
) -> dict:
    import uuid as uuid_mod

    from app.models import ExportRun
    from app.supply_exports import fail_export, pull_export_rows

    run_id = uuid_mod.UUID(str(payload["export_run_id"]))
    run = db.get(ExportRun, run_id)
    if run is None:
        raise ValueError("Export-Lauf nicht gefunden")
    try:
        return pull_export_rows(db, run, oid=oid)
    except Exception as exc:
        db.rollback()
        run = db.get(ExportRun, run_id)
        if run is not None:
            message = job_error_message(exc) or "Abfrage fehlgeschlagen"
            fail_export(db, run, message)
        raise


def enqueue(db: Session, job_type: str, payload: dict, user: Mapping[str, Any]) -> Job:
    if job_type not in HANDLERS:
        raise ValueError(f"Unknown job type: {job_type!r}")
    job = Job(
        job_type=job_type,
        payload=payload,
        status="queued",
        created_by_oid=user["oid"],
        created_by_name=user["name"],
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def job_type_label(job_type: str) -> str:
    return JOB_TYPE_LABELS.get(job_type, job_type)


def list_active_jobs(db: Session) -> list[Job]:
    stmt = (
        select(Job)
        .where(Job.status.in_(("queued", "running")))
        .order_by(Job.created_at)
    )
    return list(db.scalars(stmt).all())


def _invoke_handler(handler: JobHandler, db: Session, job: Job) -> dict:
    payload = job.payload or {}
    try:
        n_params = len(inspect.signature(handler).parameters)
    except (TypeError, ValueError):
        n_params = 2
    if n_params >= 3:
        return handler(db, payload, job.created_by_oid)  # type: ignore[misc]
    return handler(db, payload)


def _claim_one_job(db: Session) -> Job | None:
    stmt = (
        select(Job)
        .where(Job.status == "queued")
        .order_by(Job.created_at)
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    job = db.scalars(stmt).first()
    if job is None:
        db.rollback()
        return None
    job.status = "running"
    job.started_at = datetime.now(UTC)
    job.attempts += 1
    db.commit()
    return job


def _execute_job(db: Session, job: Job) -> None:
    started = time.perf_counter()
    try:
        handler = HANDLERS.get(job.job_type)
        if handler is None:
            raise ValueError(f"Unknown job type: {job.job_type!r}")
        job.result = _invoke_handler(handler, db, job)
        job.status = "succeeded"
        job.error = None
    except Exception as exc:  # noqa: BLE001 — a handler raising must never kill the worker
        job.status = "failed"
        mapped = job_error_message(exc)
        job.error = mapped if mapped is not None else traceback.format_exc()
    job.finished_at = datetime.now(UTC)
    db.commit()
    duration = time.perf_counter() - started
    logger.info(
        "job %s type=%s status=%s duration=%.2fs",
        job.id,
        job.job_type,
        job.status,
        duration,
    )


def worker_loop(stop_event: threading.Event) -> None:
    logger.info("job worker started")
    last_heartbeat = 0.0

    while not stop_event.is_set():
        try:
            now = time.monotonic()
            if now - last_heartbeat >= 30:
                logger.info("job worker heartbeat")
                last_heartbeat = now

            with SessionLocal() as db:
                claim_started = time.perf_counter()
                job = _claim_one_job(db)
                claim_duration = time.perf_counter() - claim_started

                if claim_duration > 1.0:
                    logger.warning(
                        "job claim took %.2fs",
                        claim_duration,
                    )

                if job is not None:
                    logger.info(
                        "job worker claimed job %s type=%s",
                        job.id,
                        job.job_type,
                    )
                    _execute_job(db, job)
                    continue

            stop_event.wait(2.0)

        except Exception:
            logger.exception("worker loop iteration failed")
            stop_event.wait(2.0)
