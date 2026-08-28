"""Dry-run-then-write submit for approved article batches."""

from __future__ import annotations

import copy
import json
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit import record_audit_log
from app.groups_service import (
    record_audit,
    resolve_hauptgruppe,
    resolve_untergruppe,
    snapshot_hauptgruppe,
    snapshot_untergruppe,
)
from app.models import ArticleBatch, ArticleBatchRow
from app.weclapp import job_error_message, weclapp_client_for
from core.numbering import parse_group_codes
from scripts.paths import DATA_DIR
from scripts.weclapp.client import WeclappError

MSG_DRY_RUN_FAILED = "Probelauf fehlgeschlagen — es wurde nichts geschrieben."
MSG_PARTIAL = "{n} von {m} Artikeln angelegt. {k} fehlgeschlagen."
MSG_ALREADY_EXISTS = "Artikelnummer bereits in weclapp vorhanden."
MSG_PAYLOAD_INVALID = "Freigegebene Nutzlast ist ungültig: {detail}"


class LicenceAbort(Exception):
    """Licence/auth failure — abort the run immediately."""

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


def _load_create_schema() -> dict[str, Any]:
    path = DATA_DIR / "weclapp_article_create_schema.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _validate_payload_against_schema(payload: dict[str, Any], schema: dict[str, Any]) -> str | None:
    for item in schema.get("requiredForCreate") or []:
        field = str(item.get("field") or "")
        if not field:
            continue
        value = payload.get(field)
        if value is None or (isinstance(value, str) and not value.strip()):
            return f"Pflichtfeld fehlt: {field}"
    if not payload.get("unitId"):
        return "Pflichtfeld fehlt: unitId"
    return None


def _article_exists(client: Any, article_number: str) -> dict[str, Any] | None:
    # Do not filter on active. Inactive articles still own their number;
    # reissuing would collide on create.
    data = client.get(
        "/article",
        params={"pageSize": 1, "articleNumber-eq": article_number},
    )
    rows = (data or {}).get("result") or []
    return rows[0] if rows else None


def _pending_rows(db: Session, batch_id: Any) -> list[ArticleBatchRow]:
    return list(
        db.scalars(
            select(ArticleBatchRow)
            .where(
                ArticleBatchRow.batch_id == batch_id,
                ArticleBatchRow.include.is_(True),
                ArticleBatchRow.weclapp_article_id.is_(None),
            )
            .order_by(ArticleBatchRow.position)
        )
    )


def _all_included(db: Session, batch_id: Any) -> list[ArticleBatchRow]:
    return list(
        db.scalars(
            select(ArticleBatchRow)
            .where(
                ArticleBatchRow.batch_id == batch_id,
                ArticleBatchRow.include.is_(True),
            )
            .order_by(ArticleBatchRow.position)
        )
    )


def _lock_groups_if_needed(
    db: Session,
    *,
    payload: dict[str, Any],
    actor: Mapping[str, Any],
    now: datetime,
) -> None:
    codes = parse_group_codes(payload.get("articleNumber"))
    if codes is None:
        return
    main, sub = codes
    haupt = resolve_hauptgruppe(db, main)
    if haupt is None:
        return
    unter = resolve_untergruppe(db, haupt, sub)
    if haupt.locked_at is None:
        before = snapshot_hauptgruppe(haupt)
        haupt.locked_at = now
        record_audit(
            db,
            entity="hauptgruppe",
            entity_id=haupt.id,
            action="locked_by_registration",
            actor=actor,
            before=before,
            after=snapshot_hauptgruppe(haupt),
        )
    if unter is not None and unter.locked_at is None:
        before = snapshot_untergruppe(unter)
        unter.locked_at = now
        record_audit(
            db,
            entity="untergruppe",
            entity_id=unter.id,
            action="locked_by_registration",
            actor=actor,
            before=before,
            after=snapshot_untergruppe(unter),
        )


def run_batch_submit(
    db: Session,
    *,
    batch_id: Any,
    actor_oid: str,
    actor_name: str | None = None,
) -> dict[str, Any]:
    """Phase 1 dry-run, then phase 2 sequential writes with per-row commits."""
    actor = {"oid": actor_oid, "name": actor_name or actor_oid}
    batch = db.scalars(
        select(ArticleBatch).where(ArticleBatch.id == batch_id).with_for_update()
    ).first()
    if batch is None:
        raise ValueError("Stapel nicht gefunden")
    if batch.status not in {"approved", "submitting"}:
        raise ValueError(f"Stapel-Status {batch.status!r} erlaubt kein Senden")

    batch.status = "submitting"
    batch.updated_at = datetime.now(UTC)
    db.commit()

    client = weclapp_client_for(db, actor_oid)
    schema = _load_create_schema()
    pending = _pending_rows(db, batch.id)

    # Phase 1 — dry-run, unconditional
    dry_failed = False
    for row in pending:
        payload = row.approved_payload
        if not isinstance(payload, dict):
            row.write_error = MSG_PAYLOAD_INVALID.format(detail="fehlt")
            dry_failed = True
            continue
        number = str(payload.get("articleNumber") or "").strip()
        try:
            existing = _article_exists(client, number)
        except WeclappError as exc:
            mapped = job_error_message(exc)
            if mapped:
                db.commit()
                _return_to_approved(db, batch)
                raise LicenceAbort(mapped) from exc
            row.write_error = str(exc)
            dry_failed = True
            continue
        if existing is not None:
            row.write_error = MSG_ALREADY_EXISTS
            dry_failed = True
            continue
        schema_error = _validate_payload_against_schema(payload, schema)
        if schema_error:
            row.write_error = MSG_PAYLOAD_INVALID.format(detail=schema_error)
            dry_failed = True
            continue
        row.write_error = None

    if dry_failed:
        db.commit()
        _return_to_approved(db, batch)
        raise ValueError(MSG_DRY_RUN_FAILED)

    # Phase 2 — write, one row per transaction
    succeeded = 0
    created_ids: list[str] = []
    try:
        for row_id in [row.id for row in pending]:
            row = db.get(ArticleBatchRow, row_id)
            if row is None or row.weclapp_article_id:
                continue
            payload = copy.deepcopy(row.approved_payload or {})
            try:
                response = client.post("/article", json=payload)
            except WeclappError as exc:
                mapped = job_error_message(exc)
                if mapped:
                    raise LicenceAbort(mapped) from exc
                row.write_error = str(exc)
                db.commit()
                continue
            article_id = str((response or {}).get("id") or "")
            if not article_id:
                row.write_error = "weclapp lieferte keine Artikel-ID"
                db.commit()
                continue
            now = datetime.now(UTC)
            row.weclapp_article_id = article_id
            row.submitted_at = now
            row.submitted_by_oid = actor_oid
            row.write_error = None
            _lock_groups_if_needed(db, payload=payload, actor=actor, now=now)
            created_ids.append(article_id)
            succeeded += 1
            db.commit()
    except LicenceAbort:
        db.rollback()
        batch = db.get(ArticleBatch, batch_id)
        if batch is not None:
            _return_to_approved(db, batch)
        raise

    included = _all_included(db, batch_id)
    total = len(included)
    written = sum(1 for row in included if row.weclapp_article_id)
    batch = db.get(ArticleBatch, batch_id)
    assert batch is not None
    now = datetime.now(UTC)
    if written == total:
        batch.status = "submitted"
        batch.submitted_at = now
        batch.submitted_by_oid = actor_oid
        batch.submitted_by_name = actor["name"]
        summary = f"{written} von {total} Artikeln angelegt."
        job_ok = True
    else:
        batch.status = "approved"
        failed_total = total - written
        summary = MSG_PARTIAL.format(n=written, m=total, k=failed_total)
        job_ok = False
    batch.updated_at = now
    record_audit_log(
        db,
        actor=actor,
        entity_type="article_batch",
        entity_id=batch.id,
        action="submitted" if job_ok else "submit_partial",
        detail={
            "succeeded": written,
            "failed": total - written,
            "weclapp_ids": [
                row.weclapp_article_id
                for row in included
                if row.weclapp_article_id
            ],
            "created_this_run": created_ids,
        },
    )
    db.commit()
    if not job_ok:
        raise ValueError(summary)
    return {
        "succeeded": written,
        "failed": total - written,
        "weclapp_ids": created_ids,
        "summary": summary,
    }


def _return_to_approved(db: Session, batch: ArticleBatch) -> None:
    batch.status = "approved"
    batch.updated_at = datetime.now(UTC)
    db.commit()
