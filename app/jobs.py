"""Job enqueueing, handler registry, and in-process worker loop.

This design assumes a single App Service instance. ``FOR UPDATE SKIP LOCKED``
is what makes claiming safe if that ever stops being true: concurrent workers
will not pick up the same queued row. The same locking is used when sweeping
stale ``running`` leases after a process restart.
"""

from __future__ import annotations

import inspect
import logging
import os
import socket
import threading
import time
import traceback
import uuid
from collections.abc import Callable, Mapping
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import or_, select, update
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models import ArticleSnapshot, Job
from app.weclapp import job_error_message

logger = logging.getLogger(__name__)

JobHandler = Callable[[Session, dict], dict]
HANDLERS: dict[str, JobHandler] = {}

TERMINAL_STATUSES = frozenset({"succeeded", "failed"})

# Longest known job (article snapshot) runs ~16 seconds.
STALE_JOB_TIMEOUT_SECONDS = 300
MAX_JOB_ATTEMPTS = 3

_shutdown = threading.Event()
_WORKER_ID: str | None = None
_worker_last_seen: datetime | None = None


def worker_last_seen_at() -> datetime | None:
    """UTC timestamp of the last process-liveness touch, or None if never started."""
    return _worker_last_seen


def touch_worker_last_seen() -> None:
    """Record that the worker process is alive (loop tick or in-job heartbeat)."""
    global _worker_last_seen
    _worker_last_seen = datetime.now(UTC)

JOB_TYPE_LABELS = {
    "noop": "Testlauf",
    "weclapp_article_snapshot": "Artikel-Abfrage",
    "weclapp_supply_source_export": "Bezugsquellen-Abfrage",
}

_STALE_FAILURE_ERROR = (
    "Auftrag nach 3 Versuchen abgebrochen. Der Hintergrundprozess wurde "
    "mehrfach unterbrochen. Bitte den Auftrag neu starten oder Christopher "
    "informieren."
)


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


class _JobHeartbeat:
    """Daemon thread that refreshes ``heartbeat_at`` every 30s in its own session."""

    def __init__(self, job_id: uuid.UUID) -> None:
        self._job_id = job_id
        self._stop = threading.Event()
        self._thread = threading.Thread(
            target=self._run,
            name=f"job-heartbeat-{job_id}",
            daemon=True,
        )

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=1.0)

    def tick(self) -> None:
        """Refresh process liveness and the job lease ``heartbeat_at``."""
        touch_worker_last_seen()
        try:
            with SessionLocal() as db:
                db.execute(
                    update(Job)
                    .where(Job.id == self._job_id)
                    .values(heartbeat_at=datetime.now(UTC))
                )
                db.commit()
        except Exception:
            logger.exception(
                "job heartbeat update failed for %s",
                self._job_id,
            )

    def _run(self) -> None:
        while not self._stop.wait(30.0):
            self.tick()


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
    now = datetime.now(UTC)
    job.status = "running"
    job.started_at = now
    job.heartbeat_at = now
    job.worker_id = _WORKER_ID
    job.attempts += 1
    db.commit()
    return job


def _requeue_job_row(job: Job) -> None:
    job.status = "queued"
    job.started_at = None
    job.heartbeat_at = None
    job.worker_id = None


def _sweep_stale_jobs(db: Session) -> None:
    cutoff = datetime.now(UTC) - timedelta(seconds=STALE_JOB_TIMEOUT_SECONDS)
    stmt = (
        select(Job)
        .where(
            Job.status == "running",
            or_(Job.heartbeat_at.is_(None), Job.heartbeat_at < cutoff),
        )
        .with_for_update(skip_locked=True)
    )
    stale = list(db.scalars(stmt).all())
    if not stale:
        db.rollback()
        return

    for job in stale:
        last_heartbeat = job.heartbeat_at
        if job.attempts < MAX_JOB_ATTEMPTS:
            _requeue_job_row(job)
            logger.warning(
                "job worker requeued stale job %s type=%s attempts=%s last_heartbeat=%s",
                job.id,
                job.job_type,
                job.attempts,
                last_heartbeat,
            )
        else:
            job.status = "failed"
            job.finished_at = datetime.now(UTC)
            job.error = _STALE_FAILURE_ERROR
            logger.error(
                "job worker failed stale job %s type=%s attempts=%s last_heartbeat=%s",
                job.id,
                job.job_type,
                job.attempts,
                last_heartbeat,
            )
    db.commit()


def _requeue_on_shutdown(job_id: uuid.UUID) -> None:
    """Return an in-flight job to queued if shutdown interrupted it mid-run."""
    with SessionLocal() as db:
        job = db.get(Job, job_id)
        if job is None or job.status != "running":
            return
        _requeue_job_row(job)
        db.commit()
        logger.warning(
            "job worker requeued job %s type=%s on shutdown",
            job.id,
            job.job_type,
        )


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


def worker_loop() -> None:
    global _WORKER_ID
    _WORKER_ID = f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:8]}"
    logger.info("job worker started worker_id=%s", _WORKER_ID)
    # Fresh before the first poll so /health is not 503 during startup.
    touch_worker_last_seen()
    last_heartbeat = 0.0

    while not _shutdown.is_set():
        try:
            touch_worker_last_seen()
            now = time.monotonic()
            if now - last_heartbeat >= 30:
                logger.info("job worker heartbeat")
                last_heartbeat = now

            with SessionLocal() as db:
                _sweep_stale_jobs(db)

            if _shutdown.is_set():
                break

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
                    heartbeat = _JobHeartbeat(job.id)
                    heartbeat.start()
                    try:
                        if _shutdown.is_set():
                            # Claimed under shutdown — do not start work.
                            pass
                        else:
                            _execute_job(db, job)
                    finally:
                        heartbeat.stop()
                        if _shutdown.is_set():
                            _requeue_on_shutdown(job.id)
                    continue

            _shutdown.wait(2.0)

        except Exception:
            logger.exception("worker loop iteration failed")
            _shutdown.wait(2.0)
