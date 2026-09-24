"""Shopify product images from SharePoint folders."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy.orm import Session

from app.auth import SessionUser, require_user
from app.db import get_db
from app.jobs import enqueue
from app.models import Job
from app.routes.jobs import _job_status_context, _job_status_response

router = APIRouter()


@router.get("/shopify-bilder", response_class=HTMLResponse)
def shopify_bilder_page(
    request: Request,
    user: SessionUser = Depends(require_user),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    ctx: dict[str, object] = {"user": user, "form_error": "", "sharepoint_url": ""}
    job_param = request.query_params.get("job")
    if job_param:
        try:
            job_id = uuid.UUID(job_param)
        except ValueError:
            job_id = None
        if job_id is not None:
            job = db.get(Job, job_id)
            if job is not None and job.created_by_oid == user["oid"]:
                ctx.update(_job_status_context(user, job))
    return request.app.state.templates.TemplateResponse(
        request,
        "shopify_bilder.html",
        ctx,
    )


@router.post("/shopify-bilder", response_class=HTMLResponse)
def shopify_bilder_start(
    request: Request,
    user: SessionUser = Depends(require_user),
    db: Session = Depends(get_db),
    sharepoint_url: str = Form(...),
    mode: str = Form("sync"),
    dry_run: str | None = Form(None),
    recursive: str | None = Form(None),
    replace_confirm: str | None = Form(None),
) -> Response:
    url = sharepoint_url.strip()
    replace_existing = mode == "replace"
    if not url:
        ctx = {
            "user": user,
            "form_error": "Bitte den SharePoint-Ordnerlink einfügen.",
            "sharepoint_url": url,
        }
        return request.app.state.templates.TemplateResponse(
            request,
            "shopify_bilder.html",
            ctx,
        )
    if replace_existing and replace_confirm not in {"1", "true", "on"}:
        ctx = {
            "user": user,
            "form_error": (
                "Bitte bestätigen, dass bestehende Produktbilder für betroffene "
                "Artikel gelöscht und neu hochgeladen werden sollen."
            ),
            "sharepoint_url": url,
            "form_mode": mode,
        }
        return request.app.state.templates.TemplateResponse(
            request,
            "shopify_bilder.html",
            ctx,
        )

    job = enqueue(
        db,
        "shopify_sharepoint_image_sync",
        {
            "sharepoint_url": url,
            "replace_existing": replace_existing,
            "dry_run": dry_run in {"1", "true", "on"},
            "recursive": recursive in {"1", "true", "on"},
        },
        user,
    )

    if request.headers.get("HX-Request") == "true":
        return _job_status_response(request, user, job)

    return RedirectResponse(url=f"/shopify-bilder?job={job.id}", status_code=303)
