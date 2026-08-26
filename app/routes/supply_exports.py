"""Bezugsquellen-Export routes."""

from __future__ import annotations

import uuid
from typing import Any
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth import SessionUser, require_user
from app.db import get_db
from app.models import ExportRow, ExportRun
from app.supply_export_csv import serialise_export_csv
from app.supply_export_fields import PRESET_ALL, PRESET_MANDATORY, PRESET_STANDARD
from app.supply_exports import (
    DEFAULT_SUPPLIER_ID,
    SALES_CURRENCIES,
    ZERO_CATEGORY_LABEL,
    ExportFilters,
    apply_edits,
    apply_run_settings,
    assert_run_editable,
    blocking_counts,
    build_grid_config,
    bulk_assign_category,
    create_export_pull,
    current_discount_categories,
    distinct_values,
    fetch_all_filtered_row_ids,
    fetch_filtered_rows,
    filename_timestamp,
    format_display_date,
    format_iso_date,
    format_run_timestamp,
    format_swiss_number,
    grid_row_values,
    is_override,
    list_exports,
    load_visible_fields,
    parse_iso_date,
    picker_payload,
    row_has_changes,
    row_is_highlighted,
    running_export,
    save_visible_fields,
    validate_and_preview,
)

router = APIRouter()

_FRAGMENT_HEADERS = {"Cache-Control": "no-store"}


class CellEditIn(BaseModel):
    row_id: uuid.UUID
    field: str
    value: Any = ""


class ColumnPrefIn(BaseModel):
    visible: list[str] | None = None
    preset: str | None = None


def _filters(request: Request) -> ExportFilters:
    try:
        page = int(request.query_params.get("seite") or "1")
    except ValueError:
        page = 1
    return ExportFilters(
        query=str(request.query_params.get("q") or "").strip(),
        discount_category=str(request.query_params.get("kategorie") or "").strip(),
        hauptgruppe=str(request.query_params.get("hauptgruppe") or "").strip(),
        untergruppe=str(request.query_params.get("untergruppe") or "").strip(),
        changed_only=request.query_params.get("nur_aenderungen") in {"1", "true", "on"},
        unresolved_only=request.query_params.get("nur_offen") in {"1", "true", "on"},
        page=page,
    )


def _filter_qs(filters: ExportFilters, *, page: int | None = None) -> str:
    params: list[tuple[str, str]] = []
    if filters.query:
        params.append(("q", filters.query))
    if filters.discount_category:
        params.append(("kategorie", filters.discount_category))
    if filters.hauptgruppe:
        params.append(("hauptgruppe", filters.hauptgruppe))
    if filters.untergruppe:
        params.append(("untergruppe", filters.untergruppe))
    if filters.changed_only:
        params.append(("nur_aenderungen", "1"))
    if filters.unresolved_only:
        params.append(("nur_offen", "1"))
    if page is not None:
        if page > 1:
            params.append(("seite", str(page)))
    elif filters.page > 1:
        params.append(("seite", str(filters.page)))
    return urlencode(params)


def _get_run(db: Session, run_id: uuid.UUID) -> ExportRun:
    run = db.get(ExportRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Lauf nicht gefunden")
    return run


@router.get("/bezugsquellen", response_class=HTMLResponse)
def export_list(
    request: Request,
    db: Session = Depends(get_db),
    user: SessionUser = Depends(require_user),
):
    runs = list_exports(db, supplier_id=DEFAULT_SUPPLIER_ID)
    return request.app.state.templates.TemplateResponse(
        request,
        "supply_exports/list.html",
        {
            "user": user,
            "runs": runs,
            "running": running_export(db),
            "supplier_id": DEFAULT_SUPPLIER_ID,
            "format_timestamp": format_run_timestamp,
            "format_swiss_number": format_swiss_number,
        },
    )


@router.post("/bezugsquellen/spalten")
def save_columns(
    payload: ColumnPrefIn,
    db: Session = Depends(get_db),
    user: SessionUser = Depends(require_user),
) -> JSONResponse:
    preset = (payload.preset or "").strip()
    if preset and preset not in {PRESET_STANDARD, PRESET_MANDATORY, PRESET_ALL}:
        return JSONResponse({"error": "Unbekanntes Preset"}, status_code=400)
    visible = save_visible_fields(
        db,
        str(user["oid"]),
        visible=payload.visible,
        preset=preset or None,
    )
    db.commit()
    return JSONResponse({"visible": visible, "picker": picker_payload(visible)})


@router.post("/bezugsquellen/abfragen")
def export_pull(
    db: Session = Depends(get_db),
    user: SessionUser = Depends(require_user),
    supplier_id: str = Form(DEFAULT_SUPPLIER_ID),
):
    try:
        run = create_export_pull(db, user, supplier_id=supplier_id or DEFAULT_SUPPLIER_ID)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return RedirectResponse(url=f"/bezugsquellen/{run.id}", status_code=303)


@router.get("/bezugsquellen/{run_id}", response_class=HTMLResponse)
def export_detail(
    request: Request,
    run_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: SessionUser = Depends(require_user),
):
    run = _get_run(db, run_id)
    filters = _filters(request)
    registry = current_discount_categories(db, run.supplier_id)
    context: dict[str, Any] = {
        "user": user,
        "run": run,
        "filters": filters,
        "filter_qs": _filter_qs(filters, page=0),
        "format_timestamp": format_run_timestamp,
        "format_swiss_number": format_swiss_number,
        "format_iso_date": format_iso_date,
        "format_display_date": format_display_date,
        "sales_currencies": SALES_CURRENCIES,
        "registry": registry,
        "editable": run.status == "draft",
    }

    if run.status in {"draft", "exported"}:
        rows, total, pages = fetch_filtered_rows(db, run.id, filters)
        blocks = blocking_counts(db, run)
        visible = load_visible_fields(db, str(user["oid"]))
        context.update(
            {
                "grid_config": build_grid_config(
                    run, rows, registry, visible_fields=visible
                ),
                "column_picker": picker_payload(visible),
                "total": total,
                "pages": pages,
                "page": filters.page,
                "blocks": blocks,
                "categories": distinct_values(db, run.id, ExportRow.discount_category),
                "hauptgruppen": distinct_values(db, run.id, ExportRow.hauptgruppe_code),
                "untergruppen": distinct_values(db, run.id, ExportRow.untergruppe_code),
                "summary": run.summary_json or {},
            }
        )

    return request.app.state.templates.TemplateResponse(
        request,
        "supply_exports/detail.html",
        context,
    )


@router.get("/bezugsquellen/{run_id}/status", response_class=HTMLResponse)
def export_status(
    request: Request,
    run_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: SessionUser = Depends(require_user),
):
    run = _get_run(db, run_id)
    if run.status in {"draft", "exported", "failed"}:
        return Response(
            status_code=200,
            headers={"HX-Redirect": f"/bezugsquellen/{run.id}"},
            content="",
        )
    return request.app.state.templates.TemplateResponse(
        request,
        "supply_exports/partials/running_notice.html",
        {"user": user, "run": run},
        headers=_FRAGMENT_HEADERS,
    )


@router.post("/bezugsquellen/{run_id}/edits")
def export_edits(
    run_id: uuid.UUID,
    payload: list[CellEditIn],
    user: SessionUser = Depends(require_user),
    db: Session = Depends(get_db),
) -> JSONResponse:
    run = db.get(ExportRun, run_id)
    if run is None:
        return JSONResponse({"error": "Lauf nicht gefunden"}, status_code=404)
    registry = current_discount_categories(db, run.supplier_id)
    edits = [
        {"row_id": item.row_id, "field": item.field, "value": item.value}
        for item in payload
    ]
    try:
        rows = apply_edits(db, run, edits, registry)
        db.commit()
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)

    visible = load_visible_fields(db, str(user["oid"]))
    return JSONResponse(
        {
            "rows": [
                {
                    "id": str(row.id),
                    "changed": row_has_changes(row),
                    "highlighted": row_is_highlighted(row, registry),
                    "unresolved": row.discount_intent == "unresolved",
                    "override": is_override(row, registry.get(row.discount_category)),
                    "values": dict(
                        zip(
                            visible,
                            grid_row_values(row, run, registry, visible),
                            strict=True,
                        )
                    ),
                }
                for row in rows
            ]
        }
    )


@router.post("/bezugsquellen/{run_id}/bulk")
async def bulk_action(
    run_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    user: SessionUser = Depends(require_user),
    action: str = Form(...),
    category_code: str = Form(""),
):
    from sqlalchemy import select

    run = _get_run(db, run_id)
    filters = _filters(request)
    registry = current_discount_categories(db, run.supplier_id)
    row_ids = fetch_all_filtered_row_ids(db, run.id, filters)
    try:
        assert_run_editable(run)
        if action == "assign_category":
            if not category_code.strip():
                raise ValueError("Kategorie wählen")
            bulk_assign_category(db, run, row_ids, category_code.strip(), registry)
        elif action == "mark_zero":
            bulk_assign_category(db, run, row_ids, ZERO_CATEGORY_LABEL, registry)
        else:
            raise ValueError("Unbekannte Aktion")
        db.commit()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return RedirectResponse(
        url=f"/bezugsquellen/{run.id}?{_filter_qs(filters)}",
        status_code=303,
    )


@router.post("/bezugsquellen/{run_id}/einstellungen")
def export_settings(
    run_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: SessionUser = Depends(require_user),
    price_entry_date: str = Form(""),
    sales_article_currency: str = Form(""),
):
    run = _get_run(db, run_id)
    try:
        apply_run_settings(
            run,
            price_entry_date=parse_iso_date(price_entry_date),
            sales_article_currency=sales_article_currency,
        )
        db.commit()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return RedirectResponse(url=f"/bezugsquellen/{run.id}", status_code=303)


@router.get("/bezugsquellen/{run_id}/vorschau", response_class=HTMLResponse)
def export_preview(
    request: Request,
    run_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: SessionUser = Depends(require_user),
):
    run = _get_run(db, run_id)
    report = validate_and_preview(db, run)
    return request.app.state.templates.TemplateResponse(
        request,
        "supply_exports/preview.html",
        {
            "user": user,
            "run": run,
            "report": report,
            "can_download": run.status in {"draft", "exported"} and not report.errors,
            "format_timestamp": format_run_timestamp,
            "format_swiss_number": format_swiss_number,
            "format_display_date": format_display_date,
        },
    )


@router.post("/bezugsquellen/{run_id}/download")
def export_download(
    run_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: SessionUser = Depends(require_user),
):
    run = _get_run(db, run_id)

    if run.status == "exported" and run.file:
        return Response(
            content=bytes(run.file),
            media_type="text/csv; charset=windows-1252",
            headers={
                "Content-Disposition": f'attachment; filename="{run.filename or "bezugsquellen.csv"}"'
            },
        )

    if run.status != "draft":
        raise HTTPException(status_code=400, detail="Download nur für Entwurf oder Archiv")

    report = validate_and_preview(db, run)
    if report.errors:
        raise HTTPException(
            status_code=400,
            detail=f"Validierung fehlgeschlagen ({len(report.errors)} Fehler). Siehe Vorschau.",
        )

    from sqlalchemy import select

    rows = list(
        db.scalars(
            select(ExportRow)
            .where(ExportRow.run_id == run.id)
            .order_by(ExportRow.position)
        )
    )
    rows = [row for row in rows if row_has_changes(row)]
    payload = serialise_export_csv(db, run, rows)
    filename = (
        f"bezugsquellen_{run.supplier_id}_{filename_timestamp(run.created_at)}.csv"
    )
    run.file = payload
    run.filename = filename
    run.status = "exported"
    run.included_count = len(rows)
    # Persist which rows were exported for prior-run diffs.
    for row in db.scalars(select(ExportRow).where(ExportRow.run_id == run.id)):
        row.included = row_has_changes(row)
    db.commit()

    return Response(
        content=payload,
        media_type="text/csv; charset=windows-1252",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
