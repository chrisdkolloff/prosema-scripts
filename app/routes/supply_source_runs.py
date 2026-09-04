"""Supply-source resolve preview (sibling to frozen /bezugsquellen export)."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.auth import SessionUser, require_admin, require_user
from app.db import get_db
from app.models import SupplySourceRow, SupplySourceRun
from app.supply_source_runs import (
    SupplySourceRunError,
    apply_template_overrides,
    apply_bulk_rates,
    apply_edits,
    apply_run_settings,
    approval_blockers,
    approve_run,
    attach_manual_alias,
    build_grid_config,
    can_approve,
    create_pull_run,
    create_upload_run,
    format_pct,
    format_swiss_number,
    list_runs,
    list_suppliers,
    load_rows,
    parse_aufschlag_percent,
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

OUTCOME_LABELS = {
    "UPDATED": "Aktualisiert",
    "PRICE_UPDATED": "Preis aktualisiert",
    "UNCHANGED": "Unverändert",
    "CREATED": "Neu angelegt",
    "ATTACHED": "Zugeordnet",
    "RENUMBERED": "Umnummeriert",
    "CONFLICT": "Konflikt",
    "REJECTED": "Abgelehnt",
    "GONE": "Nicht mehr vorhanden",
    "AUTH": "Zugang fehlgeschlagen",
    "UNKNOWN": "Unklar — prüfen",
}


class CellEditIn(BaseModel):
    row_id: int
    field: str
    value: Any = ""


class BulkTemplateIn(BaseModel):
    row_ids: list[int] | None = None


class BulkRatesIn(BaseModel):
    row_ids: list[int] | None = None
    rabattcode: str | None = None
    rabatt_1: str = ""
    rabatt_2: str = ""
    kein_rabatt: bool = False


def _get_run(db: Session, run_id: int) -> SupplySourceRun:
    run = db.scalars(
        select(SupplySourceRun)
        .options(
            joinedload(SupplySourceRun.supplier),
            joinedload(SupplySourceRun.upload),
        )
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
            "is_admin": "admin" in (user.get("roles") or []),
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


@router.get("/bezugsquellen/neu/vorlage.xlsx")
def download_template(
    supplier_id: int,
    db: Session = Depends(get_db),
    user: SessionUser = Depends(require_user),
):
    from app.models import Supplier
    from app.supply_source_templates import (
        SupplySourceTemplateError,
        generate_template_xlsx_for_user,
    )

    supplier = db.get(Supplier, supplier_id)
    if supplier is None or supplier.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Lieferant nicht gefunden")
    try:
        _template, data = generate_template_xlsx_for_user(db, supplier, user=user)
    except SupplySourceTemplateError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    filename = f"bezugsquellen-{supplier.supplier_number}.xlsx"
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
        },
    )


@router.post("/bezugsquellen/neu/upload")
async def start_upload(
    supplier_id: int = Form(...),
    datei: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: SessionUser = Depends(require_user),
):
    content = await datei.read()
    filename = datei.filename or "upload.xlsx"
    try:
        run = create_upload_run(
            db,
            supplier_id=supplier_id,
            filename=filename,
            content=content,
            user=user,
        )
    except SupplySourceRunError as exc:
        return RedirectResponse(
            url=f"/bezugsquellen/neu?error={quote(str(exc))}",
            status_code=303,
        )
    return RedirectResponse(url=f"/bezugsquellen/neu/{run.id}", status_code=303)


@router.get("/bezugsquellen/neu/vorlagen", response_class=HTMLResponse)
def template_admin(
    request: Request,
    db: Session = Depends(get_db),
    user: SessionUser = Depends(require_admin),
):
    from app.supply_source_templates import (
        ALL_KEYS,
        DEFAULT_COLUMNS,
        get_active_template,
        list_templates,
    )

    active = get_active_template(db)
    versions = list_templates(db)
    active_keys = (
        [str(c.get("key")) for c in (active.columns or [])]
        if active is not None
        else list(ALL_KEYS)
    )
    return request.app.state.templates.TemplateResponse(
        request,
        "supply_source_runs/templates.html",
        {
            "user": user,
            "active": active,
            "versions": versions,
            "columns": DEFAULT_COLUMNS,
            "active_keys": active_keys,
            "error": request.query_params.get("error"),
            "notice": request.query_params.get("notice"),
        },
    )


@router.post("/bezugsquellen/neu/vorlagen")
def save_template(
    keys: list[str] = Form(default=[]),
    db: Session = Depends(get_db),
    user: SessionUser = Depends(require_admin),
):
    from app.supply_source_templates import (
        REQUIRED_KEYS,
        SupplySourceTemplateError,
        create_template_version,
    )

    selected = list(dict.fromkeys([*REQUIRED_KEYS, *keys]))
    try:
        create_template_version(db, keys=selected, user=user, activate=True)
    except SupplySourceTemplateError as exc:
        return RedirectResponse(
            url=f"/bezugsquellen/neu/vorlagen?error={quote(str(exc))}",
            status_code=303,
        )
    return RedirectResponse(
        url="/bezugsquellen/neu/vorlagen?notice=" + quote("Neue Vorlagenversion ist aktiv."),
        status_code=303,
    )


@router.get("/bezugsquellen/neu/{run_id}", response_class=HTMLResponse)
def run_detail(
    request: Request,
    run_id: int,
    db: Session = Depends(get_db),
    user: SessionUser = Depends(require_user),
):
    from app.supply_source_apply import apply_summary, pending_rows

    run = _get_run(db, run_id)
    rows = load_rows(db, run.id) if run.status != "running" else []
    summary = summary_counts(rows)
    blockers = approval_blockers(rows)
    pending = pending_rows(db, run) if rows else []
    write_summary = apply_summary(pending) if pending else apply_summary(rows)
    outcomes: dict[str, list] = {}
    for row in rows:
        if not row.apply_outcome:
            continue
        outcomes.setdefault(row.apply_outcome, []).append(row)
    can_write = (
        can_approve(rows)
        and run.status in {"preview", "approved"}
        and bool(pending)
    )
    return request.app.state.templates.TemplateResponse(
        request,
        "supply_source_runs/detail.html",
        {
            "user": user,
            "run": run,
            "rows": rows,
            "summary": summary,
            "blockers": blockers,
            "can_approve": can_write,
            "write_summary": write_summary,
            "pending_count": len(pending),
            "outcomes": outcomes,
            "outcome_labels": OUTCOME_LABELS,
            "grid_config": build_grid_config(run, rows) if rows else None,
            "status_labels": STATUS_LABELS,
            "format_swiss_number": format_swiss_number,
            "format_pct": format_pct,
            "error": request.query_params.get("error"),
            "notice": request.query_params.get("notice"),
            "parse_summary": (run.upload.parse_summary if run.upload is not None else None),
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


@router.post("/bezugsquellen/neu/{run_id}/vorlagenwert")
def bulk_template(
    run_id: int,
    payload: BulkTemplateIn,
    db: Session = Depends(get_db),
    user: SessionUser = Depends(require_user),
):
    run = _get_run(db, run_id)
    try:
        applied = apply_template_overrides(
            db, run, row_ids=payload.row_ids or []
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
            aufschlag=parse_aufschlag_percent(aufschlag),
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
        approve_run(db, run, user)
    except SupplySourceRunError as exc:
        return RedirectResponse(
            url=f"/bezugsquellen/neu/{run.id}?error={quote(str(exc))}",
            status_code=303,
        )
    return RedirectResponse(
        url=f"/bezugsquellen/neu/{run.id}?notice={quote('Abschnitt wird nach weclapp geschrieben.')}",
        status_code=303,
    )
