"""Transform review UI: spec form, preview table, confirm, reconcile."""

from __future__ import annotations

import json
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.datastructures import FormData

from app.auth import SessionUser, require_user
from app.db import get_db
from app.models import ArticleSnapshot, TransformChunk, TransformRow, TransformRun
from app.snapshots import SnapshotFilters, fetch_all_filtered_rows
from app.transform.apply import CHUNK_SIZE, approve_chunk, start_transform_apply
from app.transform.diff import (
    MSG_HTML_FORMAT,
    contains_markup,
    field_is_html,
    render_diff_html,
    segments_from_fired,
)
from app.transform.preview import start_transform_preview
from app.transform.reconcile import reconcile_unknown_row
from app.transform.schemas import TransformSpec, TransformSpecError
from app.transform.summary import chunk_result_summary, preview_summary
from app.transform.ui import (
    MSG_TRANSFORM_UNAVAILABLE,
    pass_1_choices,
    transform_gate,
)
from core.article_write_fields import write_field

router = APIRouter()

MSG_NO_SELECTION = "Keine Zeile ausgewählt"
MSG_CONFIRM = "{selected} von {total} Änderungen anwenden (Block {chunk} von {chunks})"
MSG_RECONCILE = "Abgleichen"
MSG_SELECT_ALL = "alle auswählen"
MSG_DESELECT_ALL = "alle abwählen"
GROUP_STANDALONE = "Änderungen an eigenständigen Vorkommen"
GROUP_EMBEDDED = "Änderungen innerhalb eines zusammengesetzten Wortes"
GROUP_OTHER = "Weitere Änderungen"


def _require_transform_allowed(db: Session, snapshot: ArticleSnapshot | None) -> ArticleSnapshot:
    if snapshot is None:
        raise HTTPException(status_code=404, detail="Abfrage nicht gefunden")
    if not transform_gate(db, snapshot)["transform_allowed"]:
        raise HTTPException(status_code=400, detail=MSG_TRANSFORM_UNAVAILABLE)
    return snapshot


def _claimed_ids(db: Session, run_id: uuid.UUID) -> set[uuid.UUID]:
    claimed: set[uuid.UUID] = set()
    for chunk in db.scalars(select(TransformChunk).where(TransformChunk.run_id == run_id)):
        for item in chunk.row_ids or []:
            claimed.add(uuid.UUID(str(item)))
    return claimed


def pending_review_rows(db: Session, run: TransformRun) -> list[TransformRow]:
    claimed = _claimed_ids(db, run.id)
    rows = list(
        db.scalars(
            select(TransformRow)
            .where(
                TransformRow.run_id == run.id,
                TransformRow.row_status.in_(("CHANGED", "DECLINED")),
                TransformRow.apply_outcome.is_(None),
            )
            .order_by(TransformRow.article_number, TransformRow.field, TransformRow.id)
        )
    )
    return [row for row in rows if row.id not in claimed]


def group_rows(rows: list[TransformRow]) -> list[dict[str, Any]]:
    buckets = [
        ("standalone", GROUP_STANDALONE, [r for r in rows if r.inside_compound is False]),
        ("embedded", GROUP_EMBEDDED, [r for r in rows if r.inside_compound is True]),
        ("other", GROUP_OTHER, [r for r in rows if r.inside_compound is None]),
    ]
    return [{"key": key, "title": title, "rows": members} for key, title, members in buckets if members]


def row_views(rows: list[TransformRow]) -> list[dict[str, Any]]:
    views = []
    for row in rows:
        html_field = field_is_html(row.field)
        kind = write_field(row.field).value_kind
        segs = segments_from_fired(
            row.old_value,
            row.new_value,
            list(row.operations_fired or []),
            value_kind=kind,
        )
        views.append(
            {
                "row": row,
                "diff": render_diff_html(segs),
                "html_field": html_field,
                "has_markup": html_field
                and (contains_markup(row.old_value) or contains_markup(row.new_value)),
                "checked": row.row_status != "DECLINED",
                "group_key": (
                    "standalone"
                    if row.inside_compound is False
                    else "embedded"
                    if row.inside_compound is True
                    else "other"
                ),
            }
        )
    return views


def _numbers_from_form(form: FormData, snapshot: ArticleSnapshot, db: Session) -> list[str]:
    selected = [str(v).strip() for v in form.getlist("artikelnummer") if str(v).strip()]
    if selected:
        return selected
    filters = SnapshotFilters(
        query=str(form.get("q") or "").strip(),
        hauptgruppe=str(form.get("hauptgruppe") or "").strip(),
        untergruppe=str(form.get("untergruppe") or "").strip(),
        nur_aktive=str(form.get("nur_aktive") or "1") not in {"0", "false", "nein"},
    )
    rows = fetch_all_filtered_rows(db, snapshot.id, filters)
    return [row.article_number for row in rows if row.article_number]


def _spec_from_form(form: FormData, numbers: list[str]) -> TransformSpec:
    fields = [str(v) for v in form.getlist("felder") if str(v).strip()]
    allowed = set(pass_1_choices())
    bad = [key for key in fields if key not in allowed]
    if bad:
        raise TransformSpecError(
            f"Feld «{bad[0]}» darf in diesem Schritt nicht geändert werden",
            f"not PASS_1: {bad[0]}",
        )
    ops: list[dict[str, str]] = []
    kinds = form.getlist("op_art")
    searches = form.getlist("op_suche")
    replaces = form.getlist("op_ersatz")
    for i, kind in enumerate(kinds):
        search = str(searches[i]) if i < len(searches) else ""
        replace = str(replaces[i]) if i < len(replaces) else ""
        item: dict[str, str] = {"op": str(kind), "search": search}
        if str(kind) in {"replace_word", "replace_literal"}:
            item["replace"] = replace
        ops.append(item)
    return TransformSpec.model_validate(
        {"scope": {"article_numbers": numbers}, "fields": fields, "operations": ops}
    )


@router.post("/artikel-uebersicht/{snapshot_id}/transform/vorschau")
async def start_preview(
    snapshot_id: uuid.UUID,
    request: Request,
    user: SessionUser = Depends(require_user),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    snapshot = _require_transform_allowed(db, db.get(ArticleSnapshot, snapshot_id))
    form = await request.form()
    try:
        numbers = _numbers_from_form(form, snapshot, db)
        if not numbers:
            raise TransformSpecError("Keine Artikel im aktuellen Filter.", "empty scope")
        spec = _spec_from_form(form, numbers)
    except TransformSpecError as exc:
        raise HTTPException(status_code=400, detail=exc.message_de) from exc
    run, _job = start_transform_preview(db, user, snapshot_id=snapshot.id, spec=spec)
    db.commit()
    return RedirectResponse(url=f"/transform/{run.id}", status_code=303)


@router.post("/artikel-uebersicht/{snapshot_id}/transform/vorschau-vorschlag")
async def start_preview_from_proposal(
    snapshot_id: uuid.UUID,
    request: Request,
    user: SessionUser = Depends(require_user),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    snapshot = _require_transform_allowed(db, db.get(ArticleSnapshot, snapshot_id))
    form = await request.form()
    raw = str(form.get("spec_json") or "").strip()
    try:
        payload = json.loads(raw)
        if isinstance(payload, dict) and payload.get("kind") == "group_assign":
            from app.group_assign import GroupAssignSpec

            spec = GroupAssignSpec.model_validate(payload)
        else:
            spec = TransformSpec.model_validate(payload)
    except (TransformSpecError, ValidationError, ValueError, json.JSONDecodeError) as exc:
        message = getattr(exc, "message_de", None) or str(exc)
        raise HTTPException(status_code=400, detail=message) from exc
    run, _job = start_transform_preview(db, user, snapshot_id=snapshot.id, spec=spec)
    db.commit()
    return RedirectResponse(url=f"/transform/{run.id}", status_code=303)


def _run_context(db: Session, run: TransformRun) -> dict[str, Any]:
    pending = pending_review_rows(db, run)[:CHUNK_SIZE]
    views = row_views(pending)
    by_id = {item["row"].id: item for item in views}
    groups = []
    for group in group_rows(pending):
        groups.append(
            {
                **group,
                "views": [by_id[row.id] for row in group["rows"] if row.id in by_id],
            }
        )
    chunks = list(
        db.scalars(
            select(TransformChunk)
            .where(TransformChunk.run_id == run.id)
            .order_by(TransformChunk.chunk_index)
        )
    )
    latest = chunks[-1] if chunks else None
    result_summary = chunk_result_summary(db, latest) if latest and latest.status in {"applied", "failed"} else None
    remaining = len(pending_review_rows(db, run))
    total_changed = sum(1 for row in run.rows if row.row_status in {"CHANGED", "DECLINED"})
    chunk_n = (len(chunks) + 1) if pending else max(len(chunks), 1)
    chunk_total = max(1, (total_changed + CHUNK_SIZE - 1) // CHUNK_SIZE) if total_changed else 1
    unknown_rows: list[TransformRow] = []
    if latest is not None:
        ids = [uuid.UUID(str(item)) for item in (latest.row_ids or [])]
        if ids:
            unknown_rows = [
                row
                for row in db.scalars(select(TransformRow).where(TransformRow.id.in_(ids)))
                if row.apply_outcome == "UNKNOWN"
            ]
    return {
        "run": run,
        "groups": groups,
        "pending": pending,
        "views": views,
        "preview_summary": preview_summary(run) if run.status == "previewed" else None,
        "chunks": chunks,
        "latest_chunk": latest,
        "result_summary": result_summary,
        "confirm_label": MSG_CONFIRM.format(
            selected=sum(1 for item in views if item["checked"]),
            total=len(views),
            chunk=chunk_n,
            chunks=chunk_total,
        ),
        "msg_html_format": MSG_HTML_FORMAT,
        "msg_select_all": MSG_SELECT_ALL,
        "msg_deselect_all": MSG_DESELECT_ALL,
        "msg_reconcile": MSG_RECONCILE,
        "case_variants": run.case_variants or [],
        "word_positions": run.word_positions or {},
        "remaining": remaining,
        "unknown_rows": unknown_rows,
    }


@router.get("/transform/{run_id}", response_class=HTMLResponse)
def transform_run_page(
    run_id: uuid.UUID,
    request: Request,
    user: SessionUser = Depends(require_user),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    run = db.get(TransformRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Transform-Lauf nicht gefunden")
    snapshot = db.get(ArticleSnapshot, run.snapshot_id)
    ctx = {
        "user": user,
        "snapshot": snapshot,
        **_run_context(db, run),
    }
    return request.app.state.templates.TemplateResponse(
        request, "transform/review.html", ctx
    )


@router.post("/transform/{run_id}/bestaetigen")
async def confirm_chunk(
    run_id: uuid.UUID,
    request: Request,
    user: SessionUser = Depends(require_user),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    run = db.get(TransformRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Transform-Lauf nicht gefunden")
    _require_transform_allowed(db, db.get(ArticleSnapshot, run.snapshot_id))
    form = await request.form()
    selected = [uuid.UUID(str(v)) for v in form.getlist("zeile") if str(v).strip()]
    if not selected:
        raise HTTPException(status_code=400, detail=MSG_NO_SELECTION)
    existing = list(db.scalars(select(TransformChunk).where(TransformChunk.run_id == run.id)))
    chunk_index = len(existing)
    try:
        chunk = approve_chunk(
            db,
            run,
            chunk_index=chunk_index,
            approver_oid=str(user["oid"]),
            selected_row_ids=selected,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    db.commit()
    start_transform_apply(db, user, chunk_id=chunk.id)
    db.commit()
    return RedirectResponse(url=f"/transform/{run.id}", status_code=303)


@router.post("/transform/zeilen/{row_id}/abgleichen")
def reconcile_row(
    row_id: uuid.UUID,
    user: SessionUser = Depends(require_user),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    row = db.get(TransformRow, row_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Zeile nicht gefunden")
    run = db.get(TransformRun, row.run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Transform-Lauf nicht gefunden")
    _require_transform_allowed(db, db.get(ArticleSnapshot, run.snapshot_id))
    reconcile_unknown_row(
        db, row, oid=str(user["oid"]), actor_name=str(user.get("name") or user["oid"])
    )
    return RedirectResponse(url=f"/transform/{row.run_id}", status_code=303)
