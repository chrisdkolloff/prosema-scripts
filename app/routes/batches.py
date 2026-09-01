"""Article batch editor: grid page, cell edits, concurrent-editor presence."""

from __future__ import annotations

import uuid
from typing import Any
from urllib.parse import quote, urlencode

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.auth import SessionUser, require_user
from app.batch_actions import (
    STATUS_LABELS,
    BatchActionError,
    approval_dialog_context,
    approve_batch,
    batch_counts,
    build_batch_excel,
    discard_batch,
    snapshot_banner_state,
)
from app.batch_upload import (
    DEFAULT_MANUAL_ROWS,
    BatchUploadError,
    append_empty_rows,
    exclude_empty_rows,
)
from app.batches import (
    MSG_NUMBER_REASSIGNED,
    BatchEditError,
    CellEdit,
    apply_edits,
    build_grid_config,
    filtered_rows,
    group_dropdowns,
    load_batch_rows,
    refresh_draft_validation,
    schema_dropdowns,
    touch_presence,
)
from app.db import get_db
from app.jobs import enqueue
from app.models import ArticleBatch, ArticleTemplate, Job
from app.snapshots import create_snapshot_pull, excel_filename_timestamp
from app.weclapp import SETTINGS_PATH, check_weclapp_access, get_token_meta

router = APIRouter()

_FRAGMENT_HEADERS = {"Cache-Control": "no-store"}
MSG_SUBMIT_RUNNING = "Es läuft bereits ein Sendevorgang für diesen Batch."


def _weclapp_writes_ok(db: Session, oid: str) -> bool:
    """Stored token that has not already failed a probe — no extra weclapp call."""
    meta = get_token_meta(db, oid)
    return bool(meta.stored and meta.last_verified_ok is not False)


def _error_redirect(batch_id: uuid.UUID, message: str) -> RedirectResponse:
    return RedirectResponse(
        url=f"/batches/{batch_id}?error={quote(message)}",
        status_code=303,
    )


class CellEditIn(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=False)

    row_id: uuid.UUID
    field: str
    value: Any = Field(default="")


def _filters(
    request: Request,
) -> dict[str, Any]:
    q = str(request.query_params.get("q") or "").strip()
    hauptgruppe = str(request.query_params.get("hauptgruppe") or "").strip()
    kategorie = str(request.query_params.get("kategorie") or "").strip()
    aktiv = str(request.query_params.get("aktiv") or "").strip()
    nur_fehler = request.query_params.get("nur_fehler") in {"1", "true", "ja"}
    try:
        page = int(request.query_params.get("seite") or "1")
    except ValueError:
        page = 1
    return {
        "query": q,
        "hauptgruppe": hauptgruppe,
        "kategorie": kategorie,
        "aktiv": aktiv,
        "nur_fehler": nur_fehler,
        "page": page,
    }


def _active_submit_job(db: Session, batch_id: uuid.UUID) -> Job | None:
    jobs = db.scalars(
        select(Job).where(
            Job.job_type == "article_batch_submit",
            Job.status.in_(("queued", "running")),
        )
    )
    wanted = str(batch_id)
    for job in jobs:
        if str((job.payload or {}).get("batch_id") or "") == wanted:
            return job
    return None


def _load_batch(db: Session, batch_id: uuid.UUID) -> ArticleBatch | None:
    return db.scalars(
        select(ArticleBatch)
        .options(joinedload(ArticleBatch.template))
        .where(ArticleBatch.id == batch_id)
    ).first()


def _page_context(
    db: Session,
    batch: ArticleBatch,
    user: SessionUser,
    request: Request,
) -> dict[str, Any]:
    filters = _filters(request)
    all_rows = load_batch_rows(db, batch.id)
    if refresh_draft_validation(db, batch, all_rows):
        db.commit()
    page_rows, total, pages = filtered_rows(all_rows, **filters)
    haupt, _unter_by_haupt = group_dropdowns(db)
    categories = schema_dropdowns().get("Kategorie") or []
    query_params = []
    if filters["query"]:
        query_params.append(("q", filters["query"]))
    if filters["hauptgruppe"]:
        query_params.append(("hauptgruppe", filters["hauptgruppe"]))
    if filters["kategorie"]:
        query_params.append(("kategorie", filters["kategorie"]))
    if filters["aktiv"]:
        query_params.append(("aktiv", filters["aktiv"]))
    if filters["nur_fehler"]:
        query_params.append(("nur_fehler", "1"))
    filter_qs = urlencode(query_params)
    counts = batch_counts(all_rows)
    dialog = approval_dialog_context(batch, all_rows)
    banner = snapshot_banner_state(
        db, after_refresh=request.query_params.get("nach_aktualisierung") == "1"
    )
    active_template = db.scalars(
        select(ArticleTemplate).where(ArticleTemplate.is_active.is_(True))
    ).first()
    template_stale = (
        active_template is not None
        and batch.template_id is not None
        and batch.template_id != active_template.id
    )
    template_version = batch.template.version if batch.template is not None else None
    return {
        "user": user,
        "batch": batch,
        "short_id": str(batch.id).split("-")[0],
        "status_label": STATUS_LABELS.get(batch.status, batch.status),
        "filters": filters,
        "filter_qs": filter_qs,
        "total_rows": total,
        "pages": pages,
        "page": filters["page"],
        "hauptgruppen": haupt,
        "kategorien": categories,
        "grid_config": build_grid_config(db, batch, page_rows),
        "editable": batch.status == "draft",
        "counts": counts,
        **banner,
        "action_error": request.query_params.get("error") or "",
        "approve_count": dialog["approve_count"],
        "first_number": dialog["first_number"],
        "last_number": dialog["last_number"],
        "template_stale": template_stale,
        "template_version": template_version,
        "filename_label": batch.filename or "Manuell erfasst",
        "manual_default_rows": DEFAULT_MANUAL_ROWS,
        "empty_excluded": request.query_params.get("empty_excluded") or "",
        "weclapp_ok": _weclapp_writes_ok(db, user["oid"]),
        "settings_path": SETTINGS_PATH,
    }


@router.get("/batches/{batch_id}/aktionen", response_class=HTMLResponse)
def batch_actions_fragment(
    batch_id: uuid.UUID,
    request: Request,
    user: SessionUser = Depends(require_user),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    batch = _load_batch(db, batch_id)
    if batch is None:
        raise HTTPException(status_code=404, detail="Stapel nicht gefunden")
    all_rows = load_batch_rows(db, batch.id)
    counts = batch_counts(all_rows)
    dialog = approval_dialog_context(batch, all_rows)
    banner = snapshot_banner_state(
        db, after_refresh=request.query_params.get("nach_aktualisierung") == "1"
    )
    return request.app.state.templates.TemplateResponse(
        request,
        "batches/partials/action_bar.html",
        {
            "user": user,
            "batch": batch,
            "counts": counts,
            **banner,
            "action_error": "",
            "approve_count": dialog["approve_count"],
            "first_number": dialog["first_number"],
            "last_number": dialog["last_number"],
            "manual_default_rows": DEFAULT_MANUAL_ROWS,
            "weclapp_ok": _weclapp_writes_ok(db, user["oid"]),
            "settings_path": SETTINGS_PATH,
        },
        headers=_FRAGMENT_HEADERS,
    )


@router.get("/batches/{batch_id}", response_class=HTMLResponse)
def batch_detail(
    batch_id: uuid.UUID,
    request: Request,
    user: SessionUser = Depends(require_user),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    batch = _load_batch(db, batch_id)
    if batch is None:
        raise HTTPException(status_code=404, detail="Stapel nicht gefunden")
    return request.app.state.templates.TemplateResponse(
        request,
        "batches/detail.html",
        _page_context(db, batch, user, request),
    )


@router.post("/batches/{batch_id}/zeilen")
def batch_append_rows(
    batch_id: uuid.UUID,
    user: SessionUser = Depends(require_user),
    db: Session = Depends(get_db),
    anzahl: int = Form(DEFAULT_MANUAL_ROWS),
) -> RedirectResponse:
    batch = db.get(ArticleBatch, batch_id)
    if batch is None:
        raise HTTPException(status_code=404, detail="Stapel nicht gefunden")
    try:
        append_empty_rows(db, batch, count=int(anzahl))
    except (BatchUploadError, ValueError, TypeError) as exc:
        message = getattr(exc, "message", None) or str(exc)
        return _error_redirect(batch_id, message)
    db.commit()
    return RedirectResponse(url=f"/batches/{batch_id}", status_code=303)


@router.post("/batches/{batch_id}/leere-zeilen")
def batch_exclude_empty(
    batch_id: uuid.UUID,
    user: SessionUser = Depends(require_user),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    batch = db.get(ArticleBatch, batch_id)
    if batch is None:
        raise HTTPException(status_code=404, detail="Stapel nicht gefunden")
    try:
        excluded = exclude_empty_rows(db, batch)
    except BatchUploadError as exc:
        return _error_redirect(batch_id, exc.message)
    db.commit()
    return RedirectResponse(
        url=f"/batches/{batch_id}?empty_excluded={excluded}",
        status_code=303,
    )


@router.post("/batches/{batch_id}/artikeluebersicht-aktualisieren")
def batch_refresh_article_snapshot(
    batch_id: uuid.UUID,
    user: SessionUser = Depends(require_user),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    batch = _load_batch(db, batch_id)
    if batch is None:
        raise HTTPException(status_code=404, detail="Stapel nicht gefunden")
    access = check_weclapp_access(db, user["oid"])
    if access.kind != "ok":
        return _error_redirect(batch_id, access.message)
    create_snapshot_pull(db, user)
    return RedirectResponse(url=f"/batches/{batch_id}", status_code=303)


@router.post("/batches/{batch_id}/edits")
def batch_edits(
    batch_id: uuid.UUID,
    payload: list[CellEditIn],
    user: SessionUser = Depends(require_user),
    db: Session = Depends(get_db),
) -> JSONResponse:
    batch = db.get(ArticleBatch, batch_id)
    if batch is None:
        return JSONResponse({"error": "Stapel nicht gefunden"}, status_code=404)
    edits = [
        CellEdit(row_id=item.row_id, field=item.field, value=item.value) for item in payload
    ]
    try:
        results = apply_edits(db, batch, edits)
    except BatchEditError as exc:
        body: dict[str, Any] = {"error": exc.message}
        if exc.field:
            body["field"] = exc.field
        return JSONResponse(body, status_code=exc.status_code)
    db.commit()
    return JSONResponse(
        {
            "rows": [
                {
                    "id": str(item.id),
                    "proposed_article_number": item.proposed_article_number,
                    "validation_error": item.validation_error,
                    "include": item.include,
                    "corrected": item.corrected,
                    "number_reassigned": item.number_reassigned,
                    "message": MSG_NUMBER_REASSIGNED if item.number_reassigned else "",
                }
                for item in results
            ]
        }
    )


@router.post("/batches/{batch_id}/freigeben")
def batch_freigeben(
    batch_id: uuid.UUID,
    user: SessionUser = Depends(require_user),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    batch = db.get(ArticleBatch, batch_id)
    if batch is None:
        raise HTTPException(status_code=404, detail="Stapel nicht gefunden")
    try:
        approve_batch(db, batch, actor=user)
    except BatchActionError as exc:
        return _error_redirect(batch_id, exc.message)
    db.commit()
    return RedirectResponse(url=f"/batches/{batch_id}", status_code=303)


@router.post("/batches/{batch_id}/verwerfen")
def batch_verwerfen(
    batch_id: uuid.UUID,
    user: SessionUser = Depends(require_user),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    batch = db.get(ArticleBatch, batch_id)
    if batch is None:
        raise HTTPException(status_code=404, detail="Stapel nicht gefunden")
    try:
        discard_batch(db, batch, actor=user)
    except BatchActionError as exc:
        return _error_redirect(batch_id, exc.message)
    db.commit()
    return RedirectResponse(url="/artikel-registrierung", status_code=303)


@router.post("/batches/{batch_id}/senden")
def batch_senden(
    batch_id: uuid.UUID,
    request: Request,
    user: SessionUser = Depends(require_user),
    db: Session = Depends(get_db),
):
    batch = db.get(ArticleBatch, batch_id)
    if batch is None:
        raise HTTPException(status_code=404, detail="Stapel nicht gefunden")
    access = check_weclapp_access(db, user["oid"])
    if access.kind != "ok":
        return _error_redirect(batch_id, access.message)
    if batch.status != "approved":
        return _error_redirect(
            batch_id, "Nur freigegebene Batches können gesendet werden."
        )
    if _active_submit_job(db, batch.id) is not None:
        return _error_redirect(batch_id, MSG_SUBMIT_RUNNING)
    enqueue(
        db,
        "article_batch_submit",
        {
            "batch_id": str(batch.id),
            "actor_oid": user["oid"],
            "actor_name": user["name"],
        },
        user,
    )
    return RedirectResponse(url=f"/batches/{batch_id}", status_code=303)


@router.get("/batches/{batch_id}/excel")
def batch_excel(
    batch_id: uuid.UUID,
    user: SessionUser = Depends(require_user),
    db: Session = Depends(get_db),
) -> Response:
    batch = db.get(ArticleBatch, batch_id)
    if batch is None:
        raise HTTPException(status_code=404, detail="Stapel nicht gefunden")
    data = build_batch_excel(db, batch)
    stamp = excel_filename_timestamp(batch.created_at)
    filename = f"batch_{str(batch.id).split('-')[0]}_{stamp}.xlsx"
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/batches/{batch_id}/anwesenheit", response_class=HTMLResponse)
def batch_presence(
    batch_id: uuid.UUID,
    request: Request,
    user: SessionUser = Depends(require_user),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    batch = db.get(ArticleBatch, batch_id)
    if batch is None:
        raise HTTPException(status_code=404, detail="Stapel nicht gefunden")
    names = touch_presence(db, batch, user)
    db.commit()
    return request.app.state.templates.TemplateResponse(
        request,
        "batches/partials/presence.html",
        {"user": user, "names": names},
        headers=_FRAGMENT_HEADERS,
    )


@router.get("/batches/{batch_id}/anwesenheit", response_class=HTMLResponse)
def batch_presence_get(
    batch_id: uuid.UUID,
    request: Request,
    user: SessionUser = Depends(require_user),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    return batch_presence(batch_id, request, user, db)
