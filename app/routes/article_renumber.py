"""Admin routes: Artikelnummer neu vergeben."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.article_renumber import ArticleRenumberSpec, list_mismatch_candidates
from app.assistant.catalog import snapshot_for_query
from app.auth import SessionUser, require_admin
from app.db import get_db
from app.models import ArticleSnapshot
from app.snapshots import SnapshotFilters, fetch_all_filtered_rows
from app.transform.preview import start_transform_preview
from app.transform.schemas import TransformScope
from app.transform.ui import transform_gate
from app.weclapp import weclapp_client_for

router = APIRouter()

MSG_UNAVAILABLE = "Artikelnummer neu vergeben ist nur mit der aktuellen Artikelübersicht möglich."
MSG_EMPTY = "Keine Artikel ausgewählt."


def _require_current_snapshot(db: Session, snapshot_id: uuid.UUID) -> ArticleSnapshot:
    snapshot = db.get(ArticleSnapshot, snapshot_id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail="Abfrage nicht gefunden")
    if not transform_gate(db, snapshot)["transform_allowed"]:
        raise HTTPException(status_code=400, detail=MSG_UNAVAILABLE)
    return snapshot


@router.post("/artikel-uebersicht/{snapshot_id}/renumber/vorschau")
async def start_renumber_preview(
    snapshot_id: uuid.UUID,
    request: Request,
    user: SessionUser = Depends(require_admin),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    snapshot = _require_current_snapshot(db, snapshot_id)
    form = await request.form()
    mode = str(form.get("renumber_scope") or "mismatch").strip()
    numbers: list[str]
    if mode == "selected":
        numbers = [str(v).strip() for v in form.getlist("artikelnummer") if str(v).strip()]
        if not numbers:
            raise HTTPException(status_code=400, detail=MSG_EMPTY)
    elif mode == "mismatch":
        oid = str(user["oid"])
        client = weclapp_client_for(db, oid)
        mismatches = list_mismatch_candidates(db, client, snapshot=snapshot)
        numbers = [item["article_number"] for item in mismatches]
        if not numbers:
            raise HTTPException(status_code=400, detail="Keine Artikel mit abweichender Nummer.")
    else:
        filters = SnapshotFilters(
            query=str(form.get("q") or "").strip(),
            hauptgruppe=str(form.get("hauptgruppe") or "").strip(),
            untergruppe=str(form.get("untergruppe") or "").strip(),
            nur_aktive=str(form.get("nur_aktive") or "1") not in {"0", "false", "nein"},
        )
        rows = fetch_all_filtered_rows(db, snapshot.id, filters)
        numbers = [row.article_number for row in rows if row.article_number]
        if not numbers:
            raise HTTPException(status_code=400, detail=MSG_EMPTY)
    spec = ArticleRenumberSpec(scope=TransformScope(article_numbers=numbers))
    run, _job = start_transform_preview(db, user, snapshot_id=snapshot.id, spec=spec)
    db.commit()
    return RedirectResponse(url=f"/transform/{run.id}", status_code=303)


@router.get("/artikel-uebersicht/{snapshot_id}/renumber/status")
def renumber_status(
    snapshot_id: uuid.UUID,
    user: SessionUser = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    """JSON eligibility summary for the current mismatch set (read-only)."""
    snapshot = _require_current_snapshot(db, snapshot_id)
    current = snapshot_for_query(db)
    if current is None or current.id != snapshot.id:
        raise HTTPException(status_code=400, detail=MSG_UNAVAILABLE)
    from app.article_renumber import summarize_mismatch_eligibility

    client = weclapp_client_for(db, str(user["oid"]))
    return summarize_mismatch_eligibility(db, client, snapshot=snapshot)
