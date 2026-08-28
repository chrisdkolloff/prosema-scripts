"""Settings hub for external systems, weclapp token, and article templates."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy.orm import Session

from app.article_templates import (
    TemplateError,
    TemplatePermissionError,
    activate_from_upload,
    catalogue_for_display,
    download_filename,
    get_active_template,
    get_template,
    list_templates,
    pending_to_session,
    prepare_template_replacement,
)
from app.auth import SessionUser, require_admin, require_user
from app.db import get_db
from app.weclapp import (
    LANDING_TOOLS,
    SETTINGS_PATH,
    WECLAPP_TOKEN_PATH,
    NoWeclappToken,
    WeclappLicenceMissing,
    WeclappTokenInvalid,
    WeclappTokenUnreadable,
    check_weclapp_access,
    delete_token,
    format_dt,
    get_token_meta,
    landing_tool_states,
    probe_weclapp,
    store_token,
)
from scripts.weclapp.client import WeclappError

router = APIRouter()

_FRAGMENT_HEADERS = {"Cache-Control": "no-store"}
VORLAGE_PATH = "/einstellungen/vorlage"
_SESSION_PENDING_KEY = "pending_article_template"


def _is_htmx(request: Request) -> bool:
    return request.headers.get("HX-Request") == "true"


def _settings_context(user: SessionUser, db: Session, **extra: object) -> dict[str, object]:
    meta = get_token_meta(db, user["oid"])
    return {
        "user": user,
        "stored": meta.stored,
        "created_at_label": format_dt(meta.created_at),
        "last_verified_label": format_dt(meta.last_verified_at),
        "last_verified_ok": meta.last_verified_ok,
        "settings_path": SETTINGS_PATH,
        "weclapp_token_path": WECLAPP_TOKEN_PATH,
        "vorlage_path": VORLAGE_PATH,
        "is_admin": "admin" in user.get("roles", []),
        **extra,
    }


def _vorlage_context(user: SessionUser, db: Session, **extra: object) -> dict[str, object]:
    active = get_active_template(db)
    history = list_templates(db)
    return {
        "user": user,
        "is_admin": "admin" in user.get("roles", []),
        "settings_path": SETTINGS_PATH,
        "vorlage_path": VORLAGE_PATH,
        "active": active,
        "active_created_label": format_dt(active.created_at),
        "column_count": len(active.columns) if isinstance(active.columns, list) else 0,
        "history": [
            {
                "template": row,
                "created_label": format_dt(row.created_at),
                "column_count": len(row.columns) if isinstance(row.columns, list) else 0,
            }
            for row in history
        ],
        "catalogue": catalogue_for_display(),
        **extra,
    }


@router.get(SETTINGS_PATH, response_class=HTMLResponse)
def settings_page(
    request: Request,
    user: SessionUser = Depends(require_user),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    return request.app.state.templates.TemplateResponse(
        request,
        "einstellungen/index.html",
        _settings_context(user, db),
    )


@router.get(WECLAPP_TOKEN_PATH)
def weclapp_settings_redirect() -> RedirectResponse:
    return RedirectResponse(url=SETTINGS_PATH, status_code=303)


@router.post(WECLAPP_TOKEN_PATH, response_class=HTMLResponse)
def save_weclapp_token(
    request: Request,
    user: SessionUser = Depends(require_user),
    db: Session = Depends(get_db),
    token: str = Form(""),
) -> HTMLResponse:
    try:
        store_token(db, user["oid"], token)
    except ValueError as exc:
        return request.app.state.templates.TemplateResponse(
            request,
            "einstellungen/index.html",
            _settings_context(user, db, form_error=str(exc)),
            status_code=400,
        )
    return RedirectResponse(url=SETTINGS_PATH, status_code=303)


@router.post(f"{WECLAPP_TOKEN_PATH}/testen", response_class=HTMLResponse)
def test_weclapp_token(
    request: Request,
    user: SessionUser = Depends(require_user),
    db: Session = Depends(get_db),
    token: str = Form(""),
) -> HTMLResponse:
    submitted = token.strip()
    if submitted:
        store_token(db, user["oid"], submitted)
    try:
        probe_weclapp(db, user["oid"])
        result_kind = "ok"
        result_message = "weclapp-Verbindung erfolgreich."
    except NoWeclappToken as exc:
        result_kind = "error"
        result_message = str(exc)
    except (WeclappTokenInvalid, WeclappLicenceMissing, WeclappTokenUnreadable) as exc:
        result_kind = "error"
        result_message = str(exc)
    except WeclappError:
        result_kind = "error"
        result_message = "weclapp ist derzeit nicht erreichbar."

    ctx = {
        "user": user,
        "result_kind": result_kind,
        "result_message": result_message,
        "settings_path": SETTINGS_PATH,
    }
    if _is_htmx(request):
        return request.app.state.templates.TemplateResponse(
            request,
            "partials/weclapp_test_result.html",
            ctx,
            headers=_FRAGMENT_HEADERS,
        )
    return RedirectResponse(url=SETTINGS_PATH, status_code=303)


@router.post(f"{WECLAPP_TOKEN_PATH}/entfernen")
def remove_weclapp_token(
    user: SessionUser = Depends(require_user),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    delete_token(db, user["oid"])
    return RedirectResponse(url=SETTINGS_PATH, status_code=303)


@router.get("/weclapp/status", response_class=HTMLResponse)
def weclapp_status_fragment(
    request: Request,
    user: SessionUser = Depends(require_user),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    access = check_weclapp_access(db, user["oid"])
    return request.app.state.templates.TemplateResponse(
        request,
        "partials/weclapp_status.html",
        {
            "user": user,
            "access": access,
            "last_verified_label": format_dt(access.last_verified_at),
            "tools": landing_tool_states(access),
            "settings_path": SETTINGS_PATH,
            "static_tools": LANDING_TOOLS,
        },
        headers=_FRAGMENT_HEADERS,
    )


@router.get(VORLAGE_PATH, response_class=HTMLResponse)
def vorlage_settings(
    request: Request,
    user: SessionUser = Depends(require_admin),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    pending = request.session.get(_SESSION_PENDING_KEY)
    return request.app.state.templates.TemplateResponse(
        request,
        "einstellungen/vorlage.html",
        _vorlage_context(
            user,
            db,
            pending=pending,
            form_error=request.query_params.get("error") or "",
            success=request.query_params.get("ok") or "",
        ),
    )


@router.post(VORLAGE_PATH, response_class=HTMLResponse)
async def vorlage_replace(
    request: Request,
    user: SessionUser = Depends(require_admin),
    db: Session = Depends(get_db),
    datei: UploadFile = File(...),
    note: str = Form(""),
    bestaetigt: str = Form(""),
):
    filename = datei.filename or "vorlage.xlsx"
    data = await datei.read()
    confirmed = bestaetigt.strip() in {"1", "true", "ja"}

    try:
        if confirmed:
            pending_meta = request.session.get(_SESSION_PENDING_KEY)
            activate_from_upload(
                db, user=user, data=data, session_pending=pending_meta
            )
            db.commit()
            request.session.pop(_SESSION_PENDING_KEY, None)
            return RedirectResponse(url=f"{VORLAGE_PATH}?ok=1", status_code=303)

        pending = prepare_template_replacement(
            db, user=user, filename=filename, data=data, note=note
        )
        request.session[_SESSION_PENDING_KEY] = pending_to_session(pending)
        return request.app.state.templates.TemplateResponse(
            request,
            "einstellungen/vorlage.html",
            _vorlage_context(user, db, pending=pending_to_session(pending)),
        )
    except TemplatePermissionError:
        raise
    except TemplateError as exc:
        return request.app.state.templates.TemplateResponse(
            request,
            "einstellungen/vorlage.html",
            _vorlage_context(user, db, form_error=exc.message, pending=None),
            status_code=400,
        )


@router.get(f"{VORLAGE_PATH}/{{template_id}}/download")
def vorlage_download_version(
    template_id: uuid.UUID,
    user: SessionUser = Depends(require_admin),
    db: Session = Depends(get_db),
) -> Response:
    template = get_template(db, template_id)
    if template is None:
        return RedirectResponse(url=VORLAGE_PATH, status_code=303)
    filename = download_filename(template)
    return Response(
        content=bytes(template.xlsx_bytes),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
