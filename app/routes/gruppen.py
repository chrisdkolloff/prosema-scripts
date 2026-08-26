"""Group registry pages and write routes."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.auth import SessionUser, require_admin, require_user
from app.db import get_db
from app.groups_service import (
    GroupRegistryError,
    add_alias,
    change_hauptgruppe_code,
    change_untergruppe_code,
    count_active_untergruppen,
    create_hauptgruppe,
    create_untergruppe,
    list_hauptgruppen,
    remove_alias,
    rename_hauptgruppe,
    rename_untergruppe,
    restore_hauptgruppe,
    restore_untergruppe,
    soft_delete_hauptgruppe,
    soft_delete_untergruppe,
)
from app.gruppen_diagram import build_sunburst_figure, figure_html, load_active_group_tree
from app.models import GruppenAlias, Hauptgruppe, Untergruppe

router = APIRouter()


def _is_admin(user: SessionUser) -> bool:
    return "admin" in user.get("roles", [])


def _ctx(user: SessionUser, **extra: object) -> dict[str, object]:
    return {"user": user, "is_admin": _is_admin(user), **extra}


def _is_htmx(request: Request) -> bool:
    return request.headers.get("HX-Request") == "true"


def _get_hauptgruppe(db: Session, group_id: uuid.UUID) -> Hauptgruppe:
    group = db.get(Hauptgruppe, group_id)
    if group is None:
        raise HTTPException(status_code=404, detail="Hauptgruppe nicht gefunden")
    return group


def _get_untergruppe(db: Session, group_id: uuid.UUID) -> Untergruppe:
    group = db.get(Untergruppe, group_id)
    if group is None:
        raise HTTPException(status_code=404, detail="Untergruppe nicht gefunden")
    return group


def _get_alias(db: Session, alias_id: uuid.UUID) -> GruppenAlias:
    alias = db.get(GruppenAlias, alias_id)
    if alias is None:
        raise HTTPException(status_code=404, detail="Alias nicht gefunden")
    return alias


def _error_page(request: Request, user: SessionUser, message: str) -> HTMLResponse:
    return request.app.state.templates.TemplateResponse(
        request,
        "gruppen/error.html",
        _ctx(user, message=message),
        status_code=400,
    )


def _commit(db: Session) -> None:
    db.commit()


def _hauptgruppe_aliases(db: Session, group_id: uuid.UUID) -> list[GruppenAlias]:
    return list(
        db.scalars(
            select(GruppenAlias)
            .where(GruppenAlias.hauptgruppe_id == group_id)
            .order_by(GruppenAlias.alias_normalized)
        )
    )


def _detail_context(db: Session, group: Hauptgruppe, user: SessionUser, **extra: object) -> dict:
    untergruppen = list(
        db.scalars(
            select(Untergruppe)
            .where(Untergruppe.hauptgruppe_id == group.id)
            .options(selectinload(Untergruppe.aliases))
            .order_by(Untergruppe.code, Untergruppe.name)
        )
    )
    aliases = _hauptgruppe_aliases(db, group.id)
    return _ctx(
        user,
        group=group,
        untergruppen=untergruppen,
        aliases=aliases,
        **extra,
    )


def _render_detail(
    request: Request,
    db: Session,
    group: Hauptgruppe,
    user: SessionUser,
    *,
    error: str | None = None,
    status_code: int = 200,
) -> HTMLResponse:
    return request.app.state.templates.TemplateResponse(
        request,
        "gruppen/detail.html",
        _detail_context(db, group, user, error=error),
        status_code=status_code,
    )


def _render_untergruppen(
    request: Request,
    db: Session,
    group: Hauptgruppe,
    user: SessionUser,
    *,
    error: str | None = None,
    status_code: int = 200,
) -> HTMLResponse:
    return request.app.state.templates.TemplateResponse(
        request,
        "gruppen/partials/untergruppen.html",
        _detail_context(db, group, user, error=error),
        status_code=status_code,
    )


def _write_failure(
    request: Request,
    db: Session,
    user: SessionUser,
    exc: GroupRegistryError,
    *,
    hauptgruppe: Hauptgruppe | None = None,
    fragment: str | None = None,
) -> HTMLResponse:
    db.rollback()
    if fragment == "untergruppen" and hauptgruppe is not None and _is_htmx(request):
        db.refresh(hauptgruppe)
        return _render_untergruppen(request, db, hauptgruppe, user, error=exc.message)
    return _error_page(request, user, exc.message)


@router.get("/gruppen", response_class=HTMLResponse)
def gruppen_list(
    request: Request,
    user: SessionUser = Depends(require_user),
    db: Session = Depends(get_db),
    geloeschte: int = 0,
) -> HTMLResponse:
    show_deleted = geloeschte == 1
    groups = list_hauptgruppen(db, include_deleted=show_deleted)
    counts = count_active_untergruppen(db, [group.id for group in groups])
    return request.app.state.templates.TemplateResponse(
        request,
        "gruppen/list.html",
        _ctx(
            user,
            groups=groups,
            counts=counts,
            show_deleted=show_deleted,
            error=None,
        ),
    )


@router.get("/gruppen/diagramm", response_class=HTMLResponse)
def gruppen_diagramm(
    request: Request,
    user: SessionUser = Depends(require_user),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    fig = build_sunburst_figure(load_active_group_tree(db))
    return request.app.state.templates.TemplateResponse(
        request,
        "gruppen/diagramm.html",
        _ctx(user, plot_html=figure_html(fig)),
    )


@router.get("/gruppen/{group_id}", response_class=HTMLResponse)
def gruppen_detail(
    group_id: uuid.UUID,
    request: Request,
    user: SessionUser = Depends(require_user),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    group = _get_hauptgruppe(db, group_id)
    return _render_detail(request, db, group, user)


@router.post("/gruppen", response_class=HTMLResponse)
def create_hauptgruppe_route(
    request: Request,
    user: SessionUser = Depends(require_admin),
    db: Session = Depends(get_db),
    code: str = Form(...),
    name: str = Form(...),
) -> Response:
    try:
        group = create_hauptgruppe(db, code=code, name=name, actor=user)
        _commit(db)
    except GroupRegistryError as exc:
        db.rollback()
        groups = list_hauptgruppen(db, include_deleted=False)
        counts = count_active_untergruppen(db, [item.id for item in groups])
        return request.app.state.templates.TemplateResponse(
            request,
            "gruppen/list.html",
            _ctx(
                user,
                groups=groups,
                counts=counts,
                show_deleted=False,
                error=exc.message,
                form_code=code,
                form_name=name,
            ),
            status_code=400,
        )
    return RedirectResponse(url=f"/gruppen/{group.id}", status_code=303)


@router.post("/gruppen/{group_id}/umbenennen", response_class=HTMLResponse)
def rename_hauptgruppe_route(
    group_id: uuid.UUID,
    request: Request,
    user: SessionUser = Depends(require_admin),
    db: Session = Depends(get_db),
    name: str = Form(...),
) -> Response:
    group = _get_hauptgruppe(db, group_id)
    try:
        rename_hauptgruppe(db, group, name=name, actor=user)
        _commit(db)
    except GroupRegistryError as exc:
        db.rollback()
        if _is_htmx(request):
            return request.app.state.templates.TemplateResponse(
                request,
                "gruppen/partials/bezeichnung.html",
                _ctx(user, group=group, editing=True, name_error=exc.message),
            )
        return _error_page(request, user, exc.message)
    if _is_htmx(request):
        return request.app.state.templates.TemplateResponse(
            request,
            "gruppen/partials/bezeichnung.html",
            _ctx(user, group=group, editing=False),
        )
    return RedirectResponse(url=f"/gruppen/{group.id}", status_code=303)


@router.get("/gruppen/{group_id}/bezeichnung", response_class=HTMLResponse)
def hauptgruppe_bezeichnung(
    group_id: uuid.UUID,
    request: Request,
    user: SessionUser = Depends(require_user),
    db: Session = Depends(get_db),
    edit: int = 0,
) -> HTMLResponse:
    group = _get_hauptgruppe(db, group_id)
    return request.app.state.templates.TemplateResponse(
        request,
        "gruppen/partials/bezeichnung.html",
        _ctx(user, group=group, editing=edit == 1 and _is_admin(user)),
    )


@router.post("/gruppen/{group_id}/code", response_class=HTMLResponse)
def change_hauptgruppe_code_route(
    group_id: uuid.UUID,
    request: Request,
    user: SessionUser = Depends(require_admin),
    db: Session = Depends(get_db),
    code: str = Form(...),
) -> Response:
    group = _get_hauptgruppe(db, group_id)
    try:
        change_hauptgruppe_code(db, group, code=code, actor=user)
        _commit(db)
    except GroupRegistryError as exc:
        return _error_page(request, user, exc.message)
    return RedirectResponse(url=f"/gruppen/{group.id}", status_code=303)


@router.post("/gruppen/{group_id}/loeschen", response_class=HTMLResponse)
def delete_hauptgruppe_route(
    group_id: uuid.UUID,
    request: Request,
    user: SessionUser = Depends(require_admin),
    db: Session = Depends(get_db),
) -> Response:
    group = _get_hauptgruppe(db, group_id)
    try:
        soft_delete_hauptgruppe(db, group, actor=user)
        _commit(db)
    except GroupRegistryError as exc:
        return _write_failure(request, db, user, exc, hauptgruppe=group)
    return RedirectResponse(url="/gruppen?geloeschte=1", status_code=303)


@router.post("/gruppen/{group_id}/wiederherstellen", response_class=HTMLResponse)
def restore_hauptgruppe_route(
    group_id: uuid.UUID,
    request: Request,
    user: SessionUser = Depends(require_admin),
    db: Session = Depends(get_db),
) -> Response:
    group = _get_hauptgruppe(db, group_id)
    try:
        restore_hauptgruppe(db, group, actor=user)
        _commit(db)
    except GroupRegistryError as exc:
        return _error_page(request, user, exc.message)
    return RedirectResponse(url=f"/gruppen/{group.id}", status_code=303)


@router.post("/gruppen/{group_id}/untergruppen", response_class=HTMLResponse)
def create_untergruppe_route(
    group_id: uuid.UUID,
    request: Request,
    user: SessionUser = Depends(require_admin),
    db: Session = Depends(get_db),
    code: str = Form(...),
    name: str = Form(...),
) -> Response:
    parent = _get_hauptgruppe(db, group_id)
    try:
        create_untergruppe(db, parent, code=code, name=name, actor=user)
        _commit(db)
    except GroupRegistryError as exc:
        return _write_failure(request, db, user, exc, hauptgruppe=parent, fragment="untergruppen")
    db.refresh(parent)
    if _is_htmx(request):
        return _render_untergruppen(request, db, parent, user)
    return RedirectResponse(url=f"/gruppen/{parent.id}", status_code=303)


@router.post("/untergruppen/{group_id}/umbenennen", response_class=HTMLResponse)
def rename_untergruppe_route(
    group_id: uuid.UUID,
    request: Request,
    user: SessionUser = Depends(require_admin),
    db: Session = Depends(get_db),
    name: str = Form(...),
) -> Response:
    group = _get_untergruppe(db, group_id)
    parent = _get_hauptgruppe(db, group.hauptgruppe_id)
    try:
        rename_untergruppe(db, group, name=name, actor=user)
        _commit(db)
    except GroupRegistryError as exc:
        return _write_failure(request, db, user, exc, hauptgruppe=parent, fragment="untergruppen")
    db.refresh(parent)
    if _is_htmx(request):
        return _render_untergruppen(request, db, parent, user)
    return RedirectResponse(url=f"/gruppen/{parent.id}", status_code=303)


@router.post("/untergruppen/{group_id}/code", response_class=HTMLResponse)
def change_untergruppe_code_route(
    group_id: uuid.UUID,
    request: Request,
    user: SessionUser = Depends(require_admin),
    db: Session = Depends(get_db),
    code: str = Form(...),
) -> Response:
    group = _get_untergruppe(db, group_id)
    parent = _get_hauptgruppe(db, group.hauptgruppe_id)
    try:
        change_untergruppe_code(db, group, code=code, actor=user)
        _commit(db)
    except GroupRegistryError as exc:
        return _error_page(request, user, exc.message)
    return RedirectResponse(url=f"/gruppen/{parent.id}", status_code=303)


@router.post("/untergruppen/{group_id}/loeschen", response_class=HTMLResponse)
def delete_untergruppe_route(
    group_id: uuid.UUID,
    request: Request,
    user: SessionUser = Depends(require_admin),
    db: Session = Depends(get_db),
) -> Response:
    group = _get_untergruppe(db, group_id)
    parent = _get_hauptgruppe(db, group.hauptgruppe_id)
    try:
        soft_delete_untergruppe(db, group, actor=user)
        _commit(db)
    except GroupRegistryError as exc:
        return _write_failure(request, db, user, exc, hauptgruppe=parent, fragment="untergruppen")
    db.refresh(parent)
    if _is_htmx(request):
        return _render_untergruppen(request, db, parent, user)
    return RedirectResponse(url=f"/gruppen/{parent.id}", status_code=303)


@router.post("/untergruppen/{group_id}/wiederherstellen", response_class=HTMLResponse)
def restore_untergruppe_route(
    group_id: uuid.UUID,
    request: Request,
    user: SessionUser = Depends(require_admin),
    db: Session = Depends(get_db),
) -> Response:
    group = _get_untergruppe(db, group_id)
    parent = _get_hauptgruppe(db, group.hauptgruppe_id)
    try:
        restore_untergruppe(db, group, actor=user)
        _commit(db)
    except GroupRegistryError as exc:
        return _write_failure(request, db, user, exc, hauptgruppe=parent, fragment="untergruppen")
    db.refresh(parent)
    if _is_htmx(request):
        return _render_untergruppen(request, db, parent, user)
    return RedirectResponse(url=f"/gruppen/{parent.id}", status_code=303)


@router.post("/gruppen/{group_id}/aliases", response_class=HTMLResponse)
def add_hauptgruppe_alias_route(
    group_id: uuid.UUID,
    request: Request,
    user: SessionUser = Depends(require_admin),
    db: Session = Depends(get_db),
    alias: str = Form(...),
) -> Response:
    group = _get_hauptgruppe(db, group_id)
    try:
        add_alias(db, alias=alias, actor=user, hauptgruppe=group)
        _commit(db)
    except GroupRegistryError as exc:
        if _is_htmx(request):
            db.rollback()
            return request.app.state.templates.TemplateResponse(
                request,
                "gruppen/partials/aliases.html",
                _ctx(
                    user,
                    group=group,
                    aliases=_hauptgruppe_aliases(db, group.id),
                    alias_error=exc.message,
                    alias_target="hauptgruppe",
                ),
            )
        return _error_page(request, user, exc.message)
    db.refresh(group)
    if _is_htmx(request):
        return request.app.state.templates.TemplateResponse(
            request,
            "gruppen/partials/aliases.html",
            _ctx(
                user,
                group=group,
                aliases=_hauptgruppe_aliases(db, group.id),
                alias_error=None,
                alias_target="hauptgruppe",
            ),
        )
    return RedirectResponse(url=f"/gruppen/{group.id}", status_code=303)


@router.post("/untergruppen/{group_id}/aliases", response_class=HTMLResponse)
def add_untergruppe_alias_route(
    group_id: uuid.UUID,
    request: Request,
    user: SessionUser = Depends(require_admin),
    db: Session = Depends(get_db),
    alias: str = Form(...),
) -> Response:
    group = _get_untergruppe(db, group_id)
    parent = _get_hauptgruppe(db, group.hauptgruppe_id)
    try:
        add_alias(db, alias=alias, actor=user, untergruppe=group)
        _commit(db)
    except GroupRegistryError as exc:
        return _write_failure(request, db, user, exc, hauptgruppe=parent, fragment="untergruppen")
    db.refresh(parent)
    if _is_htmx(request):
        return _render_untergruppen(request, db, parent, user)
    return RedirectResponse(url=f"/gruppen/{parent.id}", status_code=303)


@router.post("/aliases/{alias_id}/loeschen", response_class=HTMLResponse)
def delete_alias_route(
    alias_id: uuid.UUID,
    request: Request,
    user: SessionUser = Depends(require_admin),
    db: Session = Depends(get_db),
) -> Response:
    alias = _get_alias(db, alias_id)
    parent_id = alias.hauptgruppe_id
    untergruppe = None
    if alias.untergruppe_id is not None:
        untergruppe = _get_untergruppe(db, alias.untergruppe_id)
        parent_id = untergruppe.hauptgruppe_id
    try:
        remove_alias(db, alias, actor=user)
        _commit(db)
    except GroupRegistryError as exc:
        return _error_page(request, user, exc.message)
    parent = _get_hauptgruppe(db, parent_id)
    if _is_htmx(request):
        if untergruppe is not None:
            return _render_untergruppen(request, db, parent, user)
        return request.app.state.templates.TemplateResponse(
            request,
            "gruppen/partials/aliases.html",
            _ctx(
                user,
                group=parent,
                aliases=_hauptgruppe_aliases(db, parent.id),
                alias_error=None,
                alias_target="hauptgruppe",
            ),
        )
    return RedirectResponse(url=f"/gruppen/{parent.id}", status_code=303)
