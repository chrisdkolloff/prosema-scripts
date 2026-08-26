"""weclapp-dependent tool stubs. Gruppen routes must not import this module's guards."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.auth import SessionUser, require_user
from app.db import get_db
from app.weclapp import SETTINGS_PATH, check_weclapp_access

router = APIRouter()


def _access_ctx(user: SessionUser, db: Session) -> dict[str, object]:
    access = check_weclapp_access(db, user["oid"])
    return {
        "user": user,
        "access": access,
        "settings_path": SETTINGS_PATH,
        "blocked": access.kind != "ok",
    }


@router.get("/artikel-registrierung", response_class=HTMLResponse)
def artikel_registrierung(
    request: Request,
    user: SessionUser = Depends(require_user),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    return request.app.state.templates.TemplateResponse(
        request,
        "artikel_registrierung.html",
        _access_ctx(user, db),
    )


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
