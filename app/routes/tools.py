"""weclapp-dependent tool stubs. Gruppen routes must not import this module's guards."""

from __future__ import annotations

from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, Response
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
            "batches": [] if ctx["blocked"] else _list_batches(db, status_filter=status_filter),
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
    if not ctx["blocked"]:
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
    access = check_weclapp_access(db, user["oid"])
    if access.kind != "ok":
        return RedirectResponse(url="/artikel-registrierung?error=1", status_code=303)

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
    access = check_weclapp_access(db, user["oid"])
    if access.kind != "ok":
        return RedirectResponse(url="/artikel-registrierung?error=1", status_code=303)
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
    return request.app.state.templates.TemplateResponse(
        request,
        "buchhaltung_export.html",
        _access_ctx(user, db),
    )
