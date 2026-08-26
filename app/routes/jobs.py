"""Job enqueue, status fragments, retry, and the licence-handoff banner."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.auth import SessionUser, require_user
from app.db import get_db
from app.jobs import (
    TERMINAL_STATUSES,
    enqueue,
    job_type_label,
    list_active_jobs,
)
from app.models import Job
from app.weclapp import SETTINGS_PATH, public_job_error

router = APIRouter()

STATUS_LABELS = {
    "queued": "In Warteschlange",
    "running": "Läuft",
    "succeeded": "Erfolgreich",
    "failed": "Fehlgeschlagen",
}

_FRAGMENT_HEADERS = {"Cache-Control": "no-store"}


def _is_htmx(request: Request) -> bool:
    return request.headers.get("HX-Request") == "true"


def _job_status_context(user: SessionUser, job: Job) -> dict[str, object]:
    error_message = public_job_error(job.error) if job.status == "failed" else None
    return {
        "user": user,
        "job": job,
        "status_label": STATUS_LABELS.get(job.status, job.status),
        "polling": job.status not in TERMINAL_STATUSES,
        "error_message": error_message,
        "can_retry": job.status == "failed" and job.created_by_oid == user["oid"],
        "settings_path": SETTINGS_PATH,
        "job_label": job_type_label(job.job_type),
    }


def _job_status_response(request: Request, user: SessionUser, job: Job) -> HTMLResponse:
    return request.app.state.templates.TemplateResponse(
        request,
        "partials/job_status.html",
        _job_status_context(user, job),
        headers=_FRAGMENT_HEADERS,
    )


@router.get("/jobs/aktiv", response_class=HTMLResponse)
def active_jobs_banner(
    request: Request,
    user: SessionUser = Depends(require_user),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    jobs = list_active_jobs(db)
    return request.app.state.templates.TemplateResponse(
        request,
        "partials/jobs_aktiv.html",
        {
            "user": user,
            "jobs": jobs,
            "job_label": job_type_label(jobs[0].job_type) if len(jobs) == 1 else None,
        },
        headers=_FRAGMENT_HEADERS,
    )


@router.post("/jobs/noop", response_class=HTMLResponse)
def start_noop(
    request: Request,
    user: SessionUser = Depends(require_user),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    job = enqueue(db, "noop", {}, user)
    return _job_status_response(request, user, job)


@router.get("/jobs/{job_id}", response_class=HTMLResponse)
def job_detail(
    job_id: uuid.UUID,
    request: Request,
    user: SessionUser = Depends(require_user),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Auftrag nicht gefunden")
    ctx = _job_status_context(user, job)
    return request.app.state.templates.TemplateResponse(
        request,
        "jobs/detail.html",
        ctx,
    )


@router.get("/jobs/{job_id}/status", response_class=HTMLResponse)
def job_status(
    job_id: uuid.UUID,
    request: Request,
    user: SessionUser = Depends(require_user),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Auftrag nicht gefunden")
    return _job_status_response(request, user, job)


@router.post("/jobs/{job_id}/erneut", response_class=HTMLResponse)
def retry_job(
    job_id: uuid.UUID,
    request: Request,
    user: SessionUser = Depends(require_user),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Auftrag nicht gefunden")
    if job.created_by_oid != user["oid"]:
        raise HTTPException(status_code=403)
    if job.status != "failed":
        raise HTTPException(status_code=400, detail="Nur fehlgeschlagene Aufträge können erneut gestartet werden")
    new_job = enqueue(db, job.job_type, dict(job.payload or {}), user)
    if _is_htmx(request):
        return _job_status_response(request, user, new_job)
    return RedirectResponse(url=f"/jobs/{new_job.id}", status_code=303)
