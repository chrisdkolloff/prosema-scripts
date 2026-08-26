"""Article batch editor: grid page, cell edits, concurrent-editor presence."""

from __future__ import annotations

import uuid
from typing import Any
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.auth import SessionUser, require_user
from app.batches import (
    BatchEditError,
    CellEdit,
    apply_edits,
    build_grid_config,
    filtered_rows,
    group_dropdowns,
    load_batch_rows,
    schema_dropdowns,
    touch_presence,
)
from app.db import get_db
from app.models import ArticleBatch

router = APIRouter()

_FRAGMENT_HEADERS = {"Cache-Control": "no-store"}


class CellEditIn(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=False)

    row_id: uuid.UUID
    field: str
    value: Any = Field(default="")


def _filters(
    request: Request,
) -> dict[str, Any]:
    q = str(request.query_params.get("q") or "").strip()
    hauptgruppe = str(request.query_params.get("hauptgruppe") or "").strip()
    kategorie = str(request.query_params.get("kategorie") or "").strip()
    aktiv = str(request.query_params.get("aktiv") or "").strip()
    nur_fehler = request.query_params.get("nur_fehler") in {"1", "true", "ja"}
    try:
        page = int(request.query_params.get("seite") or "1")
    except ValueError:
        page = 1
    return {
        "query": q,
        "hauptgruppe": hauptgruppe,
        "kategorie": kategorie,
        "aktiv": aktiv,
        "nur_fehler": nur_fehler,
        "page": page,
    }


def _page_context(
    db: Session,
    batch: ArticleBatch,
    user: SessionUser,
    request: Request,
) -> dict[str, Any]:
    filters = _filters(request)
    all_rows = load_batch_rows(db, batch.id)
    page_rows, total, pages = filtered_rows(all_rows, **filters)
    haupt, _unter = group_dropdowns(db)
    categories = schema_dropdowns().get("Kategorie") or []
    query_params = []
    if filters["query"]:
        query_params.append(("q", filters["query"]))
    if filters["hauptgruppe"]:
        query_params.append(("hauptgruppe", filters["hauptgruppe"]))
    if filters["kategorie"]:
        query_params.append(("kategorie", filters["kategorie"]))
    if filters["aktiv"]:
        query_params.append(("aktiv", filters["aktiv"]))
    if filters["nur_fehler"]:
        query_params.append(("nur_fehler", "1"))
    filter_qs = urlencode(query_params)
    return {
        "user": user,
        "batch": batch,
        "filters": filters,
        "filter_qs": filter_qs,
        "total_rows": total,
        "pages": pages,
        "page": filters["page"],
        "hauptgruppen": haupt,
        "kategorien": categories,
        "grid_config": build_grid_config(db, batch, page_rows),
        "editable": batch.status == "draft",
    }


@router.get("/batches/{batch_id}", response_class=HTMLResponse)
def batch_detail(
    batch_id: uuid.UUID,
    request: Request,
    user: SessionUser = Depends(require_user),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    batch = db.get(ArticleBatch, batch_id)
    if batch is None:
        raise HTTPException(status_code=404, detail="Stapel nicht gefunden")
    return request.app.state.templates.TemplateResponse(
        request,
        "batches/detail.html",
        _page_context(db, batch, user, request),
    )


@router.post("/batches/{batch_id}/edits")
def batch_edits(
    batch_id: uuid.UUID,
    payload: list[CellEditIn],
    user: SessionUser = Depends(require_user),
    db: Session = Depends(get_db),
) -> JSONResponse:
    batch = db.get(ArticleBatch, batch_id)
    if batch is None:
        return JSONResponse({"error": "Stapel nicht gefunden"}, status_code=404)
    edits = [
        CellEdit(row_id=item.row_id, field=item.field, value=item.value) for item in payload
    ]
    try:
        results = apply_edits(db, batch, edits)
    except BatchEditError as exc:
        body: dict[str, Any] = {"error": exc.message}
        if exc.field:
            body["field"] = exc.field
        return JSONResponse(body, status_code=exc.status_code)
    db.commit()
    return JSONResponse(
        {
            "rows": [
                {
                    "id": str(item.id),
                    "proposed_article_number": item.proposed_article_number,
                    "validation_error": item.validation_error,
                    "include": item.include,
                    "corrected": item.corrected,
                }
                for item in results
            ]
        }
    )


@router.post("/batches/{batch_id}/anwesenheit", response_class=HTMLResponse)
def batch_presence(
    batch_id: uuid.UUID,
    request: Request,
    user: SessionUser = Depends(require_user),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    batch = db.get(ArticleBatch, batch_id)
    if batch is None:
        raise HTTPException(status_code=404, detail="Stapel nicht gefunden")
    names = touch_presence(db, batch, user)
    db.commit()
    return request.app.state.templates.TemplateResponse(
        request,
        "batches/partials/presence.html",
        {"user": user, "names": names},
        headers=_FRAGMENT_HEADERS,
    )


@router.get("/batches/{batch_id}/anwesenheit", response_class=HTMLResponse)
def batch_presence_get(
    batch_id: uuid.UUID,
    request: Request,
    user: SessionUser = Depends(require_user),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    return batch_presence(batch_id, request, user, db)
