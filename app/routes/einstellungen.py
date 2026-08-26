"""Settings hub for external systems, plus weclapp token write routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.auth import SessionUser, require_user
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
