"""Artikelübersicht routes: snapshot list, viewer, filters, Excel."""

from __future__ import annotations

import uuid
from typing import Any
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy.orm import Session

from app.assistant.service import MSG_DISABLED, MSG_NO_ANSWER, MSG_UNVERIFIED, ask
from app.assistant.tools import resolve_current_snapshot
from app.auth import SessionUser, require_user
from app.batches import JSPREADSHEET_CE_VERSION, JSUITES_VERSION
from app.config import settings
from app.db import get_db
from app.models import ArticleSnapshot, AssistantQuery
from app.snapshots import (
    EXCEL_MAX_ROWS,
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
    list_snapshots,
    running_snapshot,
)

router = APIRouter()

_FRAGMENT_HEADERS = {"Cache-Control": "no-store"}
_FRESH_PULL_PARAM = "neu"

MSG_FRAGE_NOT_FOUND = "Diese Frage wurde nicht gefunden."
MSG_FRAGE_OTHER_USER = "Diese Frage gehört zu einem anderen Benutzer."
MSG_FRAGE_OTHER_SNAPSHOT = "Diese Frage bezieht sich auf einen anderen Datenstand."
MSG_FRAGE_NOT_CURRENT = (
    "Fragen sind nur auf dem neuesten Datenstand möglich. "
    "Bitte die aktuelle Artikelübersicht öffnen."
)
MSG_SELECTION_TRUNCATED = (
    "Die Treffermenge ist zu groß für eine Auswahl (mehr als 5000 Artikel). "
    "Die Übersicht wird ungefiltert gezeigt."
)


def _is_fresh_pull(request: Request) -> bool:
    return request.query_params.get(_FRESH_PULL_PARAM) == "1"


def _snapshot_detail_url(snapshot_id: uuid.UUID, *, fresh_pull: bool = False) -> str:
    url = f"/artikel-uebersicht/{snapshot_id}"
    if fresh_pull:
        url += f"?{_FRESH_PULL_PARAM}=1"
    return url


def _parse_frage_id(raw: str) -> uuid.UUID | None:
    try:
        return uuid.UUID(raw)
    except ValueError:
        return None


def _hinweis_for_query(query: AssistantQuery) -> str | None:
    parts: list[str] = []
    if query.selection_truncated:
        parts.append(MSG_SELECTION_TRUNCATED)
    if query.outcome == "answered_unverified":
        parts.append(MSG_UNVERIFIED)
    elif query.outcome == "no_answer":
        parts.append(MSG_NO_ANSWER)
    return " ".join(parts) or None


def _resolve_assistant_frage(
    request: Request,
    db: Session,
    snapshot: ArticleSnapshot,
    user: SessionUser,
) -> tuple[AssistantQuery | None, str | None]:
    """Load ``frage=<uuid>``. Ignored queries return (None, German hinweis)."""
    raw = str(request.query_params.get("frage") or "").strip()
    if not raw:
        return None, None
    frage_id = _parse_frage_id(raw)
    if frage_id is None:
        return None, MSG_FRAGE_NOT_FOUND
    query = db.get(AssistantQuery, frage_id)
    if query is None:
        return None, MSG_FRAGE_NOT_FOUND
    if query.user_oid != str(user.get("oid") or ""):
        return None, MSG_FRAGE_OTHER_USER
    if query.snapshot_id != snapshot.id:
        return None, MSG_FRAGE_OTHER_SNAPSHOT
    return query, _hinweis_for_query(query)


def _filters(
    request: Request,
    query: AssistantQuery | None = None,
) -> SnapshotFilters:
    q = str(request.query_params.get("q") or "").strip()
    hauptgruppe = str(request.query_params.get("hauptgruppe") or "").strip()
    untergruppe = str(request.query_params.get("untergruppe") or "").strip()
    nur_aktive_explicit = "nur_aktive" in request.query_params
    nur_aktive = request.query_params.get("nur_aktive", "1") not in {"0", "false", "nein"}
    try:
        page = int(request.query_params.get("seite") or "1")
    except ValueError:
        page = 1

    assistant_query_id: uuid.UUID | None = None
    assistant_article_numbers: list[str] | None = None
    if query is not None:
        assistant_query_id = query.id
        if not query.selection_truncated and query.applied_article_numbers is not None:
            assistant_article_numbers = [
                str(number) for number in query.applied_article_numbers if str(number)
            ]

    # The grid hides inactive rows by default; the assistant does not unless
    # the model added that condition. Without this the German sentence and the
    # visible row count disagree. An explicit nur_aktive=1 still wins.
    if assistant_article_numbers is not None and not nur_aktive_explicit:
        nur_aktive = False

    return SnapshotFilters(
        query=q,
        hauptgruppe=hauptgruppe,
        untergruppe=untergruppe,
        nur_aktive=nur_aktive,
        page=page,
        assistant_query_id=assistant_query_id,
        assistant_article_numbers=assistant_article_numbers,
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
    if filters.assistant_query_id is not None:
        params.append(("frage", str(filters.assistant_query_id)))
    page_num = page if page is not None else filters.page
    if page_num > 1:
        params.append(("seite", str(page_num)))
    if fresh_pull:
        params.append((_FRESH_PULL_PARAM, "1"))
    return urlencode(params)


def _assistant_viewer_fields(
    query: AssistantQuery | None,
    hinweis: str | None,
) -> dict[str, Any]:
    if query is None:
        return {
            "assistant_question": None,
            "assistant_answer": None,
            "assistant_hinweis": hinweis,
            "assistant_outcome": None,
            "assistant_asked_at": None,
            "assistant_selection_count": None,
            "assistant_truncated": False,
            "assistant_query_id": None,
        }
    numbers = query.applied_article_numbers
    return {
        "assistant_question": query.question_de,
        "assistant_answer": query.answer_de,
        "assistant_hinweis": hinweis,
        "assistant_outcome": query.outcome,
        "assistant_asked_at": query.asked_at,
        "assistant_selection_count": len(numbers) if numbers is not None else None,
        "assistant_truncated": query.selection_truncated,
        "assistant_query_id": query.id,
    }


def _viewer_context(
    db: Session,
    snapshot: ArticleSnapshot,
    user: SessionUser,
    request: Request,
) -> dict[str, Any]:
    query, hinweis = _resolve_assistant_frage(request, db, snapshot, user)
    filters = _filters(request, query)
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
        "format_timestamp": format_snapshot_timestamp,
        "format_swiss_number": format_swiss_number,
        "jspreadsheet_version": JSPREADSHEET_CE_VERSION,
        "jsuites_version": JSUITES_VERSION,
        "running_snapshot": running_snapshot(db),
        **_assistant_viewer_fields(query, hinweis),
    }
    current = resolve_current_snapshot(db)
    ctx["assistant_available"] = bool(
        settings.assistant_enabled
        and current is not None
        and current.id == snapshot.id
    )

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

    query, _hinweis = _resolve_assistant_frage(request, db, snapshot, user)
    filters = _filters(request, query)
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
    content = excel_bytes(
        snapshot,
        rows,
        filters,
        question_de=query.question_de if query is not None else None,
    )
    stamp = excel_filename_timestamp(snapshot.created_at)
    filename = f"prosema-artikel_{stamp}.xlsx"
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/artikel-uebersicht/{snapshot_id}/frage", response_class=HTMLResponse)
def snapshot_frage(
    snapshot_id: uuid.UUID,
    request: Request,
    frage: str = Form(""),
    user: SessionUser = Depends(require_user),
    db: Session = Depends(get_db),
) -> Response:
    snapshot = db.get(ArticleSnapshot, snapshot_id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail="Abfrage nicht gefunden")

    if not settings.assistant_enabled:
        ctx = _viewer_context(db, snapshot, user, request)
        ctx["assistant_hinweis"] = MSG_DISABLED
        return request.app.state.templates.TemplateResponse(
            request,
            "snapshots/detail.html",
            ctx,
        )

    current = resolve_current_snapshot(db)
    if current is None or current.id != snapshot.id:
        ctx = _viewer_context(db, snapshot, user, request)
        ctx["assistant_hinweis"] = MSG_FRAGE_NOT_CURRENT
        return request.app.state.templates.TemplateResponse(
            request,
            "snapshots/detail.html",
            ctx,
        )

    result = ask(db, user, frage)
    params: list[tuple[str, str]] = [("frage", str(result.audit_id))]
    for key in ("q", "hauptgruppe", "untergruppe"):
        value = str(request.query_params.get(key) or "").strip()
        if value:
            params.append((key, value))
    return RedirectResponse(
        url=f"/artikel-uebersicht/{snapshot_id}?{urlencode(params)}",
        status_code=303,
    )
