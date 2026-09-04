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
    "weclapp_article_snapshot": "Artikelabfrage",
    "weclapp_supply_source_export": "Bezugsquellenabfrage",
    "weclapp_supply_source_index": "Bezugsquellen-Index",
    "supply_source_resolve": "Bezugsquellen abgleichen",
    "supply_source_apply": "Bezugsquellen schreiben",
    "article_batch_submit": "Artikelregistrierung senden",
    "article_transform_preview": "Artikel-Transformation Vorschau",
    "article_transform_apply": "Artikel-Transformation anwenden",
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


@job_handler("weclapp_supply_source_index")
def handle_weclapp_supply_source_index(
    db: Session,
    payload: dict,
    oid: str,
) -> dict:
    from app.supply_source_index import pull_supply_source_index

    supplier_raw = payload.get("supplier_id")
    supplier_id = int(supplier_raw) if supplier_raw not in (None, "") else None
    try:
        return pull_supply_source_index(db, oid=oid, supplier_id=supplier_id)
    except Exception:
        db.rollback()
        raise


@job_handler("supply_source_resolve")
def handle_supply_source_resolve(
    db: Session,
    payload: dict,
    oid: str,
) -> dict:
    from app.models import SupplySourceRun
    from app.supply_source_resolve import fail_run, run_resolve

    run_id = int(payload["run_id"])
    run = db.get(SupplySourceRun, run_id)
    if run is None:
        raise ValueError("Abgleich nicht gefunden")
    try:
        return run_resolve(db, run, oid=oid)
    except Exception as exc:
        db.rollback()
        run = db.get(SupplySourceRun, run_id)
        if run is not None:
            message = job_error_message(exc) or "Abgleich fehlgeschlagen"
            fail_run(db, run, message)
        raise


@job_handler("supply_source_apply")
def handle_supply_source_apply(
    db: Session,
    payload: dict,
    oid: str,
) -> dict:
    from app.models import SupplySourceRun
    from app.supply_source_apply import apply_chunk
    from app.weclapp import weclapp_client_for

    run_id = int(payload["run_id"])
    chunk_index = int(payload.get("chunk_index") or 0)
    run = db.get(SupplySourceRun, run_id)
    if run is None:
        raise ValueError("Abgleich nicht gefunden")
    actor_name = str(payload.get("actor_name") or "")
    try:
        client = weclapp_client_for(db, oid)
        return apply_chunk(
            db,
            run,
            oid=oid,
            actor_name=actor_name or oid,
            client=client,
            chunk_index=chunk_index,
        )
    except Exception as exc:
        db.rollback()
        run = db.get(SupplySourceRun, run_id)
        if run is not None:
            message = job_error_message(exc) or "Schreiben fehlgeschlagen"
            run.status = "failed"
            run.error = message
            db.commit()
        raise


@job_handler("article_batch_submit")
def handle_article_batch_submit(
    db: Session,
    payload: dict,
    oid: str,
) -> dict:
    import uuid as uuid_mod

    from app.batch_submit import LicenceAbort, run_batch_submit
    from app.models import ArticleBatch

    batch_id = uuid_mod.UUID(str(payload["batch_id"]))
    actor_oid = str(payload.get("actor_oid") or oid)
    actor_name = str(payload.get("actor_name") or "")
    try:
        return run_batch_submit(
            db,
            batch_id=batch_id,
            actor_oid=actor_oid,
            actor_name=actor_name or None,
        )
    except LicenceAbort as exc:
        db.rollback()
        batch = db.get(ArticleBatch, batch_id)
        if batch is not None and batch.status == "submitting":
            batch.status = "approved"
            db.commit()
        raise ValueError(exc.message) from exc
    except Exception:
        db.rollback()
        batch = db.get(ArticleBatch, batch_id)
        if batch is not None and batch.status == "submitting":
            batch.status = "approved"
            db.commit()
        raise


@job_handler("article_transform_preview")
def handle_article_transform_preview(
    db: Session,
    payload: dict,
    oid: str,
) -> dict:
    import uuid as uuid_mod

    from app.models import TransformRun
    from app.transform.preview import TransformAuthAbort, fail_preview, run_preview
    from app.transform.schemas import TransformSpecError

    run_id = uuid_mod.UUID(str(payload["transform_run_id"]))
    run = db.get(TransformRun, run_id)
    if run is None:
        raise ValueError("Transform-Lauf nicht gefunden")
    try:
        return run_preview(db, run, oid=oid)
    except TransformAuthAbort as exc:
        db.rollback()
        run = db.get(TransformRun, run_id)
        if run is not None:
            fail_preview(db, run, exc.message)
        raise ValueError(exc.message) from exc
    except TransformSpecError as exc:
        db.rollback()
        run = db.get(TransformRun, run_id)
        if run is not None:
            fail_preview(db, run, exc.message_de)
        raise ValueError(exc.message_de) from exc
    except Exception as exc:
        db.rollback()
        run = db.get(TransformRun, run_id)
        if run is not None:
            message = job_error_message(exc) or str(exc) or "Vorschau fehlgeschlagen"
            fail_preview(db, run, message)
        raise


@job_handler("article_transform_apply")
def handle_article_transform_apply(
    db: Session,
    payload: dict,
    oid: str,
) -> dict:
    import uuid as uuid_mod

    from app.models import TransformChunk
    from app.transform.apply import apply_chunk, fail_chunk
    from app.transform.preview import TransformAuthAbort

    chunk_id = uuid_mod.UUID(str(payload["transform_chunk_id"]))
    chunk = db.get(TransformChunk, chunk_id)
    if chunk is None:
        raise ValueError("Abschnitt nicht gefunden")
    actor_name = str(payload.get("actor_name") or oid)
    try:
        return apply_chunk(db, chunk, oid=oid, actor_name=actor_name)
    except TransformAuthAbort as exc:
        db.rollback()
        chunk = db.get(TransformChunk, chunk_id)
        if chunk is not None:
            fail_chunk(db, chunk, exc.message)
        raise ValueError(exc.message) from exc
    except Exception as exc:
        db.rollback()
        chunk = db.get(TransformChunk, chunk_id)
        if chunk is not None and chunk.status == "applying":
            fail_chunk(
                db,
                chunk,
                job_error_message(exc) or str(exc) or "Anwenden fehlgeschlagen",
            )
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
