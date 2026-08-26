"""Artikel-Übersicht routes: snapshot list, viewer, filters, Excel."""

from __future__ import annotations

import uuid
from typing import Any
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy.orm import Session

from app.auth import SessionUser, require_user
from app.batches import JSPREADSHEET_CE_VERSION, JSUITES_VERSION
from app.db import get_db
from app.models import ArticleSnapshot
from app.snapshots import (
    EXCEL_MAX_ROWS,
    GRID_PAGE_SIZE,
    SnapshotFilters,
    build_grid_config,
    count_filtered_rows,
    create_snapshot_pull,
    distinct_hauptgruppen,
    distinct_untergruppen,
    excel_bytes,
    excel_filename_timestamp,
    fetch_all_filtered_rows,
    fetch_filtered_rows,
    format_snapshot_timestamp,
    format_swiss_number,
    running_snapshot,
    list_snapshots,
)

router = APIRouter()

_FRAGMENT_HEADERS = {"Cache-Control": "no-store"}
_FRESH_PULL_PARAM = "neu"


def _is_fresh_pull(request: Request) -> bool:
    return request.query_params.get(_FRESH_PULL_PARAM) == "1"


def _snapshot_detail_url(snapshot_id: uuid.UUID, *, fresh_pull: bool = False) -> str:
    url = f"/artikel-uebersicht/{snapshot_id}"
    if fresh_pull:
        url += f"?{_FRESH_PULL_PARAM}=1"
    return url


def _filters(request: Request) -> SnapshotFilters:
    q = str(request.query_params.get("q") or "").strip()
    hauptgruppe = str(request.query_params.get("hauptgruppe") or "").strip()
    untergruppe = str(request.query_params.get("untergruppe") or "").strip()
    nur_aktive = request.query_params.get("nur_aktive", "1") not in {"0", "false", "nein"}
    try:
        page = int(request.query_params.get("seite") or "1")
    except ValueError:
        page = 1
    return SnapshotFilters(
        query=q,
        hauptgruppe=hauptgruppe,
        untergruppe=untergruppe,
        nur_aktive=nur_aktive,
        page=page,
    )


def _filter_query_params(
    filters: SnapshotFilters,
    *,
    page: int | None = None,
    fresh_pull: bool = False,
) -> str:
    params: list[tuple[str, str]] = []
    if filters.query:
        params.append(("q", filters.query))
    if filters.hauptgruppe:
        params.append(("hauptgruppe", filters.hauptgruppe))
    if filters.untergruppe:
        params.append(("untergruppe", filters.untergruppe))
    if not filters.nur_aktive:
        params.append(("nur_aktive", "0"))
    page_num = page if page is not None else filters.page
    if page_num > 1:
        params.append(("seite", str(page_num)))
    if fresh_pull:
        params.append((_FRESH_PULL_PARAM, "1"))
    return urlencode(params)


def _viewer_context(
    db: Session,
    snapshot: ArticleSnapshot,
    user: SessionUser,
    request: Request,
) -> dict[str, Any]:
    filters = _filters(request)
    fresh_pull = _is_fresh_pull(request)
    filter_qs = _filter_query_params(filters)
    viewer_qs = _filter_query_params(filters, fresh_pull=fresh_pull)
    total_all = snapshot.row_count or 0
    ctx: dict[str, Any] = {
        "user": user,
        "snapshot": snapshot,
        "filters": filters,
        "filter_qs": filter_qs,
        "viewer_qs": viewer_qs,
        "total_all": total_all,
        "is_fresh_pull": fresh_pull,
        "format_timestamp": format_snapshot_timestamp(snapshot.created_at),
        "format_swiss_number": format_swiss_number,
        "jspreadsheet_version": JSPREADSHEET_CE_VERSION,
        "jsuites_version": JSUITES_VERSION,
        "running_snapshot": running_snapshot(db),
    }

    if snapshot.status == "complete":
        page_rows, total_filtered, pages = fetch_filtered_rows(db, snapshot.id, filters)
        ctx.update(
            {
                "page_rows": page_rows,
                "total_filtered": total_filtered,
                "pages": pages,
                "page": filters.page,
                "hauptgruppen": distinct_hauptgruppen(db, snapshot.id),
                "untergruppen": distinct_untergruppen(
                    db, snapshot.id, hauptgruppe=filters.hauptgruppe
                ),
                "grid_config": build_grid_config(snapshot, page_rows),
                "excel_qs": filter_qs,
            }
        )
    return ctx


@router.get("/artikel-uebersicht", response_class=HTMLResponse)
def snapshot_list(
    request: Request,
    user: SessionUser = Depends(require_user),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    running = running_snapshot(db)
    return request.app.state.templates.TemplateResponse(
        request,
        "snapshots/list.html",
        {
            "user": user,
            "snapshots": list_snapshots(db),
            "running_snapshot": running,
            "format_timestamp": format_snapshot_timestamp,
            "format_swiss_number": format_swiss_number,
        },
    )


@router.post("/artikel-uebersicht/abfragen", response_class=HTMLResponse)
def start_snapshot_pull(
    request: Request,
    user: SessionUser = Depends(require_user),
    db: Session = Depends(get_db),
) -> Response:
    result = create_snapshot_pull(db, user)
    if isinstance(result, ArticleSnapshot):
        if request.headers.get("HX-Request") == "true":
            return request.app.state.templates.TemplateResponse(
                request,
                "snapshots/partials/running_notice.html",
                {"user": user, "snapshot": result},
                headers=_FRAGMENT_HEADERS,
            )
        return RedirectResponse(
            url=_snapshot_detail_url(result.id, fresh_pull=True),
            status_code=303,
        )

    snapshot, _job = result
    return RedirectResponse(
        url=_snapshot_detail_url(snapshot.id, fresh_pull=True),
        status_code=303,
    )


@router.get("/artikel-uebersicht/{snapshot_id}", response_class=HTMLResponse)
def snapshot_detail(
    snapshot_id: uuid.UUID,
    request: Request,
    user: SessionUser = Depends(require_user),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    snapshot = db.get(ArticleSnapshot, snapshot_id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail="Abfrage nicht gefunden")
    return request.app.state.templates.TemplateResponse(
        request,
        "snapshots/detail.html",
        _viewer_context(db, snapshot, user, request),
    )


@router.get("/artikel-uebersicht/{snapshot_id}/untergruppen", response_class=HTMLResponse)
def snapshot_untergruppen_partial(
    snapshot_id: uuid.UUID,
    request: Request,
    user: SessionUser = Depends(require_user),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    snapshot = db.get(ArticleSnapshot, snapshot_id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail="Abfrage nicht gefunden")
    if snapshot.status != "complete":
        raise HTTPException(status_code=400, detail="Abfrage noch nicht abgeschlossen")
    hauptgruppe = str(request.query_params.get("hauptgruppe") or "").strip()
    # Changing Hauptgruppe resets Untergruppe; only options for the selection remain.
    return request.app.state.templates.TemplateResponse(
        request,
        "snapshots/partials/untergruppe_select.html",
        {
            "user": user,
            "snapshot": snapshot,
            "untergruppen": distinct_untergruppen(
                db, snapshot.id, hauptgruppe=hauptgruppe
            ),
            "filters": SnapshotFilters(hauptgruppe=hauptgruppe, untergruppe=""),
        },
        headers=_FRAGMENT_HEADERS,
    )


@router.get("/artikel-uebersicht/{snapshot_id}/zeilen", response_class=HTMLResponse)
def snapshot_rows_partial(
    snapshot_id: uuid.UUID,
    request: Request,
    user: SessionUser = Depends(require_user),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    snapshot = db.get(ArticleSnapshot, snapshot_id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail="Abfrage nicht gefunden")
    if snapshot.status != "complete":
        raise HTTPException(status_code=400, detail="Abfrage noch nicht abgeschlossen")
    ctx = _viewer_context(db, snapshot, user, request)
    return request.app.state.templates.TemplateResponse(
        request,
        "snapshots/partials/grid.html",
        ctx,
        headers=_FRAGMENT_HEADERS,
    )


@router.get("/artikel-uebersicht/{snapshot_id}/status", response_class=HTMLResponse)
def snapshot_status_poll(
    snapshot_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    user: SessionUser = Depends(require_user),
) -> HTMLResponse:
    snapshot = db.get(ArticleSnapshot, snapshot_id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail="Abfrage nicht gefunden")
    if snapshot.status == "running":
        return HTMLResponse(
            '<p class="muted">Abfrage läuft…</p>',
            headers=_FRAGMENT_HEADERS,
        )
    redirect_url = _snapshot_detail_url(snapshot_id, fresh_pull=_is_fresh_pull(request))
    return HTMLResponse("", headers={"HX-Redirect": redirect_url})


@router.get("/artikel-uebersicht/{snapshot_id}/excel")
def snapshot_excel(
    snapshot_id: uuid.UUID,
    request: Request,
    user: SessionUser = Depends(require_user),
    db: Session = Depends(get_db),
) -> Response:
    snapshot = db.get(ArticleSnapshot, snapshot_id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail="Abfrage nicht gefunden")
    if snapshot.status != "complete":
        raise HTTPException(status_code=400, detail="Abfrage noch nicht abgeschlossen")

    filters = _filters(request)
    total = count_filtered_rows(db, snapshot.id, filters)
    if total > EXCEL_MAX_ROWS:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Zu viele Zeilen ({format_swiss_number(total)}). "
                f"Maximal {format_swiss_number(EXCEL_MAX_ROWS)} Zeilen pro Export."
            ),
        )
    rows = fetch_all_filtered_rows(db, snapshot.id, filters)
    content = excel_bytes(snapshot, rows, filters)
    stamp = excel_filename_timestamp(snapshot.created_at)
    filename = f"prosema-artikel_{stamp}.xlsx"
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
