"""weclapp-dependent tool stubs. Gruppen routes must not import this module's guards."""

from __future__ import annotations

import uuid
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.article_templates import (
    catalogue_for_display,
    download_filename,
    get_active_template,
)
from app.auth import SessionUser, require_user
from app.batch_actions import STATUS_LABELS, batch_counts
from app.batch_upload import (
    DEFAULT_MANUAL_ROWS,
    BatchUploadError,
    DuplicateUpload,
    create_batch_from_upload,
    create_manual_batch,
)
from app.db import get_db
from app.models import ArticleBatch, ArticleBatchRow
from app.snapshots import format_snapshot_timestamp
from app.accounting_rombro_export import EXPORT_DIR, parse_export_date
from app.jobs import enqueue
from app.models import Job
from app.routes.jobs import _job_status_context, _job_status_response
from app.weclapp import SETTINGS_PATH, check_weclapp_access, format_dt

router = APIRouter()


def _access_ctx(user: SessionUser, db: Session) -> dict[str, object]:
    access = check_weclapp_access(db, user["oid"])
    return {
        "user": user,
        "access": access,
        "settings_path": SETTINGS_PATH,
        "blocked": access.kind != "ok",
    }


def _list_batches(db: Session, *, status_filter: str) -> list[dict]:
    stmt = select(ArticleBatch).order_by(ArticleBatch.created_at.desc())
    if status_filter == "all":
        pass
    elif status_filter in STATUS_LABELS:
        stmt = stmt.where(ArticleBatch.status == status_filter)
    else:
        stmt = stmt.where(ArticleBatch.status != "discarded")
    batches = list(db.scalars(stmt))
    items: list[dict] = []
    for batch in batches:
        rows = list(
            db.scalars(
                select(ArticleBatchRow).where(ArticleBatchRow.batch_id == batch.id)
            )
        )
        counts = batch_counts(rows)
        items.append(
            {
                "batch": batch,
                "short_id": str(batch.id).split("-")[0],
                "uploaded_at": format_snapshot_timestamp(batch.created_at),
                "status_label": STATUS_LABELS.get(batch.status, batch.status),
                "row_count": counts["row_count"],
                "error_count": counts["error_count"],
                "written_count": counts["written_count"],
                "filename_label": batch.filename or "Manuell erfasst",
            }
        )
    return items


def _template_banner(db: Session) -> dict[str, object]:
    template = get_active_template(db)
    return {
        "template": template,
        "template_version": template.version,
        "template_stand": format_dt(template.created_at),
        "catalogue": catalogue_for_display(),
    }


@router.get("/artikel-registrierung", response_class=HTMLResponse)
def artikel_registrierung(
    request: Request,
    user: SessionUser = Depends(require_user),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    ctx = _access_ctx(user, db)
    status_filter = str(request.query_params.get("status") or "").strip()
    ctx.update(
        {
            "status_filter": status_filter,
            "batches": _list_batches(db, status_filter=status_filter),
            "error": request.query_params.get("error") or "",
            "notices": [
                n
                for n in (request.query_params.get("notice") or "").split("|")
                if n
            ],
            "duplicate": False,
            "manual_default_rows": DEFAULT_MANUAL_ROWS,
        }
    )
    ctx.update(_template_banner(db))
    return request.app.state.templates.TemplateResponse(
        request,
        "artikel_registrierung.html",
        ctx,
    )


@router.get("/artikel-registrierung/vorlage")
def artikel_vorlage_download(
    user: SessionUser = Depends(require_user),
    db: Session = Depends(get_db),
) -> Response:
    template = get_active_template(db)
    filename = download_filename(template)
    return Response(
        content=bytes(template.xlsx_bytes),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/artikel-registrierung/upload")
async def artikel_registrierung_upload(
    request: Request,
    user: SessionUser = Depends(require_user),
    db: Session = Depends(get_db),
    datei: UploadFile = File(...),
    bestaetigt: str = Form(""),
):
    filename = datei.filename or "upload.xlsx"
    data = await datei.read()
    confirmed = bestaetigt.strip() in {"1", "true", "ja"}
    try:
        result = create_batch_from_upload(
            db,
            filename=filename,
            data=data,
            user=user,
            confirmed=confirmed,
        )
    except BatchUploadError as exc:
        ctx = _access_ctx(user, db)
        ctx.update(
            {
                "status_filter": "",
                "batches": _list_batches(db, status_filter=""),
                "error": exc.message,
                "notices": [],
                "duplicate": False,
                "manual_default_rows": DEFAULT_MANUAL_ROWS,
            }
        )
        ctx.update(_template_banner(db))
        return request.app.state.templates.TemplateResponse(
            request,
            "artikel_registrierung.html",
            ctx,
            status_code=400,
        )

    if isinstance(result, DuplicateUpload):
        ctx = _access_ctx(user, db)
        ctx.update(
            {
                "status_filter": "",
                "batches": _list_batches(db, status_filter=""),
                "error": "",
                "notices": [],
                "duplicate": True,
                "duplicate_date": format_snapshot_timestamp(result.created_at),
                "duplicate_short": str(result.batch.id).split("-")[0],
                "duplicate_sha": result.batch.source_sha256 or "",
                "manual_default_rows": DEFAULT_MANUAL_ROWS,
            }
        )
        ctx.update(_template_banner(db))
        return request.app.state.templates.TemplateResponse(
            request,
            "artikel_registrierung.html",
            ctx,
        )

    db.commit()
    notice = "|".join(result.notices)
    url = f"/batches/{result.batch.id}"
    if notice:
        url = f"{url}?notice={quote(notice)}"
    return RedirectResponse(url=url, status_code=303)


@router.post("/artikel-registrierung/manuell")
def artikel_registrierung_manuell(
    user: SessionUser = Depends(require_user),
    db: Session = Depends(get_db),
    zeilen: int = Form(DEFAULT_MANUAL_ROWS),
):
    try:
        batch = create_manual_batch(db, user=user, row_count=int(zeilen))
    except (BatchUploadError, ValueError, TypeError) as exc:
        message = getattr(exc, "message", None) or str(exc)
        return RedirectResponse(
            url=f"/artikel-registrierung?error={quote(message)}",
            status_code=303,
        )
    db.commit()
    return RedirectResponse(url=f"/batches/{batch.id}", status_code=303)


@router.get("/artikel", response_class=HTMLResponse)
def artikel_ansicht_redirect() -> RedirectResponse:
    return RedirectResponse(url="/artikel-uebersicht", status_code=301)


@router.post("/artikel/aktualisieren")
def artikel_aktualisieren(
    user: SessionUser = Depends(require_user),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    access = check_weclapp_access(db, user["oid"])
    if access.kind != "ok":
        return RedirectResponse(url="/artikel-uebersicht?error=1", status_code=303)
    return RedirectResponse(url="/artikel-uebersicht/abfragen", status_code=303)


@router.get("/buchhaltung-export", response_class=HTMLResponse)
def buchhaltung_export(
    request: Request,
    user: SessionUser = Depends(require_user),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    ctx = _access_ctx(user, db)
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
        "buchhaltung_export.html",
        ctx,
    )


@router.post("/buchhaltung-export", response_class=HTMLResponse)
def buchhaltung_export_start(
    request: Request,
    user: SessionUser = Depends(require_user),
    db: Session = Depends(get_db),
    date_from: str = Form(...),
    date_to: str = Form(...),
    include_storno: str | None = Form(None),
    include_drafts: str | None = Form(None),
) -> Response:
    access = check_weclapp_access(db, user["oid"])
    if access.kind != "ok":
        return RedirectResponse(url="/buchhaltung-export", status_code=303)

    try:
        parse_export_date(date_from, label="Von-Datum")
        parse_export_date(date_to, label="Bis-Datum")
    except ValueError as exc:
        ctx = _access_ctx(user, db)
        ctx["form_error"] = str(exc)
        ctx["form_date_from"] = date_from
        ctx["form_date_to"] = date_to
        ctx["form_include_storno"] = include_storno in {"1", "true", "on"}
        ctx["form_include_drafts"] = include_drafts in {"1", "true", "on"}
        return request.app.state.templates.TemplateResponse(
            request,
            "buchhaltung_export.html",
            ctx,
        )

    artifact_id = str(uuid.uuid4())
    job = enqueue(
        db,
        "weclapp_accounting_rombro_export",
        {
            "artifact_id": artifact_id,
            "date_from": date_from.strip(),
            "date_to": date_to.strip(),
            "include_storno": include_storno in {"1", "true", "on"},
            "include_drafts": include_drafts in {"1", "true", "on"},
        },
        user,
    )

    if request.headers.get("HX-Request") == "true":
        return _job_status_response(request, user, job)

    return RedirectResponse(url=f"/buchhaltung-export?job={job.id}", status_code=303)


@router.get("/buchhaltung-export/datei/{job_id}")
def buchhaltung_export_download(
    job_id: uuid.UUID,
    user: SessionUser = Depends(require_user),
    db: Session = Depends(get_db),
) -> FileResponse:
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Export nicht gefunden")
    if job.created_by_oid != user["oid"]:
        raise HTTPException(status_code=403)
    if job.job_type != "weclapp_accounting_rombro_export":
        raise HTTPException(status_code=404, detail="Export nicht gefunden")
    if job.status != "succeeded" or not job.result:
        raise HTTPException(status_code=409, detail="Export noch nicht fertig")

    artifact_id = str(job.result.get("artifact_id") or "")
    try:
        uuid.UUID(artifact_id)
    except ValueError as exc:
        raise HTTPException(status_code=500, detail="Exportdatei fehlt") from exc

    path = EXPORT_DIR / f"{artifact_id}.csv"
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Exportdatei nicht mehr vorhanden")

    filename = str(job.result.get("filename") or path.name)
    return FileResponse(
        path,
        media_type="text/csv; charset=utf-8",
        filename=filename,
    )
