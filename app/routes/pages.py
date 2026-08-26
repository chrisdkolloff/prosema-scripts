"""Server-rendered pages."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from app.auth import SessionUser, require_user
from app.version_info import load_version_info
from app.weclapp import LANDING_TOOLS

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
def index(request: Request, user: SessionUser = Depends(require_user)) -> HTMLResponse:
    return request.app.state.templates.TemplateResponse(
        request,
        "index.html",
        {"user": user, "tools": LANDING_TOOLS},
    )


@router.get("/changelog", response_class=HTMLResponse)
def changelog(request: Request, user: SessionUser = Depends(require_user)) -> HTMLResponse:
    version_info = load_version_info()
    return request.app.state.templates.TemplateResponse(
        request,
        "changelog.html",
        {"user": user, "releases": version_info.releases},
    )


@router.get("/me", response_class=HTMLResponse)
def me(request: Request, user: SessionUser = Depends(require_user)) -> HTMLResponse:
    return request.app.state.templates.TemplateResponse(
        request,
        "me.html",
        {"user": user, "roles_json": json.dumps(user["roles"])},
    )
