"""Supply-source resolve preview (sibling to frozen /bezugsquellen export)."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.auth import SessionUser, require_user
from app.db import get_db
from app.models import SupplySourceRow, SupplySourceRun
from app.supply_source_runs import (
    SupplySourceRunError,
    apply_bulk_rates,
    apply_edits,
    apply_run_settings,
    approval_blockers,
    approve_run,
    assert_editable,
    attach_manual_alias,
    build_grid_config,
    can_approve,
    create_pull_run,
    format_pct,
    format_swiss_number,
    list_runs,
    list_suppliers,
    load_rows,
    parse_rate,
    running_for_supplier,
    summary_counts,
)

router = APIRouter()

_FRAGMENT_HEADERS = {"Cache-Control": "no-store"}

STATUS_LABELS = {
    "running": "Abfrage läuft…",
    "preview": "Vorschau",
    "approved": "Freigegeben",
    "applying": "Wird geschrieben…",
    "applied": "Geschrieben",
    "failed": "Fehlgeschlagen",
}


class CellEditIn(BaseModel):
    row_id: int
    field: str
    value: Any = ""


class BulkRatesIn(BaseModel):
    row_ids: list[int] | None = None
    rabattcode: str | None = None
    rabatt_1: str = ""
    rabatt_2: str = ""
    kein_rabatt: bool = False


def _get_run(db: Session, run_id: int) -> SupplySourceRun:
    run = db.scalars(
        select(SupplySourceRun)
        .options(joinedload(SupplySourceRun.supplier))
        .where(SupplySourceRun.id == run_id)
    ).first()
    if run is None:
        raise HTTPException(status_code=404, detail="Lauf nicht gefunden")
    return run


def _parse_decimal(raw: str, *, field: str) -> Decimal:
    text = (raw or "").strip().replace(",", ".")
    try:
        value = Decimal(text)
    except InvalidOperation as exc:
        raise SupplySourceRunError(f"{field} ist keine Zahl.") from exc
    return value


def _parse_eintritt(raw: str) -> datetime | None:
    text = (raw or "").strip()
    if not text:
        return None
    try:
        value = datetime.fromisoformat(text)
    except ValueError as exc:
        raise SupplySourceRunError("Preis-Eintritt ist kein gültiges Datum.") from exc
    if value.tzinfo is None:
        from datetime import UTC

        value = value.replace(tzinfo=UTC)
    return value


@router.get("/bezugsquellen/neu", response_class=HTMLResponse)
def run_list(
    request: Request,
    db: Session = Depends(get_db),
    user: SessionUser = Depends(require_user),
):
    suppliers = list_suppliers(db)
    default_id = next(
        (s.id for s in suppliers if s.supplier_number == "10000"),
        suppliers[0].id if suppliers else None,
    )
    busy = running_for_supplier(db, default_id) if default_id else None
    return request.app.state.templates.TemplateResponse(
        request,
        "supply_source_runs/list.html",
        {
            "user": user,
            "suppliers": suppliers,
            "runs": list_runs(db),
            "busy": busy,
            "default_supplier_id": default_id,
            "status_labels": STATUS_LABELS,
            "format_swiss_number": format_swiss_number,
        },
    )


@router.post("/bezugsquellen/neu/abfragen")
def start_pull(
    supplier_id: int = Form(...),
    db: Session = Depends(get_db),
    user: SessionUser = Depends(require_user),
):
    try:
        run = create_pull_run(db, supplier_id=supplier_id, user=user)
    except SupplySourceRunError as exc:
        return RedirectResponse(
            url=f"/bezugsquellen/neu?error={quote(str(exc))}",
            status_code=303,
        )
    return RedirectResponse(url=f"/bezugsquellen/neu/{run.id}", status_code=303)


@router.get("/bezugsquellen/neu/{run_id}", response_class=HTMLResponse)
def run_detail(
    request: Request,
    run_id: int,
    db: Session = Depends(get_db),
    user: SessionUser = Depends(require_user),
):
    run = _get_run(db, run_id)
    rows = load_rows(db, run.id) if run.status != "running" else []
    summary = summary_counts(rows)
    blockers = approval_blockers(rows)
    return request.app.state.templates.TemplateResponse(
        request,
        "supply_source_runs/detail.html",
        {
            "user": user,
            "run": run,
            "rows": rows,
            "summary": summary,
            "blockers": blockers,
            "can_approve": can_approve(rows) and run.status == "preview",
            "grid_config": build_grid_config(run, rows) if rows else None,
            "status_labels": STATUS_LABELS,
            "format_swiss_number": format_swiss_number,
            "format_pct": format_pct,
            "error": request.query_params.get("error"),
            "notice": request.query_params.get("notice"),
        },
    )


@router.get("/bezugsquellen/neu/{run_id}/status")
def run_status(
    run_id: int,
    db: Session = Depends(get_db),
    user: SessionUser = Depends(require_user),
):
    run = _get_run(db, run_id)
    return JSONResponse(
        {"status": run.status, "error": run.error},
        headers=_FRAGMENT_HEADERS,
    )


@router.post("/bezugsquellen/neu/{run_id}/edits")
def save_edits(
    run_id: int,
    payload: list[CellEditIn],
    db: Session = Depends(get_db),
    user: SessionUser = Depends(require_user),
):
    run = _get_run(db, run_id)
    try:
        apply_edits(
            db,
            run,
            [{"row_id": item.row_id, "field": item.field, "value": item.value} for item in payload],
        )
    except SupplySourceRunError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    rows = load_rows(db, run.id)
    return JSONResponse(
        {
            "ok": True,
            "discount_unset": summary_counts(rows)["discount_unset"],
            "can_approve": can_approve(rows),
            "grid": build_grid_config(run, rows),
        }
    )


@router.post("/bezugsquellen/neu/{run_id}/rabatte")
def bulk_rates(
    run_id: int,
    payload: BulkRatesIn,
    db: Session = Depends(get_db),
    user: SessionUser = Depends(require_user),
):
    run = _get_run(db, run_id)
    try:
        if payload.kein_rabatt:
            applied = apply_bulk_rates(
                db,
                run,
                row_ids=payload.row_ids,
                rabattcode=payload.rabattcode,
                kein_rabatt=True,
            )
        else:
            applied = apply_bulk_rates(
                db,
                run,
                row_ids=payload.row_ids,
                rabattcode=payload.rabattcode,
                rabatt_1=parse_rate(payload.rabatt_1),
                rabatt_2=parse_rate(payload.rabatt_2),
            )
    except SupplySourceRunError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    rows = load_rows(db, run.id)
    return JSONResponse(
        {
            "ok": True,
            "applied": applied,
            "discount_unset": summary_counts(rows)["discount_unset"],
            "can_approve": can_approve(rows),
            "grid": build_grid_config(run, rows),
        }
    )


@router.post("/bezugsquellen/neu/{run_id}/einstellungen")
def save_settings(
    run_id: int,
    einkaufswaehrung: str = Form(...),
    kurs: str = Form(...),
    verkaufswaehrung: str = Form(...),
    aufschlag: str = Form(...),
    preis_eintritt: str = Form(""),
    db: Session = Depends(get_db),
    user: SessionUser = Depends(require_user),
):
    run = _get_run(db, run_id)
    try:
        apply_run_settings(
            db,
            run,
            einkaufswaehrung=einkaufswaehrung.strip(),
            kurs=_parse_decimal(kurs, field="Kurs"),
            verkaufswaehrung=verkaufswaehrung.strip(),
            aufschlag=_parse_decimal(aufschlag, field="Aufschlag"),
            preis_eintritt=_parse_eintritt(preis_eintritt),
        )
    except SupplySourceRunError as exc:
        return RedirectResponse(
            url=f"/bezugsquellen/neu/{run.id}?error={quote(str(exc))}",
            status_code=303,
        )
    return RedirectResponse(url=f"/bezugsquellen/neu/{run.id}", status_code=303)


@router.post("/bezugsquellen/neu/{run_id}/zuordnen")
def manual_match(
    run_id: int,
    row_id: int = Form(...),
    article_number: str = Form(...),
    db: Session = Depends(get_db),
    user: SessionUser = Depends(require_user),
):
    run = _get_run(db, run_id)
    row = db.get(SupplySourceRow, row_id)
    if row is None or row.run_id != run.id:
        raise HTTPException(status_code=404, detail="Zeile nicht gefunden")
    try:
        attach_manual_alias(
            db,
            run,
            row,
            article_number=article_number,
            oid=str(user["oid"]),
            name=str(user.get("name") or ""),
        )
    except SupplySourceRunError as exc:
        return RedirectResponse(
            url=f"/bezugsquellen/neu/{run.id}?error={quote(str(exc))}",
            status_code=303,
        )
    return RedirectResponse(
        url=f"/bezugsquellen/neu/{run.id}?notice={quote('Artikel zugeordnet.')}",
        status_code=303,
    )


@router.post("/bezugsquellen/neu/{run_id}/freigeben")
def approve(
    run_id: int,
    db: Session = Depends(get_db),
    user: SessionUser = Depends(require_user),
):
    run = _get_run(db, run_id)
    try:
        assert_editable(run)
        approve_run(db, run)
    except SupplySourceRunError as exc:
        return RedirectResponse(
            url=f"/bezugsquellen/neu/{run.id}?error={quote(str(exc))}",
            status_code=303,
        )
    return RedirectResponse(
        url=f"/bezugsquellen/neu/{run.id}?notice={quote('Lauf freigegeben. Schreiben folgt in einem nächsten Schritt.')}",
        status_code=303,
    )
