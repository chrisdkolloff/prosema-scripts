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
    create_hauptgruppe_with_untergruppe,
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
from app.gruppen_diagram import build_sunburst_arcs, load_active_group_tree
from app.models import GruppenAlias, Hauptgruppe, Untergruppe
from app.weclapp import (
    NoWeclappToken,
    WeclappError,
    WeclappTokenUnreadable,
    map_weclapp_error,
    weclapp_client_for,
)
from app.weclapp_categories import (
    MSG_SYNC_BANNER,
    GroupSyncIssue,
    collect_weclapp_sync_issues,
    create_haupt_and_unter_in_weclapp,
    create_unter_in_weclapp,
    rename_haupt_in_weclapp,
    rename_unter_in_weclapp,
    weclapp_category_writes_allowed,
)

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


def _active_group_maps(db: Session) -> tuple[dict[str, str], dict[tuple[str, str], str]]:
    haupts = list_hauptgruppen(db, include_deleted=False)
    by_id = {group.id: group.code for group in haupts}
    haupt = {group.code: group.name for group in haupts}
    unter: dict[tuple[str, str], str] = {}
    for row in db.scalars(select(Untergruppe).where(Untergruppe.deleted_at.is_(None))):
        parent_code = by_id.get(row.hauptgruppe_id)
        if parent_code is not None:
            unter[(parent_code, row.code)] = row.name
    return haupt, unter


def _sync_issues_for_page(request: Request, db: Session, user: SessionUser) -> list[GroupSyncIssue]:
    if not weclapp_category_writes_allowed(request):
        return []
    try:
        client = weclapp_client_for(db, user["oid"])
        haupt, unter = _active_group_maps(db)
        return collect_weclapp_sync_issues(client, haupt, unter)
    except (NoWeclappToken, WeclappTokenUnreadable, WeclappError):
        return []


def _list_context(
    request: Request,
    db: Session,
    user: SessionUser,
    groups: list[Hauptgruppe],
    *,
    show_deleted: bool,
    error: str | None = None,
    **extra: object,
) -> dict[str, object]:
    counts = count_active_untergruppen(db, [group.id for group in groups])
    return _ctx(
        user,
        groups=groups,
        counts=counts,
        show_deleted=show_deleted,
        error=error,
        sync_banner=MSG_SYNC_BANNER,
        sync_issues=_sync_issues_for_page(request, db, user),
        **extra,
    )


def _weclapp_duplicate_name(exc: WeclappError) -> bool:
    detail = exc.detail
    if not isinstance(detail, dict):
        return False
    text = f"{detail.get('error') or ''} {detail.get('detail') or ''}".casefold()
    if "name is duplicate" in text:
        return True
    for item in detail.get("validationErrors") or []:
        if not isinstance(item, dict):
            continue
        if str(item.get("title") or "").casefold() == "entity is a duplicate":
            return True
    return False


def _weclapp_write_message(exc: BaseException, *, verb: str = "angelegt") -> str:
    if isinstance(exc, NoWeclappToken):
        return (
            "Zum Anlegen von Gruppen bitte zuerst den "
            "weclapp-Token hinterlegen."
        )
    if isinstance(exc, WeclappError):
        mapped = map_weclapp_error(exc)
        if mapped is not exc:
            return str(mapped)
        if _weclapp_duplicate_name(exc):
            return "Gruppenbezeichnung ist in weclapp bereits vergeben."
        return f"Gruppe in weclapp konnte nicht {verb} werden."
    return f"Gruppe in weclapp konnte nicht {verb} werden."


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
    haupt_id = hauptgruppe.id if hauptgruppe is not None else None
    db.rollback()
    if fragment == "untergruppen" and haupt_id is not None and _is_htmx(request):
        parent = _get_hauptgruppe(db, haupt_id)
        return _render_untergruppen(request, db, parent, user, error=exc.message)
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
    return request.app.state.templates.TemplateResponse(
        request,
        "gruppen/list.html",
        _list_context(request, db, user, groups, show_deleted=show_deleted),
    )


@router.get("/gruppen/diagramm", response_class=HTMLResponse)
def gruppen_diagramm(
    request: Request,
    user: SessionUser = Depends(require_user),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    tree = load_active_group_tree(db)
    n_unter = sum(len(children) for _, children in tree)
    return request.app.state.templates.TemplateResponse(
        request,
        "gruppen/diagramm.html",
        _ctx(
            user,
            tree=tree,
            arcs=build_sunburst_arcs(tree),
            n_haupt=len(tree),
            n_unter=n_unter,
        ),
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
    unter_code: str = Form(...),
    unter_name: str = Form(...),
) -> Response:
    try:
        group, untergruppe = create_hauptgruppe_with_untergruppe(
            db,
            code=code,
            name=name,
            unter_code=unter_code,
            unter_name=unter_name,
            actor=user,
        )
        if weclapp_category_writes_allowed(request):
            client = weclapp_client_for(db, user["oid"])
            create_haupt_and_unter_in_weclapp(
                client,
                haupt_name=group.name,
                haupt_code=group.code,
                unter_name=untergruppe.name,
                unter_code=untergruppe.code,
            )
        _commit(db)
    except GroupRegistryError as exc:
        db.rollback()
        groups = list_hauptgruppen(db, include_deleted=False)
        return request.app.state.templates.TemplateResponse(
            request,
            "gruppen/list.html",
            _list_context(
                request,
                db,
                user,
                groups,
                show_deleted=False,
                error=exc.message,
                form_code=code,
                form_name=name,
                form_unter_code=unter_code,
                form_unter_name=unter_name,
            ),
            status_code=400,
        )
    except (NoWeclappToken, WeclappError) as exc:
        db.rollback()
        groups = list_hauptgruppen(db, include_deleted=False)
        return request.app.state.templates.TemplateResponse(
            request,
            "gruppen/list.html",
            _list_context(
                request,
                db,
                user,
                groups,
                show_deleted=False,
                error=_weclapp_write_message(exc),
                form_code=code,
                form_name=name,
                form_unter_code=unter_code,
                form_unter_name=unter_name,
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
    nested = db.begin_nested()
    try:
        old_name = group.name
        rename_hauptgruppe(db, group, name=name, actor=user)
        if weclapp_category_writes_allowed(request) and group.name != old_name:
            client = weclapp_client_for(db, user["oid"])
            rename_haupt_in_weclapp(
                client,
                old_name=old_name,
                new_name=group.name,
                code=group.code,
            )
        nested.commit()
        _commit(db)
    except GroupRegistryError as exc:
        nested.rollback()
        db.refresh(group)
        if _is_htmx(request):
            return request.app.state.templates.TemplateResponse(
                request,
                "gruppen/partials/bezeichnung.html",
                _ctx(user, group=group, editing=True, name_error=exc.message),
            )
        return _error_page(request, user, exc.message)
    except (NoWeclappToken, WeclappError) as exc:
        nested.rollback()
        db.refresh(group)
        message = _weclapp_write_message(exc, verb="umbenannt")
        if _is_htmx(request):
            return request.app.state.templates.TemplateResponse(
                request,
                "gruppen/partials/bezeichnung.html",
                _ctx(user, group=group, editing=True, name_error=message),
            )
        return _error_page(request, user, message)
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
        created = create_untergruppe(db, parent, code=code, name=name, actor=user)
        if weclapp_category_writes_allowed(request):
            client = weclapp_client_for(db, user["oid"])
            create_unter_in_weclapp(
                client,
                parent_name=parent.name,
                unter_name=created.name,
                unter_code=created.code,
            )
        _commit(db)
    except GroupRegistryError as exc:
        return _write_failure(request, db, user, exc, hauptgruppe=parent, fragment="untergruppen")
    except (NoWeclappToken, WeclappError) as exc:
        return _write_failure(
            request,
            db,
            user,
            GroupRegistryError(_weclapp_write_message(exc)),
            hauptgruppe=parent,
            fragment="untergruppen",
        )
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
    nested = db.begin_nested()
    try:
        old_name = group.name
        rename_untergruppe(db, group, name=name, actor=user)
        if weclapp_category_writes_allowed(request) and group.name != old_name:
            client = weclapp_client_for(db, user["oid"])
            rename_unter_in_weclapp(
                client,
                parent_name=parent.name,
                parent_code=parent.code,
                old_name=old_name,
                new_name=group.name,
                unter_code=group.code,
            )
        nested.commit()
        _commit(db)
    except GroupRegistryError as exc:
        nested.rollback()
        db.refresh(parent)
        if _is_htmx(request):
            return _render_untergruppen(request, db, parent, user, error=exc.message)
        return _error_page(request, user, exc.message)
    except (NoWeclappToken, WeclappError) as exc:
        nested.rollback()
        db.refresh(parent)
        message = _weclapp_write_message(exc, verb="umbenannt")
        if _is_htmx(request):
            return _render_untergruppen(request, db, parent, user, error=message)
        return _error_page(request, user, message)
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
